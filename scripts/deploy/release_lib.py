"""Strict, non-executing validation for offline release and backup data."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tarfile
from pathlib import Path, PurePosixPath

DEPLOY_FILES = frozenset(
    {
        "deploy/compose.yaml",
        "deploy/production.env.example",
        "deploy/staging.env.example",
        "deploy/nginx/default.conf",
        "scripts/deploy/deploy.sh",
        "scripts/deploy/deploy.py",
        "scripts/deploy/release_lib.py",
        "scripts/deploy/file_archive.py",
        "scripts/deploy/unpack-release.py",
        "RELEASE.md",
        "DEPLOYMENT.md",
    }
)
PAYLOAD_FILES = DEPLOY_FILES | {"images.tar"}
RELEASE_FILES = PAYLOAD_FILES | {"manifest.json", "SHA256SUMS"}
BACKUP_FILES = {"database.dump", "files.tar.gz", "backup.json", "SHA256SUMS"}
HEX = re.compile(r"[a-f0-9]{64}")
IMAGE_ID = re.compile(r"sha256:[a-f0-9]{64}")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_version(value: str) -> str:
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9][a-z0-9.-]*)?", value)
        or len(value) > 64
    ):
        raise ValueError("Недопустимая версия выпуска")
    return value


def safe_name(name: str) -> str:
    parts = PurePosixPath(name).parts
    if (
        not name
        or "\\" in name
        or ":" in name
        or name.startswith("/")
        or any(part in {".", ".."} for part in parts)
        or "/".join(parts) != name
        or any(ord(c) < 32 for c in name)
    ):
        raise ValueError("Недопустимый путь в архиве/контрольных суммах")
    return name


def read_json(path: Path) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Повторяющийся ключ JSON")
            result[key] = value
        return result

    value = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError("Ожидался JSON object")  # noqa: TRY004 - invalid external data
    return value


def validate_manifest(data: dict) -> dict:
    validate_version(data.get("version"))
    if data.get("format") != 1 or not re.fullmatch(
        r"[a-f0-9]{40}", data.get("git_commit", "")
    ):
        raise ValueError("Неизвестный формат manifest или Git commit")
    if (
        data.get("platform") not in {"linux/amd64", "linux/arm64"}
        or data.get("postgres_major") != 17
    ):
        raise ValueError("Неподдерживаемая платформа или major PostgreSQL")
    images = data.get("images")
    if not isinstance(images, list) or len(images) != 4:
        raise ValueError("Manifest должен содержать четыре образа")
    if {item.get("service") for item in images} != {
        "backend",
        "frontend",
        "postgres",
        "proxy",
    }:
        raise ValueError("Неполный набор образов")
    for item in images:
        if not re.fullmatch(
            r"element29/[a-z]+:[a-z0-9][a-z0-9.-]{0,127}", item.get("ref", "")
        ) or item["ref"].endswith(":latest"):
            raise ValueError("Недопустимое имя образа")
        if not IMAGE_ID.fullmatch(item.get("id", "")):
            raise ValueError("Отсутствует точный ID образа")
        if item["service"] in {"postgres", "proxy"}:
            if not re.fullmatch(
                r"[a-z0-9./:_-]+@sha256:[a-f0-9]{64}", item.get("source_ref", "")
            ):
                raise ValueError("Инфраструктурный образ должен иметь digest")
        elif item.get("source_ref") != "git:" + data["git_commit"]:
            raise ValueError("Образ приложения не соответствует Git commit")
    if len({item["ref"] for item in images}) != 4:
        raise ValueError("Повторяющиеся ссылки на образы")
    return data


def verify_files(root: Path, expected: set | frozenset) -> None:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Ожидался обычный каталог")
    actual = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Ссылки в комплекте запрещены")
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
        elif not path.is_dir():
            raise ValueError("Специальные файлы запрещены")
    if actual != set(expected):
        raise ValueError("Набор файлов не соответствует allowlist")
    checksums = {}
    for line in (root / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        if len(line) < 67 or line[64:66] != "  " or not HEX.fullmatch(line[:64]):
            raise ValueError("Некорректный SHA256SUMS")
        name = safe_name(line[66:])
        if name in checksums:
            raise ValueError("Повторяющаяся контрольная сумма")
        checksums[name] = line[:64]
    if set(checksums) != set(expected) - {"SHA256SUMS"}:
        raise ValueError("Неполный набор контрольных сумм")
    for name, expected_hash in checksums.items():
        if digest(root / name) != expected_hash:
            raise ValueError(f"Контрольная сумма не совпадает: {name}")


def write_checksums(root: Path, names: set | frozenset) -> None:
    (root / "SHA256SUMS").write_text(
        "".join(
            f"{digest(root / name)}  {name}\n"
            for name in sorted(set(names) - {"SHA256SUMS"})
        ),
        encoding="ascii",
        newline="\n",
    )


def verify_release(root: Path) -> dict:
    verify_files(root, RELEASE_FILES)
    return validate_manifest(read_json(root / "manifest.json"))


def unpack_release(archive: Path, target: Path, expected_sha256: str) -> dict:
    if not HEX.fullmatch(expected_sha256) or digest(archive) != expected_sha256:
        raise ValueError("SHA256 архива не совпадает с доверенным значением")
    if target.exists() or target.is_symlink():
        raise ValueError("Каталог назначения уже существует")
    with tarfile.open(archive, "r:*") as stream:
        members = stream.getmembers()
        names = []
        total = 0
        for member in members:
            name = safe_name(member.name)
            if not member.isfile() or name not in RELEASE_FILES or name in names:
                raise ValueError("Архив содержит ссылку, дубликат или посторонний файл")
            names.append(name)
            total += member.size
        if set(names) != set(RELEASE_FILES) or total > 30 * 1024**3:
            raise ValueError("Неполный или слишком большой выпуск")
        target.mkdir(parents=True, mode=0o700)
        try:
            for member in members:
                path = target / member.name
                path.parent.mkdir(parents=True, exist_ok=True)
                with stream.extractfile(member) as source, path.open("xb") as dest:
                    shutil.copyfileobj(source, dest)
                path.chmod(0o600)
            return verify_release(target)
        except BaseException:
            # The target was created here, never a pre-existing directory.
            shutil.rmtree(target)
            raise
