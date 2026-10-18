"""Container helper: preserve only regular upload files; never follow links."""

from __future__ import annotations

import argparse
import os
import shutil
import tarfile
from pathlib import Path, PurePosixPath


def members_checked(stream: tarfile.TarFile):
    names = set()
    members = stream.getmembers()
    for member in members:
        parts = PurePosixPath(member.name).parts
        if (
            not parts
            or parts[0] != "files"
            or member.name != "/".join(parts)
            or any(p in {".", ".."} for p in parts)
            or "\\" in member.name
            or ":" in member.name
            or member.name in names
            or not (member.isdir() or member.isfile())
        ):
            raise ValueError("Недопустимый путь или тип файла backup")
        names.add(member.name)
    if "files" not in names:
        raise ValueError("В backup нет корневого каталога files")
    by_name = {m.name: m for m in members}
    if not by_name["files"].isdir():
        raise ValueError("files должен быть каталогом")
    for member in members:
        for ancestor in PurePosixPath(member.name).parents:
            if str(ancestor) == ".":
                continue
            if str(ancestor) not in by_name or not by_name[str(ancestor)].isdir():
                raise ValueError("Некорректная иерархия backup")
    return members


def check(archive: Path) -> None:
    with tarfile.open(archive, "r:gz") as stream:
        for member in members_checked(stream):
            if member.isfile():
                with stream.extractfile(member) as source:
                    while source.read(1024 * 1024):
                        pass


def pack(source: Path, archive: Path) -> None:
    paths = [source, *sorted(source.rglob("*"))]
    if source.is_symlink() or not source.is_dir():
        raise ValueError("Некорректный uploads volume")
    for path in paths:
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("Ссылки и специальные файлы в uploads запрещены")
    with tarfile.open(archive, "x:gz") as stream:
        for path in paths:
            suffix = path.relative_to(source).as_posix()
            stream.add(
                path,
                arcname="files" if suffix == "." else "files/" + suffix,
                recursive=False,
            )
    check(archive)


def restore(archive: Path, target: Path, *, set_owner: bool = True) -> None:
    check(
        archive
    )  # All paths and compressed file data checked before removing anything.
    if target.is_symlink() or not target.is_dir():
        raise ValueError("Ожидался существующий uploads volume")
    for path in target.iterdir():
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
        else:
            raise ValueError("Специальный файл в uploads")
    with tarfile.open(archive, "r:gz") as stream:
        members = members_checked(stream)
        for member in sorted(
            members, key=lambda item: (len(PurePosixPath(item.name).parts), item.name)
        ):
            relative = PurePosixPath(member.name).relative_to("files")
            dest = target.joinpath(*relative.parts)
            if member.isdir():
                dest.mkdir(exist_ok=True, mode=0o750)
            else:
                with stream.extractfile(member) as source, dest.open("xb") as output:
                    shutil.copyfileobj(source, output)
                dest.chmod(0o640)
            if set_owner:
                os.chown(dest, 10001, 10001)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["pack", "check", "restore"])
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    if args.action == "pack":
        pack(Path("/app/uploads"), args.archive)
    elif args.action == "check":
        check(args.archive)
    else:
        restore(args.archive, Path("/app/uploads"))
