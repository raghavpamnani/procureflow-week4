#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export OLLAMA_MODELS="$(pwd)/.runtime/models"
export OLLAMA_HOST=127.0.0.1:11435
export OLLAMA_NO_CLOUD=1
export OLLAMA_NUM_PARALLEL=1
if [ -x .runtime/ollama/ollama ]; then
  exec .runtime/ollama/ollama serve
fi
echo "Project-local Ollama runtime is missing. Install Ollama from https://ollama.com/download and use its normal server, or place the official binary in .runtime/ollama/." >&2
exit 1
