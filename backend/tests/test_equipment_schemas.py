import uuid

import pytest
from pydantic import ValidationError

from app.modules.equipment.movement_schemas import EquipmentMoveInput
from app.modules.equipment.schemas import EquipmentInstanceCreate, EquipmentInstancePatch
from app.modules.inventory.schemas import ItemCreate
from app.modules.inventory.stock_schemas import MixedDocumentInput
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
