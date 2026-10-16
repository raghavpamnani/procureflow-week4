#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export PROCUREFLOW_HOME="${PROCUREFLOW_HOME:-$(pwd)/.runtime}"
export PROCUREFLOW_MODE="${PROCUREFLOW_MODE:-demo}"
export LANGSMITH_TRACING=false
exec ./scripts/python.sh -m uvicorn procureflow.api:app --host 127.0.0.1 --port "${PROCUREFLOW_PORT:-8040}"
