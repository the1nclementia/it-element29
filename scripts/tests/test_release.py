"""Security boundaries for offline artifacts; no Docker Engine required."""

import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[1] / "deploy"
sys.path.insert(0, str(DEPLOY))


def module():
    assert (DEPLOY / "release_lib.py").is_file(), "Release validator is not implemented"
    import release_lib

    return release_lib


def manifest():
    return {
        "format": 1,
        "version": "0.1.0-stage2",
        "git_commit": "a" * 40,
        "platform": "linux/amd64",
        "postgres_major": 17,
        "images": [
            {
                "service": s,
                "ref": f"element29/{s}:0.1.0-aaaaaaaaaaaa",
                "id": "sha256:" + str(i) * 64,
                "repo_digests": [],
                "source_ref": (
                    f"{s}:17.11-alpine@sha256:" + "f" * 64
                    if s in {"postgres", "proxy"}
                    else "git:" + "a" * 40
                ),
            }
            for i, s in enumerate(["backend", "frontend", "postgres", "proxy"], 1)
        ],
    }


def release(tmp_path):
    lib = module()
    root = tmp_path / "release"
    root.mkdir()
    for name in lib.PAYLOAD_FILES:
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"fixture")
    (root / "manifest.json").write_text(json.dumps(manifest()), encoding="utf-8")
    write_sums(root)
    return root


def write_sums(root):
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            entries.append(
                f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root).as_posix()}\n"
            )
    (root / "SHA256SUMS").write_text("".join(entries), encoding="ascii")


def test_valid_release(tmp_path):
    root = release(tmp_path)
    assert module().verify_release(root)["version"] == "0.1.0-stage2"


@pytest.mark.parametrize(
    "name", ["../escape", "/root/file", "x/../../escape", "C:/evil", "a\\b"]
)
def test_rejects_archive_path_traversal_before_extract(tmp_path, name):
    archive = tmp_path / "bad.tar.gz"
    with tarfile.open(archive, "w:gz") as out:
        entry = tarfile.TarInfo(name)
        entry.size = 3
        out.addfile(entry, io.BytesIO(b"bad"))
    target = tmp_path / "target"
    with pytest.raises(ValueError):
        module().unpack_release(
            archive, target, hashlib.sha256(archive.read_bytes()).hexdigest()
        )
    assert not target.exists()
    assert not (tmp_path / "escape").exists()


def test_rejects_links_and_duplicates(tmp_path):
    for duplicate in [False, True]:
        archive = tmp_path / "bad.tar"
        with tarfile.open(archive, "w") as out:
            entry = tarfile.TarInfo("images.tar")
            if not duplicate:
                entry.type = tarfile.SYMTYPE
                entry.linkname = "/etc/passwd"
            out.addfile(entry)
            if duplicate:
                out.addfile(entry)
        with pytest.raises(ValueError):
            module().unpack_release(
                archive,
                tmp_path / "target",
                hashlib.sha256(archive.read_bytes()).hexdigest(),
            )


def test_tampering_and_unlisted_secret_rejected(tmp_path):
    root = release(tmp_path)
    (root / "images.tar").write_bytes(b"tampered")
    with pytest.raises(ValueError):
        module().verify_release(root)
    write_sums(root)
    (root / ".env").write_text("PASSWORD=secret")
    write_sums(root)
    with pytest.raises(ValueError):
        module().verify_release(root)


@pytest.mark.parametrize("value", ["latest", "../1.0", "v 1", "1;echo", "", "A" * 100])
def test_invalid_version_rejected(value):
    with pytest.raises(ValueError):
        module().validate_version(value)


@pytest.mark.parametrize(
    "field,value",
    [("platform", "windows/amd64"), ("git_commit", "HEAD"), ("postgres_major", 18)],
)
def test_manifest_contract(field, value):
    data = manifest()
    data[field] = value
    with pytest.raises(ValueError):
        module().validate_manifest(data)


def test_image_id_and_immutable_source_required():
    data = manifest()
    data["images"][0]["id"] = "latest"
    with pytest.raises(ValueError):
        module().validate_manifest(data)
    data = manifest()
    data["images"][2]["source_ref"] = "postgres:17"
    with pytest.raises(ValueError):
        module().validate_manifest(data)


def test_untrusted_archive_hash_rejected(tmp_path):
    archive = tmp_path / "bad.tar"
    archive.write_bytes(b"anything")
    with pytest.raises(ValueError):
        module().unpack_release(archive, tmp_path / "dest", "0" * 64)


def test_deployment_module_exists():
    assert importlib.util.find_spec("deploy") is not None, (
        "Deployment runner is not implemented"
    )


def test_proxy_policy_blocks_caching_and_external_content():
    config = (DEPLOY.parents[1] / "deploy/nginx/default.conf").read_text(
        encoding="utf-8"
    )
    assert "add_header Cache-Control no-store always;" in config
    assert "default-src 'self'" in config
    assert "frame-ancestors 'none'" in config
    assert "error_log /var/log/nginx/error.log crit;" in config


@pytest.mark.parametrize("entrypoint", ["deploy.py", "unpack-release.py"])
def test_running_release_entrypoint_does_not_modify_package(tmp_path, entrypoint):
    import shutil

    target = tmp_path / "deploy"
    target.mkdir()
    for path in DEPLOY.glob("*.py"):
        shutil.copyfile(path, target / path.name)
    subprocess.run(
        [sys.executable, str(target / entrypoint), "--help"],
        check=True,
        capture_output=True,
    )
    assert not (target / "__pycache__").exists()
