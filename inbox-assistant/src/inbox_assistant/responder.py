"""Writes the reply text, grounded only in the client's knowledge.md.

The real Anthropic-backed responder arrives in Milestone 3. Until then `StubResponder` returns a
clearly marked English template so the rest of the pipeline can be exercised end to end.
The signature is added by `mail_client.build_reply`, never by the model.
"""

from __future__ import annotations

from typing import Protocol

from inbox_assistant.config import Client
from inbox_assistant.models import Classification, IncomingEmail, ReplyDraft, Usage


class Responder(Protocol):
    def write_reply(
        self,
        email: IncomingEmail,
        classification: Classification,
        reply_language: str,
        client: Client,
    ) -> ReplyDraft: ...


def _greeting(email: IncomingEmail) -> str:
    first_name = email.from_name.split()[0] if email.from_name.strip() else ""
    return f"Hello {first_name}," if first_name else "Hello,"


class StubResponder:
    model = "stub-responder"

    def write_reply(
        self,
        email: IncomingEmail,
        classification: Classification,
        reply_language: str,
        client: Client,
    ) -> ReplyDraft:
        cfg = client.config
        lines = [
            f"[STUB REPLY - the real reply in '{reply_language}' is written by the AI "
            "in Milestone 3]",
            "",
            _greeting(email),
            "",
            f"Thank you for contacting {cfg.business_name}.",
        ]
        if classification.category == "quote_request" and cfg.quote_required_fields:
            lines += ["", "To prepare a quote, could you please tell us:"]
            lines += [f"- {field}" for field in cfg.quote_required_fields]
        elif classification.category == "booking":
            if cfg.booking_link:
                lines += ["", f"You can check availability and book here: {cfg.booking_link}"]
            lines += ["We will confirm your booking separately once it has been made."]
        else:
            lines += ["", "(Answer based on knowledge.md would go here.)"]
        return ReplyDraft(
            body="\n".join(lines), needs_owner_followup=False, usage=Usage(self.model)
        )
