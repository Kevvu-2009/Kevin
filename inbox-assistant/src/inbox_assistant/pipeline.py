"""Per-email processing: parse -> filter -> classify -> decide -> respond -> deliver -> log."""

from __future__ import annotations

import logging
from collections.abc import Collection
from dataclasses import dataclass

from inbox_assistant import filters
from inbox_assistant.classifier import Classifier
from inbox_assistant.config import Client, ClientConfig
from inbox_assistant.mail_client import Mailbox, RawMessage, build_reply, parse_email
from inbox_assistant.models import REPLY_CATEGORIES, Action, Classification, Outcome
from inbox_assistant.responder import Responder
from inbox_assistant.store import MemoryStore

log = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "en"


def decide(classification: Classification, config: ClientConfig) -> tuple[Action, str]:
    """Return IGNORE, FLAG, or DRAFT (meaning: write a reply), plus a short reason.

    Uncertainty is checked first so a low-confidence "spam" verdict is shown to the owner
    instead of silently dropped.
    """
    if classification.needs_human:
        return Action.FLAG, "classifier says a human should handle it"
    if classification.confidence < config.min_confidence:
        return Action.FLAG, (
            f"low confidence ({classification.confidence:.2f} < {config.min_confidence:.2f})"
        )
    if classification.category == "spam":
        return Action.IGNORE, "spam"
    if classification.category not in REPLY_CATEGORIES:
        return Action.FLAG, f"category '{classification.category}' is always handled by the owner"
    return Action.DRAFT, f"category '{classification.category}' can be answered"


def reply_language(detected: str, allowed: Collection[str]) -> str:
    """Reply in the customer's language if the business supports it, otherwise English."""
    return detected if detected in allowed else DEFAULT_LANGUAGE


def delivery_action(category: str, config: ClientConfig, needs_owner_followup: bool) -> Action:
    if needs_owner_followup:
        return Action.DRAFT_AND_FLAG
    if config.mode == "auto" and category in config.auto_send_categories:
        return Action.SEND
    return Action.DRAFT


@dataclass
class Pipeline:
    client: Client
    mailbox: Mailbox
    classifier: Classifier
    responder: Responder
    store: MemoryStore
    own_addresses: frozenset[str]
    from_addr: str = ""

    def run(self) -> list[Outcome]:
        outcomes = []
        for raw in self.mailbox.fetch_new():
            try:
                outcome = self.process(raw)
            except Exception as exc:  # one bad email must never stop the run
                log.exception("Failed to process %s", raw.uid)
                outcome = self._handle_error(raw, exc)
            if outcome is not None:
                outcomes.append(outcome)
        return outcomes

    def process(self, raw: RawMessage) -> Outcome | None:
        email = parse_email(raw)
        if self.store.is_processed(email.uid, email.message_id):
            return None

        skip = filters.skip_reason(email, self.own_addresses)
        if skip:
            return self._finish(Outcome(email, raw.uid, Action.SKIP, reason=skip))

        result = self.classifier.classify(email)
        cls = result.classification
        outcome = Outcome(email, raw.uid, Action.FLAG, classification=cls, usages=[result.usage])

        action, reason = decide(cls, self.client.config)
        outcome.reason = cls.reason if result.fallback else reason
        if action is Action.IGNORE:
            outcome.action = Action.IGNORE
            return self._finish(outcome)
        if action is Action.FLAG:
            self.mailbox.flag_for_owner(email.uid)
            return self._finish(outcome)

        language = reply_language(cls.language, self.client.config.languages)
        draft = self.responder.write_reply(email, cls, language, self.client)
        outcome.usages.append(draft.usage)
        outcome.reply_language = language
        outcome.action = delivery_action(
            cls.category, self.client.config, draft.needs_owner_followup
        )
        if draft.needs_owner_followup:
            outcome.reason = "answer not in knowledge base; owner must follow up"

        outcome.reply = build_reply(
            email,
            draft.body,
            from_addr=self.from_addr or (email.to_addrs[0] if email.to_addrs else ""),
            from_name=self.client.config.business_name,
            signature=self.client.config.signature,
            auto_submitted=outcome.action is Action.SEND,
        )
        self._deliver(outcome)
        return self._finish(outcome)

    def _deliver(self, outcome: Outcome) -> None:
        assert outcome.email is not None and outcome.reply is not None
        if outcome.action is Action.SEND:
            self.mailbox.send(outcome.reply)
            return
        self.mailbox.save_draft(outcome.reply, self.client.config.drafts_folder)
        if outcome.action is Action.DRAFT_AND_FLAG:
            self.mailbox.flag_for_owner(outcome.email.uid)

    def _handle_error(self, raw: RawMessage, exc: Exception) -> Outcome:
        outcome = Outcome(None, raw.uid, Action.ERROR, reason=f"{type(exc).__name__}: {exc}")
        try:  # best effort: make sure the owner sees the email
            self.mailbox.flag_for_owner(raw.uid)
        except Exception:
            log.exception("Could not flag %s after an error", raw.uid)
        return self._finish(outcome)

    def _finish(self, outcome: Outcome) -> Outcome:
        self.store.record(outcome)
        return outcome
