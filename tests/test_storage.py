"""Storage contract, run against every backend.

The in-memory backend always runs. Azure Table Storage runs only on request (D52),
against the real table, with the Azure CLI login:

    LIFELOG_TEST_TABLE_ACCOUNT=$(terraform -chdir=infra output -raw data_storage_account) \\
        uv run pytest -m azure

Each test writes to its own category (partition) and deletes it afterwards.
"""

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from lifelog.entries import Entry
from lifelog.storage import MAX_BATCH_SIZE, MemoryRepository, Repository

TABLE_ACCOUNT = os.environ.get("LIFELOG_TEST_TABLE_ACCOUNT")

T0 = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


@pytest.fixture
def category() -> str:
    # Unique per test: isolates tests from each other and from real data.
    return f"test_{uuid4().hex[:12]}"


@pytest.fixture(
    params=[
        "memory",
        pytest.param("table", marks=pytest.mark.azure),
    ]
)
async def repository(request: pytest.FixtureRequest, category: str) -> AsyncIterator[Repository]:
    if request.param == "memory":
        yield MemoryRepository()
        return

    if not TABLE_ACCOUNT:
        pytest.skip("LIFELOG_TEST_TABLE_ACCOUNT is not set")
    from azure.identity.aio import DefaultAzureCredential

    from lifelog.storage.table import TableRepository

    table = TableRepository(TABLE_ACCOUNT, "entries", credential=DefaultAzureCredential())
    try:
        yield table
    finally:
        # Delete everything the test wrote in its own partition.
        client = table._client
        async for entity in client.query_entities(
            "PartitionKey eq @c", parameters={"c": category}, select=["PartitionKey", "RowKey"]
        ):
            await client.delete_entity(entity["PartitionKey"], entity["RowKey"])
        await table.close()


def entry(category: str, minutes: int = 0, **fields) -> Entry:
    return Entry(category=category, timestamp=T0 + timedelta(minutes=minutes), **fields)


async def test_entries_are_listed_oldest_first(repository: Repository, category: str):
    later, earlier = entry(category, 30), entry(category, 10)
    await repository.add_many([later, earlier])

    found = await repository.list(category, T0, T0 + timedelta(hours=1))

    assert [e.id for e in found] == [earlier.id, later.id]


async def test_all_fields_survive_a_round_trip(repository: Repository, category: str):
    original = Entry(
        category=category,
        timestamp=datetime(2026, 11, 3, 12, 0, 0, 123456, tzinfo=UTC),
        quantity=2.5,
        note="après le souper",
        attributes={"type": "cider", "volume_ml": 473.0, "abv_percent": 5.0},
    )
    await repository.add_many([original])

    [found] = await repository.list(category, T0, T0 + timedelta(minutes=1))

    assert found == original


async def test_start_is_included_and_end_excluded(repository: Repository, category: str):
    at_start, at_end = entry(category, 0), entry(category, 60)
    await repository.add_many([at_start, at_end])

    found = await repository.list(category, T0, T0 + timedelta(minutes=60))

    assert [e.id for e in found] == [at_start.id]


async def test_entries_in_the_same_second_keep_their_order(repository: Repository, category: str):
    first = Entry(category=category, timestamp=T0 + timedelta(microseconds=900_000))
    second = Entry(category=category, timestamp=T0 + timedelta(seconds=1))
    await repository.add_many([second, first])

    found = await repository.list(category, T0, T0 + timedelta(minutes=1))

    assert [e.id for e in found] == [first.id, second.id]


async def test_other_categories_are_not_listed(repository: Repository, category: str):
    await repository.add_many([entry(category)])

    assert await repository.list(f"{category}_other", T0, T0 + timedelta(hours=1)) == []


async def test_a_batch_is_all_or_nothing(repository: Repository, category: str):
    existing = entry(category, 0)
    await repository.add_many([existing])

    # The second entry reuses an existing id: the whole batch must be refused.
    batch = [entry(category, 10), existing.model_copy(update={"note": "duplicate"})]
    with pytest.raises(ValueError):
        await repository.add_many(batch)

    found = await repository.list(category, T0, T0 + timedelta(hours=1))
    assert [e.id for e in found] == [existing.id]


async def test_a_batch_cannot_mix_categories(repository: Repository, category: str):
    with pytest.raises(ValueError, match="same category"):
        await repository.add_many([entry(category), entry(f"{category}_other")])

    assert await repository.list(category, T0, T0 + timedelta(hours=1)) == []


async def test_a_batch_is_limited_in_size(repository: Repository, category: str):
    with pytest.raises(ValueError, match=f"At most {MAX_BATCH_SIZE}"):
        await repository.add_many([entry(category) for _ in range(MAX_BATCH_SIZE + 1)])


async def test_an_empty_batch_does_nothing(repository: Repository, category: str):
    await repository.add_many([])

    assert await repository.list(category, T0, T0 + timedelta(hours=1)) == []


def test_row_keys_sort_in_time_order():
    from lifelog.storage.table import format_timestamp, row_key

    assert format_timestamp(T0) == "2026-11-03T12:00:00.000000Z"
    assert format_timestamp(T0 + timedelta(microseconds=5)) == "2026-11-03T12:00:00.000005Z"
    early = Entry(category="drinks", timestamp=T0 + timedelta(microseconds=900_000))
    late = Entry(category="drinks", timestamp=T0 + timedelta(seconds=1))
    assert row_key(early) < row_key(late)


def test_table_entity_round_trip():
    from lifelog.storage.table import from_entity, to_entity

    original = Entry(
        category="drinks",
        timestamp=T0,
        quantity=2,
        note="après le souper",
        attributes={"type": "cider", "volume_ml": 473.0, "abv_percent": 5.0},
    )

    assert from_entity(to_entity(original)) == original
