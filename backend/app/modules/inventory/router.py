import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.modules.identity.dependencies import CsrfSession, Database, require_permission
from app.modules.identity.models import User
from app.modules.inventory import catalog_service as service
from app.modules.inventory.models import InventoryCategory, Manufacturer, PrinterModel
from app.modules.inventory.schemas import (
    CategoryCreate,
    CategoryPatch,
    CompatibilitiesInput,
    ItemCreate,
    ItemPatch,
    ManufacturerCreate,
    ManufacturerPatch,
    PrinterModelCreate,
    PrinterModelPatch,
    VersionInput,
)

router = APIRouter(prefix="/inventory", tags=["Склад: каталог"])
Reader = Annotated[User, Depends(require_permission("inventory.read"))]
Manager = Annotated[User, Depends(require_permission("inventory.manage"))]
Archived = Literal["false", "true", "all"]


@router.get("/items")
def list_items(
    session: Database,
    actor: Reader,
    q: str = Query(default="", max_length=100),
    category_id: uuid.UUID | None = None,
    manufacturer_id: uuid.UUID | None = None,
    printer_model_id: uuid.UUID | None = None,
    in_stock: bool | None = None,
    low_stock: bool | None = None,
    archived: Archived = "false",
    sort: Literal["code", "model", "balance"] = "code",
    direction: Literal["asc", "desc"] = "asc",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    return service.list_items(
        session,
        q=q,
        category_id=category_id,
        manufacturer_id=manufacturer_id,
        printer_model_id=printer_model_id,
        in_stock=in_stock,
        low_stock=low_stock,
        archived=archived,
        sort=sort,
        direction=direction,
        offset=offset,
        limit=limit,
    )


@router.post("/items", status_code=201)
def create_item(payload: ItemCreate, session: Database, actor: Manager, csrf: CsrfSession):
    return service.save_item(session, actor, csrf.token_hash, payload)


@router.get("/items/{item_id}")
def get_item(item_id: uuid.UUID, session: Database, actor: Reader):
    return service.item_response(session, service.get_item(session, item_id))


@router.patch("/items/{item_id}")
def update_item(
    item_id: uuid.UUID, payload: ItemPatch, session: Database, actor: Manager, csrf: CsrfSession
):
    return service.save_item(session, actor, csrf.token_hash, payload, item_id)


@router.post("/items/{item_id}/archive")
def archive_item(
    item_id: uuid.UUID, payload: VersionInput, session: Database, actor: Manager, csrf: CsrfSession
):
    return service.archive_item(session, actor, csrf.token_hash, item_id, payload.version, True)


@router.post("/items/{item_id}/restore")
def restore_item(
    item_id: uuid.UUID, payload: VersionInput, session: Database, actor: Manager, csrf: CsrfSession
):
    return service.archive_item(session, actor, csrf.token_hash, item_id, payload.version, False)


@router.get("/items/{item_id}/compatibilities")
def list_compatibilities(item_id: uuid.UUID, session: Database, actor: Reader):
    return service.list_compatibilities(session, item_id)


@router.put("/items/{item_id}/compatibilities")
def set_compatibilities(
    item_id: uuid.UUID,
    payload: CompatibilitiesInput,
    session: Database,
    actor: Manager,
    csrf: CsrfSession,
):
    return service.set_compatibilities(session, actor, csrf.token_hash, item_id, payload)


@router.get("/manufacturers")
def manufacturers(
    session: Database,
    actor: Reader,
    q: str = Query(default="", max_length=100),
    archived: Archived = "false",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    return service.list_references(
        session, Manufacturer, q=q, archived=archived, offset=offset, limit=limit
    )


@router.post("/manufacturers", status_code=201)
def create_manufacturer(
    payload: ManufacturerCreate, session: Database, actor: Manager, csrf: CsrfSession
):
    return service.save_reference(session, actor, csrf.token_hash, Manufacturer, payload)


@router.patch("/manufacturers/{record_id}")
def update_manufacturer(
    record_id: uuid.UUID,
    payload: ManufacturerPatch,
    session: Database,
    actor: Manager,
    csrf: CsrfSession,
):
    return service.save_reference(session, actor, csrf.token_hash, Manufacturer, payload, record_id)


@router.post("/manufacturers/{record_id}/archive")
def archive_manufacturer(
    record_id: uuid.UUID,
    payload: VersionInput,
    session: Database,
    actor: Manager,
    csrf: CsrfSession,
):
    return service.archive_reference(
        session, actor, csrf.token_hash, Manufacturer, record_id, payload.version, True
    )


@router.post("/manufacturers/{record_id}/restore")
def restore_manufacturer(
    record_id: uuid.UUID,
    payload: VersionInput,
    session: Database,
    actor: Manager,
    csrf: CsrfSession,
):
    return service.archive_reference(
        session, actor, csrf.token_hash, Manufacturer, record_id, payload.version, False
    )


@router.get("/categories")
def categories(
    session: Database,
    actor: Reader,
    q: str = Query(default="", max_length=100),
    archived: Archived = "false",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    return service.list_references(
        session, InventoryCategory, q=q, archived=archived, offset=offset, limit=limit
    )


@router.post("/categories", status_code=201)
def create_category(payload: CategoryCreate, session: Database, actor: Manager, csrf: CsrfSession):
    return service.save_reference(session, actor, csrf.token_hash, InventoryCategory, payload)


@router.patch("/categories/{record_id}")
def update_category(
    record_id: uuid.UUID,
    payload: CategoryPatch,
    session: Database,
    actor: Manager,
    csrf: CsrfSession,
):
    return service.save_reference(
        session, actor, csrf.token_hash, InventoryCategory, payload, record_id
    )


@router.post("/categories/{record_id}/archive")
def archive_category(
    record_id: uuid.UUID,
    payload: VersionInput,
    session: Database,
    actor: Manager,
    csrf: CsrfSession,
):
    return service.archive_reference(
        session, actor, csrf.token_hash, InventoryCategory, record_id, payload.version, True
    )


@router.post("/categories/{record_id}/restore")
def restore_category(
    record_id: uuid.UUID,
    payload: VersionInput,
    session: Database,
    actor: Manager,
    csrf: CsrfSession,
):
    return service.archive_reference(
        session, actor, csrf.token_hash, InventoryCategory, record_id, payload.version, False
    )


@router.get("/printer-models")
def printer_models(
    session: Database,
    actor: Reader,
    q: str = Query(default="", max_length=100),
    manufacturer_id: uuid.UUID | None = None,
    archived: Archived = "false",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    return service.list_references(
        session,
        PrinterModel,
        q=q,
        manufacturer_id=manufacturer_id,
        archived=archived,
        offset=offset,
        limit=limit,
    )


@router.post("/printer-models", status_code=201)
def create_printer_model(
    payload: PrinterModelCreate, session: Database, actor: Manager, csrf: CsrfSession
):
    return service.save_reference(session, actor, csrf.token_hash, PrinterModel, payload)


@router.patch("/printer-models/{record_id}")
def update_printer_model(
    record_id: uuid.UUID,
    payload: PrinterModelPatch,
    session: Database,
    actor: Manager,
    csrf: CsrfSession,
):
    return service.save_reference(session, actor, csrf.token_hash, PrinterModel, payload, record_id)


@router.post("/printer-models/{record_id}/archive")
def archive_printer_model(
    record_id: uuid.UUID,
    payload: VersionInput,
    session: Database,
    actor: Manager,
    csrf: CsrfSession,
):
    return service.archive_reference(
        session, actor, csrf.token_hash, PrinterModel, record_id, payload.version, True
    )


@router.post("/printer-models/{record_id}/restore")
def restore_printer_model(
    record_id: uuid.UUID,
    payload: VersionInput,
    session: Database,
    actor: Manager,
    csrf: CsrfSession,
):
    return service.archive_reference(
        session, actor, csrf.token_hash, PrinterModel, record_id, payload.version, False
    )
