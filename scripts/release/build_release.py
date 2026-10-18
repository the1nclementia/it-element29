"""Build only a clean committed snapshot; package an explicit allowlist."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy"))
from release_lib import (
    DEPLOY_FILES,
    RELEASE_FILES,
    digest,
    validate_version,
    verify_release,
    write_checksums,
)


def run(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def build(args) -> Path:
    validate_version(args.version)
    for value, repository in [
        (args.postgres_image, "postgres"),
        (args.nginx_image, "nginx"),
    ]:
        if not re.fullmatch(
            repository + r":[0-9][a-z0-9.-]*@sha256:[a-f0-9]{64}", value
        ):
            raise ValueError(f"Нужен проверенный version@sha256 для {repository}")
    if not args.postgres_image.startswith("postgres:17."):
        raise ValueError("Выпуск поддерживает только PostgreSQL 17")
    root = Path(run("git", "rev-parse", "--show-toplevel", cwd=Path(__file__).parent))
    if run("git", "status", "--porcelain", "--untracked-files=all", cwd=root):
        raise ValueError(
            "Сначала проверьте и закоммитьте все изменения; дерево Git должно быть чистым"
        )
    commit = run("git", "rev-parse", "HEAD", cwd=root)
    output = args.output.resolve()
    if output.exists():
        raise ValueError("Каталог выпуска уже существует; перезапись запрещена")
    run("docker", "info", "--format", "{{.OSType}}")
    run("docker", "buildx", "version")
    tag = f"{args.version}-{commit[:12]}"
    images = []
    with tempfile.TemporaryDirectory(prefix="element29-build-") as temp:
        work = Path(temp)
        snapshot = work / "source"
        snapshot.mkdir()
        run(
            "git",
            "archive",
            "--format=zip",
            "--output",
            str(work / "source.zip"),
            commit,
            cwd=root,
        )
        with zipfile.ZipFile(work / "source.zip") as archive:
            for member in archive.infolist():
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Ссылки в build context запрещены")
            archive.extractall(snapshot)
        for service in ["backend", "frontend"]:
            ref = f"element29/{service}:{tag}"
            command = [
                "docker",
                "buildx",
                "build",
                "--platform",
                args.platform,
                "--load",
                "--pull",
                "--tag",
                ref,
            ]
            if service == "backend":
                command += ["--target", "runtime", str(snapshot / "backend")]
            else:
                command += [
                    "--file",
                    str(snapshot / "frontend/Dockerfile"),
                    str(snapshot),
                ]
            print(f"Сборка {service} для {args.platform}...", flush=True)
            run(*command)
            images.append(
                {"service": service, "ref": ref, "source_ref": "git:" + commit}
            )
        for service, source in [
            ("postgres", args.postgres_image),
            ("proxy", args.nginx_image),
        ]:
            run("docker", "pull", "--platform", args.platform, source)
            ref = f"element29/{service}:{tag}"
            run("docker", "tag", source, ref)
            images.append({"service": service, "ref": ref, "source_ref": source})
        for item in images:
            info = json.loads(run("docker", "image", "inspect", item["ref"]))[0]
            if f"{info['Os']}/{info['Architecture']}" != args.platform:
                raise ValueError(
                    "Платформа загруженного образа не соответствует выпуску"
                )
            item.update(id=info["Id"], repo_digests=info.get("RepoDigests") or [])
        package = work / "package"
        package.mkdir()
        for name in DEPLOY_FILES:
            src = snapshot / name
            if src.is_symlink() or not src.is_file():
                raise ValueError(f"Файл allowlist отсутствует в commit: {name}")
            dest = package / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
        run(
            "docker",
            "save",
            "--output",
            str(package / "images.tar"),
            *(item["ref"] for item in images),
        )
        manifest = {
            "format": 1,
            "version": args.version,
            "git_commit": commit,
            "platform": args.platform,
            "postgres_major": 17,
            "created_utc": datetime.now(UTC).isoformat(),
            "images": images,
        }
        (package / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        write_checksums(package, RELEASE_FILES)
        verify_release(package)
        # Publish output only after all build/validation steps succeed.
        output.mkdir(parents=True)
        archive_path = (
            output / f"element29-{tag}-{args.platform.replace('/', '-')}.tar.gz"
        )
        with tarfile.open(archive_path, "w:gz") as archive:
            for name in sorted(RELEASE_FILES):
                archive.add(package / name, arcname=name, recursive=False)
        archive_path.with_suffix(archive_path.suffix + ".sha256").write_text(
            f"{digest(archive_path)}  {archive_path.name}\n", encoding="ascii"
        )
        shutil.copyfile(package / "manifest.json", output / "manifest.json")
        print(f"Выпуск: {archive_path}\nSHA256: {digest(archive_path)}")
        return archive_path


def main():
    parser = argparse.ArgumentParser(
        description="Собрать офлайн-выпуск из чистого commit"
    )
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--platform", choices=["linux/amd64", "linux/arm64"], default="linux/amd64"
    )
    parser.add_argument("--postgres-image", required=True)
    parser.add_argument("--nginx-image", required=True)
    try:
        build(parser.parse_args())
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        # Do not echo subprocess environments/commands; builder output is not an audit log.
        print(
            f"Сборка остановлена: {type(exc).__name__}. Проверьте дерево, Docker и параметры.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
