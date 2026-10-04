from __future__ import annotations

from collections.abc import Iterator
from email.message import EmailMessage

import pytest

from conftest import FIXTURES
from inbox_assistant.classifier import StubClassifier
from inbox_assistant.config import ClientConfig
from inbox_assistant.mail_client import DryRunMailbox, EmlDirMailbox, RawMessage
from inbox_assistant.models import (
    Action,
    Classification,
    ClassifierResult,
    IncomingEmail,
    ReplyDraft,
    Usage,
)
from inbox_assistant.pipeline import Pipeline, decide, delivery_action, reply_language
from inbox_assistant.responder import StubResponder
from inbox_assistant.store import MemoryStore


def cls(category="faq", confidence=0.9, needs_human=False, language="en") -> Classification:
    return Classification(
        category=category,
        language=language,
        confidence=confidence,
        needs_human=needs_human,
        reason="test",
    )


CFG = ClientConfig(business_name="Biz", languages=["fi", "en", "sv"])


@pytest.mark.parametrize(
    "classification, expected",
    [
        (cls("faq"), Action.DRAFT),
        (cls("booking"), Action.DRAFT),
        (cls("quote_request"), Action.DRAFT),
        (cls("complaint"), Action.FLAG),
        (cls("other"), Action.FLAG),
        (cls("spam"), Action.IGNORE),
        (cls("faq", needs_human=True), Action.FLAG),
        (cls("faq", confidence=0.5), Action.FLAG),
        # an unsure spam verdict is shown to the owner rather than silently dropped
        (cls("spam", confidence=0.4), Action.FLAG),
    ],
)
def test_decide(classification, expected):
    assert decide(classification, CFG)[0] is expected


@pytest.mark.parametrize(
    "detected, expected", [("fi", "fi"), ("sv", "sv"), ("de", "en"), ("ja", "en")]
)
def test_reply_language(detected, expected):
    assert reply_language(detected, CFG.languages) == expected


def test_delivery_action():
    auto = CFG.model_copy(update={"mode": "auto", "auto_send_categories": ["faq"]})
    assert delivery_action("faq", CFG, False) is Action.DRAFT  # draft mode never sends
    assert delivery_action("faq", auto, False) is Action.SEND
    assert delivery_action("booking", auto, False) is Action.DRAFT
    assert delivery_action("faq", auto, True) is Action.DRAFT_AND_FLAG


# --------------------------------------------------------------------------- end to end


class NoWriteMailbox:
    """Inner mailbox that fails the test if anything tries to write to it."""

    def __init__(self, messages: list[RawMessage]) -> None:
        self.messages = messages

    def fetch_new(self) -> Iterator[RawMessage]:
        return iter(self.messages)

    def save_draft(self, reply: EmailMessage, folder: str) -> None:
        raise AssertionError("dry-run wrote a draft")

    def flag_for_owner(self, uid: str) -> None:
        raise AssertionError("dry-run set a flag")

    def send(self, reply: EmailMessage) -> None:
        raise AssertionError("dry-run sent mail")


class FixedClassifier:
    def __init__(self, classification: Classification) -> None:
        self.classification = classification

    def classify(self, email: IncomingEmail) -> ClassifierResult:
        if "explode" in email.subject:
            raise RuntimeError("classifier blew up")
        return ClassifierResult(self.classification, Usage("fake", 10, 2))


class FollowupResponder:
    def write_reply(self, email, classification, reply_language, client) -> ReplyDraft:
        return ReplyDraft("The owner will get back to you.", True, Usage("fake-r", 100, 20))


def make_pipeline(client, mailbox, classifier=None, responder=None) -> Pipeline:
    return Pipeline(
        client=client,
        mailbox=mailbox,
        classifier=classifier or StubClassifier(),
        responder=responder or StubResponder(),
        store=MemoryStore(),
        own_addresses=frozenset(),
        from_addr="info@lakeside-demo.example",
    )


def raw(uid: str, subject: str) -> RawMessage:
    data = f"From: C <c@x.com>\nMessage-ID: <{uid}@x>\nSubject: {subject}\n\nHello?\n"
    return RawMessage(uid, data.encode())


def test_dry_run_over_fixtures_never_writes(demo_client):
    messages = list(EmlDirMailbox(FIXTURES).fetch_new())
    mailbox = DryRunMailbox(NoWriteMailbox(messages))
    outcomes = make_pipeline(demo_client, mailbox).run()

    assert len(outcomes) == len(messages)
    by_file = {o.source: o for o in outcomes}
    assert by_file["04_complaint_en.eml"].action is Action.FLAG
    assert by_file["09_spam.eml"].action is Action.IGNORE
    assert by_file["02_quote_request_fi.eml"].action is Action.DRAFT
    assert by_file["02_quote_request_fi.eml"].reply_language == "fi"
    assert by_file["05_question_de.eml"].reply_language == "en"

    drafts = [p for p in mailbox.planned if p.kind == "draft"]
    assert all(p.target == "Drafts" for p in drafts)
    assert len(drafts) == sum(o.action is Action.DRAFT for o in outcomes)


def test_reply_has_signature_and_thread_headers(demo_client):
    mailbox = DryRunMailbox(EmlDirMailbox(FIXTURES))
    outcomes = make_pipeline(demo_client, mailbox).run()
    reply = next(o.reply for o in outcomes if o.source == "03_booking_sv.eml")
    assert reply["In-Reply-To"] == "<CAF-lars-7781@mail.example.se>"
    assert reply["Subject"] == "Re: Bokning av stuga i juli"
    assert reply.get_content().rstrip().endswith("Best regards,\nLakeside Cottages")
    assert "https://example.com/book" in reply.get_content()


def test_owner_followup_saves_draft_and_flags(demo_client):
    mailbox = DryRunMailbox(NoWriteMailbox([raw("1", "Question")]))
    pipeline = make_pipeline(demo_client, mailbox, FixedClassifier(cls("faq")), FollowupResponder())
    [outcome] = pipeline.run()
    assert outcome.action is Action.DRAFT_AND_FLAG
    assert [p.kind for p in mailbox.planned] == ["draft", "flag"]


def test_one_bad_email_does_not_stop_the_run(demo_client):
    messages = [raw("1", "please explode"), raw("2", "Normal question")]
    mailbox = DryRunMailbox(NoWriteMailbox(messages))
    pipeline = make_pipeline(demo_client, mailbox, FixedClassifier(cls("faq")))
    first, second = pipeline.run()
    assert first.action is Action.ERROR and "classifier blew up" in first.reason
    assert second.action is Action.DRAFT
    assert ("flag", "1") in [(p.kind, p.target) for p in mailbox.planned]


def test_action_log_has_no_email_bodies(demo_client):
    store = MemoryStore()
    pipeline = make_pipeline(
        demo_client, DryRunMailbox(NoWriteMailbox([raw("1", "Q")])), FixedClassifier(cls("faq"))
    )
    pipeline.store = store
    pipeline.run()
    [entry] = store.log
    assert entry.action == "draft" and entry.category == "faq"
    assert entry.models == "fake,stub-responder" and entry.input_tokens == 10
    assert "Hello?" not in repr(entry)
    assert store.is_processed("1", "<1@x>")
