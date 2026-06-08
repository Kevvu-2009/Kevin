"""Central configuration loaded from environment variables.

The config object is intentionally dependency-light (pure stdlib) so that the
analytics / backtesting code can be imported and tested without ``pydantic`` or
a populated ``.env``.  IO-heavy modules (db, integrations) read the same object.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

# Load a local .env if python-dotenv is available; never required for tests.
try:  # pragma: no cover - convenience only
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass


def _get(key: str, default: str | None = None) -> str | None:
    val = os.getenv(key)
    return val if val not in (None, "") else default


def _getf(key: str, default: float) -> float:
    try:
        return float(_get(key, str(default)))
    except (TypeError, ValueError):
        return default


def _geti(key: str, default: int) -> int:
    try:
        return int(_get(key, str(default)))
    except (TypeError, ValueError):
        return default


def _getb(key: str, default: bool) -> bool:
    raw = _get(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


SUPPORTED_TIMEFRAMES = ("5m", "15m", "1h", "4h", "1d")
DEFAULT_UNIVERSE = ("BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "ADA/USDT")


@dataclass(frozen=True)
class RiskConfig:
    """Risk limits.  Defaults satisfy the project's stated mandate."""

    risk_per_trade: float = 0.0075          # fraction of equity risked per trade
    risk_per_trade_floor: float = 0.005
    risk_per_trade_cap: float = 0.01
    max_concurrent_positions: int = 5
    daily_loss_limit: float = 0.03
    weekly_loss_limit: float = 0.08
    kill_switch_drawdown: float = 0.20

    @classmethod
    def from_env(cls) -> RiskConfig:
        rpt = _getf("RISK_PER_TRADE", 0.0075)
        # Clamp into the mandated 0.5%-1% band.
        rpt = min(max(rpt, 0.005), 0.01)
        return cls(
            risk_per_trade=rpt,
            max_concurrent_positions=_geti("MAX_CONCURRENT_POSITIONS", 5),
            daily_loss_limit=_getf("DAILY_LOSS_LIMIT", 0.03),
            weekly_loss_limit=_getf("WEEKLY_LOSS_LIMIT", 0.08),
            kill_switch_drawdown=_getf("KILL_SWITCH_DRAWDOWN", 0.20),
        )


@dataclass(frozen=True)
class CostConfig:
    """Backtest cost assumptions (per side unless noted)."""

    taker_fee: float = 0.0005          # 5 bps
    maker_fee: float = 0.0002          # 2 bps
    slippage_bps: float = 5.0          # 5 bps modelled slippage on entries/exits
    latency_bars: int = 1              # signals act on the *next* bar's open


@dataclass(frozen=True)
class Settings:
    env: str = "development"
    mode: str = "paper"                # paper | live
    log_level: str = "INFO"
    log_json: bool = True

    # Postgres
    database_url: str = "postgresql+psycopg2://quantbot:changeme@localhost:5432/quantbot"
    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Data
    data_exchange: str = "binance"
    universe: tuple[str, ...] = DEFAULT_UNIVERSE
    timeframes: tuple[str, ...] = SUPPORTED_TIMEFRAMES

    risk: RiskConfig = field(default_factory=RiskConfig)
    costs: CostConfig = field(default_factory=CostConfig)

    @classmethod
    def from_env(cls) -> Settings:
        db_url = _get("DATABASE_URL")
        if not db_url:
            db_url = (
                f"postgresql+psycopg2://{_get('POSTGRES_USER', 'quantbot')}:"
                f"{_get('POSTGRES_PASSWORD', 'changeme')}@"
                f"{_get('POSTGRES_HOST', 'localhost')}:"
                f"{_get('POSTGRES_PORT', '5432')}/"
                f"{_get('POSTGRES_DB', 'quantbot')}"
            )
        redis_url = _get("REDIS_URL")
        if not redis_url:
            redis_url = (
                f"redis://{_get('REDIS_HOST', 'localhost')}:"
                f"{_get('REDIS_PORT', '6379')}/{_get('REDIS_DB', '0')}"
            )
        return cls(
            env=_get("QUANTBOT_ENV", "development"),
            mode=_get("QUANTBOT_MODE", "paper"),
            log_level=_get("LOG_LEVEL", "INFO"),
            log_json=_getb("LOG_JSON", True),
            database_url=db_url,
            redis_url=redis_url,
            data_exchange=_get("DATA_EXCHANGE", "binance"),
            risk=RiskConfig.from_env(),
            costs=CostConfig(),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton."""
    return Settings.from_env()
