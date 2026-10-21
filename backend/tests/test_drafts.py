"""Личные серверные черновики; реальные fresh PostgreSQL БД, без очистки."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from test_catalog import PASSWORD, headers, item_create, references
from test_catalog import catalog as catalog
from test_catalog import create as create_reference

from app.main import create_app
from app.modules.identity.models import User
from app.modules.identity.security import hash_password
from app.modules.inventory.models import InventoryDocument, InventoryMovement

pytestmark = pytest.mark.integration


@pytest.fixture()
def draft_context(catalog):
    browser, engine = catalog
    manufacturer, category = references(browser)
    item = item_create(browser, manufacturer, category)
    yield browser, engine, item


def create_draft(browser, item=None, document_type="receipt", **payload):
    data = {
        "document_date": date(2026, 10, 19).isoformat(),
        "items": [{"inventory_item_id": item["id"], "quantity": 5}] if item else [],
        **payload,
    }
    result = browser.post(
        "/api/v1/inventory/drafts",
        headers=headers(browser),
        json={"document_type": document_type, "payload": data},
    )
    assert result.status_code == 201, result.text
    return result.json()


def test_personal_draft_persists_across_clients_and_has_optimistic_versions(draft_context):
    browser, engine, item = draft_context
    draft = create_draft(browser)
    assert (
        draft["status"] == "draft" and draft["version"] == 1 and draft["posted_document_id"] is None
    )
    with TestClient(create_app(browser.app.state.settings)) as another:
        another.cookies.update(browser.cookies)
        listed = another.get("/api/v1/inventory/drafts").json()
        assert listed["total"] == 1 and listed["items"][0]["id"] == draft["id"]
        saved = another.patch(
            "/api/v1/inventory/drafts/" + draft["id"],
            headers=headers(another),
            json={
                "version": 1,
                "payload": {"items": [{"inventory_item_id": item["id"], "quantity": 2}]},
            },
        )
        assert saved.status_code == 200 and saved.json()["version"] == 2
    stale = browser.patch(
        "/api/v1/inventory/drafts/" + draft["id"],
        headers=headers(browser),
        json={"version": 1, "payload": {"items": []}},
    )
    assert stale.status_code == 409
    incomplete = browser.post(
        "/api/v1/inventory/drafts/" + draft["id"] + "/post",
        headers=headers(browser),
        json={"version": 2},
    )
    assert incomplete.status_code == 422
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(InventoryDocument)) == 0


def test_draft_post_replay_and_two_concurrent_requests_create_one_document(draft_context):
    browser, engine, item = draft_context
    draft = create_draft(browser, item)
    auth = headers(browser)

    def post(_):
        return browser.post(
            "/api/v1/inventory/drafts/" + draft["id"] + "/post", headers=auth, json={"version": 1}
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(post, range(2)))
    assert sorted(result.status_code for result in results) == [200, 201], [
        result.text for result in results
    ]
    assert results[0].json()["document"]["id"] == results[1].json()["document"]["id"]
    posted = results[0].json()["draft"]
    assert posted["status"] == "posted" and posted["version"] == 2
    assert (
        browser.patch(
            "/api/v1/inventory/drafts/" + draft["id"],
            headers=auth,
            json={"version": 2, "payload": {"items": []}},
        ).status_code
        == 409
    )
    assert (
        browser.post(
            "/api/v1/inventory/drafts/" + draft["id"] + "/archive",
            headers=auth,
            json={"version": 2},
        ).status_code
        == 409
    )
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(InventoryDocument)) == 1
        assert session.scalar(select(func.sum(InventoryMovement.delta))) == 5


def test_draft_post_audit_failure_rolls_back_document_ledger_and_draft(draft_context, monkeypatch):
    browser, engine, item = draft_context
    draft = create_draft(browser, item)
    from app.modules.inventory import draft_service

    actual = draft_service.audit

    def broken(session, actor, action, *args, **kwargs):
        if action == "inventory.draft_posted":
            raise RuntimeError("Synthetic draft audit failure")
        return actual(session, actor, action, *args, **kwargs)

    monkeypatch.setattr(draft_service, "audit", broken)
    with pytest.raises(RuntimeError, match="Synthetic draft audit failure"):
        browser.post(
            "/api/v1/inventory/drafts/" + draft["id"] + "/post",
            headers=headers(browser),
            json={"version": 1},
        )
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(InventoryDocument)) == 0
        assert session.scalar(select(func.count()).select_from(InventoryMovement)) == 0
    current = browser.get("/api/v1/inventory/drafts/" + draft["id"]).json()
    assert current["status"] == "draft" and current["version"] == 1


def test_drafts_owner_isolation_even_administrator_and_archive(draft_context):
    browser, engine, item = draft_context
    draft = create_draft(browser, item)
    settings = browser.app.state.settings
    with Session(engine) as session:
        session.add(
            User(
                username="draft_other",
                display_name="Другой оператор",
                password_hash=hash_password(PASSWORD),
                role_code="administrator",
                must_change_password=False,
            )
        )
        session.commit()
    with TestClient(create_app(settings)) as other:
        assert (
            other.post(
                "/api/v1/auth/login",
                headers=headers(other),
                json={"username": "draft_other", "password": PASSWORD},
            ).status_code
            == 200
        )
        assert other.get("/api/v1/inventory/drafts").json()["total"] == 0
        assert other.get("/api/v1/inventory/drafts/" + draft["id"]).status_code == 404
        assert (
            other.patch(
                "/api/v1/inventory/drafts/" + draft["id"],
                headers=headers(other),
                json={"version": 1, "payload": {"items": []}},
            ).status_code
            == 404
        )
        assert (
            other.post(
                "/api/v1/inventory/drafts/" + draft["id"] + "/post",
                headers=headers(other),
                json={"version": 1},
            ).status_code
            == 404
        )
        assert (
            other.post(
                "/api/v1/inventory/drafts/" + draft["id"] + "/archive",
                headers=headers(other),
                json={"version": 1},
            ).status_code
            == 404
        )
    archived = browser.post(
        "/api/v1/inventory/drafts/" + draft["id"] + "/archive",
        headers=headers(browser),
        json={"version": 1},
    )
    assert archived.status_code == 200 and archived.json()["archived_at"]
    assert browser.get("/api/v1/inventory/drafts").json()["total"] == 0
    assert (
        browser.get("/api/v1/inventory/drafts", params={"status": "archived"}).json()["total"] == 1
    )
    assert (
        browser.post(
            "/api/v1/inventory/drafts/" + draft["id"] + "/post",
            headers=headers(browser),
            json={"version": 2},
        ).status_code
        == 409
    )
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(InventoryMovement)) == 0


def test_draft_create_idempotent_client_id_and_validation(draft_context):
    browser, _, item = draft_context
    data = {"id": str(uuid.uuid4()), "document_type": "receipt", "payload": {"items": []}}
    first = browser.post("/api/v1/inventory/drafts", headers=headers(browser), json=data)
    assert first.status_code == 201
    replay = browser.post("/api/v1/inventory/drafts", headers=headers(browser), json=data)
    assert replay.status_code == 200 and replay.json()["id"] == first.json()["id"]
    data["payload"]["comment"] = "Другое содержимое"
    assert (
        browser.post("/api/v1/inventory/drafts", headers=headers(browser), json=data).status_code
        == 409
    )
    for payload in [
        {"unexpected": "value"},
        {"items": [{"inventory_item_id": item["id"], "quantity": True}]},
        {"items": [{"inventory_item_id": item["id"], "quantity": 1}] * 2},
        {"recipient_employee_id": str(uuid.uuid4())},
    ]:
        assert (
            browser.post(
                "/api/v1/inventory/drafts",
                headers=headers(browser),
                json={"document_type": "receipt", "payload": payload},
            ).status_code
            == 422
        )


def test_draft_current_permissions_and_runtime_grants(draft_context):
    browser, engine, item = draft_context
    draft = create_draft(browser, item)
    actor = browser.get("/api/v1/auth/me").json()["id"]
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE users SET role_code='it_specialist' WHERE id=:id"),
            {"id": uuid.UUID(actor)},
        )
        role = browser.app.state.settings.postgres_user
        for privilege in ["SELECT", "INSERT", "UPDATE"]:
            assert connection.scalar(
                text("SELECT has_table_privilege(:role,'inventory_drafts',:privilege)"),
                {"role": role, "privilege": privilege},
            )
        assert not connection.scalar(
            text("SELECT has_table_privilege(:role,'inventory_drafts','DELETE')"), {"role": role}
        )
    assert browser.get("/api/v1/inventory/drafts").json()["total"] == 0
    assert browser.get("/api/v1/inventory/drafts/" + draft["id"]).status_code == 403
    assert (
        browser.post(
            "/api/v1/inventory/drafts/" + draft["id"] + "/post",
            headers=headers(browser),
            json={"version": 1},
        ).status_code
        == 403
    )
    issue = create_draft(browser, document_type="issue")
    assert issue["document_type"] == "issue"


def test_issue_draft_stock_failure_preserves_draft_then_concurrent_post_is_once(draft_context):
    browser, engine, item = draft_context
    department = create_reference(
        browser, "directory/departments", {"code": "DRAFT", "name": "Тестовый отдел"}
    )
    employee = create_reference(
        browser,
        "directory/employees",
        {
            "personnel_number": "DRAFT-01",
            "full_name": "Вымышленный получатель",
            "department_id": department["id"],
        },
    )
    issue = create_draft(browser, item, "issue", recipient_employee_id=employee["id"])
    path = "/api/v1/inventory/drafts/" + issue["id"]
    auth = headers(browser)
    rejected = browser.post(path + "/post", headers=auth, json={"version": 1})
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["detail"]["code"] == "insufficient_stock"
    assert browser.get(path).json()["version"] == 1
    assert browser.get(path).json()["status"] == "draft"
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(InventoryDocument)) == 0
        assert session.scalar(select(func.count()).select_from(InventoryMovement)) == 0
    receipt = create_draft(browser, item)
    received = browser.post(
        "/api/v1/inventory/drafts/" + receipt["id"] + "/post",
        headers=auth,
        json={"version": 1},
    )
    assert received.status_code == 201, received.text

    def post_issue(_):
        return browser.post(path + "/post", headers=auth, json={"version": 1})

    with ThreadPoolExecutor(max_workers=2) as pool:
        posted = list(pool.map(post_issue, range(2)))
    assert sorted(result.status_code for result in posted) == [200, 201]
    assert posted[0].json()["document"]["id"] == posted[1].json()["document"]["id"]
    assert posted[0].json()["document"]["recipient_employee_id"] == employee["id"]
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(InventoryDocument)) == 2
        assert session.scalar(select(func.sum(InventoryMovement.delta))) == 0


def test_draft_save_archive_replays_and_stale_post_version(draft_context):
    browser, _, item = draft_context
    draft = create_draft(browser, item)
    path = "/api/v1/inventory/drafts/" + draft["id"]
    payload = {**draft["payload"], "comment": "Сохранённое изменение"}
    auth = headers(browser)
    for _ in range(2):
        saved = browser.patch(path, headers=auth, json={"version": 1, "payload": payload})
        assert saved.status_code == 200 and saved.json()["version"] == 2
    stale = browser.post(path + "/post", headers=auth, json={"version": 1})
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "version_conflict"
    for _ in range(2):
        archived = browser.post(path + "/archive", headers=auth, json={"version": 2})
        assert archived.status_code == 200 and archived.json()["version"] == 3
    rejected = browser.patch(path, headers=auth, json={"version": 3, "payload": payload})
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "draft_not_editable"


def test_draft_mutations_require_csrf_and_replay_requires_current_permission(draft_context):
    browser, engine, item = draft_context
    draft = create_draft(browser, item)
    path = "/api/v1/inventory/drafts/" + draft["id"]
    for method, endpoint, payload in [
        ("post", "/api/v1/inventory/drafts", {"document_type": "receipt", "payload": {}}),
        ("patch", path, {"version": 1, "payload": {}}),
        ("post", path + "/archive", {"version": 1}),
        ("post", path + "/post", {"version": 1}),
    ]:
        rejected = browser.request(method, endpoint, json=payload)
        assert rejected.status_code == 403, rejected.text
    assert browser.get(path).json()["version"] == 1
    posted = browser.post(path + "/post", headers=headers(browser), json={"version": 1})
    assert posted.status_code == 201
    actor_id = browser.get("/api/v1/auth/me").json()["id"]
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE users SET role_code=:role WHERE id=:id"),
            {"role": "manager", "id": uuid.UUID(actor_id)},
        )
    assert browser.get("/api/v1/inventory/drafts").status_code == 403
    assert browser.get(path).status_code == 403
    replay = browser.post(path + "/post", headers=headers(browser), json={"version": 1})
    assert replay.status_code == 403
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(InventoryDocument)) == 1
        assert session.scalar(select(func.sum(InventoryMovement.delta))) == 5


def test_draft_details_survive_save_reload_and_post(draft_context):
    browser, _, item = draft_context
    draft = create_draft(browser, item, supplier_name="Черновой поставщик")
    path = "/api/v1/inventory/drafts/" + draft["id"]
    payload = {**draft["payload"], "supplier_name": "  Итоговый поставщик  "}
    saved = browser.patch(path, headers=headers(browser), json={"version": 1, "payload": payload})
    assert saved.status_code == 200, saved.text
    assert browser.get(path).json()["payload"]["supplier_name"] == "Итоговый поставщик"
    posted = browser.post(path + "/post", headers=headers(browser), json={"version": 2})
    assert posted.status_code == 201, posted.text
    assert posted.json()["document"]["supplier_name"] == "Итоговый поставщик"
    department = create_reference(
        browser, "directory/departments", {"code": "ROOM", "name": "Отдел кабинета"}
    )
    employee = create_reference(
        browser,
        "directory/employees",
        {
            "personnel_number": "ROOM-01",
            "full_name": "Получатель кабинета",
            "department_id": department["id"],
        },
    )
    draft = create_draft(
        browser, item, "issue", recipient_employee_id=employee["id"], recipient_room="  314  "
    )
    path = "/api/v1/inventory/drafts/" + draft["id"]
    assert browser.get(path).json()["payload"]["recipient_room"] == "314"
    posted = browser.post(path + "/post", headers=headers(browser), json={"version": 1})
    assert posted.status_code == 201, posted.text
    assert posted.json()["document"]["recipient_room"] == "314"
    assert posted.json()["document"]["recipient_department"] == "Отдел кабинета"


@pytest.mark.parametrize("operation", ["create", "update"])
def test_historic_draft_payload_replay_accepts_missing_optional_details(draft_context, operation):
    browser, engine, item = draft_context
    draft = create_draft(browser, item)
    historic_payload = {k: v for k, v in draft["payload"].items() if k != "supplier_name"}
    from app.modules.inventory.draft_models import InventoryDraft

    with Session(engine) as session:
        stored = session.get(InventoryDraft, uuid.UUID(draft["id"]))
        stored.payload = historic_payload
        if operation == "update":
            stored.version = 2
        session.commit()
    if operation == "create":
        replay = browser.post(
            "/api/v1/inventory/drafts",
            headers=headers(browser),
            json={"id": draft["id"], "document_type": "receipt", "payload": historic_payload},
        )
    else:
        replay = browser.patch(
            "/api/v1/inventory/drafts/" + draft["id"],
            headers=headers(browser),
            json={"version": 1, "payload": historic_payload},
        )
    assert replay.status_code == 200, replay.text
