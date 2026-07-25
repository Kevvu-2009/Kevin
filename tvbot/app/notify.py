"""Telegram notifications.

Two rules:

1. **Notification failures never propagate.** A Telegram outage must not abort
   an order placement or crash the reconcile loop, so every path here swallows
   its exceptions and returns a bool.
2. **Repeated alerts are deduplicated.** "Stop missing on BTC/USDT:USDT" is
   emitted by a loop that runs every 30 seconds; without a dedup window a
   single unresolved problem would send 2,880 messages a day and you would mute
   the channel, which is how a real alert gets missed.
"""

from __future__ import annotations

import logging
import time
from enum import Enum

from .config import Settings

log = logging.getLogger(__name__)

try:  # httpx is only needed when Telegram is actually configured
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]
    HTTPX_AVAILABLE = False

TELEGRAM_MAX_CHARS = 4000


class Level(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    CRITICAL = "CRITICAL"

    @property
    def prefix(self) -> str:
        return {"INFO": "[i]", "WARN": "[!]", "CRITICAL": "[!!!]"}[self.value]


class Notifier:
    """Fire-and-forget notifier. Safe to call from anywhere, including except blocks."""

    def __init__(self, cfg: Settings) -> None:
        self.cfg = cfg
        self._client: httpx.AsyncClient | None = None
        self._last_sent: dict[str, float] = {}
        self.sent_messages: list[tuple[Level, str]] = []  # inspected by tests

    @property
    def enabled(self) -> bool:
        return bool(
            HTTPX_AVAILABLE and self.cfg.telegram_bot_token and self.cfg.telegram_chat_id
        )

    async def _get_client(self) -> httpx.AsyncClient | None:
        if not self.enabled:
            return None
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    def _suppressed(self, dedup_key: str | None) -> bool:
        if not dedup_key:
            return False
        last = self._last_sent.get(dedup_key)
        now = time.monotonic()
        if last is not None and (now - last) < self.cfg.notify_dedup_sec:
            return True
        self._last_sent[dedup_key] = now
        return False

    async def send(
        self,
        text: str,
        *,
        level: Level = Level.INFO,
        dedup_key: str | None = None,
    ) -> bool:
        """Send a message. Returns True if it reached Telegram.

        Always logs, regardless of whether Telegram is configured, so the
        JSON log file remains the complete record.
        """
        body = f"{level.prefix} {text}"[:TELEGRAM_MAX_CHARS]
        # NB: keys passed via `extra` must not collide with reserved LogRecord
        # attributes ("message", "args", "levelname", ...) - logging raises
        # KeyError at record creation, which would turn every notification into
        # an exception. Hence "notify_text" rather than "message".
        log.info("notify", extra={"notify_level": level.value, "notify_text": text})
        self.sent_messages.append((level, text))

        if self._suppressed(dedup_key):
            return False

        client = await self._get_client()
        if client is None:
            return False

        url = f"https://api.telegram.org/bot{self.cfg.telegram_bot_token}/sendMessage"
        try:
            resp = await client.post(
                url,
                json={
                    "chat_id": self.cfg.telegram_chat_id,
                    "text": body,
                    "disable_web_page_preview": True,
                },
            )
            if resp.status_code >= 400:
                log.warning("telegram_send_failed status=%s body=%s", resp.status_code, resp.text[:200])
                return False
            return True
        except Exception as exc:  # noqa: BLE001 - notifications must never raise
            log.warning("telegram_send_error %s: %s", type(exc).__name__, exc)
            return False

    # -- convenience wrappers used across the app ----------------------------
    async def info(self, text: str, dedup_key: str | None = None) -> bool:
        return await self.send(text, level=Level.INFO, dedup_key=dedup_key)

    async def warn(self, text: str, dedup_key: str | None = None) -> bool:
        return await self.send(text, level=Level.WARN, dedup_key=dedup_key)

    async def critical(self, text: str, dedup_key: str | None = None) -> bool:
        return await self.send(text, level=Level.CRITICAL, dedup_key=dedup_key)

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:  # noqa: BLE001 - shutdown must not raise
                pass
            self._client = None
