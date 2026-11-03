"""ASGI application: FastAPI hosting the MCP server.

Run locally with:
    LIFELOG_AUTH=none LIFELOG_STORAGE=memory uv run uvicorn lifelog.app:create_app --factory
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastmcp.server.auth import AuthProvider
from starlette.middleware import Middleware

from lifelog.auth import AllowedUsersMiddleware, create_auth_provider
from lifelog.categories import default_registry
from lifelog.mcp_server import create_mcp_server
from lifelog.service import LifelogService
from lifelog.settings import Settings
from lifelog.storage import MemoryRepository, Repository

logger = logging.getLogger(__name__)

MCP_PATH = "/mcp"


def create_repository(settings: Settings) -> Repository:
    """The storage backend chosen by LIFELOG_STORAGE."""
    if settings.storage == "memory":
        logger.warning("Entries are stored in memory (LIFELOG_STORAGE=memory): lost on restart")
        return MemoryRepository()

    # Imported here: only needed with Azure Table Storage.
    from azure.identity.aio import DefaultAzureCredential

    from lifelog.storage.table import TableRepository

    assert settings.table_account
    return TableRepository(
        settings.table_account, settings.table_name, credential=DefaultAzureCredential()
    )


def create_app(
    settings: Settings | None = None,
    *,
    auth_provider: AuthProvider | None = None,
    repository: Repository | None = None,
) -> FastAPI:
    """Build the FastAPI app with the MCP server mounted at /mcp.

    `auth_provider` and `repository` replace the ones built from the settings (tests).
    """
    settings = settings or Settings()
    logging.basicConfig(level=settings.log_level)

    if auth_provider is None and settings.auth == "entra":
        auth_provider = create_auth_provider(settings)
    if auth_provider is None:
        logger.warning("Authentication is disabled (LIFELOG_AUTH=none): local use only")

    repository = repository or create_repository(settings)
    service = LifelogService(repository, default_registry())

    middleware = []
    if auth_provider is not None:
        middleware.append(Middleware(AllowedUsersMiddleware, allowed_oids=settings.allowed_oids))
    mcp_app = create_mcp_server(service, auth_provider).http_app(
        path=MCP_PATH, middleware=middleware
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # The MCP session manager needs its lifespan (startup/shutdown) to run.
        async with mcp_app.lifespan(app):
            try:
                yield
            finally:
                close = getattr(repository, "close", None)
                if close is not None:
                    await close()

    # Interactive docs and the OpenAPI schema are disabled: they would be
    # reachable without authentication.
    app = FastAPI(
        title="lifelog",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    # Shared by the MCP tools and the REST API (step 6).
    app.state.service = service

    # Mounted at the root rather than at /mcp: the MCP app owns /mcp and the OAuth
    # routes (/.well-known/..., /authorize, /token...) that must live at the root.
    # Routes declared on `app` before this mount take priority.
    app.mount("/", mcp_app)

    return app
