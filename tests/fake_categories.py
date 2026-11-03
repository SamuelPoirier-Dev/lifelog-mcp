"""A fictional category, defined only in the tests: adding it must not change anything else."""

from collections.abc import Sequence
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from lifelog.categories import Category
from lifelog.entries import Entry
from lifelog.timeutils import Period


class WaterAttributes(BaseModel):
    model_config = ConfigDict(extra="forbid")
    container: Literal["glass", "bottle"] = "glass"


class WaterStats(BaseModel):
    entries: int
    glasses: float


class WaterCategory(Category[WaterAttributes, WaterStats]):
    name = "water"
    description = 'Water drunk. Example: "2 verres d\'eau".'
    attributes_model = WaterAttributes

    def compute_stats(self, entries: Sequence[Entry], period: Period, today: date) -> WaterStats:
        in_period = [entry for entry in entries if period.contains(entry.timestamp)]
        return WaterStats(entries=len(in_period), glasses=sum(e.quantity for e in in_period))
