# lifelog-mcp

Personal lifelog exposed as a remote [MCP](https://modelcontextprotocol.io) server, so that
everyday entries (habits, health…) can be recorded and queried in plain language from the
Claude app. Other Claude agents (a weekly dashboard, imports) use the same tools.

> Work in progress — see [PLAN.md](PLAN.md) (in French) for the roadmap and the decision log.

## MCP tools

| Tool | What it does |
|---|---|
| `list_categories` | Categories, what they are for, and the attributes their entries take. |
| `log_entry` | Records 1 to 100 entries in a category, all or nothing. |
| `list_entries` | Entries of a category over a period (current week by default). |
| `get_stats` | Category-specific statistics over a period (current week by default). |

Timestamps go in and come out in UTC, since the user may be travelling. Days and weeks
(periods, stats) are calendar days and ISO weeks in Québec time. The first category is
`drinks`, counted in Canadian standard drinks (13.45 g of alcohol).

## Requirements

- [uv](https://docs.astral.sh/uv/) (installs Python 3.13 automatically if needed)
- Docker (optional, to run the container)
- Node.js (optional, for MCP Inspector)

## Run locally

```bash
uv sync
LIFELOG_AUTH=none LIFELOG_STORAGE=memory uv run uvicorn lifelog.app:create_app --factory --reload
```

`LIFELOG_AUTH=none` turns authentication off and `LIFELOG_STORAGE=memory` keeps entries in
memory (lost on restart), for local use. Without them the server expects the Microsoft
Entra and Table Storage settings below and refuses to start if they are missing.

The MCP endpoint is served at `http://127.0.0.1:8000/mcp` (streamable HTTP transport).

Try it with [MCP Inspector](https://github.com/modelcontextprotocol/inspector):

```bash
npx @modelcontextprotocol/inspector
```

Then choose the *Streamable HTTP* transport, enter `http://127.0.0.1:8000/mcp` and connect.

## Run with Docker

```bash
docker build -t lifelog .
docker run --rm -p 8000:8000 -e LIFELOG_AUTH=none -e LIFELOG_STORAGE=memory lifelog
```

## Tests and lint

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Storage tests also run against the real Azure Table Storage on request (they are skipped
by default). They use the Azure CLI login and clean up after themselves:

```bash
LIFELOG_TEST_TABLE_ACCOUNT=$(terraform -chdir=infra output -raw data_storage_account) \
  uv run pytest -m azure
```

## Configuration

Settings are read from environment variables prefixed with `LIFELOG_` (or a `.env` file).

| Variable | Default | Description |
|---|---|---|
| `LIFELOG_LOG_LEVEL` | `INFO` | Python logging level |
| `LIFELOG_AUTH` | `entra` | `entra` (Microsoft Entra ID) or `none` (local development only) |
| `LIFELOG_BASE_URL` | | Public URL of the server (OAuth redirects) |
| `LIFELOG_ENTRA_TENANT_ID` | | Entra tenant ID |
| `LIFELOG_ENTRA_CLIENT_ID` | | Application (client) ID of the Entra app registration |
| `LIFELOG_ENTRA_CLIENT_SECRET` | | Client secret of the Entra app registration |
| `LIFELOG_JWT_SIGNING_KEY` | | Signs the tokens issued to MCP clients; must stay stable |
| `LIFELOG_ALLOWED_OIDS` | | Comma-separated Entra object IDs allowed to use the server |
| `LIFELOG_OAUTH_TABLE_ACCOUNT` | | Storage account holding the OAuth state (in memory if unset) |
| `LIFELOG_OAUTH_TABLE_NAME` | `oauthstate` | Table holding the OAuth state |
| `LIFELOG_OAUTH_STORAGE_ENCRYPTION_KEY` | | Encrypts the OAuth state; required with a table |
| `LIFELOG_STORAGE` | `table` | `table` (Azure Table Storage) or `memory` (local development only) |
| `LIFELOG_TABLE_ACCOUNT` | | Storage account holding the entries table; required with `table` |
| `LIFELOG_TABLE_NAME` | `entries` | Table of entries, one partition per category |

## Deploy to Azure

The infrastructure is described with Terraform in [infra/](infra/): Azure Container Apps
(scale to zero), Azure Table Storage for the entries, a Microsoft Entra app
registration for sign-in, an Azure Table Storage table for the OAuth state, and a
monthly budget alert. Requirements: an Azure
subscription, the [Azure CLI](https://learn.microsoft.com/cli/azure/) and
[Terraform](https://developer.hashicorp.com/terraform/install).

```bash
az login
```

### 1. Bootstrap (once)

[infra/bootstrap/](infra/bootstrap/) creates the resource group and the storage account
holding the Terraform states, including its own once it exists.

Create `infra/bootstrap/terraform.tfvars`:

```hcl
subscription_id = "<subscription ID>"   # az account show --query id
```

On a new subscription, the storage account does not exist yet: comment out the
`backend` block of [infra/bootstrap/main.tf](infra/bootstrap/main.tf) and apply with a
local state.

```bash
cd infra/bootstrap
terraform init
terraform apply
```

Then put the `tfstate_storage_account_name` output in the `backend` blocks of
[infra/bootstrap/main.tf](infra/bootstrap/main.tf) and
[infra/versions.tf](infra/versions.tf), uncomment the bootstrap's `backend` block and
move its state into the storage account:

```bash
terraform init -migrate-state
```

### 2. Container image

Container Apps runs amd64 images; build for that platform and push to ghcr.io (the
package must be public):

```bash
docker build --platform linux/amd64 -t ghcr.io/<github user>/lifelog-mcp:<tag> .
docker push ghcr.io/<github user>/lifelog-mcp:<tag>
```

### 3. Infrastructure

Create `infra/terraform.tfvars` (not in git):

| Variable | Description |
|---|---|
| `subscription_id` | Azure subscription ID (`az account show --query id`) |
| `image` | Container image, e.g. `ghcr.io/<github user>/lifelog-mcp:<tag>` |
| `allowed_oids` | Entra object IDs allowed to use the server (`az ad signed-in-user show --query id`) |
| `budget_email` | Address receiving the budget alerts |
| `budget_amount` | Optional, monthly budget in the billing currency (default `5`) |
| `budget_start_date` | Optional, first day of the first budget month (default `2026-10-01T00:00:00Z`) |

```bash
cd infra
terraform init
terraform apply
```

The `mcp_url` output is the URL to add as a custom connector on claude.ai.

claude.ai keeps its copy of the tool list, even in a new conversation: after changing tool
descriptions or server instructions, reconnect the connector.
