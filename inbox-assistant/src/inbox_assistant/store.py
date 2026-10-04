"""Processing state, reply history and action log.

For now this is kept in memory, so it only lasts for one run. Milestone 5 replaces it with
SQLite behind the same methods. Email bodies are never stored, only metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from inbox_assistant.models import REPLIED_ACTIONS, Outcome


@dataclass(frozen=True)
class LogEntry:
    timestamp: str
    uid: str
    message_id: str
    thread_key: str
    category: str
    language: str
    action: str
    models: str
    input_tokens: int
    output_tokens: int


@dataclass
class MemoryStore:
    processed: set[tuple[str, str]] = field(default_factory=set)
    log: list[LogEntry] = field(default_factory=list)
    replied_threads: set[str] = field(default_factory=set)
    last_reply_by_sender: dict[str, datetime] = field(default_factory=dict)

    def is_processed(self, uid: str, message_id: str) -> bool:
        return (uid, message_id) in self.processed

    def replied_in_thread(self, thread_key: str) -> bool:
        return thread_key in self.replied_threads

    def last_reply_to_sender(self, address: str) -> datetime | None:
        return self.last_reply_by_sender.get(address.lower())

    def record(self, outcome: Outcome, now: datetime | None = None) -> LogEntry:
        now = now or datetime.now(UTC)
        email = outcome.email
        cls = outcome.classification
        entry = LogEntry(
            timestamp=now.isoformat(timespec="seconds"),
            uid=email.uid if email else outcome.source,
            message_id=email.message_id if email else "",
            thread_key=email.thread_key if email else "",
            category=cls.category if cls else "",
            language=cls.language if cls else "",
            action=outcome.action.value,
            models=",".join(u.model for u in outcome.usages),
            input_tokens=sum(u.input_tokens for u in outcome.usages),
            output_tokens=sum(u.output_tokens for u in outcome.usages),
        )
        if email:
            self.processed.add((email.uid, email.message_id))
            if outcome.action in REPLIED_ACTIONS:
                self.replied_threads.add(email.thread_key)
                self.last_reply_by_sender[email.from_addr.lower()] = now
        self.log.append(entry)
        return entry
