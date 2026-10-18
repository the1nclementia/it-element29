import uuid

from pydantic import Field

from app.modules.inventory.schemas import CatalogInput, Code, Name, VersionInput


class DepartmentCreate(CatalogInput):
    code: Code
    name: Name


class DepartmentPatch(VersionInput):
    code: Code | None = None
    name: Name | None = None


class EmployeeCreate(CatalogInput):
    personnel_number: Code
    full_name: str = Field(min_length=1, max_length=300)
    department_id: uuid.UUID


class EmployeePatch(VersionInput):
    personnel_number: Code | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=300)
    department_id: uuid.UUID | None = None
