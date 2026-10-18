import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.modules.files import service
from app.modules.files.schemas import Photo, PhotoList, PhotoUpdate
from app.modules.identity.dependencies import CsrfSession, Database, require_permission
from app.modules.identity.errors import fail
from app.modules.identity.models import User

router = APIRouter(prefix="/inventory/items/{item_id}/photos", tags=["photos"])
Reader = Annotated[User, Depends(require_permission("inventory.read"))]
Manager = Annotated[User, Depends(require_permission("inventory.manage"))]


@router.get("", response_model=PhotoList)
def list_photos(item_id: uuid.UUID, session: Database, actor: Reader):
    return service.list_photos(session, item_id)


@router.post("", response_model=Photo, status_code=201)
async def add_photo(
    item_id: uuid.UUID, request: Request, session: Database, actor: Manager, csrf: CsrfSession
):
    settings = request.app.state.settings
    try:
        async with request.form(
            max_files=1, max_fields=0, max_part_size=settings.photo_max_bytes
        ) as form:
            upload = form.get("file")
            if len(form) != 1 or not isinstance(upload, UploadFile):
                fail(422, "invalid_photo_upload", "Выберите одну фотографию.")
            data = bytearray()
            while chunk := await upload.read(65536):
                if len(data) + len(chunk) > settings.photo_max_bytes:
                    fail(413, "photo_too_large", "Размер фотографии превышает допустимый предел.")
                data.extend(chunk)
            return await run_in_threadpool(
                service.add_photo,
                session,
                settings,
                actor,
                csrf.token_hash,
                item_id,
                bytes(data),
                upload.content_type or "",
            )
    except StarletteHTTPException as error:
        if isinstance(error.detail, dict):
            raise
        fail(400, "invalid_photo_upload", "Некорректная загрузка. Выберите одну фотографию.")


@router.patch("/{attachment_id}", response_model=Photo)
def update_photo(
    item_id: uuid.UUID,
    attachment_id: uuid.UUID,
    payload: PhotoUpdate,
    session: Database,
    actor: Manager,
    csrf: CsrfSession,
):
    return service.update_photo(session, actor, csrf.token_hash, item_id, attachment_id, payload)


@router.post("/{attachment_id}/archive", status_code=204)
def archive_photo(
    item_id: uuid.UUID,
    attachment_id: uuid.UUID,
    session: Database,
    actor: Manager,
    csrf: CsrfSession,
):
    service.archive_photo(session, actor, csrf.token_hash, item_id, attachment_id)


@router.get("/{attachment_id}/content")
def read_photo(
    item_id: uuid.UUID,
    attachment_id: uuid.UUID,
    request: Request,
    session: Database,
    actor: Reader,
):
    data, mime_type = service.read_photo(
        session, request.app.state.settings, item_id, attachment_id
    )
    return Response(
        data,
        media_type=mime_type,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )
