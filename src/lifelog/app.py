"""ASGI application: FastAPI hosting the MCP server.

Run locally with:
    LIFELOG_AUTH=none uv run uvicorn lifelog.app:create_app --factory
"""

import logging

from fastapi import FastAPI
from fastmcp.server.auth import AuthProvider
from starlette.middleware import Middleware

from lifelog.auth import AllowedUsersMiddleware, create_auth_provider
from lifelog.mcp_server import create_mcp_server
from lifelog.settings import Settings

logger = logging.getLogger(__name__)

MCP_PATH = "/mcp"


def create_app(
    settings: Settings | None = None, *, auth_provider: AuthProvider | None = None
) -> FastAPI:
    """Build the FastAPI app with the MCP server mounted at /mcp.

    `auth_provider` replaces the Entra provider built from the settings (tests only).
    """
    settings = settings or Settings()
    logging.basicConfig(level=settings.log_level)

    if auth_provider is None and settings.auth == "entra":
        auth_provider = create_auth_provider(settings)
    if auth_provider is None:
        logger.warning("Authentication is disabled (LIFELOG_AUTH=none): local use only")

    middleware = []
    if auth_provider is not None:
        middleware.append(Middleware(AllowedUsersMiddleware, allowed_oids=settings.allowed_oids))
    mcp_app = create_mcp_server(auth_provider).http_app(path=MCP_PATH, middleware=middleware)

    # The MCP session manager needs its lifespan (startup/shutdown) to run,
    # so FastAPI takes over the MCP app's lifespan.
    # Interactive docs and the OpenAPI schema are disabled: they would be
    # reachable without authentication.
    app = FastAPI(
        title="lifelog",
        lifespan=mcp_app.lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    # Mounted at the root rather than at /mcp: the MCP app owns /mcp and the OAuth
    # routes (/.well-known/..., /authorize, /token...) that must live at the root.
    # Routes declared on `app` before this mount take priority.
    app.mount("/", mcp_app)

    return app
