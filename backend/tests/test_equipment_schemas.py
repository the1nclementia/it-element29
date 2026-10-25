import importlib.util
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.modules.equipment.models import EquipmentInstance
from app.modules.equipment.movement_schemas import EquipmentMoveInput
from app.modules.equipment.schemas import EquipmentInstanceCreate, EquipmentInstancePatch
from app.modules.inventory import document_service, stock_service
from app.modules.inventory.schemas import ItemCreate
from app.modules.inventory.stock_schemas import (
    MixedDocumentInput,
    MixedIssueInput,
    MixedReceiptInput,
)
from app.modules.inventory.stock_service import request_hash


def test_item_declares_accounting_mode_and_equipment_type():
    value = ItemCreate(
        category_id=uuid.uuid4(),
        manufacturer_id=uuid.uuid4(),
        model="Dell P2422H",
        accounting_mode="serialized",
        item_type="monitor",
    )
    assert value.accounting_mode == "serialized"
    assert value.item_type == "monitor"


def test_item_rejects_serialized_without_equipment_type():
    with pytest.raises(ValidationError):
        ItemCreate(
            category_id=uuid.uuid4(),
            manufacturer_id=uuid.uuid4(),
            model="Dell P2422H",
            accounting_mode="serialized",
        )


def test_instance_allows_missing_numbers_but_never_invents_them():
    item_id = uuid.uuid4()
    value = EquipmentInstanceCreate(inventory_item_id=item_id, serial_number="  ")
    assert value.inventory_item_id == item_id
    assert value.serial_number is None
    assert value.inventory_number is None


def test_instance_patch_trims_identifiers():
    value = EquipmentInstancePatch(
        version=1,
        serial_number="  SN-42 ",
        inventory_number=" INV-42 ",
    )
    assert value.serial_number == "SN-42"
    assert value.inventory_number == "INV-42"


def test_instance_numbers_are_bounded():
    with pytest.raises(ValidationError):
        EquipmentInstanceCreate(inventory_item_id=uuid.uuid4(), serial_number="x" * 201)


def test_inventory_number_metadata_matches_partial_unique_index():
    index = next(
        index
        for index in EquipmentInstance.__table__.indexes
        if index.name == "uq_equipment_instances_inventory_number_key"
    )
    assert index.unique is True
    assert str(index.dialect_options["postgresql"]["where"]) == (
        "inventory_number_key IS NOT NULL AND btrim(inventory_number_key) <> ''"
    )


def test_mixed_document_requires_a_line_and_rejects_duplicate_instances():
    with pytest.raises(ValidationError):
        MixedDocumentInput(document_date="2026-10-23")
    instance_id = uuid.uuid4()
    with pytest.raises(ValidationError):
        MixedDocumentInput(
            document_date="2026-10-23",
            equipment_instances=[
                {"equipment_instance_id": instance_id},
                {"equipment_instance_id": instance_id},
            ],
        )


def test_mixed_documents_accept_new_equipment_registration_and_issue_details():
    item_id = uuid.uuid4()
    receipt = MixedReceiptInput(
        document_date="2026-10-24",
        items=[{"inventory_item_id": item_id, "quantity": 4}],
        equipment_instances=[
            {
                "inventory_item_id": item_id,
                "serial_number": " SN-100 ",
                "inventory_number": " INV-100 ",
            }
        ],
        receipt_purpose="delivery",
    )
    assert receipt.equipment_instances[0].inventory_item_id == item_id
    assert receipt.equipment_instances[0].serial_number == "SN-100"
    issue = MixedIssueInput(
        document_date="2026-10-24",
        equipment_instances=[{"equipment_instance_id": uuid.uuid4()}],
        recipient_name="  Иванов И.И.  ",
        recipient_building=" Корпус А ",
    )
    assert issue.recipient_name == "Иванов И.И."
    assert issue.recipient_building == "Корпус А"


def test_mixed_equipment_line_requires_existing_or_new_instance_source():
    with pytest.raises(ValidationError):
        MixedReceiptInput(
            document_date="2026-10-24",
            equipment_instances=[{}],
        )


def test_equipment_move_requires_destination_and_preserves_expected_placement():
    instance_id = uuid.uuid4()
    with pytest.raises(ValidationError):
        EquipmentMoveInput(
            document_date="2026-10-23",
            items=[{"equipment_instance_id": instance_id, "version": 1}],
        )
    value = EquipmentMoveInput(
        document_date="2026-10-23",
        destination_building="Корпус Б",
        items=[
            {
                "equipment_instance_id": instance_id,
                "version": 3,
                "current_building": "Корпус А",
                "current_room": "305",
            }
        ],
    )
    assert value.items[0].version == 3
    assert value.destination_building == "Корпус Б"


def test_movement_idempotency_hash_accepts_equipment_items():
    first = request_hash(
        {
            "items": [{"equipment_instance_id": str(uuid.uuid4()), "version": 1}],
            "destination_building": "A",
        }
    )
    assert len(first) == 64


def test_transfer_cannot_use_quantity_reversal_endpoint():
    with pytest.raises(Exception) as error:
        stock_service.ensure_cancellable_document_type("transfer")
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "transfer_cancel_not_supported"
    stock_service.ensure_cancellable_document_type("issue")


def test_equipment_document_line_has_additive_response_shape():
    line = type(
        "Line",
        (),
        {
            "id": uuid.UUID(int=1),
            "line_number": 2,
            "equipment_instance_id": uuid.UUID(int=2),
            "internal_code": "MON-001",
            "model": "Monitor",
            "manufacturer": "Vendor",
            "serial_number": None,
            "inventory_number": "INV-001",
        },
    )()
    assert document_service.equipment_item_response(line) == {
        "id": line.id,
        "line_number": 2,
        "equipment_instance_id": line.equipment_instance_id,
        "internal_code": "MON-001",
        "model": "Monitor",
        "manufacturer": "Vendor",
        "serial_number": None,
        "inventory_number": "INV-001",
    }


def test_inventory_number_migration_reports_normalized_duplicates():
    path = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "0009_inventory_number_uniqueness.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0009", path)
    migration = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(migration)
    assert migration.duplicate_inventory_number_keys(
        [
            {"inventory_number_key": "inv-001", "duplicate_count": 2},
            {"inventory_number_key": "inv-002", "duplicate_count": 3},
        ]
    ) == [("inv-001", 2), ("inv-002", 3)]


def test_inventory_number_migration_stops_before_index_creation_on_duplicates(monkeypatch):
    path = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "0009_inventory_number_uniqueness.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0009_duplicates", path)
    migration = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(migration)

    class DuplicateRows:
        def mappings(self):
            return [{"inventory_number_key": "inv-001", "duplicate_count": 2}]

    class ReadOnlyConnection:
        def execute(self, statement):
            assert "GROUP BY inventory_number_key" in str(statement)
            return DuplicateRows()

    created_indexes = []
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(
            get_bind=ReadOnlyConnection,
            create_index=lambda *args, **kwargs: created_indexes.append((args, kwargs)),
        ),
    )

    with pytest.raises(RuntimeError, match=r"найдены дубликаты inv-001 \(2\)"):
        migration.upgrade()

    assert created_indexes == []


def test_mixed_migration_declares_room_for_its_revision_in_alembic_version():
    path = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "0008_mixed_documents_and_inventory_numbers.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0008", path)
    migration = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(migration)
    assert migration.ALEMBIC_VERSION_COLUMN_LENGTH >= len(migration.revision)
