"""Settings: authentication is on by default and refuses to start half-configured."""

import os

import pytest
from pydantic import ValidationError

from lifelog.settings import Settings

ENTRA_SETTINGS = {
    "base_url": "https://lifelog.example.com",
    "entra_tenant_id": "00000000-0000-0000-0000-000000000001",
    "entra_client_id": "00000000-0000-0000-0000-000000000002",
    "entra_client_secret": "client-secret",
    "jwt_signing_key": "signing-key",
    "allowed_oids": "oid-1",
}


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Ignore the developer's environment variables and .env file."""
    for name in list(os.environ):
        if name.startswith("LIFELOG_"):
            monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)


def test_entra_is_the_default_and_requires_its_settings():
    with pytest.raises(ValidationError) as error:
        Settings()

    message = str(error.value)
    for name in ENTRA_SETTINGS:
        assert f"LIFELOG_{name.upper()}" in message


def test_entra_settings_are_read_from_the_environment(monkeypatch: pytest.MonkeyPatch):
    for name, value in ENTRA_SETTINGS.items():
        monkeypatch.setenv(f"LIFELOG_{name.upper()}", value)
    monkeypatch.setenv("LIFELOG_ALLOWED_OIDS", " oid-1, oid-2 ,")
    monkeypatch.setenv("LIFELOG_STORAGE", "memory")

    settings = Settings()

    assert settings.auth == "entra"
    assert settings.allowed_oids == frozenset({"oid-1", "oid-2"})


def test_auth_none_needs_no_entra_settings():
    assert Settings(auth="none", storage="memory").auth == "none"


def test_oauth_table_requires_an_encryption_key():
    with pytest.raises(ValidationError, match="LIFELOG_OAUTH_STORAGE_ENCRYPTION_KEY"):
        Settings(auth="none", storage="memory", oauth_table_account="lifelogoauth")


def test_table_is_the_default_storage_and_requires_an_account():
    with pytest.raises(ValidationError, match="LIFELOG_TABLE_ACCOUNT"):
        Settings(auth="none")

    settings = Settings(auth="none", table_account="stlifelogdata")
    assert settings.storage == "table"
