import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.db.provision import provision_runtime_role
from app.main import create_app
from app.modules.directory.models import Department, Employee, Location
from app.modules.identity.models import AuditLog, User
from app.modules.identity.security import hash_password
from app.modules.identity.service import bootstrap_admin

pytestmark = pytest.mark.integration


def test_inventory_schema_and_additive_upgrade(empty_database):
    engine, _, config = empty_database
    command.upgrade(config, "0002_identity")
    department_id, employee_id, location_id = [uuid.uuid4() for _ in range(3)]
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO departments(id,code,name) VALUES (:id,:code,:name)"),
            {"id": department_id, "code": "PRESERVE", "name": "Сохранить"},
        )
        connection.execute(
            text(
                "INSERT INTO employees(id,personnel_number,full_name,department_id) "
                "VALUES (:id,:number,:name,:department)"
            ),
            {
                "id": employee_id,
                "number": "PRESERVE-01",
                "name": "Вымышленный сотрудник этапа 2",
                "department": department_id,
            },
        )
        connection.execute(
            text(
                "INSERT INTO locations(id,code,name,department_id) "
                "VALUES (:id,:code,:name,:department)"
            ),
            {
                "id": location_id,
                "code": "PRESERVE-LOC",
                "name": "Тестовое помещение",
                "department": department_id,
            },
        )
    with Session(engine) as session:
        admin = bootstrap_admin(session, "preserved_admin", "Администратор этапа 2", PASSWORD)
        from app.modules.identity.models import User

        admin_id = admin.id
        password_hash = session.get(User, admin_id).password_hash
        original_audit = session.scalar(select(AuditLog).where(AuditLog.action == "user.bootstrap"))
        audit_id, audit_time = original_audit.id, original_audit.occurred_at

    command.upgrade(config, "head")
    tables = inspect(engine).get_table_names()
    assert "inventory_movements" in tables
    from app.modules.inventory.models import InventoryCategory

    with Session(engine) as session:
        assert session.scalar(select(Department).where(Department.code == "PRESERVE")).version == 1
        assert session.get(Employee, employee_id).full_name == "Вымышленный сотрудник этапа 2"
        assert session.get(Employee, employee_id).version == 1
        assert session.get(Location, location_id).department_id == department_id
        assert session.get(User, admin_id).password_hash == password_hash
        assert session.get(AuditLog, audit_id).occurred_at == audit_time
        assert session.get(AuditLog, audit_id).actor_id == admin_id
        assert session.scalar(
            select(InventoryCategory).where(InventoryCategory.code == "cartridges")
        )
    command.check(config)


PASSWORD = "Synthetic-catalog-password-2026"


def headers(client):
    return {
        "Origin": "http://testserver",
        "X-CSRF-Token": client.get("/api/v1/auth/csrf").json()["csrf_token"],
    }


@pytest.fixture()
def catalog(database):
    engine, settings, _ = database
    with Session(engine) as session:
        bootstrap_admin(session, "catalog_admin", "Оператор каталога", PASSWORD)
    role = "catalog_runtime_" + uuid.uuid4().hex[:12]
    with engine.begin() as connection:
        provision_runtime_role(connection, role, PASSWORD + "-runtime")
    settings = settings.model_copy(
        update={
            "postgres_user": role,
            "postgres_password": settings.postgres_password.__class__(PASSWORD + "-runtime"),
        }
    )
    app = create_app(settings)
    # Registration belongs to main integration; avoid duplicate routes after registration.
    if "/api/v1/inventory/items" not in app.openapi()["paths"]:
        from app.modules.directory.router import router as directory_router
        from app.modules.inventory.router import router

        app.include_router(router, prefix="/api/v1")
        app.include_router(directory_router, prefix="/api/v1")
    with TestClient(app) as client:
        result = client.post(
            "/api/v1/auth/login",
            headers=headers(client),
            json={"username": "catalog_admin", "password": PASSWORD},
        )
        assert result.status_code == 200, result.text
        yield client, engine


def create(client, path, payload):
    response = client.post("/api/v1/" + path, json=payload, headers=headers(client))
    assert response.status_code == 201, response.text
    return response.json()


def references(client):
    manufacturer = create(client, "inventory/manufacturers", {"name": "Производитель"})
    category = client.get("/api/v1/inventory/categories").json()["items"][0]
    return manufacturer, category


def item_create(client, manufacturer, category, code="test-01", **kwargs):
    return create(
        client,
        "inventory/items",
        {
            "internal_code": code,
            "manufacturer_id": manufacturer["id"],
            "category_id": category["id"],
            "model": "Картридж",
            "min_stock": 2,
            **kwargs,
        },
    )


