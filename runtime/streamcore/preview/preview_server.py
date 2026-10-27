"""StreamCore Preview and Live UI Server Bridge.

Integrates the modular FastAPI backend and compiled React SPA with the active
StreamCore GPU engine instance.
"""

import threading
import logging
from typing import Any
import uvicorn

from backend.app import app
from backend.dependencies import set_engine_and_cache
from ..engine import StreamCore
from .preview_cache import PreviewCache

logger = logging.getLogger("streamcore.preview")


class UvicornPreviewServer:
    """Daemon thread wrapper managing Uvicorn ASGI server lifecycle."""

    def __init__(self, asgi_app: Any, host: str, port: int):
        self.config = uvicorn.Config(
            asgi_app,
            host=host,
            port=port,
            log_level="warning",
            access_log=False,
        )
        self.server = uvicorn.Server(self.config)
        self.thread = threading.Thread(
            target=self.server.run,
            name="streamcore-preview",
            daemon=True,
        )
        self.thread.start()

    def shutdown(self) -> None:
        """Signal uvicorn server to stop."""
        self.server.should_exit = True

    def server_close(self) -> None:
        """Alias for server termination parity with http.server."""
        self.server.should_exit = True


def start_preview(
    engine: StreamCore,
    cache: PreviewCache,
    port: int,
) -> UvicornPreviewServer:
    """Start the preview server hosting FastAPI backend and React frontend."""
    # Register active engine & cache dependencies for FastAPI routers
    set_engine_and_cache(engine, cache)

    logger.info(
        "starting_fastapi_preview_server",
        extra={"port": port, "frontend": "React 18 SPA", "backend": "FastAPI"},
    )
    return UvicornPreviewServer(app, host="0.0.0.0", port=port)
