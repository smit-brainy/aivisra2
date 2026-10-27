"""FastAPI application factory for AIVISRA StreamCore.

Mounts:
- Streams router (/frame, /stream, /api/clips, /api/webrtc)
- Telemetry router (/api/status, /api/tracks, /api/detections, /api/frames/batch)
- Cameras router (/api/cameras, onboarding)
- Spatial router (/api/cameras/{id}/zones, lines, rules, occupancy)
- Search router (/api/search-visual, /api/events, snapshots)
- Static files for frontend React build (or dev proxy)
"""

import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .routers import streams, telemetry, cameras, spatial, search
from .dependencies import get_engine

app = FastAPI(
    title="AIVISRA StreamCore API",
    description="GPU-Native AI Vision Surveillance System with Local VLM & Spatial Intelligence",
    version="2.0.0",
)


@app.on_event("startup")
def on_startup():
    """Ensure engine is initialized when backend server starts."""
    get_engine()

# Enable CORS for React frontend (both local dev server on :5173 and preview server on :8765)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all modular routers verbatim
app.include_router(streams.router)
app.include_router(telemetry.router)
app.include_router(cameras.router)
app.include_router(spatial.router)
app.include_router(search.router)

# Mount Frontend static files if compiled frontend dist exists
frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    @app.api_route("/", methods=["GET", "HEAD"])
    @app.api_route("/demo", methods=["GET", "HEAD"])
    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"])
    def serve_spa(full_path: str = ""):
        # Don't intercept API calls or stream calls
        if full_path.startswith("api/") or full_path.startswith("stream/") or full_path.startswith("frame/"):
            return FileResponse(frontend_dist / "index.html")
        requested_file = frontend_dist / full_path
        if full_path and requested_file.is_file():
            return FileResponse(requested_file)
        return FileResponse(frontend_dist / "index.html")
