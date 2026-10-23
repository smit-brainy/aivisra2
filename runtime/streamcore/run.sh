#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Always execute from workspace root to avoid Python shadowing standard library 'types'
cd "$WORKSPACE_ROOT"

echo "=================================================="
echo " Starting AIVISRA StreamCore                      "
echo " Live Web Preview: http://localhost:8765          "
echo "=================================================="

exec python3 -m mis.runtime.streamcore.main \
  --config "$WORKSPACE_ROOT/config/streamcore/app.yaml" \
  --preview-port 8765 \
  --verbose-cameras \
  "$@"
