import asyncio
import importlib.util
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from io import BytesIO
from queue import Queue
from threading import Event
from time import monotonic

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image, PngImagePlugin
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings


def photo_service():
    assert importlib.util.find_spec("app.modules.files.service"), "Photo service is required"
    from app.modules.files import service

    return service


def settings(tmp_path, **kwargs):
    return Settings(_env_file=None, postgres_password="synthetic", uploads_dir=tmp_path, **kwargs)


def image_bytes(format="PNG", size=(8, 4), **save_kwargs):
    output = BytesIO()
    Image.new("RGB", size, "red").save(output, format=format, **save_kwargs)
    return output.getvalue()


def test_image_is_decoded_and_metadata_removed(tmp_path):
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Description", "private synthetic annotation")
    result = photo_service().normalize_image(
        image_bytes(pnginfo=metadata), "image/png", settings(tmp_path)
    )
    assert result.width == 8 and result.height == 4
    assert result.mime_type == "image/png"
    with Image.open(BytesIO(result.data)) as decoded:
        assert decoded.info == {}


@pytest.mark.parametrize("declared", ["image/jpeg", "image/svg+xml", "text/html"])
def test_mime_spoofing_rejected(tmp_path, declared):
    with pytest.raises(HTTPException) as error:
        photo_service().normalize_image(image_bytes(), declared, settings(tmp_path))
    assert error.value.status_code == 415


@pytest.mark.parametrize("payload", [b"<svg></svg>", b"", b"\x89PNG\r\n\x1a\nbroken"])
def test_invalid_image_is_not_stored(tmp_path, payload):
    with pytest.raises(HTTPException) as error:
        photo_service().normalize_image(payload, "image/png", settings(tmp_path))
    assert error.value.status_code == 415
    assert list(tmp_path.iterdir()) == []


def test_byte_and_pixel_limits(tmp_path):
    service = photo_service()
    for data, limits in [
        (image_bytes(), {"photo_max_bytes": 10}),
        (image_bytes(size=(100, 100)), {"photo_max_pixels": 99}),
    ]:
        with pytest.raises(HTTPException) as error:
            service.normalize_image(data, "image/png", settings(tmp_path, **limits))
        assert error.value.status_code == 413


def test_exif_orientation_normalized_and_removed(tmp_path):
    exif = Image.Exif()
    exif[274] = 6
    result = photo_service().normalize_image(
        image_bytes("JPEG", exif=exif), "image/jpeg", settings(tmp_path)
    )
    assert (result.width, result.height) == (4, 8)
    with Image.open(BytesIO(result.data)) as decoded:
        assert not decoded.getexif()


@pytest.mark.parametrize("key", ["../outside.png", "/outside.png", "a/b.png", "a\\b.png", "C:x"])
def test_storage_keys_cannot_escape_upload_root(tmp_path, key):
    with pytest.raises(HTTPException):
        photo_service().storage_path(tmp_path, key)


def test_atomic_file_failure_preserves_previous_file(tmp_path, monkeypatch):
    service = photo_service()
    old = tmp_path / "old.png"
    old.write_bytes(b"previous image")

    def fail_replace(*args):
        raise OSError("synthetic storage failure")

    monkeypatch.setattr(service.os, "replace", fail_replace)
    with pytest.raises(HTTPException) as error:
        service.store_image(
            settings(tmp_path),
            service.normalize_image(image_bytes(), "image/png", settings(tmp_path)),
        )
    assert error.value.status_code == 503
    assert old.read_bytes() == b"previous image"


