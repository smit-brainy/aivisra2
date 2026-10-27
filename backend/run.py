"""Standalone runner for the StreamCore Backend.

Usage:
    python -m backend.run [--host 0.0.0.0] [--port 8765] [--config runtime/streamcore/app.yaml]
"""

import argparse
import os
import uvicorn
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="AIVISRA StreamCore Standalone Backend Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host address to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on (default: 8765)")
    parser.add_argument("--config", default="runtime/streamcore/app.yaml", help="Path to app.yaml configuration")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    args = parser.parse_args()

    os.environ["STREAMCORE_CONFIG"] = args.config

    print(f"Starting AIVISRA StreamCore Backend on http://{args.host}:{args.port}")
    print(f"Swagger API Documentation: http://{args.host}:{args.port}/docs")
    uvicorn.run("backend.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()