def test_catalog_normalization_versions_search_and_immutable_code(catalog):
    client, _ = catalog
    manufacturer, category = references(client)
    item = item_create(client, manufacturer, category, model="Модель 100%_точно")
    assert item["internal_code"] == "TEST-01"
    assert item["balance"] == 0 and item["unit"] == "pcs" and item["is_low_stock"]
    assert client.get("/api/v1/inventory/items", params={"q": "100%_"}).json()["total"] == 1
    assert client.get("/api/v1/inventory/items", params={"q": "100X"}).json()["total"] == 0
    response = client.patch(
        "/api/v1/inventory/items/" + item["id"],
        headers=headers(client),
        json={"version": 1, "model": "Изменение"},
    )
    assert response.status_code == 200 and response.json()["version"] == 2
    assert (
        client.patch(
            "/api/v1/inventory/items/" + item["id"],
            headers=headers(client),
            json={"version": 1, "model": "Устаревшее"},
        ).status_code
        == 409
    )
    assert (
        client.patch(
            "/api/v1/inventory/items/" + item["id"],
            headers=headers(client),
            json={"version": 2, "internal_code": "NEW"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/inventory/manufacturers",
            headers=headers(client),
            json={"name": "  ПРОИЗВОДИТЕЛЬ  "},
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/v1/inventory/items",
            headers=headers(client),
            json={
                "internal_code": "TEST-01",
                "manufacturer_id": manufacturer["id"],
                "category_id": category["id"],
                "model": "Дубль",
            },
        ).status_code
        == 409
    )


def test_compatibilities_archive_restore_and_inactive_references(catalog):
    client, engine = catalog
    manufacturer, category = references(client)
    item = item_create(client, manufacturer, category)
    printer = create(
        client,
        "inventory/printer-models",
        {"manufacturer_id": manufacturer["id"], "model": "Лазерный принтер"},
    )
    path = "/api/v1/inventory/items/" + item["id"] + "/compatibilities"
    response = client.put(
        path, headers=headers(client), json={"version": 1, "printer_model_ids": [printer["id"]]}
    )
    assert response.status_code == 200, response.text
    assert client.get(path).json()["total"] == 1
    assert (
        client.put(
            path,
            headers=headers(client),
            json={"version": 2, "printer_model_ids": [printer["id"], printer["id"]]},
        ).status_code
        == 422
    )
    assert (
        client.put(
            path, headers=headers(client), json={"version": 2, "printer_model_ids": []}
        ).status_code
        == 200
    )
    assert client.get(path).json()["total"] == 0
    assert (
        client.put(
            path, headers=headers(client), json={"version": 3, "printer_model_ids": [printer["id"]]}
        ).status_code
        == 200
    )
    from sqlalchemy import func

    from app.modules.inventory.models import InventoryCompatibility

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(InventoryCompatibility)) == 1
    response = client.post(
        "/api/v1/inventory/items/" + item["id"] + "/archive",
        headers=headers(client),
        json={"version": 4},
    )
    assert response.status_code == 200
    assert client.get("/api/v1/inventory/items").json()["total"] == 0
    assert client.get("/api/v1/inventory/items", params={"archived": "true"}).json()["total"] == 1
    response = client.post(
        "/api/v1/inventory/items/" + item["id"] + "/restore",
        headers=headers(client),
        json={"version": 5},
    )
    assert response.status_code == 200 and response.json()["archived_at"] is None
    assert (
        client.post(
            "/api/v1/inventory/manufacturers/" + manufacturer["id"] + "/archive",
            headers=headers(client),
            json={"version": 1},
        ).status_code
        == 200
    )
    response = client.post(
        "/api/v1/inventory/items",
        headers=headers(client),
        json={
            "internal_code": "TEST-02",
            "manufacturer_id": manufacturer["id"],
            "category_id": category["id"],
            "model": "Архивный",
        },
    )
    assert response.status_code == 409