def test_stream_limit_rejects_before_app_or_multipart_parsing():
    assert importlib.util.find_spec("app.modules.files.middleware")
    from app.modules.files.middleware import PhotoBodyLimitMiddleware

    called = False
    sent = []
    chunks = iter([b"a" * 50, b"b" * 51])

    async def app(scope, receive, send):
        nonlocal called
        called = True

    async def receive():
        return {"type": "http.request", "body": next(chunks), "more_body": True}

    async def send(message):
        sent.append(message)

    middleware = PhotoBodyLimitMiddleware(app, max_body_bytes=100)
    asyncio.run(
        middleware(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/inventory/items/00000000-0000-0000-0000-000000000001/photos",
                "headers": [],
            },
            receive,
            send,
        )
    )
    assert not called
    assert sent[0]["status"] == 413


def test_photo_update_cannot_remove_only_primary_or_clear_metadata():
    from pydantic import ValidationError

    assert importlib.util.find_spec("app.modules.files.schemas"), "Photo schema is required"
    from app.modules.files.schemas import PhotoUpdate

    for payload in [
        {},
        {"is_primary": False},
        {"position": -1},
        {"position": True},
        {"position": None},
    ]:
        with pytest.raises(ValidationError):
            PhotoUpdate.model_validate(payload)
    assert PhotoUpdate(is_primary=True).is_primary


@pytest.fixture()
def photo_db(identity_db, tmp_path):
    from app.modules.identity.models import AuthSession, User
    from app.modules.inventory.models import InventoryCategory, InventoryItem, Manufacturer

    engine, config = identity_db
    config = config.model_copy(update={"uploads_dir": tmp_path})
    with Session(engine) as session:
        user = User(
            username="photos",
            display_name="Synthetic",
            password_hash="unused",
            role_code="storekeeper",
            must_change_password=False,
        )
        manufacturer = Manufacturer(name="Synthetic", name_key="synthetic")
        category = session.scalar(
            select(InventoryCategory).where(InventoryCategory.code == "cartridges")
        )
        session.add_all([user, manufacturer])
        session.flush()
        item = InventoryItem(
            internal_code="PHOTO-1",
            category_id=category.id,
            manufacturer_id=manufacturer.id,
            model="Synthetic",
        )
        session.add(item)
        session_hash = secrets.token_hex(32)
        session.add(
            AuthSession(
                token_hash=session_hash,
                user_id=user.id,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        session.commit()
        return engine, config, user.id, item.id, session_hash


def upload_photo(fixture):
    from app.modules.identity.models import User

    engine, config, actor_id, item_id, session_hash = fixture
    with Session(engine) as session:
        return photo_service().add_photo(
            session,
            config,
            session.get(User, actor_id),
            session_hash,
            item_id,
            image_bytes(),
            "image/png",
        )


@pytest.mark.integration
def test_photo_count_archive_primary_and_history(photo_db):
    from app.modules.files.models import FileAttachment, InventoryItemAttachment
    from app.modules.identity.models import User

    photos = [upload_photo(photo_db) for _ in range(5)]
    assert photos[0].is_primary
    with pytest.raises(HTTPException) as error:
        upload_photo(photo_db)
    assert error.value.status_code == 409
    engine, config, actor_id, item_id, session_hash = photo_db
    with Session(engine) as session:
        photo_service().archive_photo(
            session, session.get(User, actor_id), session_hash, item_id, photos[0].id
        )
        listed = photo_service().list_photos(session, item_id)
        assert listed.total == 4 and listed.items[0].is_primary
        assert session.scalar(select(func.count()).select_from(FileAttachment)) == 5
        assert session.scalar(select(func.count()).select_from(InventoryItemAttachment)) == 5
    assert len(list(config.uploads_dir.iterdir())) == 5
    assert upload_photo(photo_db).id


@pytest.mark.integration
def test_commit_failure_preserves_old_photo_and_links(photo_db, monkeypatch):
    from app.modules.files.models import FileAttachment
    from app.modules.identity.models import User

    old = upload_photo(photo_db)
    engine, config, actor_id, item_id, session_hash = photo_db
    old_files = {file.name: file.read_bytes() for file in config.uploads_dir.iterdir()}
    with Session(engine) as session:

        def failed_commit():
            raise RuntimeError("synthetic commit failure")

        monkeypatch.setattr(session, "commit", failed_commit)
        with pytest.raises(RuntimeError):
            photo_service().add_photo(
                session,
                config,
                session.get(User, actor_id),
                session_hash,
                item_id,
                image_bytes(),
                "image/png",
            )
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(FileAttachment)) == 1
        assert photo_service().list_photos(session, item_id).items[0].id == old.id
    assert all((config.uploads_dir / name).read_bytes() == data for name, data in old_files.items())


@pytest.mark.integration
def test_concurrent_upload_enforces_limit_and_one_primary(photo_db):
    from app.modules.identity.models import User
    from app.modules.inventory.models import InventoryItem

    for _ in range(4):
        upload_photo(photo_db)
    engine, config, actor_id, item_id, session_hash = photo_db
    pids = Queue()

    def upload():
        with Session(engine) as session:
            actor = session.get(User, actor_id)
            pids.put(session.scalar(text("SELECT pg_backend_pid()")))
            try:
                return photo_service().add_photo(
                    session, config, actor, session_hash, item_id, image_bytes(), "image/png"
                )
            except HTTPException as error:
                return error.status_code

    with Session(engine) as blocker, ThreadPoolExecutor(max_workers=2) as pool:
        blocker.scalar(select(InventoryItem).where(InventoryItem.id == item_id).with_for_update())
        futures = [pool.submit(upload) for _ in range(2)]
        try:
            wait_for_locks(engine, [pids.get(timeout=5), pids.get(timeout=5)])
        finally:
            blocker.rollback()
        results = [future.result(timeout=10) for future in futures]
    assert sum(value == 409 for value in results) == 1
    with Session(photo_db[0]) as session:
        photos = photo_service().list_photos(session, photo_db[3])
        assert photos.total == 5
        assert sum(photo.is_primary for photo in photos.items) == 1


def wait_for_locks(engine, pids):
    deadline = monotonic() + 2
    while monotonic() < deadline:
        with engine.connect() as connection:
            waiting = connection.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE pid = ANY(:pids) AND wait_event_type = 'Lock'"
                ),
                {"pids": pids},
            )
        if waiting == len(pids):
            return
        Event().wait(0.01)
    pytest.fail("Workers did not reach the controlled PostgreSQL lock wait")


