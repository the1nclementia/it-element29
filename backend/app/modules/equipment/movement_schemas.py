import uuid
from datetime import date
from typing import Annotated

from pydantic import ConfigDict, Field, model_validator

from app.modules.identity.schemas import InputModel

Text = Annotated[str, Field(min_length=1, max_length=300)]


class EquipmentMoveLine(InputModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True)
    equipment_instance_id: uuid.UUID
    version: int = Field(ge=1)
    current_building: str | None = Field(default=None, max_length=200)
    current_room: str | None = Field(default=None, max_length=100)
    current_department: str | None = Field(default=None, max_length=200)
    current_recipient: str | None = Field(default=None, max_length=300)


class EquipmentMoveInput(InputModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True)
    document_date: date
    destination_building: str | None = Field(default=None, max_length=200)
    destination_room: str | None = Field(default=None, max_length=100)
    destination_department: str | None = Field(default=None, max_length=200)
    destination_recipient: str | None = Field(default=None, max_length=300)
    comment: str = Field(default="", max_length=2000)
    items: list[EquipmentMoveLine] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_destination_and_items(self):
        if not any(
            value
            for value in (
                self.destination_building,
                self.destination_room,
                self.destination_department,
                self.destination_recipient,
            )
        ):
            raise ValueError("Укажите хотя бы один реквизит пункта назначения.")
        if len({line.equipment_instance_id for line in self.items}) != len(self.items):
            raise ValueError("Экземпляр не может повторяться в одном перемещении.")
        return self
