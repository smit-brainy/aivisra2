#!/usr/bin/env bash
# Standalone Backend Server Runner
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${1:-8765}"
echo "=========================================================="
echo " Starting AIVISRA StreamCore Standalone FastAPI Backend"
echo " Web API: http://127.0.0.1:${PORT}"
echo " Swagger Docs: http://127.0.0.1:${PORT}/docs"
echo "=========================================================="

/home/brainy/miniconda3/envs/nvr/bin/python3 -m backend.run --port "${PORT}"

