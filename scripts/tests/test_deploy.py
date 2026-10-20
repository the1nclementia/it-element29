"""State-machine tests mock only the external Docker process boundary."""

import importlib
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy"))
from test_release import manifest, release


def module():
    assert importlib.util.find_spec("deploy") is not None, (
        "Deployment runner is not implemented"
    )
    return importlib.import_module("deploy")


def config_text():
    return "\n".join(
        [
            "POSTGRES_DB=element29",
            "POSTGRES_USER=element29_owner",
            "POSTGRES_PASSWORD=" + "a" * 64,
            "APP_DB_USER=element29_runtime",
            "APP_DB_PASSWORD=" + "b" * 64,
            'APP_ORIGINS=["https://it29.example.internal"]',
            "HTTPS_BIND=127.0.0.1",
            "HTTPS_PORT=443",
            "TLS_DIRECTORY=/etc/element29/tls",
            "TLS_CA_FILE=/etc/ssl/certs/ca-certificates.crt",
        ]
    )


def test_parse_env_is_data_and_enforces_distinct_roles(tmp_path):
    path = tmp_path / "runtime.env"
    path.write_text(config_text(), encoding="utf-8")
    assert module().read_config(path)["POSTGRES_USER"] == "element29_owner"
    path.write_text(
        config_text().replace(
            "APP_DB_USER=element29_runtime", "APP_DB_USER=element29_owner"
        )
    )
    with pytest.raises(ValueError):
        module().read_config(path)


