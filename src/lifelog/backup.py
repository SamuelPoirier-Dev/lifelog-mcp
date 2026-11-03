"""Backup of the entries table to JSON lines, and restore (D58, D72).

Entities are copied as stored (raw Table Storage properties, one JSON object per line):
the restore writes them back unchanged, whatever the category. Uses the Azure CLI login
(or any credential DefaultAzureCredential finds):

    uv run python -m lifelog.backup export --account <account> --output entries.jsonl
    uv run python -m lifelog.backup restore --account <account> --input entries.jsonl

A restore replaces the entries of the file and leaves the other entries untouched.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Iterable
from typing import TextIO

from azure.data.tables import UpdateMode
from azure.data.tables.aio import TableClient


async def export_entities(client: TableClient, output: TextIO) -> int:
    """Write every entity of the table to `output`; returns how many."""
    count = 0
    async for entity in client.list_entities():
        output.write(json.dumps(dict(entity), ensure_ascii=False, sort_keys=True) + "\n")
        count += 1
    return count


async def restore_entities(client: TableClient, lines: Iterable[str]) -> int:
    """Write back the entities of an export (insert or replace); returns how many."""
    count = 0
    for line in lines:
        if not line.strip():
            continue
        await client.upsert_entity(json.loads(line), mode=UpdateMode.REPLACE)
        count += 1
    return count


async def _run(command: str, account: str, table: str, file: TextIO) -> int:
    # Imported here: not needed by the functions above (tests).
    from azure.identity.aio import DefaultAzureCredential

    async with (
        DefaultAzureCredential() as credential,
        TableClient(
            endpoint=f"https://{account}.table.core.windows.net",
            table_name=table,
            credential=credential,
        ) as client,
    ):
        if command == "export":
            return await export_entities(client, file)
        return await restore_entities(client, file)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m lifelog.backup", description=__doc__)
    parser.add_argument("command", choices=["export", "restore"])
    parser.add_argument("--account", required=True, help="storage account of the table")
    parser.add_argument("--table", default="entries")
    parser.add_argument("--output", help="export: file to write")
    parser.add_argument("--input", help="restore: file to read")
    args = parser.parse_args(argv)
    if args.command == "export" and not args.output:
        parser.error("export needs --output")
    if args.command == "restore" and not args.input:
        parser.error("restore needs --input")

    exporting = args.command == "export"
    path, mode = (args.output, "w") if exporting else (args.input, "r")
    with open(path, mode, encoding="utf-8") as file:
        count = asyncio.run(_run(args.command, args.account, args.table, file))
    verb = "Exported" if exporting else "Restored"
    # The count only: never the content of the entries (D71).
    print(f"{verb} {count} entities", file=sys.stderr)


if __name__ == "__main__":
    main()
