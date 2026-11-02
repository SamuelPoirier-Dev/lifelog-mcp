"""What a storage backend must provide."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from lifelog.entries import Entry

# Azure Table Storage writes at most 100 entities in one transaction.
MAX_BATCH_SIZE = 100


class Repository(Protocol):
    async def add_many(self, entries: Sequence[Entry]) -> None:
        """Store entries of a single category, all or nothing (D9).

        Raises ValueError if the entries mix categories or exceed MAX_BATCH_SIZE.
        """
        ...

    async def list(self, category: str, start: datetime, end: datetime) -> list[Entry]:
        """Entries of a category with start <= timestamp < end (UTC), oldest first."""
        ...


def check_batch(entries: Sequence[Entry]) -> str | None:
    """Validate a batch for add_many and return its category (None if empty)."""
    if len(entries) > MAX_BATCH_SIZE:
        raise ValueError(f"At most {MAX_BATCH_SIZE} entries can be stored at once")
    categories = {entry.category for entry in entries}
    if len(categories) > 1:
        raise ValueError("All entries of a batch must belong to the same category")
    return categories.pop() if categories else None
