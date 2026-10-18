import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_password_is_required(monkeypatch):
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("password", ["", "   "])
def test_empty_password_is_rejected(password):
    with pytest.raises(ValidationError):
        Settings(postgres_password=password, _env_file=None)


def test_special_characters_are_not_parsed_as_url_delimiters():
    settings = Settings(postgres_password="test@/%:# with space", _env_file=None)
    assert settings.database_url.password == "test@/%:# with space"
    assert settings.database_url.drivername == "postgresql+psycopg"
    assert "test@" not in repr(settings)
    assert "test@" not in str(settings.database_url)


@pytest.mark.parametrize("port", [0, 65536])
def test_invalid_database_port_is_rejected(port):
    with pytest.raises(ValidationError):
        Settings(postgres_password="test-only", postgres_port=port, _env_file=None)


def test_production_rejects_insecure_cookie_or_http_origin():
    with pytest.raises(ValidationError):
        Settings(postgres_password="test-only", environment="production", _env_file=None)
    with pytest.raises(ValidationError):
        Settings(
            postgres_password="test-only",
            environment="production",
            cookie_secure=True,
            app_origins=["http://app.internal"],
            _env_file=None,
        )
    assert Settings(
        postgres_password="test-only",
        environment="production",
        cookie_secure=True,
        app_origins=["https://app.internal"],
        _env_file=None,
    ).cookie_secure


@pytest.mark.parametrize(
    "origin",
    ["*", "https://*.internal", "https://app.internal/path", "https://user:pass@app.internal"],
)
def test_unsafe_origin_configuration_rejected(origin):
    with pytest.raises(ValidationError):
        Settings(postgres_password="test-only", app_origins=[origin], _env_file=None)
