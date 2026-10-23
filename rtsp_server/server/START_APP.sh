#!/usr/bin/env bash
# AIVISRA Virtual CCTV & Enterprise NVR - Linux Launcher
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Ensure tools/mediamtx is executable
if [ -f "$DIR/tools/mediamtx" ]; then
    chmod +x "$DIR/tools/mediamtx"
    # Clean up any lingering background instance of this mediamtx binary
    pkill -f "$DIR/tools/mediamtx" 2>/dev/null || true
    sleep 0.2
fi

# Detect python
if command -v python3 >/dev/null 2>&1; then
    PY="python3"
elif command -v python >/dev/null 2>&1; then
    PY="python"
else
    echo "Error: Python 3 not found on system."
    exit 1
fi

# Check DISPLAY
if [ -z "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ]; then
    echo "No desktop DISPLAY detected. Starting in CLI mode."
    echo "Usage: ./START_APP.sh --video /path/to/video.mp4 --count 10"
    $PY app.py --cli "$@"
else
    $PY app.py "$@"
fi
