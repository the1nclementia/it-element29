import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.db.session import build_engine
from app.main import create_app

pytestmark = pytest.mark.integration
PASSWORD = "Test-only-password-2026"
NEW_PASSWORD = "Another-test-password-2026"
ORIGIN = {"Origin": "http://testserver"}


@pytest.fixture()
def client(identity_db):
    with TestClient(create_app(identity_db[1])) as client:
        yield client


def csrf(client):
    response = client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    return {**ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


def login(client, username="admin", password=PASSWORD):
    return client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
        headers=csrf(client),
    )


def bootstrap(identity_db):
    from app.modules.identity.service import bootstrap_admin

    with Session(identity_db[0]) as session:
        return bootstrap_admin(session, "admin", "Тестовый администратор", PASSWORD)


def add_user(client, role="manager", username="employee"):
    response = client.post(
        "/api/v1/users",
        json={
            "username": username,
            "display_name": "Тестовый сотрудник",
            "role": role,
            "password": PASSWORD,
        },
        headers=csrf(client),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_anonymous_csrf_required_before_login(client):
    response = client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert (
        client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": PASSWORD}, headers=ORIGIN
        ).status_code
        == 403
    )


def test_login_logout_refresh_and_database_stores_only_token_hash(client, identity_db):
    from app.modules.identity.models import AuthSession, User

    bootstrap(identity_db)
    old_cookie = client.get("/api/v1/auth/csrf").headers["set-cookie"]
    response = login(client, "ADMIN")
    assert response.status_code == 200, response.text
    assert response.json()["user"]["role"] == "administrator"
    assert response.headers["set-cookie"] != old_cookie
    assert client.get("/api/v1/auth/me").status_code == 200
    # A new browser page has no in-memory state but can restore its existing cookie.
    with TestClient(create_app(identity_db[1])) as refreshed:
        refreshed.cookies.update(client.cookies)
        assert refreshed.get("/api/v1/auth/me").json()["username"] == "admin"
    with Session(identity_db[0]) as session:
        user = session.scalar(select(User))
        assert user.password_hash.startswith("$argon2id$")
        raw = client.cookies.get("element29_session")
        assert raw not in [row.token_hash for row in session.scalars(select(AuthSession))]
    copied = dict(client.cookies)
    assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401
    client.cookies.update(copied)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_invalid_unknown_and_blocked_credentials_are_indistinguishable(client, identity_db):
    from app.modules.identity.models import User

    bootstrap(identity_db)
    wrong = login(client, password="incorrect-password")
    unknown = login(client, username="unknown")
    with Session(identity_db[0]) as session:
        session.execute(update(User).values(is_active=False))
        session.commit()
    blocked = login(client)
    assert wrong.status_code == unknown.status_code == blocked.status_code == 401
    assert wrong.json() == unknown.json() == blocked.json()


