"""MCP tools tested in memory: the client talks to the server without HTTP."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from fake_categories import WaterCategory
from fastmcp import Client
from fastmcp.exceptions import ToolError

from lifelog.categories import CategoryRegistry, default_registry
from lifelog.categories.drinks import DrinksCategory
from lifelog.mcp_server import create_mcp_server
from lifelog.service import LifelogService
from lifelog.storage import MemoryRepository

# Thursday, November 5th 2026, 10:00 in Québec.
NOW = datetime(2026, 11, 5, 15, 0, tzinfo=UTC)
BEER = {"type": "beer", "volume_ml": 473, "abv_percent": 5}


def make_service(registry: CategoryRegistry | None = None) -> LifelogService:
    return LifelogService(MemoryRepository(), registry or default_registry(), now=lambda: NOW)


@pytest.fixture
async def client() -> AsyncIterator[Client]:
    async with Client(create_mcp_server(make_service())) as client:
        yield client


def category_values(input_schema: dict) -> list[str]:
    """Allowed categories: an enum, or a const when there is only one (D59)."""
    schema = input_schema["properties"]["category"]
    return schema.get("enum") or [schema["const"]]


async def log(client: Client, *entries: dict) -> list[dict]:
    result = await client.call_tool("log_entry", {"category": "drinks", "entries": list(entries)})
    return result.structured_content["result"]


async def test_the_four_tools_are_listed(client: Client):
    tools = {tool.name: tool for tool in await client.list_tools()}

    assert set(tools) == {"list_categories", "log_entry", "list_entries", "get_stats"}
    read_only = {name for name, tool in tools.items() if tool.annotations.read_only_hint}
    assert read_only == {"list_categories", "list_entries", "get_stats"}


async def test_log_entry_describes_the_categories_and_their_attributes(client: Client):
    [tool] = [tool for tool in await client.list_tools() if tool.name == "log_entry"]

    assert '"2 bières ce soir"' in tool.description
    assert "abv_percent" in tool.description
    assert "never copy them from an earlier" in tool.description
    assert category_values(tool.input_schema) == ["drinks"]


def test_server_instructions_forbid_reusing_or_guessing_values():
    instructions = create_mcp_server(make_service()).instructions

    assert "Do not reuse values" in instructions
    assert "cannot be edited or deleted" in instructions


async def test_a_new_category_is_offered_without_changing_the_tools():
    service = make_service(CategoryRegistry([DrinksCategory(), WaterCategory()]))
    async with Client(create_mcp_server(service)) as client:
        tools = await client.list_tools()
        await client.call_tool("log_entry", {"category": "water", "entries": [{"quantity": 2}]})
        stats = await client.call_tool("get_stats", {"category": "water"})

    for tool in tools:
        if "category" in tool.input_schema["properties"]:
            assert category_values(tool.input_schema) == ["drinks", "water"]
    assert stats.structured_content == {"entries": 1, "glasses": 2.0}


async def test_two_beers_then_the_weekly_total(client: Client):
    [entry] = await log(client, {"quantity": 2, "attributes": BEER})

    stats = await client.call_tool("get_stats", {"category": "drinks"})

    assert entry["timestamp"] == "2026-11-05T15:00:00Z"
    assert entry["attributes"] == {"type": "beer", "volume_ml": 473.0, "abv_percent": 5.0}
    assert stats.structured_content["start"] == "2026-11-02"
    assert stats.structured_content["standard_drinks"] == 2.8


async def test_a_beer_without_volume_is_refused_with_a_question_for_the_user(client: Client):
    with pytest.raises(ToolError, match="volume_ml and abv_percent required .* ask the user"):
        await log(client, {"quantity": 2, "attributes": {"type": "beer"}})


async def test_one_invalid_entry_stores_nothing(client: Client):
    with pytest.raises(ToolError, match="Nothing was stored. entry 2:"):
        await log(client, {"attributes": {"type": "wine"}}, {"attributes": {"type": "beer"}})

    page = await client.call_tool("list_entries", {"category": "drinks"})
    assert page.structured_content["entries"] == []


async def test_past_entries_keep_their_utc_timestamp(client: Client):
    await log(client, {"timestamp": "2026-10-16T00:30:00Z", "attributes": {"type": "wine"}})

    page = await client.call_tool(
        "list_entries", {"category": "drinks", "start": "2026-10-01", "end": "2026-10-31"}
    )

    [entry] = page.structured_content["entries"]
    assert entry["timestamp"] == "2026-10-16T00:30:00Z"


@pytest.mark.parametrize("timestamp", ["2026-11-04T21:30:00", "2026-11-04T21:30:00-05:00"])
async def test_a_timestamp_not_in_utc_is_refused(client: Client, timestamp: str):
    with pytest.raises(ToolError, match="must be in UTC"):
        await log(client, {"timestamp": timestamp, "attributes": {"type": "wine"}})


async def test_an_end_without_start_is_refused(client: Client):
    with pytest.raises(ToolError, match="needs a start"):
        await client.call_tool("get_stats", {"category": "drinks", "end": "2026-10-31"})


async def test_list_categories(client: Client):
    result = await client.call_tool("list_categories")

    [drinks] = result.structured_content["result"]
    assert drinks["name"] == "drinks"
    assert "volume_ml" in drinks["attributes_schema"]["properties"]


async def test_unexpected_errors_are_masked():
    class BrokenRepository(MemoryRepository):
        async def list(self, *args, **kwargs):
            raise RuntimeError("connection string with secrets")

    service = LifelogService(BrokenRepository(), default_registry(), now=lambda: NOW)
    async with Client(create_mcp_server(service)) as client:
        with pytest.raises(ToolError) as error:
            await client.call_tool("list_entries", {"category": "drinks"})

    assert "secrets" not in str(error.value)
