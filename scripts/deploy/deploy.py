"""Offline deployment state machine. Configuration and manifest are data, never code."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

sys.dont_write_bytecode = (
    True  # A verified immutable release must not acquire __pycache__.
)
from file_archive import check as check_files
from release_lib import (
    BACKUP_FILES,
    digest,
    read_json,
    verify_files,
    verify_release,
    write_checksums,
)

CONFIG_KEYS = {
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "APP_DB_USER",
    "APP_DB_PASSWORD",
    "APP_ORIGINS",
    "HTTPS_BIND",
    "HTTPS_PORT",
    "TLS_DIRECTORY",
    "TLS_CA_FILE",
}


def read_config(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if (
            not sep
            or key not in CONFIG_KEYS
            or key in values
            or not value
            or value != value.strip()
            or "$" in value
            or "`" in value
            or "\x00" in value
        ):
            raise ValueError(
                "Некорректный env: неизвестный/повторный ключ или недопустимый синтаксис"
            )
        values[key] = value
    if set(values) != CONFIG_KEYS:
        raise ValueError("В env отсутствуют обязательные настройки")
    for key in ["POSTGRES_DB", "POSTGRES_USER"]:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,47}", values[key]):
            raise ValueError("Недопустимый идентификатор БД")
    runtime_role = values["APP_DB_USER"]
    if (
        not re.fullmatch(r"[a-z][a-z0-9_]{2,62}", runtime_role)
        or runtime_role == "postgres"
        or runtime_role.startswith("pg_")
    ):
        raise ValueError("APP_DB_USER: 3–63 символа a-z/0-9/_, не системная роль")
    for key in ["POSTGRES_PASSWORD", "APP_DB_PASSWORD"]:
        if not re.fullmatch(r"[a-fA-F0-9]{64}", values[key]):
            raise ValueError(
                "Пароль БД должен быть отдельным случайным 64-символьным hex secret"
            )
    if (
        values["POSTGRES_USER"] == values["APP_DB_USER"]
        or values["POSTGRES_PASSWORD"] == values["APP_DB_PASSWORD"]
    ):
        raise ValueError("Owner и runtime должны иметь разные имена и секреты")
    ipaddress.IPv4Address(values["HTTPS_BIND"])
    if (
        not values["HTTPS_PORT"].isdigit()
        or not 1 <= int(values["HTTPS_PORT"]) <= 65535
    ):
        raise ValueError("Некорректный TLS порт")
    origins = json.loads(values["APP_ORIGINS"])
    if (
        not isinstance(origins, list)
        or len(origins) != 1
        or not isinstance(origins[0], str)
    ):
        raise ValueError("Задайте ровно один HTTPS origin")
    origin = urlsplit(origins[0])
    if (
        origin.scheme != "https"
        or not origin.hostname
        or origin.path
        or origin.query
        or origin.fragment
        or origin.username
        or origin.password
        or origin.port
        and origin.port != int(values["HTTPS_PORT"])
        or not origin.port
        and int(values["HTTPS_PORT"]) != 443
        or not re.fullmatch(r"[a-zA-Z0-9.-]+", origin.hostname)
    ):
        raise ValueError(
            "APP_ORIGINS должен содержать точный HTTPS origin с опубликованным портом"
        )
    for key in ["TLS_DIRECTORY", "TLS_CA_FILE"]:
        if not values[key].startswith("/") or any(
            char in values[key] for char in ":\n\r"
        ):
            raise ValueError("TLS пути должны быть абсолютными Linux путями")
    return values


def execute(
    args: list[str], *, env=None, stdin=None, stdout=None, interactive=False
) -> str:
    # Capture diagnostics: SQL errors and interpolated environments must not leak to logs.
    result = subprocess.run(
        args,
        env=env,
        stdin=stdin,
        stdout=stdout
        if stdout is not None
        else (None if interactive else subprocess.PIPE),
        stderr=None if interactive else subprocess.PIPE,
        check=False,
        text=not (stdin is not None or stdout is not None),
    )
    if result.returncode:
        raise RuntimeError(
            f"Внешняя команда завершилась с кодом {result.returncode}; подробности намеренно не записаны в журнал"
        )
    if isinstance(result.stdout, bytes):
        return result.stdout.decode("utf-8")
    return result.stdout or ""


class Deployment:
    def __init__(self, environment: str, config_path: Path, state: Path):
        if environment not in {"production", "staging"}:
            raise ValueError("Неизвестный серверный контур")
        self.project = "element29-" + environment
        self.config_path = config_path.resolve()
        self.state = state.resolve()
        self.config = read_config(self.config_path)
        self.stage = "проверка"
        self.last_backup = None

    def announce(self, stage):
        self.stage = stage
        print(f"Этап: {stage}", flush=True)

    def preflight(self):
        if sys.version_info < (3, 12) or sys.platform != "linux" or os.geteuid() != 0:
            raise ValueError("Нужны Linux, Python 3.12+ и sudo/root")
        for command in ["docker", "curl"]:
            if not shutil.which(command):
                raise ValueError(f"Не установлена команда {command}")
        for path in [self.config_path, self.state]:
            stat = path.stat()
            if path.is_symlink() or stat.st_uid != 0 or stat.st_mode & 0o077:
                raise ValueError(
                    "Config/state должны принадлежать root, права 0600/0700"
                )
        tls = Path(self.config["TLS_DIRECTORY"])
        for path in [
            tls / "fullchain.pem",
            tls / "privkey.pem",
            Path(self.config["TLS_CA_FILE"]),
        ]:
            if not path.is_file():
                raise ValueError("TLS сертификат, ключ или CA-файл отсутствуют")
        key = (tls / "privkey.pem").stat()
        if key.st_uid != 0 or key.st_mode & 0o077:
            raise ValueError("TLS private key должен принадлежать root с правами 0600")
        info = json.loads(
            execute(["docker", "info", "--format", "{{json .}}"], env=self.base_env())
        )
        if info.get("OSType") != "linux":
            raise ValueError("Требуется Linux Docker Engine")
        version = (
            execute(["docker", "compose", "version", "--short"], env=self.base_env())
            .strip()
            .lstrip("v")
        )
        match = re.match(r"(\d+)\.(\d+)\.(\d+)", version)
        if not match or tuple(map(int, match.groups())) < (2, 24, 0):
            raise ValueError("Требуется Docker Compose plugin >=2.24.0")

    def base_env(self):
        # No DOCKER_HOST, COMPOSE_FILE, shell POSTGRES_* or automatic .env overrides.
        return {
            "PATH": os.environ.get("PATH", "/usr/sbin:/usr/bin:/sbin:/bin"),
            "HOME": "/root",
            "LANG": "C.UTF-8",
            "DOCKER_HOST": "unix:///var/run/docker.sock",
        }

    def compose(self, root: Path, *args: str, **kwargs):
        manifest = verify_release(root)
        env = self.base_env() | self.config | {"DATA_PREFIX": self.project}
        env.update(
            {
                item["service"].upper() + "_IMAGE": item["ref"]
                for item in manifest["images"]
            }
        )
        command = [
            "docker",
            "compose",
            "--project-name",
            self.project,
            "--project-directory",
            str(root / "deploy"),
            "--env-file",
            "/dev/null",
            "--file",
            str(root / "deploy/compose.yaml"),
            "--profile",
            "ops",
            *args,
        ]
        return execute(command, env=env, **kwargs)

    def prepare(self, root: Path):
        manifest = verify_release(root)
        machine = os.uname().machine if hasattr(os, "uname") else "x86_64"
        platform = {"x86_64": "linux/amd64", "aarch64": "linux/arm64"}.get(machine)
        if manifest["platform"] != platform:
            raise ValueError("Архитектура выпуска не соответствует серверу")
        self.announce("проверка Compose и загрузка образов")
        self.compose(root, "config", "--quiet")
        execute(
            ["docker", "load", "--input", str(root / "images.tar")], env=self.base_env()
        )
        for item in manifest["images"]:
            actual = json.loads(
                execute(
                    ["docker", "image", "inspect", item["ref"]], env=self.base_env()
                )
            )[0]
            if (
                actual["Id"] != item["id"]
                or f"{actual['Os']}/{actual['Architecture']}" != manifest["platform"]
            ):
                raise ValueError(
                    "ID/платформа загруженного образа не соответствует manifest"
                )
        proxy = next(
            item["ref"] for item in manifest["images"] if item["service"] == "proxy"
        )
        # Compose run validates external volumes even for a service not using them.
        # Validate TLS/nginx independently, before install creates persistent data.
        execute(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--volume",
                f"{root / 'deploy/nginx/default.conf'}:/etc/nginx/conf.d/default.conf:ro",
                "--volume",
                f"{self.config['TLS_DIRECTORY']}:/etc/nginx/tls:ro",
                proxy,
                "nginx",
                "-t",
            ],
            env=self.base_env(),
        )

    def current(self) -> Path:
        data = read_json(self.state / "current.json")
        if data.get("project") != self.project or data.get("config") != str(
            self.config_path
        ):
            raise ValueError(
                "Project или путь config изменились; автоматическое переключение запрещено"
            )
        if data.get("config_sha256") != digest(self.config_path):
            raise ValueError(
                "Config изменён после deploy; сначала согласуйте изменение и обновите state вручную"
            )
        root = Path(data["release"])
        if not root.is_absolute() or verify_release(root) != data.get("manifest"):
            raise ValueError("Текущий выпуск повреждён или изменён")
        return root

    def mark_current(self, root: Path):
        data = {
            "project": self.project,
            "config": str(self.config_path),
            "config_sha256": digest(self.config_path),
            "release": str(root.resolve()),
            "manifest": verify_release(root),
        }
        self.atomic_json(self.state / "current.json", data)

    @staticmethod
    def atomic_json(path: Path, data: dict):
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        temp.chmod(0o600)
        temp.replace(path)

    def pending(self, root: Path):
        self.atomic_json(
            self.state / "pending.json",
            {
                "release": str(root.resolve()),
                "backup": str(self.last_backup) if self.last_backup else None,
                "version": verify_release(root)["version"],
            },
        )

    def migrate(self, root: Path):
        self.pending(root)
        self.announce("миграция Alembic отдельным процессом")
        self.compose(
            root,
            "run",
            "--rm",
            "--no-deps",
            "owner-ops",
            "python",
            "-m",
            "alembic",
            "upgrade",
            "head",
        )
        self.compose(
            root,
            "run",
            "--rm",
            "--no-deps",
            "owner-ops",
            "python",
            "-m",
            "app.cli",
            "provision-db-role",
        )

    def start(self, root: Path):
        self.announce("запуск и HTTPS readiness")
        # PostgreSQL is explicitly managed by install/update. Restore must not downgrade
        # its binaries; backup/restart must preserve the running compatible patch too.
        self.compose(
            root,
            "up",
            "-d",
            "--no-deps",
            "--wait",
            "--wait-timeout",
            "180",
            "backend",
            "frontend",
            "proxy",
        )
        self.health(root)
        self.mark_current(root)
        (self.state / "pending.json").unlink(missing_ok=True)

    def health(self, root: Path):
        origin = json.loads(self.config["APP_ORIGINS"])[0]
        host = urlsplit(origin).hostname
        address = self.config["HTTPS_BIND"]
        if address == "0.0.0.0":
            address = "127.0.0.1"
        execute(
            [
                "curl",
                "--fail",
                "--silent",
                "--show-error",
                "--noproxy",
                "*",
                "--max-time",
                "20",
                "--cacert",
                self.config["TLS_CA_FILE"],
                "--resolve",
                f"{host}:{self.config['HTTPS_PORT']}:{address}",
                origin + "/api/v1/health/ready",
            ],
            env=self.base_env(),
        )

    def install(self, root: Path):
        if (self.state / "current.json").exists() or (
            self.state / "pending.json"
        ).exists():
            raise ValueError("Контур уже инициализирован или требует восстановления")
        self.prepare(root)
        existing = execute(
            ["docker", "volume", "ls", "--format", "{{.Name}}"], env=self.base_env()
        ).splitlines()
        names = [self.project + "-postgres", self.project + "-files"]
        if any(name in existing for name in names):
            raise ValueError(
                "Volumes уже существуют; install не принимает существующие данные"
            )
        self.pending(root)
        for name in names:
            execute(["docker", "volume", "create", name], env=self.base_env())
        self.compose(root, "up", "-d", "--wait", "--wait-timeout", "180", "postgres")
        self.migrate(root)
        self.start(root)

    def update(self, root: Path):
        if (self.state / "pending.json").exists():
            raise ValueError(
                "Незавершённая операция: сначала диагностика/восстановление"
            )
        old = self.current()
        old_manifest, new_manifest = verify_release(old), verify_release(root)
        if old_manifest["postgres_major"] != new_manifest["postgres_major"]:
            raise ValueError("Major PostgreSQL меняется отдельной процедурой")
        self.prepare(root)
        self.announce("остановка записи и согласованный backup")
        self.compose(
            old, "stop", "proxy", "backend", "runtime-ops", "owner-ops", "file-ops"
        )
        self.last_backup = self.backup(old)
        # Only after verified backup may the PostgreSQL patch image and schema change.
        self.pending(root)
        self.compose(root, "up", "-d", "--wait", "--wait-timeout", "180", "postgres")
        self.migrate(root)
        self.start(root)

    def backup(self, root: Path) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        dest = self.state / "backups" / timestamp
        dest.mkdir(parents=True, mode=0o700)
        self.last_backup = dest
        print(f"Резервная копия: {dest}", flush=True)
        with (dest / "database.dump").open("xb") as output:
            self.compose(
                root,
                "exec",
                "-T",
                "postgres",
                "sh",
                "-ec",
                'exec pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"',
                stdout=output,
            )
        self.compose(
            root,
            "run",
            "--rm",
            "--no-deps",
            "-v",
            f"{dest}:/backup",
            "file-ops",
            "python",
            "/tools/file_archive.py",
            "pack",
            "/backup/files.tar.gz",
        )
        data = {
            "format": 1,
            "project": self.project,
            "postgres_db": self.config["POSTGRES_DB"],
            "release": verify_release(root),
            "created_utc": timestamp,
            "recovery_only": (self.state / "pending.json").exists(),
        }
        self.atomic_json(dest / "backup.json", data)
        write_checksums(dest, BACKUP_FILES)
        self.verify_backup(root, dest)
        return dest

    def verify_backup(self, root: Path, backup: Path) -> dict:
        verify_files(backup, BACKUP_FILES)
        data = read_json(backup / "backup.json")
        if (
            data.get("format") != 1
            or data.get("project") != self.project
            or data.get("postgres_db") != self.config["POSTGRES_DB"]
        ):
            raise ValueError("Backup относится к другому контуру/БД")
        check_files(backup / "files.tar.gz")
        if (backup / "database.dump").stat().st_size < 5:
            raise ValueError("Пустой dump")
        with (backup / "database.dump").open("rb") as stream:
            # Fully read/decompress dump, not only its TOC. Does not execute restored SQL.
            self.compose(
                root,
                "exec",
                "-T",
                "postgres",
                "pg_restore",
                "--file=/dev/null",
                stdin=stream,
            )
        return data

    def restore(self, root: Path, backup: Path, confirmation: str):
        # Pure validation and typed confirmation precede even Docker image load/stop.
        manifest = verify_release(root)
        expected = f"RESTORE {self.project} {manifest['version']}"
        if confirmation != expected:
            raise ValueError("Введённая фраза не совпадает; восстановление отменено")
        verify_files(backup, BACKUP_FILES)
        data = read_json(backup / "backup.json")
        if data.get("release") != manifest or data.get("recovery_only"):
            raise ValueError(
                "Требуется точный исходный выпуск backup; аварийный снимок требует ручной диагностики"
            )
        if (
            data.get("project") != self.project
            or data.get("postgres_db") != self.config["POSTGRES_DB"]
        ):
            raise ValueError("Backup не соответствует контуру/БД")
        check_files(backup / "files.tar.gz")
        current = self.current()
        self.prepare(root)
        self.verify_backup(current, backup)
        self.announce("остановка записи перед явным восстановлением")
        self.compose(
            current, "stop", "proxy", "backend", "runtime-ops", "owner-ops", "file-ops"
        )
        self.backup(current)  # Preserve current data before destructive restoration.
        self.pending(root)
        self.announce("явное восстановление базы и файлов")
        # Use the currently running compatible PostgreSQL 17 patch, not a binary downgrade.
        self.compose(
            current,
            "exec",
            "-T",
            "postgres",
            "sh",
            "-ec",
            'dropdb --force --if-exists -U "$POSTGRES_USER" -- "$POSTGRES_DB"; '
            'createdb -U "$POSTGRES_USER" -O "$POSTGRES_USER" -- "$POSTGRES_DB"',
        )
        with (backup / "database.dump").open("rb") as source:
            self.compose(
                current,
                "exec",
                "-T",
                "postgres",
                "sh",
                "-ec",
                "exec pg_restore --exit-on-error --single-transaction --no-owner --no-privileges "
                '-U "$POSTGRES_USER" -d "$POSTGRES_DB"',
                stdin=source,
            )
        self.compose(
            root,
            "run",
            "--rm",
            "--no-deps",
            "-v",
            f"{backup}:/backup:ro",
            "file-ops",
            "python",
            "/tools/file_archive.py",
            "restore",
            "/backup/files.tar.gz",
        )
        self.compose(
            root,
            "run",
            "--rm",
            "--no-deps",
            "owner-ops",
            "python",
            "-m",
            "app.cli",
            "provision-db-role",
        )
        self.start(root)


def main() -> int:
    parser = argparse.ArgumentParser(description="Офлайн deploy ИТ-элемент [29]")
    parser.add_argument(
        "action",
        choices=["install", "update", "backup", "restore", "health", "create-admin"],
    )
    parser.add_argument(
        "--environment", required=True, choices=["production", "staging"]
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--release", type=Path)
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--username")
    parser.add_argument("--display-name")
    args = parser.parse_args()
    operation = None
    try:
        if sys.platform != "linux" or sys.version_info < (3, 12):
            raise ValueError("Серверный runner требует Ubuntu 24.04 / Python 3.12+")
        if os.geteuid() != 0:
            raise ValueError("Запустите через sudo")
        os.umask(0o077)
        state = Path("/var/lib/element29") / args.environment
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        import fcntl

        with (state / "deploy.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError(
                    "Другая операция deploy/backup/restore уже выполняется"
                ) from None
            operation = Deployment(args.environment, args.config, state)
            operation.preflight()
            root = args.release.resolve() if args.release else None
            if args.action in {"install", "update", "restore"} and root is None:
                raise ValueError("Обязателен --release")
            if args.action == "install":
                operation.install(root)
            elif args.action == "update":
                operation.update(root)
            elif args.action == "restore":
                if args.backup is None or not sys.stdin.isatty():
                    raise ValueError(
                        "Нужны --backup и интерактивный терминал для подтверждения"
                    )
                version = verify_release(root)["version"]
                phrase = input(
                    f"Будут заменены база и файлы. Введите RESTORE {operation.project} {version}: "
                )
                operation.restore(root, args.backup.resolve(), phrase)
            elif args.action == "health":
                operation.health(operation.current())
            elif args.action == "create-admin":
                if not args.username or not args.display_name or not sys.stdin.isatty():
                    raise ValueError(
                        "Нужны --username, --display-name и интерактивный терминал"
                    )
                operation.compose(
                    operation.current(),
                    "run",
                    "--rm",
                    "--no-deps",
                    "runtime-ops",
                    "python",
                    "-m",
                    "app.cli",
                    "create-admin",
                    "--username",
                    args.username,
                    "--display-name",
                    args.display_name,
                    interactive=True,
                )
            else:
                if (state / "pending.json").exists():
                    raise ValueError("Сначала разберите незавершённую операцию")
                root = operation.current()
                operation.compose(
                    root,
                    "stop",
                    "proxy",
                    "backend",
                    "runtime-ops",
                    "owner-ops",
                    "file-ops",
                )
                operation.backup(root)
                operation.start(root)
            print("Операция завершена; проверки пройдены.")
            return 0
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        stage = operation.stage if operation else "проверка параметров"
        print(f"Остановка на этапе «{stage}»: {exc}", file=sys.stderr)
        if operation and operation.last_backup:
            print(f"Сохранён путь backup: {operation.last_backup}", file=sys.stderr)
        print(
            "Автоматический rollback/restore не выполнялся. Проверьте состояние до возобновления записи.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
