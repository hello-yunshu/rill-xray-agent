#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
python3 scripts/run_all_checks.py
command -v shellcheck >/dev/null || { echo 'ShellCheck required' >&2; exit 2; }
shellcheck bin/* integrations/xray_bash_onekey/repository_files/scripts/*.sh
