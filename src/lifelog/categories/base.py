"""What a category must provide: its attributes, their validation and its statistics."""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, ClassVar

from pydantic import BaseModel

from lifelog.entries import Entry
from lifelog.timeutils import Period


class Category[AttributesT: BaseModel, StatsT: BaseModel](ABC):
    """A kind of entry (drinks, ...). One category = one module.

    Subclasses set the class attributes and implement `compute_stats`.
    """

    # Identifier used by the tools and the API, e.g. "drinks".
    name: ClassVar[str]
    # Shown to Claude: what the category records, with French examples (D11).
    description: ClassVar[str]
    # Validates the category-specific attributes of an entry.
    attributes_model: ClassVar[type[BaseModel]]

    def validate_attributes(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        """Validate raw attributes and return them as stored (defaults applied, D40).

        Raises pydantic.ValidationError with a message meant to be shown to Claude.
        """
        return self.attributes_model.model_validate(dict(raw)).model_dump(mode="json")

    def parse_attributes(self, entry: Entry) -> AttributesT:
        """Typed attributes of a stored entry of this category."""
        return self.attributes_model.model_validate(entry.attributes)  # type: ignore[return-value]

    @abstractmethod
    def compute_stats(self, entries: Sequence[Entry], period: Period, today: date) -> StatsT:
        """Statistics over the entries of the period; entries outside it are ignored."""
