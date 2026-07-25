"""Configuration for the TradingView -> Bybit webhook execution bot.

Pure stdlib + dataclasses so that ``sizing``, ``risk`` and ``state`` can be
imported and unit-tested without pydantic, ccxt, or a populated ``.env`` (the
same convention as ``src/quantbot/config.py`` elsewhere in this repo).

Nothing here reads the network or touches disk at import time. ``validate()``
is called explicitly from the FastAPI lifespan so tests can build partial
settings objects without tripping the LIVE-mode guards.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache

try:  # pragma: no cover - convenience only
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass


class ConfigError(RuntimeError):
    """Raised at startup when the configuration is unsafe to run with."""


class Mode(str, Enum):
    """Execution mode. Ordered least to most dangerous."""

    DRY_RUN = "DRY_RUN"  # log intended orders, place nothing, no credentials needed
    TESTNET = "TESTNET"  # real API calls against Bybit testnet (default)
    LIVE = "LIVE"  # real money; requires LIVE_CONFIRM


#: The exact string LIVE_CONFIRM must equal before LIVE mode will start.
LIVE_CONFIRM_PHRASE = "I_UNDERSTAND_THIS_TRADES_REAL_MONEY"

#: TradingView ticker -> ccxt unified symbol.
DEFAULT_SYMBOL_MAP: dict[str, str] = {
    "BTCUSDT.P": "BTC/USDT:USDT",
    "ETHUSDT.P": "ETH/USDT:USDT",
}

#: TradingView's published webhook source addresses. Verify against
#: https://www.tradingview.com/support/solutions/43000529348/ before relying on
#: this list; TradingView has changed it before and will change it again.
TRADINGVIEW_WEBHOOK_IPS: tuple[str, ...] = (
    "52.89.214.238",
    "34.212.75.30",
    "54.218.53.128",
    "52.32.178.7",
)


def _get(key: str, default: str | None = None) -> str | None:
    val = os.getenv(key)
    return val if val not in (None, "") else default


def _getf(key: str, default: float) -> float:
    try:
        return float(_get(key, str(default)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _geti(key: str, default: int) -> int:
    try:
        return int(_get(key, str(default)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _getb(key: str, default: bool) -> bool:
    raw = _get(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _getlist(key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = _get(key)
    if raw is None:
        return default
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _get_symbol_map(key: str, default: dict[str, str]) -> dict[str, str]:
    """Parse ``BTCUSDT.P=BTC/USDT:USDT,ETHUSDT.P=ETH/USDT:USDT``."""
    raw = _get(key)
    if raw is None:
        return dict(default)
    out: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            raise ConfigError(f"{key}: expected 'TVSYMBOL=ccxt/symbol', got {pair!r}")
        tv, ccxt_sym = pair.split("=", 1)
        out[tv.strip()] = ccxt_sym.strip()
    return out


@dataclass(frozen=True)
class Settings:
    """Every knob the bot has. Defaults are the safe end of each range."""

    # ---- mode / credentials -------------------------------------------------
    mode: Mode = Mode.TESTNET
    live_confirm: str = ""
    api_key: str = ""
    api_secret: str = ""

    # ---- webhook security ---------------------------------------------------
    webhook_secret: str = ""
    ip_allowlist_enabled: bool = True
    ip_allowlist: tuple[str, ...] = TRADINGVIEW_WEBHOOK_IPS
    trust_proxy_headers: bool = False

    # ---- instruments --------------------------------------------------------
    symbol_map: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_SYMBOL_MAP))
    expected_timeframe: str = "60"

    # ---- sizing / risk ------------------------------------------------------
    risk_pct: float = 0.005
    max_leverage: float = 3.0
    max_positions_total: int = 2
    max_positions_per_symbol: int = 1
    rr_min: float = 2.9
    rr_max: float = 3.1
    stop_dist_min_pct: float = 0.004
    stop_dist_max_pct: float = 0.03

    # ---- kill switches ------------------------------------------------------
    daily_loss_limit_pct: float = 0.03
    max_consecutive_losses: int = 5
    halt_file: str = "./HALT"
    halt_env: bool = False

    # ---- execution timing ---------------------------------------------------
    max_signal_age_sec: int = 90
    entry_fill_timeout_sec: int = 45
    entry_poll_interval_sec: float = 1.0
    max_slippage_pct: float = 0.0015
    reconcile_interval_sec: int = 30

    # ---- exchange resilience ------------------------------------------------
    retry_attempts: int = 5
    retry_base_delay_sec: float = 0.5
    retry_max_delay_sec: float = 20.0

    # ---- persistence / logging ----------------------------------------------
    db_path: str = "./data/tradingbot.sqlite3"
    log_file: str = "./logs/tradingbot.jsonl"
    log_level: str = "INFO"

    # ---- notifications ------------------------------------------------------
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    notify_dedup_sec: int = 300

    # ---- dry run ------------------------------------------------------------
    dry_run_equity: float = 10_000.0

    # ---- server -------------------------------------------------------------
    host: str = "127.0.0.1"
    port: int = 8000

    # -- derived helpers ------------------------------------------------------
    @property
    def ccxt_symbols(self) -> tuple[str, ...]:
        return tuple(self.symbol_map.values())

    @property
    def reverse_symbol_map(self) -> dict[str, str]:
        return {v: k for k, v in self.symbol_map.items()}

    def resolve_symbol(self, tv_symbol: str) -> str | None:
        """TradingView ticker -> ccxt symbol, or None if not configured."""
        return self.symbol_map.get(tv_symbol.strip().upper())

    @property
    def places_real_orders(self) -> bool:
        return self.mode in (Mode.TESTNET, Mode.LIVE)

    @property
    def use_testnet(self) -> bool:
        return self.mode is Mode.TESTNET


def load_settings() -> Settings:
    """Build a Settings object from the process environment."""
    raw_mode = (_get("MODE", "TESTNET") or "TESTNET").strip().upper()
    try:
        mode = Mode(raw_mode)
    except ValueError as exc:
        valid = ", ".join(m.value for m in Mode)
        raise ConfigError(f"MODE={raw_mode!r} is not one of: {valid}") from exc

    return Settings(
        mode=mode,
        live_confirm=_get("LIVE_CONFIRM", "") or "",
        api_key=_get("BYBIT_API_KEY", "") or "",
        api_secret=_get("BYBIT_API_SECRET", "") or "",
        webhook_secret=_get("WEBHOOK_SECRET", "") or "",
        ip_allowlist_enabled=_getb("IP_ALLOWLIST_ENABLED", True),
        ip_allowlist=_getlist("IP_ALLOWLIST", TRADINGVIEW_WEBHOOK_IPS),
        trust_proxy_headers=_getb("TRUST_PROXY_HEADERS", False),
        symbol_map=_get_symbol_map("SYMBOL_MAP", DEFAULT_SYMBOL_MAP),
        expected_timeframe=_get("EXPECTED_TIMEFRAME", "60") or "60",
        risk_pct=_getf("RISK_PCT", 0.005),
        max_leverage=_getf("MAX_LEVERAGE", 3.0),
        max_positions_total=_geti("MAX_POSITIONS_TOTAL", 2),
        max_positions_per_symbol=_geti("MAX_POSITIONS_PER_SYMBOL", 1),
        rr_min=_getf("RR_MIN", 2.9),
        rr_max=_getf("RR_MAX", 3.1),
        stop_dist_min_pct=_getf("STOP_DIST_MIN_PCT", 0.004),
        stop_dist_max_pct=_getf("STOP_DIST_MAX_PCT", 0.03),
        daily_loss_limit_pct=_getf("DAILY_LOSS_LIMIT_PCT", 0.03),
        max_consecutive_losses=_geti("MAX_CONSECUTIVE_LOSSES", 5),
        halt_file=_get("HALT_FILE", "./HALT") or "./HALT",
        halt_env=_getb("HALT", False),
        max_signal_age_sec=_geti("MAX_SIGNAL_AGE_SEC", 90),
        entry_fill_timeout_sec=_geti("ENTRY_FILL_TIMEOUT_SEC", 45),
        entry_poll_interval_sec=_getf("ENTRY_POLL_INTERVAL_SEC", 1.0),
        max_slippage_pct=_getf("MAX_SLIPPAGE_PCT", 0.0015),
        reconcile_interval_sec=_geti("RECONCILE_INTERVAL_SEC", 30),
        retry_attempts=_geti("RETRY_ATTEMPTS", 5),
        retry_base_delay_sec=_getf("RETRY_BASE_DELAY_SEC", 0.5),
        retry_max_delay_sec=_getf("RETRY_MAX_DELAY_SEC", 20.0),
        db_path=_get("DB_PATH", "./data/tradingbot.sqlite3") or "./data/tradingbot.sqlite3",
        log_file=_get("LOG_FILE", "./logs/tradingbot.jsonl") or "./logs/tradingbot.jsonl",
        log_level=(_get("LOG_LEVEL", "INFO") or "INFO").upper(),
        telegram_bot_token=_get("TELEGRAM_BOT_TOKEN", "") or "",
        telegram_chat_id=_get("TELEGRAM_CHAT_ID", "") or "",
        notify_dedup_sec=_geti("NOTIFY_DEDUP_SEC", 300),
        dry_run_equity=_getf("DRY_RUN_EQUITY", 10_000.0),
        host=_get("HOST", "127.0.0.1") or "127.0.0.1",
        port=_geti("PORT", 8000),
    )


def validate(settings: Settings) -> None:
    """Fail fast on configurations that would lose money or silently no-op.

    Called from the FastAPI lifespan, never at import time.
    """
    problems: list[str] = []

    if not settings.webhook_secret:
        problems.append("WEBHOOK_SECRET is empty - the webhook would accept anything.")
    elif len(settings.webhook_secret) < 16:
        problems.append("WEBHOOK_SECRET is shorter than 16 chars; use a long random string.")

    if settings.places_real_orders and not (settings.api_key and settings.api_secret):
        problems.append(f"MODE={settings.mode.value} requires BYBIT_API_KEY and BYBIT_API_SECRET.")

    if settings.mode is Mode.LIVE and settings.live_confirm != LIVE_CONFIRM_PHRASE:
        problems.append(
            f"MODE=LIVE requires LIVE_CONFIRM={LIVE_CONFIRM_PHRASE!r} "
            f"(got {settings.live_confirm!r})."
        )

    if not settings.symbol_map:
        problems.append("SYMBOL_MAP is empty - no signal could ever be routed.")

    if not 0 < settings.risk_pct <= 0.05:
        problems.append(f"RISK_PCT={settings.risk_pct} outside sane band (0, 0.05].")

    if settings.max_leverage <= 0:
        problems.append("MAX_LEVERAGE must be positive.")

    if not 0 < settings.stop_dist_min_pct < settings.stop_dist_max_pct:
        problems.append("Require 0 < STOP_DIST_MIN_PCT < STOP_DIST_MAX_PCT.")

    if not 0 < settings.rr_min <= settings.rr_max:
        problems.append("Require 0 < RR_MIN <= RR_MAX.")

    if settings.max_signal_age_sec <= 0:
        problems.append("MAX_SIGNAL_AGE_SEC must be positive; 0 would reject every signal.")

    if settings.max_positions_total < settings.max_positions_per_symbol:
        problems.append("MAX_POSITIONS_TOTAL must be >= MAX_POSITIONS_PER_SYMBOL.")

    if settings.ip_allowlist_enabled and not settings.ip_allowlist:
        problems.append("IP_ALLOWLIST_ENABLED=true but IP_ALLOWLIST is empty.")

    if problems:
        raise ConfigError("Invalid configuration:\n  - " + "\n  - ".join(problems))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
