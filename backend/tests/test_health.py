from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def unavailable_database_app(**overrides):
    return create_app(
        Settings(
            postgres_password="test-secret-never-return",
            postgres_host="127.0.0.1",
            postgres_port=1,
            db_connect_timeout=1,
            _env_file=None,
            **overrides,
        )
    )


def test_liveness_is_independent_of_database():
    with TestClient(unavailable_database_app()) as client:
        response = client.get("/api/v1/health/live")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_readiness_is_503_without_database_and_does_not_leak_secrets():
    with TestClient(unavailable_database_app()) as client:
        response = client.get("/api/v1/health/ready")
        assert response.status_code == 503
        assert response.json() == {"status": "not_ready"}
        assert "test-secret" not in response.text
        assert "postgresql" not in response.text


def test_no_public_docs_or_business_routes_by_default():
    with TestClient(unavailable_database_app()) as client:
        for path in ["/docs", "/redoc", "/openapi.json", "/api/v1/equipment"]:
            assert client.get(path).status_code == 404
        assert client.get("/api/v1/users").status_code == 401


def test_openapi_can_be_enabled_explicitly_for_development():
    with TestClient(unavailable_database_app(enable_api_docs=True)) as client:
        response = client.get("/openapi.json")
        assert response.status_code == 200
        assert {
            "/api/v1/health/live",
            "/api/v1/health/ready",
            "/api/v1/auth/me",
        } <= set(response.json()["paths"])
