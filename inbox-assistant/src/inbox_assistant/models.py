"""Shared data types used across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from email.message import EmailMessage
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["faq", "booking", "quote_request", "complaint", "spam", "other"]

# Categories the bot is allowed to answer. Everything else is flagged or ignored.
REPLY_CATEGORIES: frozenset[str] = frozenset({"faq", "booking", "quote_request"})


@dataclass(frozen=True)
class IncomingEmail:
    """A parsed incoming message. `raw` keeps all headers for the filters."""

    uid: str
    message_id: str
    from_addr: str
    from_name: str
    to_addrs: tuple[str, ...]
    subject: str
    date: str
    in_reply_to: str
    references: tuple[str, ...]
    body_text: str
    raw: EmailMessage = field(repr=False, compare=False)

    @property
    def thread_key(self) -> str:
        """Stable id for the conversation: the first message's Message-ID.

        References lists the whole chain oldest-first, so its first entry is the thread root.
        Falls back to In-Reply-To, then to this message's own Message-ID.
        """
        if self.references:
            return self.references[0]
        if self.in_reply_to:
            return self.in_reply_to
        return self.message_id


class Classification(BaseModel):
    """Strict schema for the classifier's JSON output."""

    category: Category
    language: str = Field(min_length=2, max_length=8)
    confidence: float = Field(ge=0.0, le=1.0)
    needs_human: bool
    reason: str = Field(default="", max_length=300)


@dataclass(frozen=True)
class Usage:
    """Which model handled a call and how many tokens it used (for the action log)."""

    model: str
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class ClassifierResult:
    classification: Classification
    usage: Usage
    # True when the model output could not be parsed and we fell back to needs_human.
    fallback: bool = False


@dataclass(frozen=True)
class ReplyDraft:
    """Reply text from the responder (without signature) plus whether the owner must follow up."""

    body: str
    needs_owner_followup: bool
    usage: Usage


class Action(StrEnum):
    SKIP = "skip"  # filtered out before any AI call
    IGNORE = "ignore"  # spam: log only
    FLAG = "flag"  # flag for owner, no reply
    DRAFT = "draft"  # reply saved to Drafts
    DRAFT_AND_FLAG = "draft_and_flag"  # draft saved, owner must still follow up
    SEND = "send"  # reply sent via SMTP (auto mode)
    ERROR = "error"  # something went wrong with this email; owner should look


@dataclass
class Outcome:
    """What happened (or would happen in dry-run) to one email."""

    email: IncomingEmail | None
    source: str  # file name or UID, for display
    action: Action
    reason: str = ""
    classification: Classification | None = None
    reply_language: str | None = None
    reply: EmailMessage | None = None
    usages: list[Usage] = field(default_factory=list)
