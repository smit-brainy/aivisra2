#!/usr/bin/env bash
# Standalone Frontend Vite Dev Server Runner
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/frontend"

echo "=========================================================="
echo " Starting AIVISRA StreamCore React Dev Server"
echo " Dev URL: http://localhost:5173"
echo " Backend Proxy: http://127.0.0.1:8765"
echo "=========================================================="

npm run dev -- --host 0.0.0.0

