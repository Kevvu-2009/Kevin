"""Structured logging.

Uses ``structlog`` when available (JSON in production, pretty in dev) and falls
back to stdlib ``logging`` so the package never hard-fails on import.  A small
set of helper functions standardise the event *categories* required by the
spec: signals, orders, fills, errors, risk events, strategy decisions.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

_CONFIGURED = False


def configure_logging(level: str = "INFO", json: bool = True) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    lvl = getattr(logging, level.upper(), logging.INFO)
    try:
        import structlog

        logging.basicConfig(format="%(message)s", stream=sys.stdout, level=lvl)
        processors = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
        ]
        processors.append(
            structlog.processors.JSONRenderer()
            if json
            else structlog.dev.ConsoleRenderer()
        )
        structlog.configure(
            processors=processors,
            wrapper_class=structlog.make_filtering_bound_logger(lvl),
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )
    except Exception:  # pragma: no cover - structlog optional
        logging.basicConfig(
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
            stream=sys.stdout,
            level=lvl,
        )


class _StdlibShim:
    """Adapts stdlib logging to structlog's keyword-event API.

    Lets the rest of the codebase call ``log.info("event", key=val)`` even when
    structlog is not installed, by folding the kwargs into the message.
    """

    def __init__(self, logger: logging.Logger) -> None:
        self._log = logger

    @staticmethod
    def _fmt(event: str, kw: dict[str, Any]) -> str:
        if not kw:
            return event
        extras = " ".join(f"{k}={v}" for k, v in kw.items())
        return f"{event} {extras}"

    def debug(self, event: str, **kw: Any) -> None:
        self._log.debug(self._fmt(event, kw))

    def info(self, event: str, **kw: Any) -> None:
        self._log.info(self._fmt(event, kw))

    def warning(self, event: str, **kw: Any) -> None:
        self._log.warning(self._fmt(event, kw))

    def error(self, event: str, **kw: Any) -> None:
        self._log.error(self._fmt(event, kw))

    def exception(self, event: str, **kw: Any) -> None:  # pragma: no cover
        self._log.exception(self._fmt(event, kw))


def get_logger(name: str = "quantbot") -> Any:
    try:
        import structlog

        return structlog.get_logger(name)
    except Exception:  # pragma: no cover
        return _StdlibShim(logging.getLogger(name))


# --- Category helpers -------------------------------------------------------
# Each helper attaches a `category` so downstream sinks (stdout, Postgres
# event_log) can filter by signal/order/fill/error/risk/strategy.

def log_signal(log: Any, **kw: Any) -> None:
    log.info("signal", category="signal", **kw)


def log_order(log: Any, **kw: Any) -> None:
    log.info("order", category="order", **kw)


def log_fill(log: Any, **kw: Any) -> None:
    log.info("fill", category="fill", **kw)


def log_risk(log: Any, **kw: Any) -> None:
    log.warning("risk_event", category="risk", **kw)


def log_strategy(log: Any, **kw: Any) -> None:
    log.info("strategy_decision", category="strategy", **kw)


def log_error(log: Any, **kw: Any) -> None:
    log.error("error", category="error", **kw)
