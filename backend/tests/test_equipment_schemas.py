import uuid

import pytest
from pydantic import ValidationError

from app.modules.equipment.schemas import EquipmentInstanceCreate, EquipmentInstancePatch
from app.modules.inventory.schemas import ItemCreate


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
