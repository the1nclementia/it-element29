"""Private normalized images; generated paths and transactional typed links."""

import hashlib
import os
import re
import tempfile
import uuid
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.files.models import FileAttachment, InventoryItemAttachment
from app.modules.files.schemas import Photo, PhotoList, PhotoUpdate
from app.modules.identity.authorization import revalidate_mutation
from app.modules.identity.errors import fail
from app.modules.identity.models import User
from app.modules.identity.repository import audit
from app.modules.inventory.models import InventoryItem

FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}


@dataclass(frozen=True)
class NormalizedImage:
    data: bytes
    mime_type: str
    extension: str
    width: int
    height: int


def normalize_image(data: bytes, declared_type: str, settings: Settings) -> NormalizedImage:
    if len(data) > settings.photo_max_bytes:
        fail(413, "photo_too_large", "Размер фотографии превышает допустимый предел.")
    if declared_type not in {value[0] for value in FORMATS.values()}:
        fail(415, "invalid_photo", "Разрешены только фотографии JPEG, PNG и WebP.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as original:
                format_name = original.format
                if format_name not in FORMATS or FORMATS[format_name][0] != declared_type:
                    fail(415, "photo_mime_mismatch", "Тип файла не совпадает с изображением.")
                if original.width * original.height > settings.photo_max_pixels:
                    fail(413, "photo_too_many_pixels", "Разрешение фотографии слишком велико.")
                if getattr(original, "n_frames", 1) != 1:
                    fail(415, "animated_photo", "Используйте неподвижное изображение.")
                original.load()
                oriented = ImageOps.exif_transpose(original)
                mode = "RGBA" if format_name != "JPEG" and "A" in oriented.getbands() else "RGB"
                if format_name != "JPEG" and "transparency" in oriented.info:
                    mode = "RGBA"
                clean = Image.new(mode, oriented.size)
                clean.paste(oriented.convert(mode))
                output = BytesIO()
                clean.save(output, format=format_name)
                normalized = output.getvalue()
                if len(normalized) > settings.photo_max_bytes:
                    fail(413, "photo_too_large", "Размер фотографии превышает допустимый предел.")
                mime_type, extension = FORMATS[format_name]
                return NormalizedImage(normalized, mime_type, extension, clean.width, clean.height)
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        fail(413, "photo_too_many_pixels", "Разрешение фотографии слишком велико.")
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        fail(415, "invalid_photo", "Файл не является корректным изображением.")


def storage_path(root: Path, storage_key: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}\.(?:jpg|png|webp)", storage_key):
        fail(404, "photo_not_found", "Фотография не найдена.")
    absolute = root.absolute()
    for part in (absolute, *absolute.parents):
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            fail(503, "photo_storage_unavailable", "Хранилище фотографий недоступно.")
    path = absolute / storage_key
    if path.is_symlink() or path.resolve().parent != absolute.resolve():
        fail(404, "photo_not_found", "Фотография не найдена.")
    return path


def store_image(settings: Settings, image: NormalizedImage) -> str:
    key = f"{uuid.uuid4().hex}.{image.extension}"
    path = storage_path(settings.uploads_dir, key)
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = storage_path(settings.uploads_dir, key)
        with tempfile.NamedTemporaryFile(prefix=".pending-", dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            file.write(image.data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
        # The image is durable before its database link becomes visible.
        if os.name != "nt":
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    except OSError:
        fail(503, "photo_storage_unavailable", "Не удалось сохранить фотографию. Повторите позже.")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return key


def photo_response(file: FileAttachment, link: InventoryItemAttachment) -> Photo:
    return Photo(
        id=file.id,
        content_url=f"/api/v1/inventory/items/{link.inventory_item_id}/photos/{file.id}/content",
        position=link.position,
        is_primary=link.is_primary,
        width=file.width,
        height=file.height,
        mime_type=file.mime_type,
        size=file.size,
        archived_at=link.archived_at,
    )


def active_links(session: Session, item_id: uuid.UUID) -> list[InventoryItemAttachment]:
    return list(
        session.scalars(
            select(InventoryItemAttachment)
            .where(
                InventoryItemAttachment.inventory_item_id == item_id,
                InventoryItemAttachment.archived_at.is_(None),
            )
            .order_by(InventoryItemAttachment.position, InventoryItemAttachment.id)
            .execution_options(populate_existing=True)
        )
    )


def list_photos(session: Session, item_id: uuid.UUID) -> PhotoList:
    if session.get(InventoryItem, item_id) is None:
        fail(404, "item_not_found", "Позиция не найдена.")
    rows = session.execute(
        select(FileAttachment, InventoryItemAttachment)
        .join(
            InventoryItemAttachment, InventoryItemAttachment.file_attachment_id == FileAttachment.id
        )
        .where(
            InventoryItemAttachment.inventory_item_id == item_id,
            InventoryItemAttachment.archived_at.is_(None),
        )
        .order_by(InventoryItemAttachment.position, InventoryItemAttachment.id)
    ).all()
    return PhotoList(items=[photo_response(file, link) for file, link in rows], total=len(rows))


def lock_item(session: Session, item_id: uuid.UUID, actor: User, session_hash: str):
    item = session.scalar(
        select(InventoryItem)
        .where(InventoryItem.id == item_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if item is None:
        fail(404, "item_not_found", "Позиция не найдена.")
    revalidate_mutation(session, actor, session_hash, "inventory.manage")
    if item.archived_at is not None:
        fail(409, "item_archived", "Сначала восстановите архивную позицию.")


def add_photo(
    session: Session,
    settings: Settings,
    actor: User,
    session_hash: str,
    item_id: uuid.UUID,
    data: bytes,
    declared_type: str,
) -> Photo:
    image = normalize_image(data, declared_type, settings)
    try:
        lock_item(session, item_id, actor, session_hash)
        links = active_links(session, item_id)
        if len(links) >= settings.photo_max_per_item:
            fail(409, "photo_limit_reached", "Достигнут предел фотографий для позиции.")
        key = store_image(settings, image)
        file = FileAttachment(
            storage_key=key,
            mime_type=image.mime_type,
            size=len(image.data),
            sha256=hashlib.sha256(image.data).hexdigest(),
            width=image.width,
            height=image.height,
            uploaded_by_id=actor.id,
        )
        session.add(file)
        session.flush()
        link = InventoryItemAttachment(
            inventory_item_id=item_id,
            file_attachment_id=file.id,
            position=min(max((link.position for link in links), default=-1) + 1, 2_147_483_647),
            is_primary=not links,
        )
        session.add(link)
        audit(session, actor.id, "photo.uploaded", item_id)
        session.flush()
        result = photo_response(file, link)
        session.commit()
        return result
    except Exception:
        # A new unlinked file may remain after rollback; old files are never touched.
        session.rollback()
        raise


def find_link(links: list[InventoryItemAttachment], attachment_id: uuid.UUID):
    for link in links:
        if link.file_attachment_id == attachment_id:
            return link
    fail(404, "photo_not_found", "Фотография не найдена.")


def update_photo(
    session: Session,
    actor: User,
    session_hash: str,
    item_id: uuid.UUID,
    attachment_id: uuid.UUID,
    payload: PhotoUpdate,
) -> Photo:
    try:
        lock_item(session, item_id, actor, session_hash)
        links = active_links(session, item_id)
        link = find_link(links, attachment_id)
        if payload.is_primary:
            for other in links:
                if other.is_primary and other.id != link.id:
                    other.is_primary = False
            session.flush()  # Release the partial unique slot before selecting another primary.
            link.is_primary = True
        if payload.position is not None:
            link.position = payload.position
        audit(session, actor.id, "photo.updated", item_id)
        session.flush()
        result = photo_response(session.get(FileAttachment, attachment_id), link)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise


def archive_photo(
    session: Session, actor: User, session_hash: str, item_id: uuid.UUID, attachment_id: uuid.UUID
) -> None:
    try:
        lock_item(session, item_id, actor, session_hash)
        links = active_links(session, item_id)
        link = find_link(links, attachment_id)
        was_primary = link.is_primary
        link.archived_at = datetime.now(UTC)
        link.is_primary = False
        session.flush()
        if was_primary:
            remaining = [other for other in links if other.id != link.id]
            if remaining:
                remaining[0].is_primary = True
        audit(session, actor.id, "photo.archived", item_id)
        session.commit()
    except Exception:
        session.rollback()
        raise


def read_photo(
    session: Session, settings: Settings, item_id: uuid.UUID, attachment_id: uuid.UUID
) -> tuple[bytes, str]:
    file = session.scalar(
        select(FileAttachment)
        .join(
            InventoryItemAttachment, InventoryItemAttachment.file_attachment_id == FileAttachment.id
        )
        .where(
            InventoryItemAttachment.inventory_item_id == item_id,
            InventoryItemAttachment.file_attachment_id == attachment_id,
            InventoryItemAttachment.archived_at.is_(None),
        )
    )
    if file is None:
        fail(404, "photo_not_found", "Фотография не найдена.")
    path = storage_path(settings.uploads_dir, file.storage_key)
    try:
        descriptor = os.open(
            path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        )
        with os.fdopen(descriptor, "rb") as content:
            data = content.read(settings.photo_max_bytes + 1)
        if len(data) != file.size or hashlib.sha256(data).hexdigest() != file.sha256:
            fail(503, "photo_storage_unavailable", "Фотография временно недоступна.")
        return data, file.mime_type
    except FileNotFoundError:
        fail(404, "photo_not_found", "Фотография не найдена.")
    except OSError:
        fail(503, "photo_storage_unavailable", "Фотография временно недоступна.")
