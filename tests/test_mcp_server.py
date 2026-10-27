"""MCP server tested in memory: the client talks to the server without HTTP."""

from fastmcp import Client

from lifelog.mcp_server import create_mcp_server


async def test_ping_tool_is_listed():
    async with Client(create_mcp_server()) as client:
        tools = await client.list_tools()

    assert [tool.name for tool in tools] == ["ping"]


async def test_ping_returns_pong():
    async with Client(create_mcp_server()) as client:
        result = await client.call_tool("ping")

    assert result.data == "pong"
