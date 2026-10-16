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
