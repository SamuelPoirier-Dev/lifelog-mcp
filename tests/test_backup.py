"""Backup export and restore (D72).

The round trip runs against a fake table client. Against the real table, on request
(D52): see tests/test_storage.py.
"""

import io
import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from lifelog.backup import export_entities, restore_entities
from lifelog.entries import Entry
from lifelog.storage.table import to_entity

T0 = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


class FakeTableClient:
    """The two TableClient methods the backup uses, entities kept by key."""

    def __init__(self, entities: list[dict[str, Any]] | None = None) -> None:
        self.entities = {(e["PartitionKey"], e["RowKey"]): dict(e) for e in entities or []}

    async def list_entities(self):
        for entity in self.entities.values():
            yield dict(entity)

    async def upsert_entity(self, entity: dict[str, Any], *, mode: Any) -> None:
        self.entities[(entity["PartitionKey"], entity["RowKey"])] = dict(entity)


# Built once: each Entry gets a new id.
ENTITIES: list[dict[str, Any]] = [
    to_entity(
        Entry(
            category="drinks",
            timestamp=T0,
            quantity=2,
            note="Souper chez Marc — ½ verre",
            attributes={"type": "beer", "volume_ml": 355, "abv": 5.0},
        )
    ),
    to_entity(Entry(category="drinks", timestamp=T0 + timedelta(hours=1), quantity=0.5)),
]


async def test_export_writes_one_json_object_per_entity():
    output = io.StringIO()

    count = await export_entities(FakeTableClient(ENTITIES), output)

    lines = output.getvalue().splitlines()
    assert count == len(lines) == 2
    assert [json.loads(line) for line in lines] == ENTITIES


async def test_restore_writes_back_exactly_what_was_exported():
    output = io.StringIO()
    await export_entities(FakeTableClient(ENTITIES), output)
    target = FakeTableClient()

    count = await restore_entities(target, io.StringIO(output.getvalue()))

    assert count == 2
    assert list(target.entities.values()) == ENTITIES
    # Types survive the trip: a float stays a float (Edm.Double in Table Storage).
    assert all(isinstance(e["quantity"], float) for e in target.entities.values())


async def test_restore_twice_changes_nothing_and_skips_blank_lines():
    output = io.StringIO()
    await export_entities(FakeTableClient(ENTITIES), output)
    target = FakeTableClient()
    lines = output.getvalue() + "\n\n"

    await restore_entities(target, io.StringIO(lines))
    count = await restore_entities(target, io.StringIO(lines))

    assert count == 2
    assert list(target.entities.values()) == ENTITIES


@pytest.mark.azure
async def test_round_trip_on_the_real_table():
    account = os.environ.get("LIFELOG_TEST_TABLE_ACCOUNT")
    if not account:
        pytest.skip("LIFELOG_TEST_TABLE_ACCOUNT is not set")
    from azure.data.tables.aio import TableClient
    from azure.identity.aio import DefaultAzureCredential

    category = f"test_{uuid4().hex[:12]}"
    written = [
        to_entity(Entry(category=category, timestamp=T0, quantity=1, note="é")),
        to_entity(Entry(category=category, timestamp=T0, quantity=2.5)),
    ]
    async with (
        DefaultAzureCredential() as credential,
        TableClient(
            endpoint=f"https://{account}.table.core.windows.net",
            table_name="entries",
            credential=credential,
        ) as client,
    ):
        try:
            for entity in written:
                await client.create_entity(entity)
            output = io.StringIO()
            await export_entities(client, output)
            exported = [
                line
                for line in output.getvalue().splitlines()
                if json.loads(line)["PartitionKey"] == category
            ]
            for entity in written:
                await client.delete_entity(entity["PartitionKey"], entity["RowKey"])

            await restore_entities(client, exported)

            restored = [
                dict(e)
                async for e in client.query_entities(
                    "PartitionKey eq @c", parameters={"c": category}
                )
            ]
            key = lambda e: e["RowKey"]  # noqa: E731
            assert sorted(restored, key=key) == sorted(written, key=key)
        finally:
            async for entity in client.query_entities(
                "PartitionKey eq @c", parameters={"c": category}, select=["PartitionKey", "RowKey"]
            ):
                await client.delete_entity(entity["PartitionKey"], entity["RowKey"])
