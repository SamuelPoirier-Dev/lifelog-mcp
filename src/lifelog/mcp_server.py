"""MCP server definition: the tools exposed to MCP clients such as claude.ai."""

from fastmcp import FastMCP

SERVER_INSTRUCTIONS = (
    "Personal lifelog: record and query everyday entries (habits, health...) grouped by category."
)


def create_mcp_server() -> FastMCP:
    """Build the FastMCP server and register its tools."""
    mcp = FastMCP(name="lifelog", instructions=SERVER_INSTRUCTIONS)

    @mcp.tool
    def ping() -> str:
        """Check that the lifelog server is reachable. Returns "pong"."""
        return "pong"

    return mcp