@pytest.mark.parametrize("name", ["a", "ab", "postgres", "pg_runtime", "pg_owner"])
def test_runtime_role_is_rejected_before_deployment(tmp_path, name):
    path = tmp_path / "runtime.env"
    path.write_text(
        config_text().replace("APP_DB_USER=element29_runtime", "APP_DB_USER=" + name),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        module().Deployment("staging", path, tmp_path / "state")


def test_runtime_role_accepts_backend_identifier_limit(tmp_path):
    path = tmp_path / "runtime.env"
    name = "a" * 63
    path.write_text(
        config_text().replace("APP_DB_USER=element29_runtime", "APP_DB_USER=" + name),
        encoding="utf-8",
    )
    assert module().read_config(path)["APP_DB_USER"] == name


@pytest.mark.parametrize(
    "extra",
    [
        "\nEVIL=$(touch /tmp/pwn)",
        "\nPOSTGRES_DB=duplicate",
        "\nCOMPOSE_FILE=/tmp/evil.yaml",
    ],
)
def test_config_rejects_unknown_keys_duplicates_and_shell(extra, tmp_path):
    path = tmp_path / "runtime.env"
    path.write_text(config_text() + extra)
    with pytest.raises(ValueError):
        module().read_config(path)


@pytest.mark.parametrize(
    "origin",
    [
        '["http://example.internal"]',
        '["https://example.internal/path"]',
        '["https://example.internal:8443"]',
    ],
)
def test_origin_must_match_tls_port(origin, tmp_path):
    path = tmp_path / "runtime.env"
    path.write_text(config_text().replace('["https://it29.example.internal"]', origin))
    with pytest.raises(ValueError):
        module().read_config(path)


def runner(tmp_path, monkeypatch):
    mod = module()
    root = release(tmp_path)
    config = tmp_path / "runtime.env"
    config.write_text(config_text())
    state = tmp_path / "state"
    state.mkdir()
    obj = mod.Deployment("staging", config, state)
    calls = []

    def external(args, *, env=None, stdin=None, stdout=None, interactive=False):
        calls.append(args)
        if args[:3] == ["docker", "image", "inspect"]:
            item = next(i for i in manifest()["images"] if i["ref"] == args[3])
            return json.dumps(
                [{"Id": item["id"], "Os": "linux", "Architecture": "amd64"}]
            )
        return ""

    monkeypatch.setattr(mod, "execute", external)
    monkeypatch.setattr(obj, "preflight", lambda: None)
    monkeypatch.setattr(obj, "health", lambda _: None)
    return obj, root, calls


def test_failed_backup_prevents_migration_and_no_automatic_restart(
    tmp_path, monkeypatch
):
    obj, root, calls = runner(tmp_path, monkeypatch)
    obj.mark_current(root)

    def broken_backup(_):
        raise ValueError("backup unreadable")

    monkeypatch.setattr(obj, "backup", broken_backup)
    with pytest.raises(ValueError):
        obj.update(root)
    assert not any("upgrade" in c or "start" in c for c in calls)
    assert any("stop" in c and "backend" in c for c in calls)


def test_migration_failure_keeps_current_marker_and_backup(tmp_path, monkeypatch):
    obj, old, calls = runner(tmp_path, monkeypatch)
    obj.mark_current(old)
    original = (obj.state / "current.json").read_bytes()
    backup = tmp_path / "saved-backup"
    backup.mkdir()
    monkeypatch.setattr(obj, "backup", lambda _: backup)
    original_compose = obj.compose

    def compose(root, *args, **kwargs):
        if "upgrade" in args:
            raise RuntimeError("migration failed")
        return original_compose(root, *args, **kwargs)

    monkeypatch.setattr(obj, "compose", compose)
    with pytest.raises(RuntimeError):
        obj.update(old)
    assert backup.exists()
    assert (obj.state / "current.json").read_bytes() == original
    assert not any("pg_restore" in " ".join(c) for c in calls)
    assert not any("up" in c and "backend" in c for c in calls)


def test_postgres_update_failure_leaves_pending_recovery_marker(tmp_path, monkeypatch):
    obj, root, _ = runner(tmp_path, monkeypatch)
    obj.mark_current(root)
    backup = tmp_path / "backup"
    backup.mkdir()
    monkeypatch.setattr(obj, "backup", lambda _: backup)
    compose = obj.compose

    def fail_postgres(root, *args, **kwargs):
        if "up" in args and "postgres" in args:
            raise RuntimeError("postgres failed")
        return compose(root, *args, **kwargs)

    monkeypatch.setattr(obj, "compose", fail_postgres)
    with pytest.raises(RuntimeError):
        obj.update(root)
    pending = json.loads((obj.state / "pending.json").read_text())
    assert pending["backup"] == str(backup)


def test_restore_wrong_confirmation_never_touches_docker(tmp_path, monkeypatch):
    obj, root, calls = runner(tmp_path, monkeypatch)
    monkeypatch.setattr(obj, "verify_backup", lambda *_: {"release": manifest()})
    with pytest.raises(ValueError):
        obj.restore(root, tmp_path / "backup", "wrong")
    assert calls == []


def test_restore_mismatched_version_never_touches_docker(tmp_path, monkeypatch):
    obj, root, calls = runner(tmp_path, monkeypatch)
    other = manifest()
    other["git_commit"] = "b" * 40
    monkeypatch.setattr(obj, "verify_backup", lambda *_: {"release": other})
    with pytest.raises(ValueError):
        obj.restore(root, tmp_path / "backup", "RESTORE element29-staging 0.1.0-stage2")
    assert calls == []


def test_changed_config_path_rejected(tmp_path, monkeypatch):
    obj, root, _ = runner(tmp_path, monkeypatch)
    obj.mark_current(root)
    obj.config_path = tmp_path / "other.env"
    with pytest.raises(ValueError):
        obj.current()


def test_restore_start_never_recreates_postgres(tmp_path, monkeypatch):
    obj, root, calls = runner(tmp_path, monkeypatch)
    obj.start(root)
    commands = [call for call in calls if "up" in call]
    assert len(commands) == 1
    assert "--no-deps" in commands[0]
    assert "postgres" not in commands[0]


def test_install_migrates_once_before_backend_start(tmp_path, monkeypatch):
    obj, root, calls = runner(tmp_path, monkeypatch)
    obj.install(root)
    migrations = [index for index, call in enumerate(calls) if "upgrade" in call]
    starts = [
        index for index, call in enumerate(calls) if "up" in call and "backend" in call
    ]
    assert len(migrations) == len(starts) == 1
    assert migrations[0] < starts[0]
    assert (obj.state / "current.json").exists()
    assert not (obj.state / "pending.json").exists()


def test_prepare_validates_nginx_before_external_volumes_exist(tmp_path, monkeypatch):
    obj, root, calls = runner(tmp_path, monkeypatch)
    execute = module().execute

    def no_volumes(args, **kwargs):
        # Compose validates every external volume even for run --no-deps proxy.
        if args[:2] == ["docker", "compose"] and "run" in args:
            raise RuntimeError("external volume does not exist")
        return execute(args, **kwargs)

    monkeypatch.setattr(module(), "execute", no_volumes)
    obj.prepare(root)
    assert not any(call[:3] == ["docker", "volume", "create"] for call in calls)


def test_file_backup_roundtrip_and_traversal_rejection(tmp_path):
    assert importlib.util.find_spec("file_archive"), (
        "File backup helper is not implemented"
    )
    files = importlib.import_module("file_archive")
    source = tmp_path / "source"
    source.mkdir()
    (source / "тест.txt").write_bytes(b"file data")
    archive = tmp_path / "files.tar.gz"
    files.pack(source, archive)
    files.check(archive)
    dest = tmp_path / "dest"
    dest.mkdir()
    files.restore(archive, dest, set_owner=False)
    assert (dest / "тест.txt").read_bytes() == b"file data"
    evil = tmp_path / "evil.tar.gz"
    with tarfile.open(evil, "w:gz") as out:
        entry = tarfile.TarInfo("../escape")
        entry.size = 1
        out.addfile(entry, io.BytesIO(b"x"))
    with pytest.raises(ValueError):
        files.restore(evil, dest, set_owner=False)
    assert (dest / "тест.txt").read_bytes() == b"file data"


def test_file_restore_refuses_existing_files_without_modification(tmp_path):
    files = importlib.import_module("file_archive")
    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "new.txt").write_bytes(b"new")
    (target / "existing.txt").write_bytes(b"preserve")
    archive = tmp_path / "files.tar.gz"
    files.pack(source, archive)
    with pytest.raises(ValueError, match="пуст"):
        files.restore(archive, target, set_owner=False)
    assert (target / "existing.txt").read_bytes() == b"preserve"
    assert not (target / "new.txt").exists()


