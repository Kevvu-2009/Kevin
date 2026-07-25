"""FastAPI application: webhook ingress, health, and lifecycle wiring.

The webhook handler does the minimum amount of work required to accept or
refuse a signal, then hands execution to a background task and returns. This is
deliberate: TradingView's webhook client times out quickly, and the entry
pipeline can legitimately spend 45 seconds waiting for a limit fill. Returning
200 before the trade completes is correct here *because the idempotency claim
has already been committed synchronously* - the response is an acknowledgement
of receipt, not of execution.

Order of checks in the handler, cheapest and most decisive first:

    IP allowlist -> JSON parse -> schema validation -> shared secret
    -> reconciliation gate -> idempotency claim -> staleness
    -> background execution

Staleness is the last synchronous gate because it is pure and needs no exchange
call, so the HTTP response can honestly say whether the signal will be acted on
rather than reporting "accepted" for an alert the background task is about to
throw away.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import logging.handlers
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .config import Mode, Settings, get_settings
from .config import validate as validate_settings
from .engine import Engine
from .exchange import ExchangeAPI, build_exchange
from .models import SignalStatus, WebhookPayload
from .notify import Notifier
from .reconcile import Reconciler
from .risk import RiskManager
from .state import Store

log = logging.getLogger("tvbot")

_LOG_RESERVED = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName",
}


class JsonFormatter(logging.Formatter):
    """One JSON object per line, so the log file is greppable and machine-readable."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _LOG_RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(cfg: Settings) -> None:
    root = logging.getLogger()
    root.setLevel(cfg.log_level)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(JsonFormatter())
    root.addHandler(stream)

    if cfg.log_file:
        path = Path(cfg.log_file).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=25 * 1024 * 1024, backupCount=10
        )
        file_handler.setFormatter(JsonFormatter())
        root.addHandler(file_handler)

    # ccxt is extremely chatty at DEBUG and will leak request bodies.
    logging.getLogger("ccxt").setLevel(logging.WARNING)


@dataclass
class AppState:
    cfg: Settings
    store: Store
    exchange: ExchangeAPI
    notifier: Notifier
    risk: RiskManager
    engine: Engine
    reconciler: Reconciler
    started_at: float
    background: set[asyncio.Task[Any]]


def _client_ip(request: Request, cfg: Settings) -> str:
    """Resolve the caller's address.

    ``X-Forwarded-For`` is only honoured when TRUST_PROXY_HEADERS is set,
    because an attacker can otherwise spoof the header and walk straight
    through the allowlist.
    """
    if cfg.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()
    return request.client.host if request.client else ""


