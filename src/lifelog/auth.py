"""Authentication: Microsoft Entra ID through FastMCP's OAuth proxy, plus an allow-list.

claude.ai talks OAuth to this server, which forwards the sign-in to Entra (OAuth proxy).
Only the Entra users listed in LIFELOG_ALLOWED_OIDS may then use the MCP endpoint.
"""

import logging

from cryptography.fernet import Fernet
from fastmcp.server.auth.jwt_issuer import derive_jwt_key
from fastmcp.server.auth.providers.azure import AzureProvider
from key_value.aio.protocols import AsyncKeyValue
from key_value.aio.stores.azure_tables import AzureTablesStore
from key_value.aio.stores.azure_tables.store import AzureTablesSanitizationStrategy
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from lifelog.settings import Settings

logger = logging.getLogger(__name__)

# Scope exposed by the Entra app registration ("Expose an API").
API_SCOPE = "access"

# MCP clients allowed to receive the OAuth redirect: claude.ai (web and mobile apps go
# through the same callback) and local tools such as MCP Inspector.
ALLOWED_CLIENT_REDIRECT_URIS = [
    "https://claude.ai/api/mcp/auth_callback",
    "https://claude.com/api/mcp/auth_callback",
    "http://localhost:*",
    "http://127.0.0.1:*",
]


def create_auth_provider(settings: Settings) -> AzureProvider:
    """Build the Entra OAuth proxy from complete settings (checked by Settings)."""
    assert settings.entra_client_secret and settings.jwt_signing_key
    return AzureProvider(
        client_id=settings.entra_client_id,
        client_secret=settings.entra_client_secret.get_secret_value(),
        tenant_id=settings.entra_tenant_id,
        base_url=settings.base_url,
        required_scopes=[API_SCOPE],
        jwt_signing_key=settings.jwt_signing_key.get_secret_value(),
        client_storage=create_oauth_storage(settings),
        allowed_client_redirect_uris=ALLOWED_CLIENT_REDIRECT_URIS,
    )


def create_oauth_storage(settings: Settings) -> AsyncKeyValue | None:
    """Encrypted Azure Table Storage for the OAuth state, or None for FastMCP's default.

    The table is reached with the Container App's managed identity: no storage key.
    """
    if not settings.oauth_table_account:
        logger.warning("OAuth state is not persisted: clients must sign in again after a restart")
        return None

    # Imported here: only needed when a table is configured.
    from azure.identity.aio import DefaultAzureCredential

    assert settings.oauth_storage_encryption_key
    # Azure Tables rejects keys containing "/", "?"... (e.g. URL client IDs): such keys
    # are replaced by a hash.
    sanitizer = AzureTablesSanitizationStrategy()
    table = AzureTablesStore(
        account_name=settings.oauth_table_account,
        credential=DefaultAzureCredential(),
        table_name=settings.oauth_table_name,
        collection_sanitization_strategy=sanitizer,
        key_sanitization_strategy=sanitizer,
    )
    fernet_key = derive_jwt_key(
        high_entropy_material=settings.oauth_storage_encryption_key.get_secret_value(),
        salt="lifelog-oauth-storage",
    )
    # After a key change, unreadable entries count as missing (clients sign in again)
    # instead of failing every request, as in FastMCP's default storage.
    return FernetEncryptionWrapper(
        key_value=table, fernet=Fernet(fernet_key), raise_on_decryption_error=False
    )


class AllowedUsersMiddleware:
    """Reject authenticated requests from Entra users that are not on the allow-list.

    Runs after FastMCP's authentication middleware, which puts the validated token in
    scope["user"]. Unauthenticated requests are left alone: public routes (OAuth
    discovery) stay reachable and the MCP endpoint answers them with 401 itself.
    """

    def __init__(self, app: ASGIApp, allowed_oids: frozenset[str]) -> None:
        self.app = app
        self.allowed_oids = allowed_oids

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            token = getattr(scope.get("user"), "access_token", None)
            if token is not None and token.claims.get("oid") not in self.allowed_oids:
                logger.warning("Rejected a request from a user not on the allow-list")
                response = JSONResponse(
                    {"error": "forbidden", "error_description": "User not allowed"},
                    status_code=403,
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
