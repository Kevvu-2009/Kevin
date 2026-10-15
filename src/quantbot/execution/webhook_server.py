"""HTTP server that receives TradingView webhook alerts.

Endpoints:
    POST /webhook/tradingview   alert body (see ``integrations.tradingview``)
    GET  /health                liveness
    GET  /api/status            equity, open positions, kill-switch state

TradingView only delivers webhooks to ports 80/443, so in production put this
behind HTTPS (a reverse proxy such as Caddy/nginx, or a host like Railway/Fly
that terminates TLS) and point the alert at ``https://<host>/webhook/tradingview``.

Run:  python -m quantbot.cli webhook --venue paper --port 8080
"""

# No ``from __future__ import annotations``: FastAPI must resolve the locally
# imported ``Request`` annotation at route-definition time.
import os
import threading

from quantbot.integrations.tradingview import AlertError, TradingViewBridge
from quantbot.logging_setup import get_logger

log = get_logger("execution.webhook_server")

# Source IPs TradingView sends webhooks from (per TradingView's docs).
TRADINGVIEW_IPS = frozenset({"52.89.214.238", "34.212.75.30", "54.218.53.128", "52.32.178.7"})


def allowed_ips_from_env() -> frozenset[str] | None:
    """``TRADINGVIEW_ALLOWED_IPS``: unset/empty = allow all, ``tradingview`` =
    TradingView's published IPs, otherwise a comma-separated list."""
    raw = os.getenv("TRADINGVIEW_ALLOWED_IPS", "").strip()
    if not raw:
        return None
    if raw.lower() == "tradingview":
        return TRADINGVIEW_IPS
    return frozenset(ip.strip() for ip in raw.split(",") if ip.strip())


def create_app(bridge: TradingViewBridge, allowed_ips: frozenset[str] | None = None,
               stop_poll_seconds: float = 0.0):
    """Build the FastAPI app.  ``stop_poll_seconds > 0`` starts a background
    loop that checks stops/take-profits against live venue prices."""
    from contextlib import asynccontextmanager

    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse

    stop_event = threading.Event()

    def _poll_stops() -> None:
        while not stop_event.wait(stop_poll_seconds):
            try:
                for ex in bridge.check_stops():
                    log.info("stop_poll_exit", **ex)
            except Exception as e:  # pragma: no cover - keep the loop alive
                log.error("stop_poll_failed", error=str(e))

    @asynccontextmanager
    async def lifespan(_app):
        if stop_poll_seconds > 0:
            threading.Thread(target=_poll_stops, name="stop-poll", daemon=True).start()
        yield
        stop_event.set()

    app = FastAPI(title="QuantBot TradingView Webhook", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/status")
    def status() -> dict:
        return bridge.status()

    @app.post("/webhook/tradingview")
    async def tradingview(request: Request) -> JSONResponse:
        client_ip = request.client.host if request.client else ""
        if allowed_ips is not None and client_ip not in allowed_ips:
            log.warning("webhook_ip_rejected", ip=client_ip)
            return JSONResponse({"error": "forbidden"}, status_code=403)
        raw = await request.body()
        try:
            result = bridge.handle(raw)
        except AlertError as e:
            log.warning("webhook_rejected", ip=client_ip, error=str(e), status=e.status)
            return JSONResponse({"error": str(e)}, status_code=e.status)
        log.info("webhook_processed", **result)
        return JSONResponse(result)

    return app
