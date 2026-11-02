"""Drinks category: validation, defaults, standard drinks and statistics."""

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from lifelog.categories.drinks import DrinksCategory, standard_drinks
from lifelog.entries import Entry
from lifelog.timeutils import Period

drinks = DrinksCategory()


def drink(when: datetime, quantity: float = 1, **attributes) -> Entry:
    return Entry(
        category="drinks",
        timestamp=when,
        quantity=quantity,
        attributes=drinks.validate_attributes(attributes),
    )


class TestStandardDrinks:
    @pytest.mark.parametrize(
        ("volume_ml", "abv_percent"),
        [(341, 5), (142, 12), (43, 40)],  # the reference beer, glass of wine and shot
    )
    def test_reference_containers_are_one_standard_drink(self, volume_ml, abv_percent):
        assert standard_drinks(volume_ml, abv_percent) == pytest.approx(1, abs=0.01)

    def test_quantity_multiplies_the_containers(self):
        entry = drink(
            datetime(2026, 11, 3, 20), quantity=2, type="beer", volume_ml=473, abv_percent=5
        )
        assert drinks.entry_standard_drinks(entry) == pytest.approx(2.77, abs=0.01)

    def test_alcohol_free_beer_is_zero(self):
        entry = drink(datetime(2026, 11, 3, 20), type="beer", volume_ml=355, abv_percent=0)
        assert drinks.entry_standard_drinks(entry) == 0


class TestValidation:
    def test_wine_defaults_are_stored(self):
        assert drinks.validate_attributes({"type": "wine"}) == {
            "type": "wine",
            "volume_ml": 142.0,
            "abv_percent": 12.0,
        }

    def test_spirits_defaults(self):
        attributes = drinks.validate_attributes({"type": "spirits"})
        assert (attributes["volume_ml"], attributes["abv_percent"]) == (43.0, 40.0)

    def test_a_default_can_be_overridden(self):
        attributes = drinks.validate_attributes({"type": "wine", "abv_percent": 13.5})
        assert (attributes["volume_ml"], attributes["abv_percent"]) == (142.0, 13.5)

    def test_cider_defaults_to_five_percent(self):
        attributes = drinks.validate_attributes({"type": "cider", "volume_ml": 473})
        assert attributes["abv_percent"] == 5.0

    def test_cider_needs_a_volume(self):
        with pytest.raises(ValidationError, match="volume_ml required for type 'cider'"):
            drinks.validate_attributes({"type": "cider"})

    def test_beer_needs_its_abv(self):
        with pytest.raises(ValidationError, match="abv_percent required for type 'beer'"):
            drinks.validate_attributes({"type": "beer", "volume_ml": 473})

    def test_other_needs_volume_and_abv(self):
        with pytest.raises(ValidationError, match="volume_ml and abv_percent required"):
            drinks.validate_attributes({"type": "other"})

    @pytest.mark.parametrize(
        "attributes",
        [
            {"type": "beer", "volume_ml": 0, "abv_percent": 5},
            {"type": "beer", "volume_ml": 6000, "abv_percent": 5},
            {"type": "beer", "volume_ml": 473, "abv_percent": 101},
            {"type": "beer", "volume_ml": 473, "abv_percent": -1},
            {"type": "bière", "volume_ml": 473, "abv_percent": 5},
            {"type": "wine", "brand": "x"},  # unknown fields are refused (D46)
        ],
    )
    def test_invalid_attributes_are_refused(self, attributes):
        with pytest.raises(ValidationError):
            drinks.validate_attributes(attributes)


class TestStats:
    today = date(2026, 11, 5)  # a Thursday

    def test_stats_over_a_period_starting_mid_week(self):
        period = Period(date(2026, 10, 28), date(2026, 11, 8))  # Wednesday to Sunday
        entries = [
            # Before the period: ignored.
            drink(datetime(2026, 10, 25, 21), type="wine"),
            # Wednesday Oct 28: two reference beers.
            drink(
                datetime(2026, 10, 28, 20), quantity=2, type="beer", volume_ml=341, abv_percent=5
            ),
            # 00:30 on Tuesday Nov 3: counts for Nov 3, in the next week.
            drink(datetime(2026, 11, 3, 0, 30), type="wine"),
        ]

        stats = drinks.compute_stats(entries, period, self.today)

        assert stats.entries == 2
        assert stats.standard_drinks == 3.0
        assert [(week.week, week.start, week.standard_drinks) for week in stats.weeks] == [
            ("2026-W44", date(2026, 10, 26), 2.0),
            ("2026-W45", date(2026, 11, 2), 1.0),
        ]
        # Oct 28 to Nov 5 (today): 9 days, 2 with an entry.
        assert (stats.days_counted, stats.days_without_entry) == (9, 7)

    def test_empty_weeks_are_listed(self):
        period = Period(date(2026, 11, 2), date(2026, 11, 15))
        entries = [drink(datetime(2026, 11, 3, 20), type="wine")]

        stats = drinks.compute_stats(entries, period, today=date(2026, 11, 20))

        assert [(week.week, week.standard_drinks) for week in stats.weeks] == [
            ("2026-W45", 1.0),
            ("2026-W46", 0.0),
        ]
        assert stats.days_without_entry == 13

    def test_no_entries(self):
        stats = drinks.compute_stats([], Period.week_of(self.today), self.today)

        assert (stats.entries, stats.standard_drinks) == (0, 0.0)
        assert stats.days_without_entry == 4  # Monday to Thursday

    def test_totals_are_rounded_to_one_decimal(self):
        entries = [drink(datetime(2026, 11, 3, 20), type="spirits")]  # 1.009 standard drink
        stats = drinks.compute_stats(entries, Period.week_of(self.today), self.today)
        assert stats.standard_drinks == 1.0
