from __future__ import annotations

import pytest

from conftest import FIXTURES, load_fixture
from inbox_assistant.mail_client import (
    DryRunMailbox,
    EmlDirMailbox,
    RawMessage,
    ReadOnlyMailboxError,
    build_reply,
    parse_email,
    reply_subject,
)


def test_every_fixture_parses():
    names = sorted(p.name for p in FIXTURES.glob("*.eml"))
    assert len(names) >= 10
    for name in names:
        email = load_fixture(name)
        assert email.message_id.startswith("<")
        assert email.from_addr
        assert email.body_text


def test_multipart_finnish_quote_is_decoded():
    email = load_fixture("02_quote_request_fi.eml")
    assert email.subject == "Tarjouspyyntö: mökki juhannukseksi"
    assert email.from_name == "Matti Virtanen"
    assert email.from_addr == "matti.virtanen@example.fi"
    # plain part preferred over html, quoted-printable decoded
    assert "kahdeksalle hengelle" in email.body_text
    assert "<p>" not in email.body_text


def test_html_only_body_is_converted_to_text():
    email = load_fixture("06_newsletter.eml")
    assert "Advertise with us" in email.body_text
    assert "<" not in email.body_text


def test_thread_key_uses_first_reference():
    assert load_fixture("10_thread_reply_en.eml").thread_key == "<emily-001@example.com>"
    assert load_fixture("01_faq_en.eml").thread_key == "<emily-001@example.com>"


def test_thread_key_falls_back_to_in_reply_to():
    raw = b"From: a@x.com\nMessage-ID: <m2@x>\nIn-Reply-To: <m1@x>\n\nhi\n"
    assert parse_email(RawMessage("1", raw)).thread_key == "<m1@x>"


def test_missing_message_id_gets_placeholder():
    email = parse_email(RawMessage("42", b"From: a@x.com\nSubject: hi\n\nhello\n"))
    assert email.message_id == "<missing-id-42@local>"


@pytest.mark.parametrize(
    "subject, expected",
    [
        ("Question", "Re: Question"),
        ("Re: Question", "Re: Question"),
        ("RE:Question", "RE:Question"),
        ("Vs: Kysymys", "Vs: Kysymys"),
        ("SV: Fråga", "SV: Fråga"),
        ("", "Re:"),
    ],
)
def test_reply_subject(subject, expected):
    assert reply_subject(subject) == expected


def test_build_reply_threads_correctly():
    original = load_fixture("10_thread_reply_en.eml")
    reply = build_reply(
        original, "Yes, there is parking.", "info@biz.example", "Biz", "Cheers,\nBiz"
    )
    assert reply["Subject"] == "Re: Question about pets and sauna"
    assert reply["In-Reply-To"] == "<emily-003@example.com>"
    assert reply["References"] == (
        "<emily-001@example.com> <owner-reply-002@lakeside-demo.example> <emily-003@example.com>"
    )
    assert reply["To"] == "Emily Carter <emily.carter@example.com>"
    assert reply["From"] == "Biz <info@biz.example>"
    assert reply["Message-ID"].endswith("@biz.example>")
    assert reply["Auto-Submitted"] is None
    assert reply.get_content() == "Yes, there is parking.\n\nCheers,\nBiz\n"


def test_build_reply_respects_reply_to_and_marks_auto_sent():
    raw = (
        b"From: Shop <shop@x.com>\nReply-To: Real Person <real@x.com>\n"
        b"Message-ID: <r1@x>\nSubject: Hi\n\nhello\n"
    )
    reply = build_reply(
        parse_email(RawMessage("1", raw)), "ok", "me@b.com", "B", auto_submitted=True
    )
    assert reply["To"] == "Real Person <real@x.com>"
    assert reply["References"] == "<r1@x>"
    assert reply["Auto-Submitted"] == "auto-replied"


def test_eml_dir_mailbox_is_read_only(tmp_path):
    box = EmlDirMailbox(FIXTURES)
    assert len(list(box.fetch_new())) >= 10
    with pytest.raises(ReadOnlyMailboxError):
        box.flag_for_owner("x")


def test_dry_run_mailbox_records_instead_of_writing():
    box = DryRunMailbox(EmlDirMailbox(FIXTURES))
    original = load_fixture("01_faq_en.eml")
    reply = build_reply(original, "hi", "me@b.com", "B")
    box.save_draft(reply, "Drafts")
    box.flag_for_owner("01_faq_en.eml")
    box.send(reply)
    assert [p.kind for p in box.planned] == ["draft", "flag", "send"]