def backup_fixture(tmp_path, project="element29-production"):
    import file_archive

    mod = module()
    backup = tmp_path / "backup"
    backup.mkdir()
    files = tmp_path / "uploads"
    files.mkdir()
    (files / "photo.png").write_bytes(b"synthetic image")
    file_archive.pack(files, backup / "files.tar.gz")
    (backup / "database.dump").write_bytes(b"PGDMPsynthetic")
    (backup / "backup.json").write_text(
        json.dumps(
            {
                "format": 1,
                "project": project,
                "postgres_db": "source_db",
                "release": manifest(),
                "created_utc": "20261019T000000Z",
                "recovery_only": False,
            }
        )
    )
    mod.write_checksums(backup, mod.BACKUP_FILES)
    return backup


def test_restore_new_rejects_existing_state_before_docker(tmp_path, monkeypatch):
    obj, root, calls = runner(tmp_path, monkeypatch)
    obj.mark_current(root)
    backup = backup_fixture(tmp_path)
    with pytest.raises(ValueError):
        obj.restore_new(root, backup, "RESTORE-NEW element29-staging 0.1.0-stage2")
    assert calls == []


def test_restore_new_rejects_source_project_and_wrong_confirmation(
    tmp_path, monkeypatch
):
    obj, root, calls = runner(tmp_path, monkeypatch)
    backup = backup_fixture(tmp_path, project=obj.project)
    for confirmation in ["wrong", "RESTORE-NEW element29-staging 0.1.0-stage2"]:
        with pytest.raises(ValueError):
            obj.restore_new(root, backup, confirmation)
    assert calls == []


def test_restore_new_uses_empty_database_and_keeps_source_untouched(
    tmp_path, monkeypatch
):
    obj, root, calls = runner(tmp_path, monkeypatch)
    backup = backup_fixture(tmp_path)
    original_execute = module().execute

    def execute(args, **kwargs):
        result = original_execute(args, **kwargs)
        if any("pg_namespace" in arg for arg in args):
            return "0\n"
        return result

    monkeypatch.setattr(module(), "execute", execute)
    original_dump = (backup / "database.dump").read_bytes()
    obj.restore_new(root, backup, "RESTORE-NEW element29-staging 0.1.0-stage2")
    commands = [" ".join(command) for command in calls]
    restore_index = next(
        i
        for i, command in enumerate(commands)
        if "pg_restore --exit-on-error" in command
    )
    provision_index = next(
        i for i, command in enumerate(commands) if "provision-db-role" in command
    )
    start_index = next(
        i
        for i, command in enumerate(commands)
        if " up " in command and "backend" in command
    )
    assert restore_index < provision_index < start_index
    assert not any(
        "dropdb" in command or "--clean" in command or " volume rm " in command
        for command in commands
    )
    assert not any("upgrade" in command for command in commands)
    assert (backup / "database.dump").read_bytes() == original_dump
    assert obj.current() == root
    assert not (obj.state / "pending.json").exists()
    assert (obj.state / "restored-from.json").is_file()