@pytest.mark.integration
def test_waiting_photo_upload_revalidates_revoked_session(photo_db):
    from app.modules.identity.models import AuthSession, User
    from app.modules.inventory.models import InventoryItem

    engine, config, actor_id, item_id, session_hash = photo_db
    pids = Queue()

    def upload():
        with Session(engine) as session:
            actor = session.get(User, actor_id)
            pids.put(session.scalar(text("SELECT pg_backend_pid()")))
            try:
                photo_service().add_photo(
                    session, config, actor, session_hash, item_id, image_bytes(), "image/png"
                )
            except HTTPException as error:
                return error.status_code

    with Session(engine) as blocker, ThreadPoolExecutor(max_workers=1) as pool:
        blocker.scalar(select(InventoryItem).where(InventoryItem.id == item_id).with_for_update())
        future = pool.submit(upload)
        try:
            wait_for_locks(engine, [pids.get(timeout=5)])
            with Session(engine) as administration:
                administration.get(AuthSession, session_hash).expires_at = datetime.now(
                    UTC
                ) - timedelta(seconds=1)
                administration.commit()
        finally:
            blocker.rollback()
        assert future.result(timeout=10) == 401
    with Session(engine) as session:
        assert photo_service().list_photos(session, item_id).total == 0
    assert list(config.uploads_dir.iterdir()) == []


@pytest.mark.integration
def test_large_photo_position_does_not_break_later_upload(photo_db):
    from app.modules.files.schemas import PhotoUpdate
    from app.modules.identity.models import User

    first = upload_photo(photo_db)
    engine, _, actor_id, item_id, session_hash = photo_db
    with Session(engine) as session:
        photo_service().update_photo(
            session,
            session.get(User, actor_id),
            session_hash,
            item_id,
            first.id,
            PhotoUpdate(position=2_147_483_647),
        )
    assert upload_photo(photo_db).id


