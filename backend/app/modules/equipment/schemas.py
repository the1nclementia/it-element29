import uuid
from typing import Annotated, Literal

from pydantic import StringConstraints, field_validator, model_validator

from app.modules.identity.schemas import InputModel
from app.modules.inventory.schemas import VersionInput

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
OptionalText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
ItemType = Literal["cartridge", "consumable", "monitor", "computer", "printer"]


class EquipmentInstanceCreate(InputModel):
    inventory_item_id: uuid.UUID
    serial_number: OptionalText | None = None
    inventory_number: OptionalText | None = None
    current_building: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None
    ) = None
    current_room: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None
    ) = None
    current_department: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None
    ) = None
    current_recipient: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None
    ) = None
    is_under_repair: bool = False

    @field_validator("serial_number", "inventory_number", mode="before")
    @classmethod
    def blank_numbers_are_missing(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value


class EquipmentInstancePatch(VersionInput):
    serial_number: OptionalText | None = None
    inventory_number: OptionalText | None = None

    @field_validator("serial_number", "inventory_number", mode="before")
    @classmethod
    def blank_numbers_are_missing(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value


class EquipmentItemFields(InputModel):
    accounting_mode: Literal["quantity", "serialized"] = "quantity"
    item_type: ItemType = "cartridge"

    @model_validator(mode="after")
    def serialized_has_equipment_type(self):
        if self.accounting_mode == "serialized" and self.item_type not in {
            "monitor",
            "computer",
            "printer",
        }:
            raise ValueError("Для поэкземплярного учёта выберите тип оборудования.")
        return self
