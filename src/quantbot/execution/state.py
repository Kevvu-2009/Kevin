"""Engine state persistence.

A small serialisable snapshot of the live engine so it can resume after a
restart (crash recovery).  Backed by Redis when available, with a JSON-file
fallback for local/dev use.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EngineState:
    mode: str = "paper"
    equity: float = 10_000.0
    peak_equity: float = 10_000.0
    open_positions: dict[str, dict] = field(default_factory=dict)
    last_bar_ts: dict[str, str] = field(default_factory=dict)   # per symbol
    kill_switch_active: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)

    @classmethod
    def from_json(cls, raw: str) -> "EngineState":
        return cls(**json.loads(raw))


class StateStore:
    """Redis-backed store with JSON-file fallback."""

    def __init__(self, key: str = "quantbot:engine_state", redis_url: str | None = None,
                 file_path: str | Path = "artifacts/engine_state.json") -> None:
        self.key = key
        self.file_path = Path(file_path)
        self._redis = None
        if redis_url:
            try:
                import redis

                self._redis = redis.from_url(redis_url)
                self._redis.ping()
            except Exception:  # pragma: no cover - fallback to file
                self._redis = None

    def save(self, state: EngineState) -> None:
        payload = state.to_json()
        if self._redis is not None:
            self._redis.set(self.key, payload)
        else:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self.file_path.write_text(payload)

    def load(self) -> EngineState | None:
        if self._redis is not None:
            raw = self._redis.get(self.key)
            if raw:
                return EngineState.from_json(raw.decode() if isinstance(raw, bytes) else raw)
            return None
        if self.file_path.exists():
            return EngineState.from_json(self.file_path.read_text())
        return None
