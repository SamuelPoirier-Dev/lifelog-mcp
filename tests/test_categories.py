"""Generic model and registry: a new category plugs in without touching the others."""

from collections.abc import Sequence
from datetime import date, datetime
from typing import Literal

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from lifelog.categories import Category, CategoryRegistry, UnknownCategoryError, default_registry
from lifelog.categories.drinks import DrinksCategory
from lifelog.entries import Entry
from lifelog.timeutils import Period

# --- A fictional category, defined only here --------------------------------------------


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


# --- Tests ---------------------------------------------------------------------------------


@pytest.fixture
def registry() -> CategoryRegistry:
    return CategoryRegistry([DrinksCategory(), WaterCategory()])


def test_a_new_category_works_next_to_drinks(registry: CategoryRegistry):
    water = registry.get("water")
    attributes = water.validate_attributes({})
    entry = Entry(
        category="water", timestamp=datetime(2026, 11, 3, 9), quantity=2, attributes=attributes
    )

    stats = water.compute_stats([entry], Period.week_of(date(2026, 11, 3)), date(2026, 11, 3))

    assert attributes == {"container": "glass"}
    assert stats == WaterStats(entries=1, glasses=2)
    assert registry.get("drinks").validate_attributes({"type": "wine"})["volume_ml"] == 142.0


def test_the_new_category_validates_its_own_attributes(registry: CategoryRegistry):
    with pytest.raises(ValidationError):
        registry.get("water").validate_attributes({"container": "bucket"})


def test_registry_lists_categories_in_order(registry: CategoryRegistry):
    assert [category.name for category in registry] == ["drinks", "water"]


def test_unknown_category_lists_the_available_ones(registry: CategoryRegistry):
    with pytest.raises(UnknownCategoryError, match="Available categories: drinks, water"):
        registry.get("sleep")


def test_a_category_cannot_be_registered_twice(registry: CategoryRegistry):
    with pytest.raises(ValueError, match="already registered"):
        registry.register(WaterCategory())


def test_default_registry_is_not_affected_by_tests():
    assert [category.name for category in default_registry()] == ["drinks"]


class TestEntry:
    def test_naive_timestamp_is_stored_in_utc(self):
        entry = Entry(category="drinks", timestamp=datetime(2026, 11, 3, 20, 0))
        assert entry.timestamp.isoformat() == "2026-11-04T01:00:00+00:00"

    def test_quantity_defaults_to_one(self):
        assert Entry(category="drinks", timestamp=datetime(2026, 11, 3)).quantity == 1

    @pytest.mark.parametrize("quantity", [0, -1])
    def test_quantity_must_be_positive(self, quantity: float):
        with pytest.raises(ValidationError):
            Entry(category="drinks", timestamp=datetime(2026, 11, 3), quantity=quantity)

    def test_half_a_glass_is_allowed(self):
        assert (
            Entry(category="drinks", timestamp=datetime(2026, 11, 3), quantity=0.5).quantity == 0.5
        )
