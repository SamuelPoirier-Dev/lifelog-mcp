"""Azure Table Storage, reached with Entra ID (managed identity): no account key.

One table, one partition per category (D56). The row key starts with the timestamp in a
fixed-length format, so a period is a row key range, returned in time order (D57). A
batch (one category, D9) is written in a single transaction.
"""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from azure.core.credentials_async import AsyncTokenCredential
from azure.data.tables import TableTransactionError
from azure.data.tables.aio import TableClient

from lifelog.entries import Entry
from lifelog.storage.base import check_batch
from lifelog.timeutils import to_utc

# Fixed length: row keys are compared as strings (D57).
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def format_timestamp(moment: datetime) -> str:
    return to_utc(moment).strftime(TIMESTAMP_FORMAT)


def row_key(entry: Entry) -> str:
    return f"{format_timestamp(entry.timestamp)}_{entry.id}"


def to_entity(entry: Entry) -> dict[str, Any]:
    entity: dict[str, Any] = {
        "PartitionKey": entry.category,
        "RowKey": row_key(entry),
        "id": str(entry.id),
        "quantity": float(entry.quantity),
        # Category-specific attributes vary: stored as JSON text, never filtered on.
        "attributes": json.dumps(entry.attributes, ensure_ascii=False),
    }
    if entry.note is not None:
        entity["note"] = entry.note
    return entity


def from_entity(entity: dict[str, Any]) -> Entry:
    timestamp = entity["RowKey"].split("_", 1)[0]
    return Entry(
        id=entity["id"],
        category=entity["PartitionKey"],
        timestamp=datetime.strptime(timestamp, TIMESTAMP_FORMAT).replace(tzinfo=UTC),
        quantity=entity["quantity"],
        note=entity.get("note"),
        attributes=json.loads(entity["attributes"]),
    )


class TableRepository:
    """Owns its client and credential: call `close()` on shutdown."""

    def __init__(self, account: str, table: str, credential: AsyncTokenCredential) -> None:
        self._credential = credential
        self._client = TableClient(
            endpoint=f"https://{account}.table.core.windows.net",
            table_name=table,
            credential=credential,
        )

    async def close(self) -> None:
        await self._client.close()
        await self._credential.close()

    async def add_many(self, entries: Sequence[Entry]) -> None:
        if check_batch(entries) is None:
            return
        operations = [("create", to_entity(entry)) for entry in entries]
        try:
            await self._client.submit_transaction(operations)
        except TableTransactionError as error:
            raise ValueError(f"The entries could not be stored: {error.message}") from error

    async def list(self, category: str, start: datetime, end: datetime) -> list[Entry]:
        # "<start>" <= "<start>_<id>" and "<end>_<id>" > "<end>": start included, end excluded.
        entities = self._client.query_entities(
            query_filter="PartitionKey eq @category and RowKey ge @start and RowKey lt @end",
            parameters={
                "category": category,
                "start": format_timestamp(start),
                "end": format_timestamp(end),
            },
        )
        return [from_entity(entity) async for entity in entities]
