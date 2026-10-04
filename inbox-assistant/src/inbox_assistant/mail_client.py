"""Reading and writing mail.

The pipeline only talks to the `Mailbox` interface, so tests and dry-runs can swap in fakes:

* `EmlDirMailbox`  — reads `.eml` files from a folder (read-only; used for fixtures and dry-runs)
* `DryRunMailbox`  — wraps any mailbox; reads pass through, writes are only recorded and printed
* IMAP/SMTP mailbox — Milestone 4/6
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import formataddr, formatdate, getaddresses, make_msgid, parseaddr
from html import unescape
from pathlib import Path
from typing import Protocol

from inbox_assistant.models import IncomingEmail

_MSGID_RE = re.compile(r"<[^<>\s]+>")
# Reply prefixes used by common mail clients: English Re, Finnish Vs, Swedish Sv, German Aw.
_REPLY_PREFIX_RE = re.compile(r"^\s*(re|vs|sv|aw)\s*:", re.IGNORECASE)


@dataclass(frozen=True)
class RawMessage:
    """An unparsed message as fetched. `uid` is the IMAP UID (or file name for .eml folders)."""

    uid: str
    data: bytes


class ReadOnlyMailboxError(RuntimeError):
    pass


class Mailbox(Protocol):
    def fetch_new(self) -> Iterator[RawMessage]: ...

    def save_draft(self, reply: EmailMessage, folder: str) -> None: ...

    def flag_for_owner(self, uid: str) -> None: ...

    def send(self, reply: EmailMessage) -> None: ...


# --------------------------------------------------------------------------- parsing


def _header(msg: EmailMessage, name: str) -> str:
    """Read a header as text without letting one malformed header crash parsing."""
    try:
        value = msg.get(name)
    except Exception:  # malformed header that the email library can't decode
        return ""
    return str(value).strip() if value is not None else ""


def _message_ids(value: str) -> tuple[str, ...]:
    return tuple(_MSGID_RE.findall(value))


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?</\1>", "", html)
    html = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", html)
    text = unescape(re.sub(r"<[^>]+>", "", html))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _body_text(msg: EmailMessage) -> str:
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    try:
        content = part.get_content()
    except (LookupError, UnicodeError):  # unknown or wrong charset
        payload = part.get_payload(decode=True) or b""
        content = payload.decode("utf-8", errors="replace")
    if not isinstance(content, str):
        return ""
    if part.get_content_type() == "text/html":
        content = _html_to_text(content)
    return content.strip()


def parse_email(raw: RawMessage) -> IncomingEmail:
    msg = BytesParser(policy=policy.default).parsebytes(raw.data)
    assert isinstance(msg, EmailMessage)

    from_name, from_addr = parseaddr(_header(msg, "From"))
    to_addrs = tuple(addr.lower() for _, addr in getaddresses([_header(msg, "To")]) if addr)
    message_id = (_message_ids(_header(msg, "Message-ID")) or (f"<missing-id-{raw.uid}@local>",))[0]
    in_reply_to_ids = _message_ids(_header(msg, "In-Reply-To"))

    return IncomingEmail(
        uid=raw.uid,
        message_id=message_id,
        from_addr=from_addr.lower(),
        from_name=from_name,
        to_addrs=to_addrs,
        subject=_header(msg, "Subject"),
        date=_header(msg, "Date"),
        in_reply_to=in_reply_to_ids[0] if in_reply_to_ids else "",
        references=_message_ids(_header(msg, "References")),
        body_text=_body_text(msg),
        raw=msg,
    )


# --------------------------------------------------------------------------- replies


def reply_subject(subject: str) -> str:
    subject = subject.strip()
    if _REPLY_PREFIX_RE.match(subject):
        return subject
    return f"Re: {subject}" if subject else "Re:"


def build_reply(
    original: IncomingEmail,
    body: str,
    from_addr: str,
    from_name: str,
    signature: str = "",
    auto_submitted: bool = False,
) -> EmailMessage:
    """Build a reply that threads correctly under `original` in any mail client.

    `auto_submitted=True` marks it per RFC 3834 so other bots don't answer it (used for auto-send).
    """
    reply = EmailMessage()
    reply_to = _header(original.raw, "Reply-To")
    to_name, to_addr = parseaddr(reply_to) if reply_to else (original.from_name, original.from_addr)

    reply["From"] = formataddr((from_name, from_addr)) if from_addr else from_name
    reply["To"] = formataddr((to_name, to_addr))
    reply["Subject"] = reply_subject(original.subject)
    reply["Date"] = formatdate(localtime=True)
    domain = from_addr.rpartition("@")[2] or None
    reply["Message-ID"] = make_msgid(domain=domain)
    reply["In-Reply-To"] = original.message_id
    references = list(original.references)
    if original.message_id not in references:
        references.append(original.message_id)
    reply["References"] = " ".join(references)
    if auto_submitted:
        reply["Auto-Submitted"] = "auto-replied"

    text = body.rstrip()
    if signature.strip():
        text = f"{text}\n\n{signature.strip()}"
    reply.set_content(text + "\n")
    return reply


# --------------------------------------------------------------------------- mailboxes


class EmlDirMailbox:
    """Reads every `.eml` file in a folder (sorted by name). Never writes anything."""

    def __init__(self, folder: Path) -> None:
        if not folder.is_dir():
            raise FileNotFoundError(f"Email folder not found: {folder}")
        self.folder = folder

    def fetch_new(self) -> Iterator[RawMessage]:
        for path in sorted(self.folder.glob("*.eml")):
            yield RawMessage(uid=path.name, data=path.read_bytes())

    def save_draft(self, reply: EmailMessage, folder: str) -> None:
        raise ReadOnlyMailboxError("An .eml folder is read-only; use --dry-run")

    def flag_for_owner(self, uid: str) -> None:
        raise ReadOnlyMailboxError("An .eml folder is read-only; use --dry-run")

    def send(self, reply: EmailMessage) -> None:
        raise ReadOnlyMailboxError("An .eml folder is read-only; use --dry-run")


@dataclass(frozen=True)
class PlannedWrite:
    kind: str  # "draft" | "flag" | "send"
    target: str  # folder, UID or recipient
    message: EmailMessage | None = None


@dataclass
class DryRunMailbox:
    """Passes reads through to `inner` but only records writes. Guarantees zero mailbox writes."""

    inner: Mailbox
    planned: list[PlannedWrite] = field(default_factory=list)

    def fetch_new(self) -> Iterator[RawMessage]:
        return self.inner.fetch_new()

    def save_draft(self, reply: EmailMessage, folder: str) -> None:
        self.planned.append(PlannedWrite("draft", folder, reply))

    def flag_for_owner(self, uid: str) -> None:
        self.planned.append(PlannedWrite("flag", uid))

    def send(self, reply: EmailMessage) -> None:
        self.planned.append(PlannedWrite("send", str(reply["To"]), reply))
