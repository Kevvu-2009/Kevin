"""Rules that skip an email BEFORE any AI call (no-reply senders, auto-replies, mailing lists,
loop protection). Implemented in Milestone 2; for now every email passes."""

from __future__ import annotations

from collections.abc import Collection

from inbox_assistant.models import IncomingEmail


def skip_reason(email: IncomingEmail, own_addresses: Collection[str]) -> str | None:
    """Return why `email` must be skipped, or None if the bot may look at it."""
    return None
