"""Application settings, read from environment variables prefixed with LIFELOG_."""

from typing import Annotated, Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LIFELOG_", env_file=".env")

    log_level: str = "INFO"

    # "entra" (default) protects the MCP endpoint with Microsoft Entra ID.
    # "none" disables authentication and is meant for local development only.
    auth: Literal["entra", "none"] = "entra"

    # Public URL of the server, e.g. https://lifelog.example.azurecontainerapps.io
    base_url: str | None = None
    entra_tenant_id: str | None = None
    entra_client_id: str | None = None
    entra_client_secret: SecretStr | None = None
    # Signs the tokens the server issues to MCP clients. Must stay the same across
    # restarts, otherwise every client has to sign in again.
    jwt_signing_key: SecretStr | None = None
    # Entra object IDs (`oid` claim) allowed to use the server, comma-separated.
    allowed_oids: Annotated[frozenset[str], NoDecode] = frozenset()

    # OAuth state (registered clients, tokens) is kept in Azure Table Storage when an
    # account is set, and in memory otherwise (lost on restart).
    oauth_table_account: str | None = None
    oauth_table_name: str = "oauthstate"
    # Encrypts the OAuth state before it is written to the table.
    oauth_storage_encryption_key: SecretStr | None = None

    # Where entries are stored: "table" (Azure Table Storage, default) or "memory" (local
    # development only, lost on restart).
    storage: Literal["table", "memory"] = "table"
    # Storage account holding the entries table.
    table_account: str | None = None
    table_name: str = "entries"

    @field_validator("allowed_oids", mode="before")
    @classmethod
    def _split_oids(cls, value: object) -> object:
        if isinstance(value, str):
            return frozenset(oid.strip() for oid in value.split(",") if oid.strip())
        return value

    @model_validator(mode="after")
    def _check_config(self) -> "Settings":
        """Fail at startup rather than run with incomplete authentication or storage."""
        missing: list[str] = []
        if self.auth == "entra":
            required = {
                "base_url": self.base_url,
                "entra_tenant_id": self.entra_tenant_id,
                "entra_client_id": self.entra_client_id,
                "entra_client_secret": self.entra_client_secret,
                "jwt_signing_key": self.jwt_signing_key,
                "allowed_oids": self.allowed_oids,
            }
            missing += [name for name, value in required.items() if not value]
        if self.oauth_table_account and not self.oauth_storage_encryption_key:
            missing.append("oauth_storage_encryption_key")
        if self.storage == "table" and not self.table_account:
            missing.append("table_account")
        if missing:
            names = ", ".join(f"LIFELOG_{name.upper()}" for name in missing)
            raise ValueError(f"Missing settings: {names}")
        return self
