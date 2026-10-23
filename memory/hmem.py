"""Meterless H-MEM wrapper — hierarchical memory shared across agents.

In-process implementation with the planned interface. When the Meterless SDK
is confirmed, swap the internals of write/query/get_all; callers don't change.
"""
import uuid
from datetime import datetime, timezone

_SESSIONS: dict[str, "HMem"] = {}


class HMem:
    def __init__(self, session_id: str | None = None):
        self.session_id = session_id or f"hmem-{uuid.uuid4().hex[:12]}"
        self._records: list[dict] = []

    @classmethod
    def session(cls, session_id: str | None = None) -> "HMem":
        """Return the shared instance for a session id, creating it if needed."""
        if session_id and session_id in _SESSIONS:
            return _SESSIONS[session_id]
        mem = cls(session_id)
        _SESSIONS[mem.session_id] = mem
        return mem

    def write(self, content: dict, level: str = "episodic", provenance: dict | None = None,
              confidence: float = 1.0) -> str:
        key = f"mem-{uuid.uuid4().hex[:10]}"
        self._records.append({
            "key": key,
            "content": content,
            "level": level,
            "provenance": provenance or {},
            "confidence": confidence,
            "written_at": datetime.now(timezone.utc).isoformat(),
        })
        return key

    def query(self, intent: str = "", filters: dict | None = None) -> list[dict]:
        """Match records whose provenance contains every filter key/value and whose
        content mentions every word of intent (case-insensitive)."""
        filters = filters or {}
        words = [w for w in intent.lower().split() if w]
        out = []
        for rec in self._records:
            if any(rec["provenance"].get(k) != v for k, v in filters.items()):
                continue
            blob = str(rec["content"]).lower()
            if all(w in blob for w in words):
                out.append(rec)
        return out

    def get_all(self, level: str | None = None) -> list[dict]:
        return [r for r in self._records if level is None or r["level"] == level]

    def clear_source(self, source: str) -> None:
        """Drop a source's findings before a retry overwrites them."""
        self._records = [r for r in self._records if r["provenance"].get("source") != source]
