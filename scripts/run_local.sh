#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export PROCUREFLOW_MODE=ollama
export PROCUREFLOW_MODEL="${PROCUREFLOW_MODEL:-qwen3:1.7b}"
export OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11435}"
export PROCUREFLOW_HOME="${PROCUREFLOW_HOME:-$(pwd)/.runtime/local-model-demo}"
exec ./scripts/run.sh
