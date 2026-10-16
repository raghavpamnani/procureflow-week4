#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ -n "${PROCUREFLOW_VENV:-}" ]; then
  python_bin="$PROCUREFLOW_VENV/bin/python"
elif [ "$(uname -s)" = Darwin ] && [ -x "$HOME/Library/Caches/ProcureFlow/venv/bin/python" ]; then
  python_bin="$HOME/Library/Caches/ProcureFlow/venv/bin/python"
else
  python_bin="$(pwd)/.venv/bin/python"
fi
if [ ! -x "$python_bin" ]; then
  echo 'Run ./scripts/setup.sh first.' >&2
  exit 1
fi
exec "$python_bin" "$@"
