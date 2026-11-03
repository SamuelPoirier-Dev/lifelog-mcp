"""Authentication over HTTP: Entra OAuth routes, bearer token required, allow-list."""

from collections.abc import AsyncIterator

import pytest
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from fastmcp.utilities.asgi_transport import run_asgi_lifespan
from fastmcp.utilities.tests import ASGIServer
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper

from lifelog.app import MCP_PATH, create_app
from lifelog.auth import API_SCOPE, create_oauth_storage
from lifelog.settings import Settings

ALLOWED_OID = "11111111-1111-1111-1111-111111111111"
OTHER_OID = "22222222-2222-2222-2222-222222222222"

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1"},
    },
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream"}


async def _serve(app) -> AsyncIterator[ASGIServer]:
    async with run_asgi_lifespan(app):
        yield ASGIServer(url=f"http://127.0.0.1{MCP_PATH}", app=app, transport_type="http")


@pytest.fixture
async def static_token_server() -> AsyncIterator[ASGIServer]:
    """App whose tokens are checked against a fixed list instead of Entra."""
    verifier = StaticTokenVerifier(
        tokens={
            "allowed-token": {"client_id": "c", "scopes": [API_SCOPE], "oid": ALLOWED_OID},
            "other-token": {"client_id": "c", "scopes": [API_SCOPE], "oid": OTHER_OID},
            "no-oid-token": {"client_id": "c", "scopes": [API_SCOPE]},
        }
    )
    settings = Settings(auth="none", storage="memory", allowed_oids=frozenset({ALLOWED_OID}))
    async for server in _serve(create_app(settings, auth_provider=verifier)):
        yield server


@pytest.fixture
async def entra_server() -> AsyncIterator[ASGIServer]:
    """App with the real Entra provider, built from fake settings (no network needed)."""
    settings = Settings(
        auth="entra",
        storage="memory",
        base_url="https://lifelog.example.com",
        entra_tenant_id="00000000-0000-0000-0000-000000000001",
        entra_client_id="00000000-0000-0000-0000-000000000002",
        entra_client_secret="client-secret",
        jwt_signing_key="test-signing-key-long-enough",
        allowed_oids=frozenset({ALLOWED_OID}),
    )
    async for server in _serve(create_app(settings)):
        yield server


async def test_allowed_user_calls_a_tool(static_token_server: ASGIServer):
    async with static_token_server.client(auth="allowed-token") as client:
        result = await client.call_tool("list_categories")

    assert result.structured_content["result"][0]["name"] == "drinks"


@pytest.mark.parametrize("token", ["other-token", "no-oid-token"])
async def test_user_not_on_the_allow_list_is_forbidden(static_token_server: ASGIServer, token: str):
    async with static_token_server.http_client() as http:
        response = await http.post(
            MCP_PATH,
            json=INITIALIZE,
            headers={**MCP_HEADERS, "Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 403


@pytest.mark.parametrize("token", [None, "unknown-token"])
async def test_mcp_requires_a_valid_token(static_token_server: ASGIServer, token: str | None):
    headers = dict(MCP_HEADERS)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with static_token_server.http_client() as http:
        response = await http.post(MCP_PATH, json=INITIALIZE, headers=headers)

    assert response.status_code == 401


async def test_entra_mcp_endpoint_requires_a_token(entra_server: ASGIServer):
    async with entra_server.http_client() as http:
        response = await http.post(MCP_PATH, json=INITIALIZE, headers=MCP_HEADERS)

    assert response.status_code == 401
    assert "resource_metadata" in response.headers["www-authenticate"]


@pytest.mark.parametrize(
    "path",
    ["/.well-known/oauth-protected-resource/mcp", "/.well-known/oauth-authorization-server"],
)
async def test_entra_oauth_discovery_is_public(entra_server: ASGIServer, path: str):
    async with entra_server.http_client() as http:
        response = await http.get(path)

    assert response.status_code == 200


async def test_entra_advertises_the_api_scope(entra_server: ASGIServer):
    async with entra_server.http_client() as http:
        response = await http.get("/.well-known/oauth-protected-resource/mcp")

    # Short form: the OAuth proxy adds the Entra prefix (api://<client id>/) itself.
    assert response.json()["scopes_supported"] == [API_SCOPE]


@pytest.mark.parametrize("path", ["/", "/docs", "/redoc", "/openapi.json", "/health"])
async def test_entra_has_no_other_public_route(entra_server: ASGIServer, path: str):
    async with entra_server.http_client() as http:
        response = await http.get(path)

    assert response.status_code == 404


def test_oauth_state_is_in_memory_without_a_table():
    assert create_oauth_storage(Settings(auth="none", storage="memory")) is None


def test_oauth_state_in_a_table_is_encrypted():
    settings = Settings(
        auth="none",
        storage="memory",
        oauth_table_account="lifelogoauth",
        oauth_storage_encryption_key="test-encryption-key-long-enough",
    )

    assert isinstance(create_oauth_storage(settings), FernetEncryptionWrapper)
