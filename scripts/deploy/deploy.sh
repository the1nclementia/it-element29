#!/usr/bin/env bash
set -euo pipefail
umask 077
command -v python3 >/dev/null || { printf '%s\n' 'Требуется Python 3.12+' >&2; exit 1; }
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$script_dir/deploy.py" "$@"
