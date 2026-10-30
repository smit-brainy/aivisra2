#!/usr/bin/env bash
# Standalone Backend Server Runner
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${1:-8765}"

# Prefer the active conda env (expected: `conda activate nvr`), then $PYTHON,
# then python3 on PATH.
if [ -n "${CONDA_PREFIX:-}" ] && [ -x "${CONDA_PREFIX}/bin/python3" ]; then
  PYTHON_BIN="${CONDA_PREFIX}/bin/python3"
elif [ -n "${PYTHON:-}" ]; then
  PYTHON_BIN="${PYTHON}"
else
  PYTHON_BIN="python3"
fi

echo "=========================================================="
echo " Starting AIVISRA StreamCore Standalone FastAPI Backend"
echo " Python: ${PYTHON_BIN}"
echo " Web API: http://127.0.0.1:${PORT}"
echo " Swagger Docs: http://127.0.0.1:${PORT}/docs"
echo "=========================================================="

"${PYTHON_BIN}" -m backend.run --port "${PORT}"
