"""Drinks category: alcoholic drinks, counted in Canadian standard drinks.

A Canadian standard drink holds 13.45 g of pure alcohol (ethanol density 0.789 g/ml):
    standard drinks = volume (ml) x ABV / 100 x 0.789 / 13.45, per container (D4).
The entry quantity is the number of containers (D3).
"""

from collections.abc import Sequence
from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lifelog.categories.base import Category
from lifelog.entries import Entry
from lifelog.timeutils import (
    Period,
    counted_days,
    days_without_entry,
    iso_week_label,
    local_date,
    week_start,
)

STANDARD_DRINK_GRAMS = 13.45
ETHANOL_GRAMS_PER_ML = 0.789


class DrinkType(StrEnum):
    BEER = "beer"
    CIDER = "cider"
    WINE = "wine"
    SPIRITS = "spirits"
    OTHER = "other"


# Default (volume in ml, ABV in %) per type; None = must be given (D4, D39).
# Beer and "other" vary too much to guess; a cider's volume too (355, 473, 500 ml...).
DEFAULTS: dict[DrinkType, tuple[float | None, float | None]] = {
    DrinkType.BEER: (None, None),
    DrinkType.CIDER: (None, 5.0),
    DrinkType.WINE: (142.0, 12.0),
    DrinkType.SPIRITS: (43.0, 40.0),
    DrinkType.OTHER: (None, None),
}


class DrinkAttributes(BaseModel):
    """Attributes of a drink entry, for one container."""

    model_config = ConfigDict(extra="forbid")

    type: DrinkType = Field(
        description="beer (bière), cider (cidre), wine (vin), spirits (spiritueux, shooter), "
        "other (anything else: cocktail, sake...)."
    )
    volume_ml: float | None = Field(
        default=None,
        ge=1,
        le=5000,
        description="Volume of one container in ml. Required for beer, cider and other; "
        "defaults: wine 142, spirits 43.",
    )
    abv_percent: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Alcohol by volume in %. Required for beer and other; "
        "defaults: cider 5, wine 12, spirits 40.",
    )

    @model_validator(mode="after")
    def _apply_defaults(self) -> "DrinkAttributes":
        default_volume, default_abv = DEFAULTS[self.type]
        if self.volume_ml is None:
            self.volume_ml = default_volume
        if self.abv_percent is None:
            self.abv_percent = default_abv
        missing = [
            name
            for name, value in (("volume_ml", self.volume_ml), ("abv_percent", self.abv_percent))
            if value is None
        ]
        if missing:
            raise ValueError(
                f"{' and '.join(missing)} required for type '{self.type}': "
                "ask the user, do not guess."
            )
        return self

    @property
    def standard_drinks_per_container(self) -> float:
        """Standard drinks in one container."""
        assert self.volume_ml is not None and self.abv_percent is not None
        return standard_drinks(self.volume_ml, self.abv_percent)


def standard_drinks(volume_ml: float, abv_percent: float) -> float:
    """Canadian standard drinks in a volume of a drink."""
    return volume_ml * abv_percent / 100 * ETHANOL_GRAMS_PER_ML / STANDARD_DRINK_GRAMS


class WeekStats(BaseModel):
    week: str = Field(description='ISO week, e.g. "2026-W45".')
    start: date = Field(description="Monday of the week.")
    standard_drinks: float


class DrinkStats(BaseModel):
    start: date
    end: date
    entries: int
    standard_drinks: float = Field(description="Total over the period.")
    weeks: list[WeekStats] = Field(description="Every ISO week of the period, even empty.")
    days_counted: int = Field(description="Days of the period up to today.")
    days_without_entry: int = Field(description="Days counted with no drink at all.")


class DrinksCategory(Category[DrinkAttributes, DrinkStats]):
    name = "drinks"
    description = (
        "Alcoholic drinks. One entry per kind of drink, quantity = number of containers "
        "(bottles, cans, glasses, shots). Stats are in Canadian standard drinks. "
        'Examples: "2 bières ce soir", "un verre de vin", "un shooter de vodka", '
        '"une canette de cidre de 473 ml", "une IPA 473 ml 6,5 %".'
    )
    attributes_model = DrinkAttributes

    def entry_standard_drinks(self, entry: Entry) -> float:
        """Standard drinks of an entry: per container x quantity."""
        return self.parse_attributes(entry).standard_drinks_per_container * entry.quantity

    def compute_stats(self, entries: Sequence[Entry], period: Period, today: date) -> DrinkStats:
        in_period = [entry for entry in entries if period.contains(entry.timestamp)]

        per_week = dict.fromkeys(period.week_starts(), 0.0)
        for entry in in_period:
            per_week[week_start(local_date(entry.timestamp))] += self.entry_standard_drinks(entry)

        entry_days = {local_date(entry.timestamp) for entry in in_period}
        return DrinkStats(
            start=period.start,
            end=period.end,
            entries=len(in_period),
            standard_drinks=round(sum(per_week.values()), 1),
            weeks=[
                WeekStats(
                    week=iso_week_label(monday), start=monday, standard_drinks=round(total, 1)
                )
                for monday, total in per_week.items()
            ],
            days_counted=len(counted_days(period, today)),
            days_without_entry=days_without_entry(period, entry_days, today),
        )
