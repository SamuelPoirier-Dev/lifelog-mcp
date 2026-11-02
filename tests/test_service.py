"""Service layer on the in-memory storage, with a fixed clock."""

from datetime import UTC, date, datetime

import pytest

from lifelog.categories import UnknownCategoryError, default_registry
from lifelog.service import InvalidEntriesError, LifelogService
from lifelog.storage import MAX_BATCH_SIZE, MemoryRepository

# Thursday, November 5th 2026, 10:00 in Québec.
NOW = datetime(2026, 11, 5, 15, 0, tzinfo=UTC)


@pytest.fixture
def service() -> LifelogService:
    return LifelogService(MemoryRepository(), default_registry(), now=lambda: NOW)


async def test_two_beers_tonight_then_the_weekly_total(service: LifelogService):
    beer = {"type": "beer", "volume_ml": 341, "abv_percent": 5}
    await service.log_entries(
        "drinks", [{"quantity": 2, "timestamp": "2026-11-05T20:00", "attributes": beer}]
    )

    stats = await service.get_stats("drinks")

    assert (stats.start, stats.end) == (date(2026, 11, 2), date(2026, 11, 8))
    assert stats.standard_drinks == 2.0


async def test_timestamp_defaults_to_now(service: LifelogService):
    [entry] = await service.log_entries("drinks", [{"attributes": {"type": "wine"}}])

    assert entry.timestamp == NOW
    assert entry.quantity == 1


async def test_timestamp_without_time_zone_is_quebec_time(service: LifelogService):
    [entry] = await service.log_entries(
        "drinks", [{"timestamp": "2026-11-04T21:30", "attributes": {"type": "wine"}}]
    )

    assert entry.timestamp == datetime(2026, 11, 5, 2, 30, tzinfo=UTC)


async def test_defaults_of_the_category_are_stored(service: LifelogService):
    [entry] = await service.log_entries("drinks", [{"attributes": {"type": "spirits"}}])

    assert entry.attributes == {"type": "spirits", "volume_ml": 43.0, "abv_percent": 40.0}


async def test_one_invalid_entry_stores_nothing(service: LifelogService):
    items = [
        {"attributes": {"type": "wine"}},
        {"attributes": {"type": "beer", "volume_ml": 473}},  # no ABV
        {"quantity": 0, "attributes": {"type": "wine"}},
    ]

    with pytest.raises(InvalidEntriesError) as error:
        await service.log_entries("drinks", items)

    assert len(error.value.errors) == 2
    assert error.value.errors[0].startswith("entry 2: abv_percent required for type 'beer'")
    assert error.value.errors[1].startswith("entry 3: quantity:")
    assert (await service.list_entries("drinks")).entries == []


async def test_unknown_fields_are_refused(service: LifelogService):
    with pytest.raises(InvalidEntriesError, match="entry 1: colour"):
        await service.log_entries("drinks", [{"colour": "red", "attributes": {"type": "wine"}}])


async def test_unknown_category(service: LifelogService):
    with pytest.raises(UnknownCategoryError, match="Available categories: drinks"):
        await service.log_entries("sleep", [{}])


@pytest.mark.parametrize("count", [0, MAX_BATCH_SIZE + 1])
async def test_batch_size_is_checked(service: LifelogService, count: int):
    with pytest.raises(InvalidEntriesError):
        await service.log_entries("drinks", [{"attributes": {"type": "wine"}}] * count)


async def test_list_entries_defaults_to_the_current_week(service: LifelogService):
    wine = {"type": "wine"}
    await service.log_entries(
        "drinks",
        [
            {"timestamp": "2026-11-01T20:00", "attributes": wine},  # previous Sunday
            {"timestamp": "2026-11-03T20:00", "attributes": wine},
            {"timestamp": "2026-11-02T00:30", "attributes": wine},  # Monday 00:30
        ],
    )

    page = await service.list_entries("drinks")

    assert (page.start, page.end) == (date(2026, 11, 2), date(2026, 11, 8))
    assert [entry.timestamp.isoformat() for entry in page.entries] == [
        "2026-11-02T05:30:00+00:00",
        "2026-11-04T01:00:00+00:00",
    ]


async def test_list_entries_of_a_given_period(service: LifelogService):
    await service.log_entries(
        "drinks", [{"timestamp": "2026-10-15T20:00", "attributes": {"type": "wine"}}]
    )

    page = await service.list_entries("drinks", start=date(2026, 10, 1), end=date(2026, 10, 31))

    assert len(page.entries) == 1


async def test_end_without_start_is_refused(service: LifelogService):
    with pytest.raises(ValueError, match="needs a start"):
        await service.get_stats("drinks", end=date(2026, 10, 31))


def test_list_categories_describes_the_attributes(service: LifelogService):
    [drinks] = service.list_categories()

    assert drinks.name == "drinks"
    assert "bières" in drinks.description
    assert set(drinks.attributes_schema["properties"]) == {"type", "volume_ml", "abv_percent"}
