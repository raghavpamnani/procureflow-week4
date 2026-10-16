#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ "$(uname -s)" = Darwin ]; then
  export OLLAMA_MODELS="${PROCUREFLOW_MODEL_DIR:-$HOME/Library/Caches/ProcureFlow/models}"
  cached_bin="$HOME/Library/Caches/ProcureFlow/ollama/ollama"
else
  export OLLAMA_MODELS="${PROCUREFLOW_MODEL_DIR:-$(pwd)/.runtime/models}"
  cached_bin="$(pwd)/.runtime/ollama/ollama"
fi
export OLLAMA_HOST=127.0.0.1:11435
export OLLAMA_NO_CLOUD=1
export OLLAMA_NUM_PARALLEL=1
if [ -n "${PROCUREFLOW_OLLAMA_BIN:-}" ]; then
  exec "$PROCUREFLOW_OLLAMA_BIN" serve
elif [ -x "$cached_bin" ]; then
  exec "$cached_bin" serve
elif command -v ollama >/dev/null 2>&1; then
  exec ollama serve
fi
echo "Install the official Ollama runtime from https://ollama.com/download, then run this script again." >&2
exit 1
