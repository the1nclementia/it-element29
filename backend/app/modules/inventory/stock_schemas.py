import uuid
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator


class StockInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True)


class DocumentLineInput(StockInput):
    inventory_item_id: uuid.UUID
    quantity: Annotated[StrictInt, Field(ge=1, le=1_000_000)]


class DocumentInput(StockInput):
    document_date: date
    comment: str = Field(default="", max_length=2000)
    items: list[DocumentLineInput] = Field(min_length=1, max_length=100)

    @field_validator("items")
    @classmethod
    def unique_items(cls, values):
        if len({line.inventory_item_id for line in values}) != len(values):
            raise ValueError("Позиция не может повторяться в одном документе.")
        return values


class ReceiptInput(DocumentInput):
    receipt_purpose: Literal["delivery", "opening_balance"] = "delivery"
    external_number: str | None = Field(default=None, max_length=100)
    supplier_name: str | None = Field(default=None, max_length=200)


class IssueInput(DocumentInput):
    recipient_employee_id: uuid.UUID | None = None
    recipient_name: str | None = Field(default=None, max_length=300)
    recipient_building: str | None = Field(default=None, max_length=200)
    recipient_department: str | None = Field(default=None, max_length=200)
    recipient_room: str | None = Field(default=None, max_length=100)

    @field_validator(
        "recipient_name", "recipient_building", "recipient_department", "recipient_room"
    )
    @classmethod
    def trim_recipient_fields(cls, value):
        return value.strip() if value is not None else value

    @model_validator(mode="after")
    def recipient_required(self):
        if self.recipient_employee_id is None and not self.recipient_name:
            raise ValueError("Укажите сотрудника или ФИО получателя.")
        return self


class ReversalInput(StockInput):
    reason: str = Field(min_length=1, max_length=1000)


class EquipmentDocumentLineInput(StockInput):
    equipment_instance_id: uuid.UUID


class MixedDocumentInput(StockInput):
    document_date: date
    comment: str = Field(default="", max_length=2000)
    items: list[DocumentLineInput] = Field(default_factory=list, max_length=100)
    equipment_instances: list[EquipmentDocumentLineInput] = Field(
        default_factory=list, max_length=100
    )

    @field_validator("items")
    @classmethod
    def unique_items(cls, values):
        if len({line.inventory_item_id for line in values}) != len(values):
            raise ValueError("Позиция не может повторяться в одном документе.")
        return values

    @field_validator("equipment_instances")
    @classmethod
    def unique_equipment(cls, values):
        if len({line.equipment_instance_id for line in values}) != len(values):
            raise ValueError("Экземпляр не может повторяться в одном документе.")
        return values

    @model_validator(mode="after")
    def require_line(self):
        if not self.items and not self.equipment_instances:
            raise ValueError("Документ должен содержать хотя бы одну строку.")
        return self
