"""Local backup boundaries: synthetic data and mocked Docker process only."""

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def module():
    assert importlib.util.find_spec("backup_local"), "Local backup helper is absent"
    return importlib.import_module("backup_local")


def setup(tmp_path, monkeypatch, *, active=None, healthy=True):
    mod = module()
    root = tmp_path / "repo"
    root.mkdir()
    calls = []
    services = [
        {
            "Service": "postgres",
            "ID": "db-id",
            "State": "running",
            "Health": "healthy" if healthy else "unhealthy",
        },
        {"Service": "backend", "ID": "api-id", "State": "exited", "Health": ""},
        {"Service": "proxy", "ID": "proxy-id", "State": "exited", "Health": ""},
    ]
    if active:
        services.append(
            {
                "Service": active,
                "ID": "active-id",
                "State": "running",
                "Health": "healthy",
            }
        )

    def execute(args, **kwargs):
        calls.append(args)
        if "ps" in args:
            return json.dumps(services)
        if args[:2] == ["docker", "inspect"]:
            return json.dumps(
                {
                    "image": "sha256:" + "a" * 64,
                    "mounts": [
                        {
                            "Type": "volume",
                            "Name": "isolated-files",
                            "Destination": "/app/uploads",
                        }
                    ],
                }
            )
        if "pg_dump" in " ".join(args):
            kwargs["stdout"].write(b"PGDMPsynthetic")
        if "pack" in args:
            import file_archive

            source = tmp_path / "synthetic-files"
            source.mkdir()
            (source / "photo.png").write_bytes(b"synthetic-photo")
            file_archive.pack(source, root / "backups/copy/files.tar.gz")
        return ""

    monkeypatch.setattr(mod, "execute", execute)
    return mod, root, calls


@pytest.mark.parametrize("active", ["backend", "proxy", "migrate", "unknown-writer"])
def test_running_writer_rejected_before_creating_backup(tmp_path, monkeypatch, active):
    mod, root, calls = setup(tmp_path, monkeypatch, active=active)
    with pytest.raises(ValueError, match="останов"):
        mod.backup_local(root, root / "backups/copy")
    assert not (root / "backups/copy").exists()
    assert not any("pg_dump" in " ".join(call) for call in calls)


def test_unhealthy_postgres_rejected(tmp_path, monkeypatch):
    mod, root, _ = setup(tmp_path, monkeypatch, healthy=False)
    with pytest.raises(ValueError, match="PostgreSQL"):
        mod.backup_local(root, root / "backups/copy")
    assert not (root / "backups/copy").exists()


@pytest.mark.parametrize("kind", ["existing", "outside"])
def test_output_must_be_new_inside_ignored_backups(tmp_path, monkeypatch, kind):
    mod, root, calls = setup(tmp_path, monkeypatch)
    output = root / "backups/copy" if kind == "existing" else tmp_path / "outside"
    if kind == "existing":
        output.mkdir(parents=True)
        (output / "preserve").write_bytes(b"original")
    with pytest.raises(ValueError):
        mod.backup_local(root, output)
    assert calls == []
    if kind == "existing":
        assert (output / "preserve").read_bytes() == b"original"


def test_backup_uses_binary_dump_readonly_files_and_validated_hashes(
    tmp_path, monkeypatch
):
    mod, root, calls = setup(tmp_path, monkeypatch)
    output = root / "backups/copy"
    mod.backup_local(root, output)
    assert (output / "database.dump").read_bytes() == b"PGDMPsynthetic"
    manifest = json.loads((output / "backup.json").read_text())
    assert manifest["format"] == "element29-local-backup-1"
    assert manifest["files"]["database.dump"] == mod.digest(output / "database.dump")
    assert manifest["files"]["files.tar.gz"] == mod.digest(output / "files.tar.gz")
    assert any("pg_restore --file=/dev/null" in " ".join(call) for call in calls)
    archive = next(call for call in calls if "pack" in call)
    assert "type=volume,src=isolated-files,dst=/app/uploads,readonly" in archive
    assert "--network" in archive and "none" in archive
    assert not any(
        "stop" in call or "up" in call or "restore" in call for call in calls
    )
    assert len([call for call in calls if "ps" in call]) == 2


def test_failed_dump_check_does_not_publish_success_manifest(tmp_path, monkeypatch):
    mod, root, _ = setup(tmp_path, monkeypatch)
    execute = mod.execute

    def fail(args, **kwargs):
        if "pg_restore" in " ".join(args):
            raise RuntimeError("synthetic failure")
        return execute(args, **kwargs)

    monkeypatch.setattr(mod, "execute", fail)
    output = root / "backups/copy"
    with pytest.raises(RuntimeError):
        mod.backup_local(root, output)
    assert (output / "database.dump").is_file()
    assert not (output / "backup.json").exists()
