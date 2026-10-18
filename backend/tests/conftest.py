"""Fresh databases in an explicitly marked isolated cluster; no reset or cleanup SQL."""

import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import text

from app.core.config import Settings
from app.db.session import build_engine

MARKER = "e29-stage3-isolated-tests-v1"


@pytest.fixture()
def empty_database():
    if os.environ.get("RUN_DB_TESTS") != "1":
        pytest.skip("Требуется отдельный PostgreSQL: RUN_DB_TESTS=1 и TEST_* параметры")
    required = [
        "TEST_POSTGRES_HOST",
        "TEST_POSTGRES_PORT",
        "TEST_POSTGRES_DB",
        "TEST_POSTGRES_USER",
        "TEST_POSTGRES_PASSWORD",
        "TEST_CLUSTER_MARKER",
    ]
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        pytest.fail("Не заданы параметры изолированного кластера: " + ", ".join(missing))
    if os.environ["TEST_CLUSTER_MARKER"] != MARKER:
        pytest.fail("Неверный контрольный marker тестового кластера")
    settings = Settings(
        _env_file=None,
        postgres_host=os.environ["TEST_POSTGRES_HOST"],
        postgres_port=int(os.environ["TEST_POSTGRES_PORT"]),
        postgres_db=os.environ["TEST_POSTGRES_DB"],
        postgres_user=os.environ["TEST_POSTGRES_USER"],
        postgres_password=os.environ["TEST_POSTGRES_PASSWORD"],
        app_origins=["http://testserver"],
        cookie_secure=False,
        login_limit=3,
        login_ip_limit=30,
    )
    control = build_engine(settings)
    name = "e29_test_" + uuid.uuid4().hex
    try:
        with control.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            marker = connection.scalar(text("SELECT marker FROM public.test_cluster_marker"))
            if marker != MARKER:
                pytest.fail("Кластер не является разрешённым изолированным тестовым кластером")
            driver = connection.connection.driver_connection
            connection.exec_driver_sql(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)).as_string(driver)
            )
    finally:
        control.dispose()
    settings = settings.model_copy(update={"postgres_db": name})
    engine = build_engine(settings)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["settings"] = settings
    try:
        yield engine, settings, config
    finally:
        engine.dispose()


@pytest.fixture()
def database(empty_database):
    command.upgrade(empty_database[2], "head")
    return empty_database


@pytest.fixture()
def identity_db(database):
    return database[:2]