def create_app(cfg: Settings | None = None) -> FastAPI:
    settings = cfg or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        setup_logging(settings)
        validate_settings(settings)

        log.info(
            "starting",
            extra={
                "mode": settings.mode.value,
                "symbols": list(settings.symbol_map.items()),
                "risk_pct": settings.risk_pct,
                "max_leverage": settings.max_leverage,
            },
        )
        if settings.mode is Mode.LIVE:
            log.warning("LIVE MODE - real money is at risk")

        store = Store(settings.db_path)
        notifier = Notifier(settings)
        exchange = build_exchange(settings)
        risk = RiskManager(settings, store)
        engine = Engine(settings, exchange, store, risk, notifier)
        reconciler = Reconciler(settings, exchange, store, notifier)

        app.state.ctx = AppState(
            cfg=settings,
            store=store,
            exchange=exchange,
            notifier=notifier,
            risk=risk,
            engine=engine,
            reconciler=reconciler,
            started_at=time.time(),
            background=set(),
        )

        await exchange.open()
        for symbol in settings.ccxt_symbols:
            try:
                await exchange.prepare_symbol(symbol, settings.max_leverage)
            except Exception as exc:  # noqa: BLE001 - non-fatal at startup
                log.warning("prepare_symbol_failed symbol=%s err=%s", symbol, exc)

        await reconciler.startup()
        reconciler.start_background()

        await notifier.info(
            f"Bot started in {settings.mode.value} mode. "
            f"Symbols: {', '.join(settings.symbol_map)}. "
            f"Reconciliation {'OK' if reconciler.ready else 'FAILED - webhooks refused'}."
        )

        try:
            yield
        finally:
            await reconciler.stop_background()
            for task in list(app.state.ctx.background):
                task.cancel()
            await exchange.close()
            await notifier.close()
            store.close()
            log.info("stopped")

    app = FastAPI(
        title="TradingView -> Bybit perps execution bot",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None,  # no interactive docs on a trading endpoint
        redoc_url=None,
        openapi_url=None,
    )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_request_error path=%s", request.url.path)
        ctx: AppState | None = getattr(request.app.state, "ctx", None)
        if ctx is not None:
            await ctx.notifier.critical(
                f"Unhandled error on {request.url.path}: {type(exc).__name__}: {exc}",
                dedup_key=f"unhandled:{request.url.path}",
            )
        return JSONResponse(status_code=500, content={"status": "error"})

    @app.post("/webhook")
    async def webhook(request: Request) -> Response:
        ctx: AppState = request.app.state.ctx
        cfg = ctx.cfg

        # 1. IP allowlist, before we parse anything.
        if cfg.ip_allowlist_enabled:
            ip = _client_ip(request, cfg)
            if ip not in cfg.ip_allowlist:
                log.warning("webhook_ip_rejected", extra={"client_ip": ip})
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN, content={"status": "forbidden"}
                )

        # 2. Body + schema.
        raw = await request.body()
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            log.warning("webhook_bad_json err=%s", exc)
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST, content={"status": "bad_json"}
            )

        try:
            payload = WebhookPayload.model_validate(data)
        except ValidationError as exc:
            log.warning(
                "webhook_schema_rejected",
                extra={"errors": exc.errors(include_url=False, include_input=False)},
            )
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={"status": "invalid_payload"},
            )

        # 3. Shared secret, constant-time.
        if not hmac.compare_digest(payload.secret, cfg.webhook_secret):
            log.warning(
                "webhook_bad_secret", extra={"signal_id": payload.signal_id, "symbol": payload.symbol}
            )
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED, content={"status": "unauthorized"}
            )

        # 4. Refuse to trade until we know what we already hold.
        if not ctx.reconciler.ready:
            log.error("webhook_refused_not_reconciled", extra={"signal_id": payload.signal_id})
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "not_reconciled"},
            )

        # 5. Idempotency: committed synchronously, before we return 200.
        if not ctx.engine.claim(payload):
            log.info("webhook_duplicate", extra={"signal_id": payload.signal_id})
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"status": "duplicate", "signal_id": payload.signal_id},
            )

        # 6. Staleness, synchronously. This gate needs no exchange call, so it
        #    runs here rather than in the background task: the HTTP response
        #    then tells the truth about whether the signal will be acted on.
        #    The engine re-checks it too, because time passes between accepting
        #    a signal and reaching the exchange.
        freshness = ctx.risk.check_staleness(payload, int(time.time() * 1000))
        if not freshness.allowed:
            ctx.store.set_signal_status(
                payload.signal_id,
                SignalStatus.REJECTED,
                f"{freshness.code}: {freshness.reason}",
            )
            log.warning(
                "webhook_stale",
                extra={"signal_id": payload.signal_id, "reason": freshness.reason},
            )
            await ctx.notifier.warn(
                f"Signal rejected [{freshness.code}] {payload.symbol} "
                f"{payload.side.value}: {freshness.reason}",
                dedup_key=f"reject:{freshness.code}:{payload.symbol}",
            )
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "status": "rejected",
                    "code": freshness.code,
                    "signal_id": payload.signal_id,
                },
            )

        log.info(
            "webhook_accepted",
            extra={"signal_id": payload.signal_id, "payload": payload.redacted()},
        )

        # 7. Execute out of band so TradingView's client does not time out.
        task = asyncio.create_task(_run_entry(ctx, payload))
        ctx.background.add(task)
        task.add_done_callback(ctx.background.discard)

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "accepted", "signal_id": payload.signal_id},
        )

    @app.get("/healthz")
    async def healthz(request: Request) -> Response:
        ctx: AppState | None = getattr(request.app.state, "ctx", None)
        if ctx is None:
            return JSONResponse(status_code=503, content={"status": "starting"})
        healthy = ctx.reconciler.ready
        return JSONResponse(
            status_code=200 if healthy else 503,
            content={
                "status": "ok" if healthy else "not_reconciled",
                "mode": ctx.cfg.mode.value,
                "uptime_sec": round(time.time() - ctx.started_at, 1),
                "last_reconcile_age_sec": (
                    round(time.time() - ctx.reconciler.last_run_ts, 1)
                    if ctx.reconciler.last_run_ts
                    else None
                ),
            },
        )

    @app.get("/status")
    async def status_endpoint(request: Request) -> Response:
        ctx: AppState = request.app.state.ctx
        try:
            equity = await ctx.exchange.fetch_equity()
        except Exception as exc:  # noqa: BLE001 - status must always render
            return JSONResponse(
                status_code=200,
                content={"error": f"equity unavailable: {exc}", "mode": ctx.cfg.mode.value},
            )
        report = ctx.reconciler.last_report
        return JSONResponse(
            status_code=200,
            content={
                "mode": ctx.cfg.mode.value,
                "reconciled": ctx.reconciler.ready,
                "risk": ctx.risk.snapshot(equity),
                "positions": [
                    {
                        "symbol": p.symbol,
                        "side": p.side,
                        "qty": p.qty,
                        "entry": p.entry_price,
                        "stop": p.stop_price,
                        "target": p.target_price,
                        "adopted": p.adopted,
                    }
                    for p in ctx.store.list_open_positions()
                ],
                "last_reconcile": None
                if report is None
                else {
                    "ok": report.ok,
                    "symbols_checked": report.symbols_checked,
                    "repairs": report.repairs,
                    "errors": report.errors,
                },
            },
        )

    return app


async def _run_entry(ctx: AppState, payload: WebhookPayload) -> None:
    """Background entry execution. Must never raise into the event loop."""
    try:
        result = await ctx.engine.execute_entry(payload)
        log.info(
            "entry_result",
            extra={
                "signal_id": payload.signal_id,
                "result_status": result.status,
                "reason": result.reason,
            },
        )
    except Exception as exc:  # noqa: BLE001 - last line of defence
        log.exception("entry_task_crashed signal_id=%s", payload.signal_id)
        ctx.store.set_signal_status(
            payload.signal_id, SignalStatus.ERROR, f"{type(exc).__name__}: {exc}"
        )
        await ctx.notifier.critical(
            f"Entry task crashed for {payload.signal_id}: {type(exc).__name__}: {exc}"
        )


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        log_config=None,  # our JSON handlers own the root logger
    )
