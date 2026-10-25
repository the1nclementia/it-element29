"""Проверки forward-миграции типов документов и идентификаторов оборудования."""

import uuid

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_catalog import catalog as catalog
from test_catalog import references
from test_equipment import serialized_item
from test_stock import headers

from app.modules.identity.service import bootstrap_admin

pytestmark = pytest.mark.integration


def _document_row(actor_id, document_type):
    return {
        "id": uuid.uuid4(),
        "number": f"INV-MIG-{uuid.uuid4().hex[:12]}",
        "actor": actor_id,
        "key": uuid.uuid4(),
        "hash": "d" * 64,
        "document_type": document_type,
    }


def test_migration_replaces_only_type_checks_and_preserves_old_rows(empty_database):
    engine, _, config = empty_database
    command.upgrade(config, "0007_equipment_instances")
    with Session(engine) as session:
        actor = bootstrap_admin(
            session,
            "mixed_migration",
            "Оператор миграции",
            "Synthetic-migration-password-2026",
        )
        actor_id = actor.id
    legacy = _document_row(actor_id, "receipt")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO inventory_documents "
                "(id, number, document_type, document_date, created_by_id, "
                "idempotency_key, request_hash) "
                "VALUES (:id, :number, :document_type, '2026-10-23', "
                ":actor, :key, :hash)"
            ),
            legacy,
        )
        connection.execute(
            text(
                "INSERT INTO inventory_drafts (id, owner_id, document_type, payload) "
                "VALUES (:id, :actor, 'issue', CAST(:payload AS jsonb))"
            ),
            {"id": uuid.uuid4(), "actor": actor_id, "payload": '{"items": []}'},
        )
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(
                    text(
                        "INSERT INTO inventory_documents "
                        "(id, number, document_type, document_date, created_by_id, "
                        "idempotency_key, request_hash) "
                        "VALUES (:id, :number, 'return', '2026-10-23', :actor, :key, :hash)"
                    ),
                    _document_row(actor_id, "return"),
                )
    command.upgrade(config, "head")
    with engine.begin() as connection:
        version_length = connection.execute(
            text(
                "SELECT character_maximum_length "
                "FROM information_schema.columns "
                "WHERE table_name = 'alembic_version' AND column_name = 'version_num'"
            )
        ).scalar_one()
        assert version_length >= len("0008_mixed_documents_and_inventory_numbers")
        stored = (
            connection.execute(
                text("SELECT number, document_type FROM inventory_documents WHERE id=:id"),
                {"id": legacy["id"]},
            )
            .mappings()
            .one()
        )
        assert stored == {"number": legacy["number"], "document_type": "receipt"}
        for document_type in ("return", "replacement", "transfer"):
            connection.execute(
                text(
                    "INSERT INTO inventory_documents "
                    "(id, number, document_type, document_date, created_by_id, "
                    "idempotency_key, request_hash) "
                    "VALUES (:id, :number, :document_type, '2026-10-23', "
                    ":actor, :key, :hash)"
                ),
                _document_row(actor_id, document_type),
            )
            connection.execute(
                text(
                    "INSERT INTO inventory_drafts (id, owner_id, document_type, payload) "
                    "VALUES (:id, :actor, :document_type, CAST(:payload AS jsonb))"
                ),
                {
                    "id": uuid.uuid4(),
                    "actor": actor_id,
                    "document_type": document_type,
                    "payload": '{"items": []}',
                },
            )
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(
                    text(
                        "INSERT INTO inventory_documents "
                        "(id, number, document_type, document_date, created_by_id, "
                        "idempotency_key, request_hash) "
                        "VALUES (:id, :number, 'unknown', '2026-10-23', :actor, :key, :hash)"
                    ),
                    _document_row(actor_id, "unknown"),
                )
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(
                    text(
                        "INSERT INTO inventory_drafts (id, owner_id, document_type, payload) "
                        "VALUES (:id, :actor, 'unknown', CAST(:payload AS jsonb))"
                    ),
                    {"id": uuid.uuid4(), "actor": actor_id, "payload": '{"items": []}'},
                )


def test_inventory_number_is_globally_unique_and_searchable(catalog):
    browser, _ = catalog
    manufacturer, category = references(browser)
    item = serialized_item(browser, manufacturer, category, "MONITOR-NUMBERS")
    payload = {"inventory_item_id": item["id"], "inventory_number": " INV-REPEAT "}
    first = browser.post("/api/v1/equipment/instances", headers=headers(browser), json=payload)
    duplicate_payload = {
        **payload,
        "inventory_number": "  inv-repeat  ",
    }
    second = browser.post(
        "/api/v1/equipment/instances", headers=headers(browser), json=duplicate_payload
    )
    assert first.status_code == 201
    assert second.status_code == 409
    result = browser.get("/api/v1/equipment/instances", params={"q": "inv-repeat"})
    assert result.status_code == 200 and result.json()["total"] == 1