def test_restore_new_refuses_nonempty_database_before_restore(tmp_path, monkeypatch):
    obj, root, calls = runner(tmp_path, monkeypatch)
    backup = backup_fixture(tmp_path)
    original_execute = module().execute

    def execute(args, **kwargs):
        result = original_execute(args, **kwargs)
        if any("pg_namespace" in arg for arg in args):
            return "1\n"
        return result

    monkeypatch.setattr(module(), "execute", execute)
    with pytest.raises(ValueError, match="пуст"):
        obj.restore_new(root, backup, "RESTORE-NEW element29-staging 0.1.0-stage2")
    assert (obj.state / "pending.json").exists()
    assert not any(
        "pg_restore --exit-on-error" in " ".join(command) for command in calls
    )
    assert not any("backend" in command and "up" in command for command in calls)


@pytest.mark.parametrize("resource", ["volume", "container"])
def test_restore_new_refuses_existing_target_resources(tmp_path, monkeypatch, resource):
    obj, root, calls = runner(tmp_path, monkeypatch)
    backup = backup_fixture(tmp_path)
    original_execute = module().execute

    def execute(args, **kwargs):
        result = original_execute(args, **kwargs)
        if resource == "volume" and args[:3] == ["docker", "volume", "ls"]:
            return "element29-staging-files\n"
        if resource == "container" and args[:2] == ["docker", "ps"]:
            return "synthetic-container\n"
        return result

    monkeypatch.setattr(module(), "execute", execute)
    with pytest.raises(ValueError):
        obj.restore_new(root, backup, "RESTORE-NEW element29-staging 0.1.0-stage2")
    assert not any(command[:3] == ["docker", "volume", "create"] for command in calls)
    assert not any("up" in command for command in calls)


@pytest.mark.parametrize("defect", ["checksum", "release", "recovery_only"])
def test_restore_new_rejects_invalid_backup_before_docker(
    tmp_path, monkeypatch, defect
):
    obj, root, calls = runner(tmp_path, monkeypatch)
    backup = backup_fixture(tmp_path)
    if defect == "checksum":
        (backup / "database.dump").write_bytes(b"tampered")
    else:
        metadata = json.loads((backup / "backup.json").read_text())
        if defect == "release":
            metadata["release"]["git_commit"] = "b" * 40
        else:
            metadata["recovery_only"] = True
        (backup / "backup.json").write_text(json.dumps(metadata))
        module().write_checksums(backup, module().BACKUP_FILES)
    with pytest.raises(ValueError):
        obj.restore_new(root, backup, "RESTORE-NEW element29-staging 0.1.0-stage2")
    assert calls == []


@pytest.mark.parametrize("step", ["dump_check", "database_restore", "files_restore"])
def test_restore_new_failure_keeps_pending_and_never_starts_app(
    tmp_path, monkeypatch, step
):
    obj, root, calls = runner(tmp_path, monkeypatch)
    backup = backup_fixture(tmp_path)
    original_execute = module().execute

    def execute(args, **kwargs):
        result = original_execute(args, **kwargs)
        if any("pg_namespace" in arg for arg in args):
            return "0\n"
        fail = (
            step == "dump_check"
            and "--file=/dev/null" in args
            or step == "database_restore"
            and any("pg_restore --exit-on-error" in arg for arg in args)
            or step == "files_restore"
            and "restore" in args
        )
        if fail:
            raise RuntimeError("synthetic restore failure")
        return result

    monkeypatch.setattr(module(), "execute", execute)
    with pytest.raises(RuntimeError):
        obj.restore_new(root, backup, "RESTORE-NEW element29-staging 0.1.0-stage2")
    assert (obj.state / "pending.json").exists()
    assert not (obj.state / "current.json").exists()
    assert (backup / "database.dump").read_bytes() == b"PGDMPsynthetic"
    assert not any("up" in command and "backend" in command for command in calls)
