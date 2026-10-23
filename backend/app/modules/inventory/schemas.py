import re
import uuid
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator, model_validator

from app.modules.identity.schemas import InputModel

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class CatalogInput(InputModel):
    @field_validator("*", mode="before")
    @classmethod
    def strip_strings(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def reject_nulls(self):
        for name in self.model_fields_set:
            if getattr(self, name) is None and name != "article":
                raise ValueError("Поле не может быть пустым")
        return self


class VersionInput(CatalogInput):
    version: int = Field(strict=True, ge=1)


class ManufacturerCreate(CatalogInput):
    name: Name


class ManufacturerPatch(VersionInput):
    name: Name | None = None


class CategoryCreate(CatalogInput):
    code: Code | None = None
    name: Name

    @field_validator("code", mode="before")
    @classmethod
    def category_code(cls, value):
        if value is None:
            return value
        value = value.lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", value):
            raise ValueError("Код категории: латинские буквы, цифры, дефис или подчёркивание")
        return value


class CategoryPatch(VersionInput):
    name: Name | None = None


class PrinterModelCreate(CatalogInput):
    manufacturer_id: uuid.UUID
    model: Name


class PrinterModelPatch(VersionInput):
    manufacturer_id: uuid.UUID | None = None
    model: Name | None = None


class ItemFields(CatalogInput):
    category_id: uuid.UUID
    manufacturer_id: uuid.UUID
    model: Name
    article: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = None
    description: str = Field(default="", max_length=5000)
    min_stock: int = Field(default=0, strict=True, ge=0, le=9_007_199_254_740_991)
    accounting_mode: Literal["quantity", "serialized"] = "quantity"
    item_type: Literal["cartridge", "consumable", "monitor", "computer", "printer"] = "cartridge"

    @model_validator(mode="after")
    def serialized_has_equipment_type(self):
        if self.accounting_mode == "serialized" and self.item_type not in {
            "monitor",
            "computer",
            "printer",
        }:
            raise ValueError("Для поэкземплярного учёта выберите тип оборудования.")
        return self


class ItemCreate(ItemFields):
    internal_code: Code | None = None

    @field_validator("internal_code")
    @classmethod
    def uppercase_code(cls, value):
        return value.upper() if value is not None else value


class ItemPatch(VersionInput):
    category_id: uuid.UUID | None = None
    manufacturer_id: uuid.UUID | None = None
    model: Name | None = None
    article: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = None
    description: str | None = Field(default=None, max_length=5000)
    min_stock: int | None = Field(default=None, strict=True, ge=0, le=9_007_199_254_740_991)
    accounting_mode: Literal["quantity", "serialized"] | None = None
    item_type: Literal["cartridge", "consumable", "monitor", "computer", "printer"] | None = None

    @model_validator(mode="after")
    def validate_serialized_type(self):
        if self.accounting_mode == "serialized" and self.item_type in {"cartridge", "consumable"}:
            raise ValueError("Для поэкземплярного учёта выберите тип оборудования.")
        return self


class CompatibilitiesInput(VersionInput):
    printer_model_ids: list[uuid.UUID] = Field(max_length=100)

    @field_validator("printer_model_ids")
    @classmethod
    def unique_models(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Модель принтера указана несколько раз")
        return value