def test_directory_archive_blocks_active_employees_and_versions(catalog):
    client, _ = catalog
    department = create(client, "directory/departments", {"code": "it", "name": "Отдел"})
    employee = create(
        client,
        "directory/employees",
        {
            "personnel_number": "SYN-01",
            "full_name": "Вымышленный получатель",
            "department_id": department["id"],
        },
    )
    path = "/api/v1/directory/departments/" + department["id"] + "/archive"
    assert client.post(path, headers=headers(client), json={"version": 1}).status_code == 409
    assert (
        client.post(
            "/api/v1/directory/employees/" + employee["id"] + "/archive",
            headers=headers(client),
            json={"version": 1},
        ).status_code
        == 200
    )
    assert client.post(path, headers=headers(client), json={"version": 1}).status_code == 200
    assert (
        client.post(
            "/api/v1/directory/employees/" + employee["id"] + "/restore",
            headers=headers(client),
            json={"version": 2},
        ).status_code
        == 409
    )
    assert client.get("/api/v1/directory/employees").json()["total"] == 0
    assert (
        client.get("/api/v1/directory/employees", params={"archived": "all"}).json()["total"] == 1
    )


def test_catalog_concurrent_edits_reject_stale_version(catalog):
    client, _ = catalog
    manufacturer, category = references(client)
    item = item_create(client, manufacturer, category)
    auth = headers(client)

    def edit(model):
        return client.patch(
            "/api/v1/inventory/items/" + item["id"],
            headers=auth,
            json={"version": 1, "model": model},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(edit, ["Вариант один", "Вариант два"]))
    assert sorted(result) == [200, 409]
    assert client.get("/api/v1/inventory/items/" + item["id"]).json()["version"] == 2


def test_catalog_audit_failure_rolls_back_record(catalog, monkeypatch):
    client, engine = catalog
    from app.modules.inventory import catalog_service
    from app.modules.inventory.models import Manufacturer

    def broken_audit(*args, **kwargs):
        raise RuntimeError("Synthetic audit failure")

    monkeypatch.setattr(catalog_service, "audit", broken_audit)
    with pytest.raises(RuntimeError, match="Synthetic audit failure"):
        client.post(
            "/api/v1/inventory/manufacturers",
            headers=headers(client),
            json={"name": "Не фиксировать"},
        )
    with Session(engine) as session:
        assert session.scalar(select(Manufacturer)) is None


@pytest.mark.parametrize(
    "role,catalog_status,directory_status",
    [
        ("manager", 403, 403),
        ("it_specialist", 403, 403),
        ("storekeeper", 201, 403),
        ("administrator", 201, 201),
    ],
)
def test_catalog_and_directory_permissions_enforced_on_api(
    catalog, role, catalog_status, directory_status
):
    client, engine = catalog
    with Session(engine) as session:
        session.add(
            User(
                username="role_user",
                display_name="Проверка прав",
                password_hash=hash_password(PASSWORD),
                role_code=role,
                is_active=True,
                must_change_password=False,
            )
        )
        session.commit()
    client.post("/api/v1/auth/logout", headers=headers(client))
    response = client.post(
        "/api/v1/auth/login",
        headers=headers(client),
        json={"username": "role_user", "password": PASSWORD},
    )
    assert response.status_code == 200
    for path in [
        "inventory/items",
        "inventory/manufacturers",
        "inventory/categories",
        "inventory/printer-models",
        "directory/employees",
        "directory/departments",
    ]:
        assert client.get("/api/v1/" + path).status_code == 200
    assert (
        client.post(
            "/api/v1/inventory/manufacturers", headers=headers(client), json={"name": "Справочник"}
        ).status_code
        == catalog_status
    )
    assert (
        client.post(
            "/api/v1/directory/departments",
            headers=headers(client),
            json={"code": "NEW", "name": "Подразделение"},
        ).status_code
        == directory_status
    )
    client.post("/api/v1/auth/logout", headers=headers(client))
    assert client.get("/api/v1/inventory/items").status_code == 401


def test_runtime_grants_for_stage3_are_minimal(catalog):
    client, engine = catalog
    role = client.app.state.settings.postgres_user
    with engine.connect() as connection:
        for table in [
            "manufacturers",
            "inventory_categories",
            "printer_models",
            "inventory_items",
            "inventory_compatibilities",
            "departments",
            "employees",
            "inventory_item_attachments",
        ]:
            assert connection.scalar(
                text("SELECT has_table_privilege(:role,:table,'SELECT, INSERT, UPDATE')"),
                {"role": role, "table": table},
            )
            assert not connection.scalar(
                text("SELECT has_table_privilege(:role,:table,'DELETE')"),
                {"role": role, "table": table},
            )
        for table in [
            "inventory_documents",
            "inventory_document_items",
            "inventory_movements",
            "file_attachments",
            "audit_logs",
        ]:
            assert connection.scalar(
                text("SELECT has_table_privilege(:role,:table,'SELECT, INSERT')"),
                {"role": role, "table": table},
            )
            for privilege in ["UPDATE", "DELETE", "TRUNCATE"]:
                assert not connection.scalar(
                    text("SELECT has_table_privilege(:role,:table,:privilege)"),
                    {"role": role, "table": table, "privilege": privilege},
                )
        assert connection.scalar(
            text("SELECT has_sequence_privilege(:role,'inventory_document_number_seq','USAGE')"),
            {"role": role},
        )
        for sequence in ("inventory_category_code_seq", "inventory_item_code_seq"):
            assert connection.scalar(
                text("SELECT has_sequence_privilege(:role,:sequence,'USAGE')"),
                {"role": role, "sequence": sequence},
            )
        assert not connection.scalar(
            text("SELECT has_schema_privilege(:role,'public','CREATE')"), {"role": role}
        )


