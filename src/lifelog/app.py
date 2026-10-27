"""ASGI application: FastAPI hosting the MCP server.

Run locally with:
    uv run uvicorn lifelog.app:create_app --factory
"""

import logging

from fastapi import FastAPI

from lifelog.mcp_server import create_mcp_server
from lifelog.settings import Settings

MCP_PATH = "/mcp"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app with the MCP server mounted at /mcp."""
    settings = settings or Settings()
    logging.basicConfig(level=settings.log_level)

    mcp_app = create_mcp_server().http_app(path=MCP_PATH)

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

    # Mounted at the root rather than at /mcp: the MCP app owns /mcp and, once
    # auth is added, the OAuth routes (/.well-known/..., /auth/...) that must
    # live at the root. Routes declared on `app` before this mount take priority.
    app.mount("/", mcp_app)

    return app
