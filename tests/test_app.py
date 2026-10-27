"""Full FastAPI app tested over HTTP, in-process (no socket, no uvicorn)."""

from collections.abc import AsyncIterator

import pytest
from fastmcp.utilities.asgi_transport import run_asgi_lifespan
from fastmcp.utilities.tests import ASGIServer

from lifelog.app import MCP_PATH, create_app
from lifelog.settings import Settings


@pytest.fixture
async def server() -> AsyncIterator[ASGIServer]:
    app = create_app(Settings())
    async with run_asgi_lifespan(app):
        yield ASGIServer(url=f"http://127.0.0.1{MCP_PATH}", app=app, transport_type="http")


async def test_mcp_client_calls_ping_over_http(server: ASGIServer):
    async with server.client() as client:
        result = await client.call_tool("ping")

    assert result.data == "pong"


@pytest.mark.parametrize("path", ["/", "/docs", "/redoc", "/openapi.json", "/health"])
async def test_no_public_route_besides_mcp(server: ASGIServer, path: str):
    async with server.http_client() as http:
        response = await http.get(path)

    assert response.status_code == 404