def test_category_names_are_unique_across_case_whitespace_edits_and_archive(catalog):
    client, _ = catalog
    first = create(client, "inventory/categories", {"code": "cables", "name": "USB Кабели"})
    second = create(client, "inventory/categories", {"code": "keyboards", "name": "Клавиатуры"})
    duplicate = client.post(
        "/api/v1/inventory/categories",
        headers=headers(client),
        json={"code": "cables-copy", "name": "  usb   КАБЕЛИ  "},
    )
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["detail"]["code"] == "duplicate_record"
    edited = client.patch(
        "/api/v1/inventory/categories/" + second["id"],
        headers=headers(client),
        json={"version": 1, "name": "usb кабели"},
    )
    assert edited.status_code == 409, edited.text
    same = client.patch(
        "/api/v1/inventory/categories/" + first["id"],
        headers=headers(client),
        json={"version": 1, "name": "USB кабели"},
    )
    assert same.status_code == 200, same.text
    archived = client.post(
        "/api/v1/inventory/categories/" + first["id"] + "/archive",
        headers=headers(client),
        json={"version": 2},
    )
    assert archived.status_code == 200
    duplicate = client.post(
        "/api/v1/inventory/categories",
        headers=headers(client),
        json={"code": "cables-new", "name": "USB КАБЕЛИ"},
    )
    assert duplicate.status_code == 409, duplicate.text
    assert client.get("/api/v1/inventory/categories", params={"q": "USB"}).json()["total"] == 0
    assert (
        client.get("/api/v1/inventory/categories", params={"q": "USB", "archived": "all"}).json()[
            "total"
        ]
        == 1
    )


def test_concurrent_category_names_cannot_create_duplicates(catalog):
    client, _ = catalog
    auth = headers(client)

    def create_category(entry):
        return client.post("/api/v1/inventory/categories", headers=auth, json=entry)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                create_category,
                [
                    {"code": "cables-a", "name": "USB Кабели"},
                    {"code": "cables-b", "name": "usb   КАБЕЛИ"},
                ],
            )
        )
    assert sorted(result.status_code for result in results) == [201, 409], [
        result.text for result in results
    ]


def test_server_generates_stable_codes_without_changing_explicit_codes(catalog):
    client, _ = catalog
    manufacturer, category = references(client)
    generated_category = create(client, "inventory/categories", {"name": "Автокоды"})
    assert generated_category["code"].startswith("CAT-")
    renamed_category = client.patch(
        "/api/v1/inventory/categories/" + generated_category["id"],
        headers=headers(client),
        json={"version": 1, "name": "Переименованные автокоды"},
    )
    assert renamed_category.status_code == 200
    assert renamed_category.json()["code"] == generated_category["code"]
    generated_item = create(
        client,
        "inventory/items",
        {
            "manufacturer_id": manufacturer["id"],
            "category_id": generated_category["id"],
            "model": "Картридж",
        },
    )
    assert generated_item["internal_code"].startswith("ITEM-")
    updated = client.patch(
        "/api/v1/inventory/items/" + generated_item["id"],
        headers=headers(client),
        json={"version": 1, "model": "Новая модель"},
    )
    assert updated.status_code == 200
    assert updated.json()["internal_code"] == generated_item["internal_code"]

    explicit_category = create(
        client,
        "inventory/categories",
        {"code": "legacy-category", "name": "Старый код категории"},
    )
    explicit_item = create(
        client,
        "inventory/items",
        {
            "internal_code": "legacy-item",
            "manufacturer_id": manufacturer["id"],
            "category_id": explicit_category["id"],
            "model": "Существующий код",
        },
    )
    assert explicit_category["code"] == "legacy-category"
    assert explicit_item["internal_code"] == "LEGACY-ITEM"
