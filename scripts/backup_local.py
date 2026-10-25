"""Verified local Compose backup; never stops writers or restores existing data."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "deploy"))
from file_archive import check
from release_lib import digest

from deploy import execute


def compose(root: Path, *args: str, **kwargs):
    return execute(
        [
            "docker",
            "compose",
            "--project-directory",
            str(root),
            "--file",
            str(root / "docker-compose.yml"),
            *args,
        ],
        **kwargs,
    )


def stopped_state(root: Path) -> tuple[str, str]:
    raw = compose(root, "ps", "--all", "--format", "json").strip()
    rows = (
        json.loads(raw)
        if raw.startswith("[")
        else [json.loads(line) for line in raw.splitlines() if line.strip()]
    )
    if any(
        row["Service"] not in {"postgres", "frontend"}
        and row["State"] not in {"exited", "created", "dead"}
        for row in rows
    ):
        raise ValueError(
            "Сначала остановите backend, proxy и все операционные контейнеры"
        )
    postgres = [row for row in rows if row["Service"] == "postgres"]
    backend = [row for row in rows if row["Service"] == "backend"]
    if (
        len(postgres) != 1
        or postgres[0]["State"] != "running"
        or postgres[0].get("Health") != "healthy"
    ):
        raise ValueError("Нужен ровно один работающий healthy PostgreSQL")
    if len(backend) != 1:
        raise ValueError("Нужен существующий остановленный backend с файловым volume")
    return postgres[0]["ID"], backend[0]["ID"]


def backup_local(root: Path, output: Path) -> None:
    root = root.resolve()
    output = output.resolve()
    backups = root / "backups"
    if (
        backups.resolve() != backups
        or not output.is_relative_to(backups)
        or output == backups
    ):
        raise ValueError("Каталог копии должен находиться внутри backups проекта")
    if output.exists():
        raise ValueError("Каталог копии уже существует; перезапись запрещена")
    state = stopped_state(root)
    details = json.loads(
        execute(
            [
                "docker",
                "inspect",
                "--format",
                '{"image":{{json .Image}},"mounts":{{json .Mounts}}}',
                state[1],
            ]
        )
    )
    mounts = [
        mount for mount in details["mounts"] if mount["Destination"] == "/app/uploads"
    ]
    if len(mounts) != 1 or mounts[0]["Type"] != "volume":
        raise ValueError("Ожидался именованный files volume остановленного backend")
    volume = mounts[0]["Name"]
    image = details["image"]
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", volume) or not re.fullmatch(
        r"sha256:[a-f0-9]{64}", image
    ):
        raise ValueError("Некорректные идентификаторы Docker")
    # A failed operation keeps its partial files and never claims a valid backup.
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    with (output / "database.dump").open("xb") as stream:
        compose(
            root,
            "exec",
            "-T",
            "postgres",
            "sh",
            "-ec",
            'exec pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"',
            stdout=stream,
        )
    with (output / "database.dump").open("rb") as stream:
        if stream.read(5) != b"PGDMP":
            raise ValueError("Некорректный PostgreSQL custom dump")
        stream.seek(0)
        compose(
            root,
            "exec",
            "-T",
            "postgres",
            "sh",
            "-ec",
            "exec pg_restore --file=/dev/null",
            stdin=stream,
        )
    execute(
        [
            "docker",
            "run",
            "--rm",
            "--pull",
            "never",
            "--network",
            "none",
            "--read-only",
            "--user",
            "0:0",
            "--security-opt",
            "no-new-privileges:true",
            "--mount",
            f"type=volume,src={volume},dst=/app/uploads,readonly",
            "--mount",
            f"type=bind,src={root / 'scripts/deploy/file_archive.py'},dst=/tools/file_archive.py,readonly",
            "--mount",
            f"type=bind,src={output},dst=/backup",
            "--entrypoint",
            "python",
            image,
            "/tools/file_archive.py",
            "pack",
            "/backup/files.tar.gz",
        ]
    )
    check(output / "files.tar.gz")
    if stopped_state(root) != state:
        raise ValueError("Контейнеры изменились во время backup; копия не подтверждена")
    manifest = {
        "format": "element29-local-backup-1",
        "created_utc": datetime.now(UTC).isoformat(),
        "backend_image_id": image,
        "files": {
            name: digest(output / name) for name in ["database.dump", "files.tar.gz"]
        },
    }
    with (output / "backup.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2)
        stream.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Резервная копия остановленного локального приложения"
    )
    parser.add_argument(
        "--output", required=True, type=Path, help="Новый каталог внутри backups/"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output if args.output.is_absolute() else root / args.output
    try:
        backup_local(root, output)
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        print(f"Резервная копия не подтверждена: {exc}", file=sys.stderr)
        return 1
    print(f"Проверены dump, архив файлов и SHA256: {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
