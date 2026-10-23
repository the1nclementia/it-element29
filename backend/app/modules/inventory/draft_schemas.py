import uuid
from datetime import date
from typing import Literal

from pydantic import Field, field_validator

from app.modules.inventory.stock_schemas import DocumentLineInput, StockInput


class DraftPayload(StockInput):
    document_date: date | None = None
    comment: str = Field(default="", max_length=2000)
    items: list[DocumentLineInput] = Field(default_factory=list, max_length=100)

    @field_validator("items")
    @classmethod
    def unique_items(cls, value):
        if len({line.inventory_item_id for line in value}) != len(value):
            raise ValueError("Позиция не может повторяться в одном черновике.")
        return value


class ReceiptDraftPayload(DraftPayload):
    receipt_purpose: Literal["delivery", "opening_balance"] = "delivery"
    external_number: str | None = Field(default=None, max_length=100)
    supplier_name: str | None = Field(default=None, max_length=200)


class IssueDraftPayload(DraftPayload):
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


class DraftCreate(StockInput):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    document_type: Literal["receipt", "issue"]
    payload: dict


class DraftVersion(StockInput):
    version: int = Field(strict=True, ge=1)


class DraftUpdate(DraftVersion):
    payload: dict
