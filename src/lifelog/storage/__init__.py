"""Storage backends for entries (in memory or Azure Table Storage), behind Repository."""

from lifelog.storage.base import MAX_BATCH_SIZE, Repository
from lifelog.storage.memory import MemoryRepository

__all__ = ["MAX_BATCH_SIZE", "MemoryRepository", "Repository"]
