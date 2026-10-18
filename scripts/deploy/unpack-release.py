#!/usr/bin/env python3
"""Run this only after authenticating this helper through a trusted channel."""

import argparse
import sys
from pathlib import Path

sys.dont_write_bytecode = True
from release_lib import unpack_release

parser = argparse.ArgumentParser(description="Проверить и распаковать офлайн-выпуск")
parser.add_argument("archive", type=Path)
parser.add_argument("target", type=Path)
parser.add_argument("--sha256", required=True)
args = parser.parse_args()
try:
    data = unpack_release(args.archive, args.target, args.sha256)
    print(f"Проверен выпуск {data['version']}, commit {data['git_commit']}")
except (ValueError, OSError) as exc:
    parser.exit(1, f"Отказ проверки: {exc}\n")
