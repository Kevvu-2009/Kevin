"""Processing state and action log.

Milestone 1 keeps this in memory (nothing survives between runs). Milestone 5 replaces it with
SQLite behind the same methods. Email bodies are never stored, only metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from inbox_assistant.models import Outcome


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

    def is_processed(self, uid: str, message_id: str) -> bool:
        return (uid, message_id) in self.processed

    def record(self, outcome: Outcome) -> LogEntry:
        email = outcome.email
        cls = outcome.classification
        entry = LogEntry(
            timestamp=datetime.now(UTC).isoformat(timespec="seconds"),
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
        self.log.append(entry)
        return entry