def test_expired_session_denied(client, identity_db):
    from app.modules.identity.models import AuthSession

    bootstrap(identity_db)
    assert login(client).status_code == 200
    with Session(identity_db[0]) as session:
        session.execute(
            update(AuthSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        session.commit()
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/users").status_code == 401


def test_csrf_origin_and_token_are_checked_on_mutations(client, identity_db):
    bootstrap(identity_db)
    assert login(client).status_code == 200
    valid = csrf(client)
    assert client.post("/api/v1/auth/logout", headers=ORIGIN).status_code == 403
    assert (
        client.post(
            "/api/v1/auth/logout", headers={**valid, "Origin": "https://evil.invalid"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/auth/logout", headers={"X-CSRF-Token": valid["X-CSRF-Token"]}
        ).status_code
        == 403
    )
    assert client.get("/api/v1/auth/me").status_code == 200


def test_rate_limit_is_shared_between_clients_and_does_not_disclose_account(client, identity_db):
    bootstrap(identity_db)
    for _ in range(3):
        assert login(client, password="incorrect-password").status_code == 401
    with TestClient(create_app(identity_db[1])) as another:
        response = login(another)
        assert response.status_code == 429
        assert int(response.headers["Retry-After"]) > 0


@pytest.mark.parametrize(
    "role,allowed,denied",
    [
        ("manager", "reports.read", "inventory.issue"),
        ("storekeeper", "inventory.manage", "equipment.manage"),
        ("it_specialist", "equipment.manage", "inventory.manage"),
        ("administrator", "users.manage", None),
    ],
)
def test_each_role_and_direct_admin_api(client, identity_db, role, allowed, denied):
    bootstrap(identity_db)
    login(client)
    add_user(client, role)
    with TestClient(create_app(identity_db[1])) as member:
        assert login(member, "employee").status_code == 200
        assert member.get("/api/v1/dashboard").status_code == 403
        assert (
            member.post(
                "/api/v1/auth/password",
                json={
                    "current_password": PASSWORD,
                    "new_password": NEW_PASSWORD,
                },
                headers=csrf(member),
            ).status_code
            == 200
        )
        permissions = member.get("/api/v1/auth/permissions").json()["permissions"]
        assert allowed in permissions
        if denied:
            assert denied not in permissions
        assert member.get("/api/v1/users").status_code == (200 if role == "administrator" else 403)
        if role != "administrator":
            assert (
                member.post(
                    "/api/v1/users",
                    json={
                        "username": "intruder",
                        "display_name": "Нет доступа",
                        "role": "administrator",
                        "password": PASSWORD,
                    },
                    headers=csrf(member),
                ).status_code
                == 403
            )
        metrics = member.get("/api/v1/dashboard").json()["metrics"]
        assert len(metrics) == 8
        available = {
            "cartridge_balance",
            "issues_today",
            "low_stock",
            "equipment_total",
            "equipment_active",
            "equipment_stock",
            "equipment_maintenance",
        }
        for metric in metrics:
            if metric["key"] in available:
                assert metric["value"] == 0 and metric["available"]
            else:
                assert metric["value"] is None and not metric["available"]


def test_admin_edits_revoke_sessions_and_password_reset_is_temporary(client, identity_db):
    bootstrap(identity_db)
    login(client)
    user = add_user(client)
    with TestClient(create_app(identity_db[1])) as member:
        login(member, "employee")
        response = client.patch(
            f"/api/v1/users/{user['id']}", json={"role": "storekeeper"}, headers=csrf(client)
        )
        assert response.status_code == 200
        assert member.get("/api/v1/auth/me").status_code == 401
        login(member, "employee")
        assert (
            client.patch(
                f"/api/v1/users/{user['id']}", json={"is_active": False}, headers=csrf(client)
            ).status_code
            == 200
        )
        assert member.get("/api/v1/auth/me").status_code == 401
        assert login(member, "employee").status_code == 401
        assert (
            client.patch(
                f"/api/v1/users/{user['id']}", json={"is_active": True}, headers=csrf(client)
            ).status_code
            == 200
        )
        login(member, "employee")
        assert (
            client.post(
                f"/api/v1/users/{user['id']}/reset-password",
                json={"new_password": NEW_PASSWORD},
                headers=csrf(client),
            ).status_code
            == 204
        )
        assert member.get("/api/v1/auth/me").status_code == 401
        assert (
            login(member, "employee", NEW_PASSWORD).json()["user"]["must_change_password"] is True
        )


def test_admin_cannot_disable_or_demote_self_and_bootstrap_is_one_time(client, identity_db):
    from app.modules.identity.service import bootstrap_admin

    bootstrap(identity_db)
    user = login(client).json()["user"]
    for payload in [{"is_active": False}, {"role": "manager"}]:
        assert (
            client.patch(
                f"/api/v1/users/{user['id']}", json=payload, headers=csrf(client)
            ).status_code
            == 409
        )
    with Session(identity_db[0]) as session, pytest.raises(ValueError):
        bootstrap_admin(session, "otheradmin", "Ещё администратор", PASSWORD)


def test_username_unique_normalized_and_audit_never_contains_secrets(client, identity_db):
    from app.modules.identity.models import AuditLog

    bootstrap(identity_db)
    login(client)
    add_user(client)
    response = client.post(
        "/api/v1/users",
        json={
            "username": "EMPLOYEE",
            "display_name": "Дубликат",
            "role": "manager",
            "password": PASSWORD,
        },
        headers=csrf(client),
    )
    assert response.status_code == 409
    assert PASSWORD not in response.text
    with Session(identity_db[0]) as session:
        rows = list(session.scalars(select(AuditLog)))
        assert any(row.action == "user.created" for row in rows)
        for row in rows:
            assert "password" not in str(row.changes).lower()
            assert PASSWORD not in str(row.changes)


def test_validation_does_not_echo_plaintext_passwords(client, identity_db):
    bootstrap(identity_db)
    login(client)
    response = client.post(
        "/api/v1/users",
        json={
            "username": "employee",
            "display_name": "Тест",
            "role": "invalid",
            "password": PASSWORD,
        },
        headers=csrf(client),
    )
    assert response.status_code == 422
    assert PASSWORD not in response.text
    assert "input" not in response.text


def test_password_change_revokes_other_sessions_and_rejects_old_password(client, identity_db):
    bootstrap(identity_db)
    login(client)
    with TestClient(create_app(identity_db[1])) as second:
        login(second)
        assert (
            client.post(
                "/api/v1/auth/password",
                headers=csrf(client),
                json={
                    "current_password": PASSWORD,
                    "new_password": NEW_PASSWORD,
                },
            ).status_code
            == 200
        )
        assert client.get("/api/v1/auth/me").status_code == 200
        assert second.get("/api/v1/auth/me").status_code == 401
        assert login(second).status_code == 401
        assert login(second, password=NEW_PASSWORD).status_code == 200


def test_rate_limit_counts_concurrent_attempts_atomically(identity_db):
    def attempt(_):
        with TestClient(create_app(identity_db[1])) as browser:
            return login(browser, "missing").status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(attempt, range(7)))
    assert statuses.count(401) == 3
    assert statuses.count(429) == 4


def test_concurrent_admin_demotions_cannot_remove_all_administrators(client, identity_db):
    from app.modules.identity.models import User

    bootstrap(identity_db)
    original = login(client).json()["user"]
    new_admin = add_user(client, role="administrator", username="anotheradmin")
    with TestClient(create_app(identity_db[1])) as second:
        login(second, "anotheradmin")
        second.post(
            "/api/v1/auth/password",
            json={
                "current_password": PASSWORD,
                "new_password": NEW_PASSWORD,
            },
            headers=csrf(second),
        )
        first_headers, second_headers = csrf(client), csrf(second)
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(
                client.patch,
                f"/api/v1/users/{new_admin['id']}",
                json={"role": "manager"},
                headers=first_headers,
            )
            b = pool.submit(
                second.patch,
                f"/api/v1/users/{original['id']}",
                json={"role": "manager"},
                headers=second_headers,
            )
            statuses = [a.result().status_code, b.result().status_code]
        assert statuses.count(200) == 1
        assert any(status in (401, 403) for status in statuses)
    with Session(identity_db[0]) as session:
        assert (
            len(list(session.scalars(select(User).where(User.role_code == "administrator")))) == 1
        )


def test_runtime_role_can_authenticate_but_cannot_modify_audit_or_schema(identity_db):
    from app.db.provision import provision_runtime_role

    engine, settings = identity_db
    bootstrap(identity_db)
    role = "test_runtime_" + secrets.token_hex(5)
    password = secrets.token_urlsafe(32)
    with engine.begin() as connection:
        provision_runtime_role(connection, role, password)
    limited_settings = settings.model_copy(
        update={
            "postgres_user": role,
            "postgres_password": settings.postgres_password.__class__(password),
        }
    )
    limited = build_engine(limited_settings)
    try:
        with TestClient(create_app(limited_settings)) as browser:
            assert login(browser).status_code == 200
            assert browser.get("/api/v1/dashboard").status_code == 200
            add_user(browser)
        with limited.connect() as connection:
            for table in ["audit_logs", "users", "inventory_documents", "inventory_movements"]:
                assert not connection.scalar(
                    text("SELECT has_table_privilege(current_user, :table, 'DELETE')"),
                    {"table": table},
                )
            for table in ["audit_logs", "inventory_documents", "inventory_movements"]:
                assert not connection.scalar(
                    text("SELECT has_table_privilege(current_user, :table, 'UPDATE')"),
                    {"table": table},
                )
            assert not connection.scalar(
                text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
            )
    finally:
        limited.dispose()


def test_admin_request_waiting_for_lock_rechecks_revoked_session(client, identity_db):
    from sqlalchemy import delete

    from app.modules.identity.models import AuthSession

    bootstrap(identity_db)
    admin = login(client).json()["user"]
    headers = csrf(client)
    engine, _ = identity_db
    with ThreadPoolExecutor(max_workers=1) as pool:
        with engine.begin() as blocker:
            blocker.execute(text("SELECT pg_advisory_xact_lock(29, 2)"))
            pending = pool.submit(
                client.post,
                "/api/v1/users",
                headers=headers,
                json={
                    "username": "stale_request",
                    "display_name": "Запрос старой сессии",
                    "role": "manager",
                    "password": PASSWORD,
                },
            )
            deadline = time.monotonic() + 5
            while not blocker.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
                    "AND wait_event='advisory' AND pid<>pg_backend_pid()"
                )
            ):
                assert time.monotonic() < deadline, "Mutation did not reach the administration lock"
                time.sleep(0.02)
            # Password changes revoke all sessions while holding this same lock.
            blocker.execute(delete(AuthSession).where(AuthSession.user_id == admin["id"]))
        assert pending.result(timeout=5).status_code == 401
