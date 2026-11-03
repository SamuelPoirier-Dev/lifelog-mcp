"""The generic entry: one thing recorded in one category."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from lifelog.timeutils import to_utc


class Entry(BaseModel):
    """An entry, as stored. Its attributes have already been validated by its category."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    category: str
    # Stored in UTC. Entries from users arrive in UTC (D60); in code, a time without a
    # time zone is Québec time (D8).
    timestamp: datetime
    # How many units: for drinks, the number of containers (D3). Decimals allowed (D42).
    quantity: float = Field(default=1, gt=0)
    note: str | None = Field(default=None, max_length=500)
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return to_utc(value)
