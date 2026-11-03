"""MCP server definition: the tools exposed to MCP clients such as claude.ai.

The tools are thin wrappers around LifelogService; the business rules live there.
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from typing import Annotated, Any, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth import AuthProvider
from pydantic import Field

from lifelog.categories import CategoryRegistry, UnknownCategoryError
from lifelog.entries import Entry
from lifelog.service import CategoryInfo, EntryPage, LifelogService, NewEntry
from lifelog.storage import MAX_BATCH_SIZE

SERVER_INSTRUCTIONS = """\
Personal lifelog: record and query everyday entries (habits, health...) grouped by category.
The user speaks French and may be anywhere in the world.

- Pick the category from the user's words; call list_categories when unsure.
- Timestamps sent to log_entry must be in UTC (ending with "Z"): convert from the user's
  current time zone. Omit the timestamp for something happening now. Past dates are fine
  ("hier soir", entries imported from another app).
- Timestamps returned by the tools are in UTC: convert them to the user's time zone.
- Days and weeks (stats, start/end dates) are calendar days and ISO weeks (Monday to
  Sunday) in Québec time. Convert "cette semaine", "ce mois-ci"... into start/end dates.
- Attributes: send only the values the user stated for this entry. Do not reuse values
  from earlier entries unless the user asks for it ("la même", "pareil"), and never guess
  (volume, ABV...): leave a value out and the tool will say what to ask the user.
- Entries cannot be edited or deleted: confirm the values with the user before logging
  when in doubt. Never offer to correct an entry: say it cannot be done from here.
"""


def create_mcp_server(service: LifelogService, auth: AuthProvider | None = None) -> FastMCP:
    """Build the FastMCP server and register its tools."""
    # Unexpected errors reach the client as a generic message; details stay in the logs.
    mcp = FastMCP(
        name="lifelog", instructions=SERVER_INSTRUCTIONS, auth=auth, mask_error_details=True
    )
    registry = service.registry

    # The category names, listed in the tool schemas (D59).
    CategoryName = Annotated[
        Literal[tuple(category.name for category in registry)],  # type: ignore[valid-type]
        Field(description="Category of the entries."),
    ]
    Start = Annotated[
        date | None,
        Field(description="First day (Québec time), included. Defaults to this week's Monday."),
    ]
    End = Annotated[
        date | None,
        Field(description="Last day (Québec time), included. Defaults to today if start is set."),
    ]

    @mcp.tool(annotations={"readOnlyHint": True})
    def list_categories() -> list[CategoryInfo]:
        """List the categories, what they are for and the attributes their entries take."""
        return service.list_categories()

    @mcp.tool(
        description=_log_entry_description(registry),
        annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False},
    )
    async def log_entry(
        category: CategoryName,
        entries: Annotated[list[NewEntry], Field(min_length=1, max_length=MAX_BATCH_SIZE)],
    ) -> list[Entry]:
        with _expected_errors():
            return await service.log_entries(category, entries)

    @mcp.tool(annotations={"readOnlyHint": True})
    async def list_entries(
        category: CategoryName, start: Start = None, end: End = None
    ) -> EntryPage:
        """List the entries of a category over a period, oldest first.

        Without dates: the current week. Example: "qu'est-ce que j'ai noté hier ?".
        """
        with _expected_errors():
            return await service.list_entries(category, start, end)

    @mcp.tool(annotations={"readOnlyHint": True})
    async def get_stats(
        category: CategoryName, start: Start = None, end: End = None
    ) -> dict[str, Any]:
        """Statistics of a category over a period (totals, per ISO week...).

        Without dates: the current week. Examples: "combien de verres cette semaine ?",
        "mon total du mois d'octobre".
        """
        with _expected_errors():
            stats = await service.get_stats(category, start, end)
        return stats.model_dump(mode="json")

    return mcp


def _log_entry_description(registry: CategoryRegistry) -> str:
    """log_entry's description, with each category and its attributes schema."""
    categories = "\n".join(
        f"- {category.name}: {category.description}\n"
        f"  attributes schema: {json.dumps(category.attributes_model.model_json_schema())}"
        for category in registry
    )
    return f"""\
Record one or more entries in a category, all or nothing: if one entry is invalid, nothing
is stored and the error says which one.

One entry per kind of thing, quantity = how many. Example: "2 bières ce soir" is one entry
with quantity 2. Omit timestamp for now; otherwise give it in UTC (ending with "Z").
At most {MAX_BATCH_SIZE} entries per call.

Attributes hold only what the user stated for this entry: never copy them from an earlier
entry unless the user asks ("la même"), never guess. Leave a value out and the error will
say what to ask. Entries cannot be edited or deleted afterwards.

Categories:
{categories}
"""


@contextmanager
def _expected_errors() -> Iterator[None]:
    """Pass the service's validation errors on to Claude, which can act on them (D61).

    ValueError covers invalid entries and periods. Any other error is masked.
    """
    try:
        yield
    except (ValueError, UnknownCategoryError) as error:
        raise ToolError(str(error)) from error
