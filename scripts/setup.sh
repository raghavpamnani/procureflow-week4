#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ "$(uname -s)" = Darwin ]; then
  venv_path="${PROCUREFLOW_VENV:-$HOME/Library/Caches/ProcureFlow/venv}"
else
  venv_path="${PROCUREFLOW_VENV:-$(pwd)/.venv}"
fi
if [ ! -x "$venv_path/bin/python" ]; then
  python3 -m venv "$venv_path"
fi
"$venv_path/bin/python" -m pip install -r requirements.lock
printf 'Environment ready: %s\nRun ./scripts/run.sh\n' "$venv_path"
