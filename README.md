# lifelog-mcp

Personal lifelog exposed as a remote [MCP](https://modelcontextprotocol.io) server, so that
everyday entries (habits, health…) can be recorded and queried in plain language from the
Claude app, plus a read-only REST API for dashboards.

> Work in progress — see [PLAN.md](PLAN.md) (in French) for the roadmap and the decision log.

## Requirements

- [uv](https://docs.astral.sh/uv/) (installs Python 3.13 automatically if needed)
- Docker (optional, to run the container)
- Node.js (optional, for MCP Inspector)

## Run locally

```bash
uv sync
uv run uvicorn lifelog.app:create_app --factory --reload
```

The MCP endpoint is served at `http://127.0.0.1:8000/mcp` (streamable HTTP transport).

Try it with [MCP Inspector](https://github.com/modelcontextprotocol/inspector):

```bash
npx @modelcontextprotocol/inspector
```

Then choose the *Streamable HTTP* transport, enter `http://127.0.0.1:8000/mcp` and connect.

## Run with Docker

```bash
docker build -t lifelog .
docker run --rm -p 8000:8000 lifelog
```

## Tests and lint

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Configuration

Settings are read from environment variables prefixed with `LIFELOG_` (or a `.env` file).

| Variable | Default | Description |
|---|---|---|
| `LIFELOG_LOG_LEVEL` | `INFO` | Python logging level |
