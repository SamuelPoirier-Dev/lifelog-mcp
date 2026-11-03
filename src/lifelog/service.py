"""Business operations shared by the MCP tools and the REST API.

The service validates input with the category, resolves periods in Québec time and
talks to the storage. It knows nothing about MCP or HTTP. Timestamps come in and go out
in UTC (D60).
"""

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from lifelog.categories import CategoryRegistry
from lifelog.entries import Entry
from lifelog.storage import MAX_BATCH_SIZE, Repository
from lifelog.timeutils import Period, local_today


class NewEntry(BaseModel):
    """An entry to record."""

    model_config = ConfigDict(extra="forbid")

    timestamp: datetime | None = Field(
        default=None,
        description='When it happened, in UTC (e.g. "2026-11-03T01:00:00Z"). Defaults to now.',
    )
    quantity: float = Field(default=1, gt=0, description="How many (decimals allowed).")
    note: str | None = Field(default=None, max_length=500)
    attributes: dict[str, Any] = Field(
        default_factory=dict, description="Attributes of the category (see its schema)."
    )

    @field_validator("timestamp")
    @classmethod
    def _require_utc(cls, value: datetime | None) -> datetime | None:
        """UTC only: the user may be away from Québec, the time zone must not be guessed (D60)."""
        if value is not None and value.utcoffset() != timedelta(0):
            raise ValueError(
                "must be in UTC (e.g. 2026-11-03T01:00:00Z): "
                "convert from the user's current time zone"
            )
        return value


class InvalidEntriesError(ValueError):
    """Some entries of a batch are invalid: nothing was stored (D9)."""

    def __init__(self, errors: Sequence[str]) -> None:
        self.errors = list(errors)
        super().__init__("Nothing was stored. " + " | ".join(self.errors))


class CategoryInfo(BaseModel):
    name: str
    description: str
    attributes_schema: dict[str, Any] = Field(description="JSON Schema of the attributes.")


class EntryPage(BaseModel):
    start: date
    end: date
    entries: list[Entry]


class LifelogService:
    def __init__(
        self,
        repository: Repository,
        registry: CategoryRegistry,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repository = repository
        self._registry = registry
        self._now = now

    @property
    def registry(self) -> CategoryRegistry:
        return self._registry

    def list_categories(self) -> list[CategoryInfo]:
        return [
            CategoryInfo(
                name=category.name,
                description=category.description,
                attributes_schema=category.attributes_model.model_json_schema(),
            )
            for category in self._registry
        ]

    async def log_entries(
        self, category_name: str, items: Sequence[NewEntry | Mapping[str, Any]]
    ) -> list[Entry]:
        """Validate every item, then store them all or none (D9).

        Raises UnknownCategoryError or InvalidEntriesError (one message per invalid item).
        """
        category = self._registry.get(category_name)
        if not items:
            raise InvalidEntriesError(["at least one entry is required"])
        if len(items) > MAX_BATCH_SIZE:
            raise InvalidEntriesError([f"at most {MAX_BATCH_SIZE} entries at once"])

        now = self._now()
        entries: list[Entry] = []
        errors: list[str] = []
        for number, item in enumerate(items, start=1):
            try:
                new = item if isinstance(item, NewEntry) else NewEntry.model_validate(item)
                entries.append(
                    Entry(
                        category=category.name,
                        timestamp=new.timestamp or now,
                        quantity=new.quantity,
                        note=new.note,
                        attributes=category.validate_attributes(new.attributes),
                    )
                )
            except ValidationError as error:
                errors.append(f"entry {number}: {describe(error)}")
        if errors:
            raise InvalidEntriesError(errors)

        await self._repository.add_many(entries)
        return entries

    async def list_entries(
        self, category_name: str, start: date | None = None, end: date | None = None
    ) -> EntryPage:
        """Entries of a period (current week by default, D7), oldest first."""
        period, entries = await self._load(category_name, start, end)
        return EntryPage(start=period.start, end=period.end, entries=entries)

    async def get_stats(
        self, category_name: str, start: date | None = None, end: date | None = None
    ) -> BaseModel:
        """Category-specific statistics of a period (current week by default, D7)."""
        category = self._registry.get(category_name)
        period, entries = await self._load(category_name, start, end)
        return category.compute_stats(entries, period, local_today(self._now()))

    async def _load(
        self, category_name: str, start: date | None, end: date | None
    ) -> tuple[Period, list[Entry]]:
        category = self._registry.get(category_name)
        period = Period.resolve(start, end, local_today(self._now()))
        utc_start, utc_end = period.utc_bounds()
        return period, await self._repository.list(category.name, utc_start, utc_end)


def describe(error: ValidationError) -> str:
    """Pydantic errors as one readable line, e.g. "quantity: must be greater than 0"."""
    parts = []
    for item in error.errors():
        message = item["msg"].removeprefix("Value error, ")
        location = ".".join(str(part) for part in item["loc"])
        parts.append(f"{location}: {message}" if location else message)
    return "; ".join(parts)
