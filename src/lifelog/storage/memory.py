"""In-memory storage: tests and local development. Everything is lost on restart."""

from collections.abc import Sequence
from datetime import datetime

from lifelog.entries import Entry
from lifelog.storage.base import check_batch
from lifelog.timeutils import to_utc


class MemoryRepository:
    def __init__(self) -> None:
        self._entries: list[Entry] = []

    async def add_many(self, entries: Sequence[Entry]) -> None:
        check_batch(entries)
        new_ids = [entry.id for entry in entries]
        existing = {entry.id for entry in self._entries}
        if len(set(new_ids)) != len(new_ids) or existing.intersection(new_ids):
            raise ValueError("An entry with the same id already exists")
        self._entries.extend(entries)

    async def list(self, category: str, start: datetime, end: datetime) -> list[Entry]:
        start, end = to_utc(start), to_utc(end)
        found = [
            entry
            for entry in self._entries
            if entry.category == category and start <= entry.timestamp < end
        ]
        return sorted(found, key=lambda entry: entry.timestamp)