@pytest.mark.integration
@pytest.mark.parametrize(
    "role,allowed",
    [("administrator", True), ("storekeeper", True), ("it_specialist", False), ("manager", False)],
)
def test_photo_http_permissions_and_private_content(photo_db, role, allowed):
    from app.main import create_app
    from app.modules.identity.models import AuthSession, User
    from app.modules.identity.security import csrf_token, token_hash

    photo = upload_photo(photo_db)
    engine, config, actor_id, item_id, _ = photo_db
    raw = secrets.token_urlsafe(32)
    with Session(engine) as session:
        session.get(User, actor_id).role_code = role
        session.add(
            AuthSession(
                token_hash=token_hash(raw),
                user_id=actor_id,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        session.commit()
    with TestClient(create_app(config)) as client:
        assert client.get(photo.content_url).status_code == 401
        client.cookies.set("element29_session", raw)
        content = client.get(photo.content_url)
        assert content.status_code == 200
        assert content.headers["cache-control"] == "no-store"
        assert content.headers["x-content-type-options"] == "nosniff"
        assert Image.open(BytesIO(content.content)).size == (8, 4)
        response = client.post(
            f"/api/v1/inventory/items/{item_id}/photos",
            files={"file": ("../../private.png", image_bytes(), "image/png")},
            headers={"Origin": "http://testserver", "X-CSRF-Token": csrf_token(raw)},
        )
        assert response.status_code == (201 if allowed else 403), response.text
        if allowed:
            assert len(list(config.uploads_dir.iterdir())) == 2
            assert all("private" not in file.name for file in config.uploads_dir.iterdir())
        url = f"/api/v1/inventory/items/{item_id}/photos"
        assert client.get(url).status_code == 200
        headers = {"Origin": "http://testserver", "X-CSRF-Token": csrf_token(raw)}
        changed = client.patch(f"{url}/{photo.id}", json={"position": 2}, headers=headers)
        assert changed.status_code == (200 if allowed else 403)
        archived = client.post(f"{url}/{photo.id}/archive", headers=headers)
        assert archived.status_code == (204 if allowed else 403)
        assert client.get(photo.content_url).status_code == (404 if allowed else 200)


@pytest.mark.integration
def test_archived_photo_and_wrong_item_never_serve_content(photo_db):
    import uuid

    from app.modules.identity.models import User

    photo = upload_photo(photo_db)
    engine, config, actor_id, item_id, session_hash = photo_db
    with Session(engine) as session:
        with pytest.raises(HTTPException) as error:
            photo_service().read_photo(session, config, uuid.uuid4(), photo.id)
        assert error.value.status_code == 404
        photo_service().archive_photo(
            session, session.get(User, actor_id), session_hash, item_id, photo.id
        )
        with pytest.raises(HTTPException) as error:
            photo_service().read_photo(session, config, item_id, photo.id)
        assert error.value.status_code == 404


@pytest.mark.integration
def test_photo_primary_patch_preserves_single_primary(photo_db):
    from app.modules.files.schemas import PhotoUpdate
    from app.modules.identity.models import User

    first, second = upload_photo(photo_db), upload_photo(photo_db)
    engine, _, actor_id, item_id, session_hash = photo_db
    with Session(engine) as session:
        changed = photo_service().update_photo(
            session,
            session.get(User, actor_id),
            session_hash,
            item_id,
            second.id,
            PhotoUpdate(is_primary=True, position=0),
        )
        assert changed.is_primary
        photos = photo_service().list_photos(session, item_id)
        assert [photo.id for photo in photos.items if photo.is_primary] == [second.id]
        assert not next(photo for photo in photos.items if photo.id == first.id).is_primary


@pytest.mark.integration
def test_runtime_role_can_manage_photos_but_cannot_mutate_file_metadata(photo_db):
    import uuid

    from sqlalchemy import update
    from sqlalchemy.exc import DBAPIError

    from app.db.provision import provision_runtime_role
    from app.db.session import build_engine
    from app.modules.files.models import FileAttachment
    from app.modules.identity.models import User

    engine, config, actor_id, item_id, session_hash = photo_db
    role = "photo_runtime_" + uuid.uuid4().hex[:16]
    password = secrets.token_urlsafe(32)
    with engine.begin() as connection:
        provision_runtime_role(connection, role, password)
    runtime_config = config.model_copy(
        update={
            "postgres_user": role,
            "postgres_password": __import__("pydantic").SecretStr(password),
        }
    )
    runtime = build_engine(runtime_config)
    try:
        photo = upload_photo((runtime, runtime_config, actor_id, item_id, session_hash))
        with Session(runtime) as session:
            assert session.scalar(text("SELECT current_user")) == role
            content, mime = photo_service().read_photo(session, runtime_config, item_id, photo.id)
            assert mime == "image/png" and Image.open(BytesIO(content)).size == (8, 4)
            photo_service().archive_photo(
                session, session.get(User, actor_id), session_hash, item_id, photo.id
            )
            assert photo_service().list_photos(session, item_id).total == 0
            with pytest.raises(DBAPIError):
                session.execute(
                    update(FileAttachment).where(FileAttachment.id == photo.id).values(size=1)
                )
            session.rollback()
        assert len(list(config.uploads_dir.iterdir())) == 1
    finally:
        runtime.dispose()


@pytest.mark.integration
def test_file_and_upload_root_symlinks_are_rejected(photo_db, tmp_path):
    from app.modules.files.models import FileAttachment

    photo = upload_photo(photo_db)
    engine, config, _, item_id, _ = photo_db
    with Session(engine) as session:
        file = session.get(FileAttachment, photo.id)
        original_path = config.uploads_dir / file.storage_key
        link = tmp_path / ("a" * 32 + ".png")
        link.symlink_to(original_path)
        with pytest.raises(HTTPException) as error:
            photo_service().storage_path(tmp_path, link.name)
        assert error.value.status_code == 404
        root_link = tmp_path / "linked-root"
        root_link.symlink_to(config.uploads_dir, target_is_directory=True)
        with pytest.raises(HTTPException) as error:
            photo_service().read_photo(
                session, config.model_copy(update={"uploads_dir": root_link}), item_id, photo.id
            )
        assert error.value.status_code == 503
        assert original_path.read_bytes() == image_bytes()


@pytest.mark.integration
def test_concurrent_primary_selection_has_exactly_one_winner(photo_db):
    from app.modules.files.schemas import PhotoUpdate
    from app.modules.identity.models import User
    from app.modules.inventory.models import InventoryItem

    photos = [upload_photo(photo_db) for _ in range(2)]
    engine, _, actor_id, item_id, session_hash = photo_db
    pids = Queue()

    def select_primary(photo):
        with Session(engine) as session:
            actor = session.get(User, actor_id)
            pids.put(session.scalar(text("SELECT pg_backend_pid()")))
            return photo_service().update_photo(
                session, actor, session_hash, item_id, photo.id, PhotoUpdate(is_primary=True)
            )

    with Session(engine) as blocker, ThreadPoolExecutor(max_workers=2) as pool:
        blocker.scalar(select(InventoryItem).where(InventoryItem.id == item_id).with_for_update())
        futures = [pool.submit(select_primary, photo) for photo in photos]
        try:
            wait_for_locks(engine, [pids.get(timeout=5), pids.get(timeout=5)])
        finally:
            blocker.rollback()
        for future in futures:
            assert future.result(timeout=10).is_primary
    with Session(engine) as session:
        assert (
            sum(photo.is_primary for photo in photo_service().list_photos(session, item_id).items)
            == 1
        )
