"""Camera management, metadata, areas, and onboarding endpoints.

Serves:
- /api/cameras (GET, POST)
- /api/cameras/{camera_id} (GET, PUT metadata)
- /api/areas (GET, POST), /api/areas/{area_id} (PUT, DELETE)
- /api/capabilities (GET)
- /api/cameras/{camera_id}/onboarding/status (GET)
- /api/cameras/{camera_id}/recommendations (GET)
- /api/cameras/{camera_id}/capabilities (GET, PUT)
- /api/cameras/{camera_id}/onboarding/analyze (POST)
- /api/cameras/{camera_id}/onboarding/reset (POST)
"""

import json
import csv
import io
import logging
import threading
import time
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit
from fastapi import APIRouter, HTTPException, Request, status

from ..dependencies import get_engine
from ..schemas.models import (
    AreaCreateRequest,
    AreaUpdateRequest,
    CameraAnalyzeRequest,
    CameraMetadataRequest,
    CameraRegisterRequest,
    ApplyCapabilitiesRequest,
)
from ..state_store import get_state_store
from ..database import connect
from runtime.onboarding.onboarding_service import sanitize_rtsp_url

router = APIRouter(tags=["Cameras & Onboarding"])
logger = logging.getLogger("streamcore.backend.cameras")

DETAIL_FPS = {"low": 1.0, "standard": 5.0, "high": 15.0, "maximum": 25.0}


def _camera_health(engine: Any) -> dict[str, dict[str, Any]]:
    """Read per-camera health from the live metrics registry."""
    metrics = getattr(engine, "metrics", None) if engine else None
    if metrics is None:
        return {}
    try:
        return (metrics.view().get("cameras") or {})
    except Exception:
        return {}


def _normalize_status(health: dict[str, Any] | None) -> str:
    """Return connection status; health remains available as a separate field."""
    if not health:
        return "unknown"
    state = str(health.get("state") or "").upper()
    # A stream with an active reader is online even when its FPS health is
    # degraded. The health field still exposes that performance detail.
    if state == "CONNECTED":
        return "online"
    value = str(health.get("health") or "").upper()
    if value in ("DEGRADED", "STALE"):
        return "degraded"
    if value == "RECONNECTING":
        return "reconnecting"
    if value == "OFFLINE":
        return "offline"
    if state == "DEGRADED":
        return "degraded"
    if state == "RECONNECTING":
        return "reconnecting"
    return "offline"


def _camera_payload(camera: Any, meta: dict[str, Any], areas: dict[str, dict[str, Any]],
                    health: dict[str, Any] | None, stored: Any = None) -> dict[str, Any]:
    area_id = meta.get("area_id")
    area = areas.get(area_id) if area_id else None
    display_name = meta.get("display_name") or camera.id
    health = health or {}
    status_value = _normalize_status(health)
    return {
        "camera_id": camera.id,
        "name": display_name,
        "display_name": display_name,
        "area_id": area_id,
        "area": {"area_id": area["area_id"], "name": area["name"]} if area else None,
        "kind": meta.get("kind") or "both",
        "level": meta.get("level") or "standard",
        "notes": meta.get("notes"),
        "rtsp_url": sanitize_rtsp_url((stored["uri"] if stored else camera.uri)),
        "codec": stored["codec"] if stored else camera.codec,
        "decoder": stored["decoder"] if stored else camera.decoder,
        "decoding_fps": stored["decoding_fps"] if stored else None,
        "enabled": camera.enabled,
        "live_path": camera.live_path,
        "stream_url": f"/stream/{camera.id}",
        "frame_url": f"/frame/{camera.id}.jpg",
        "status": status_value,
        "health": health.get("health"),
        "state": health.get("state"),
        "online": status_value == "online",
        "fps": health.get("actual_fps"),
        "ai_fps": health.get("ai_fps"),
        "expected_fps": health.get("expected_fps"),
        "frame_age_ms": health.get("frame_age_ms"),
        "last_frame_time": health.get("last_frame_time"),
        "last_error": health.get("last_error"),
        "reconnect_count": health.get("reconnect_count", 0),
    }


def _configured_cameras(engine: Any) -> list[Any]:
    return list(getattr(engine, "cameras", None) or [])


def _resolve_area_id(area_value: str | None, *, create: bool = False) -> str | None:
    """Resolve an area ID or name for UI and CSV imports."""
    clean = (area_value or "").strip()
    if not clean:
        return None
    store = get_state_store()
    areas = store.list_areas()
    for area in areas:
        if area["area_id"] == clean or area["name"].casefold() == clean.casefold():
            return area["area_id"]
    if create:
        return store.create_area(clean)["area_id"]
    raise ValueError(f"Unknown area '{clean}'. Create it first or leave Area blank.")


def _assign_camera_area(camera_id: str, area_id: str | None, display_name: str) -> None:
    store = get_state_store()
    store.ensure_camera(camera_id, display_name)
    if area_id is not None:
        store.update_camera(camera_id, {"area_id": area_id})


@router.get("/api/capabilities")
def get_capabilities():
    """List all registered AI capabilities."""
    engine = get_engine()
    service = getattr(engine, "onboarding_service", None) if engine else None
    if service is not None:
        return [c.to_dict() for c in service.registry.all()]
    return []


@router.get("/api/cameras")
def get_cameras():
    """List configured cameras with operator metadata and live health."""
    engine = get_engine()
    store = get_state_store()
    areas = {area["area_id"]: area for area in store.list_areas()}
    health_by_camera = _camera_health(engine)
    running = {camera.id: camera for camera in _configured_cameras(engine)}
    # Read all camera configuration in one short transaction.  Opening a new
    # SQLite connection for every camera made this endpoint increasingly slow
    # while the event writer was active, which caused the UI to fall back to an
    # empty list under load.
    with connect() as conn:
        rows = conn.execute("SELECT camera_id, name, uri, codec, decoder, status, decoding_fps FROM cameras ORDER BY created_at ASC").fetchall()
    cameras = []
    for row in rows:
        cameras.append(running.get(row["camera_id"]) or SimpleNamespace(
            id=row["camera_id"], uri=row["uri"], codec=row["codec"], decoder=row["decoder"],
            enabled=row["status"] not in ("disabled", "offline"), live_path=None,
        ))
    if not cameras:
        cameras = list(running.values())
    return [
        _camera_payload(
            camera,
            store.ensure_camera(camera.id, camera.id),
            areas,
            health_by_camera.get(camera.id),
            next((row for row in rows if row["camera_id"] == camera.id), None),
        )
        for camera in cameras
    ]


@router.get("/api/cameras/{camera_id}")
def get_camera(camera_id: str):
    """Return one configured camera with metadata and live health."""
    engine = get_engine()
    camera = next((c for c in _configured_cameras(engine) if c.id == camera_id), None)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Unknown camera: {camera_id}")
    store = get_state_store()
    areas = {area["area_id"]: area for area in store.list_areas()}
    return _camera_payload(
        camera,
        store.ensure_camera(camera.id, camera.id),
        areas,
        _camera_health(engine).get(camera.id),
    )


@router.put("/api/cameras/{camera_id}")
def update_camera_metadata(camera_id: str, payload: CameraMetadataRequest):
    """Update operator-editable metadata and persisted stream configuration."""
    engine = get_engine()
    with connect() as conn:
        stored_camera = conn.execute("SELECT 1 FROM cameras WHERE camera_id = ?", (camera_id,)).fetchone()
    if not any(c.id == camera_id for c in _configured_cameras(engine)) and stored_camera is None:
        raise HTTPException(status_code=404, detail=f"Unknown camera: {camera_id}")

    fields = payload.model_dump(exclude_unset=True)
    stream_fields = {}
    if "camera_id" in fields:
        stream_fields["camera_id"] = fields.pop("camera_id")
    if "name" in fields:
        stream_fields["name"] = fields.pop("name")
    if "uri" in fields or "rtsp_url" in fields:
        stream_fields["uri"] = fields.pop("uri", fields.pop("rtsp_url", None))
    for key in ("codec", "decoder", "decoding_fps"):
        if key in fields:
            stream_fields[key] = fields.pop(key)
    if "display_name" in fields and "name" not in stream_fields:
        stream_fields["name"] = fields["display_name"]
    store = get_state_store()
    try:
        store.update_camera(camera_id, fields)
        if "level" in fields and engine is not None:
            target_fps = DETAIL_FPS[fields["level"]]
            setter = getattr(engine, "set_camera_target_fps", None)
            if setter is not None:
                setter(camera_id, target_fps)
        if stream_fields:
            assignments = ", ".join(f"{key} = ?" for key in stream_fields)
            values = list(stream_fields.values()) + [time.time(), camera_id]
            with connect() as conn:
                cursor = conn.execute(
                    f"UPDATE cameras SET {assignments}, updated_at = ? WHERE camera_id = ?",
                    values,
                )
                if cursor.rowcount == 0:
                    raise ValueError(f"Camera '{camera_id}' is not stored in the database")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    camera = next((c for c in _configured_cameras(engine) if c.id == camera_id), None)
    if camera is None:
        with connect() as conn:
            row = conn.execute("SELECT camera_id, uri, codec, decoder, status FROM cameras WHERE camera_id = ?", (camera_id,)).fetchone()
        if row is None:
            # The ID may have been changed; return the persisted record when possible.
            new_id = stream_fields.get("camera_id", camera_id)
            with connect() as conn:
                row = conn.execute("SELECT camera_id, uri, codec, decoder, status FROM cameras WHERE camera_id = ?", (new_id,)).fetchone()
        if row is not None:
            camera = SimpleNamespace(id=row["camera_id"], uri=row["uri"], codec=row["codec"], decoder=row["decoder"], enabled=row["status"] not in ("disabled", "offline"), live_path=None)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Unknown camera: {camera_id}")
    areas = {area["area_id"]: area for area in store.list_areas()}
    return _camera_payload(
        camera,
        store.ensure_camera(camera_id, camera_id),
        areas,
        _camera_health(engine).get(camera_id),
    )


@router.get("/api/areas")
def get_areas():
    """List camera grouping areas with their camera counts."""
    store = get_state_store()
    counts: dict[str, int] = {}
    for meta in store.list_cameras().values():
        area_id = meta.get("area_id")
        if area_id:
            counts[area_id] = counts.get(area_id, 0) + 1
    return [
        {**area, "camera_count": counts.get(area["area_id"], 0)}
        for area in store.list_areas()
    ]


@router.post("/api/areas", status_code=status.HTTP_201_CREATED)
def create_area(payload: AreaCreateRequest):
    """Create a camera grouping area."""
    try:
        return get_state_store().create_area(payload.name, payload.sort_order)
    except ValueError as exc:
        detail = str(exc)
        code = 409 if "already exists" in detail else 400
        raise HTTPException(status_code=code, detail=detail)


@router.put("/api/areas/{area_id}")
def update_area(area_id: str, payload: AreaUpdateRequest):
    """Rename or reorder an area."""
    try:
        return get_state_store().update_area(
            area_id, name=payload.name, sort_order=payload.sort_order
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown area: {area_id}")
    except ValueError as exc:
        detail = str(exc)
        code = 409 if "already exists" in detail else 400
        raise HTTPException(status_code=code, detail=detail)


@router.delete("/api/areas/{area_id}")
def delete_area(area_id: str):
    """Delete an area; cameras in it become unassigned."""
    if not get_state_store().delete_area(area_id):
        raise HTTPException(status_code=404, detail=f"Unknown area: {area_id}")
    return {"area_id": area_id, "deleted": True}


@router.post("/api/cameras", status_code=status.HTTP_201_CREATED)
def register_camera(payload: CameraRegisterRequest):
    """Persist a camera and attach its stream without blocking the API request."""
    camera_id = (payload.camera_id or payload.name or "").strip()
    rtsp_url = (payload.rtsp_url or payload.uri or "").strip()
    if not camera_id or not rtsp_url:
        raise HTTPException(
            status_code=400,
            detail="Missing camera_id or rtsp_url in request payload.",
        )
    if urlsplit(rtsp_url).scheme not in ("rtsp", "rtsps", "file", "videotestsrc"):
        raise HTTPException(status_code=400, detail="RTSP URL must use rtsp:// or rtsps://")
    try:
        area_id = _resolve_area_id(payload.area_id, create=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        with connect() as conn:
            conn.execute(
                """INSERT INTO cameras
                (camera_id, name, uri, codec, decoder, decoding_fps, status,
                 camera_metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    camera_id, (payload.name or camera_id).strip(), rtsp_url,
                    payload.codec, payload.decoder, payload.decoding_fps,
                    payload.status,
                    json.dumps(payload.camera_metadata) if payload.camera_metadata is not None else None,
                    time.time(), time.time(),
                ),
            )
    except Exception as exc:
        if "UNIQUE" in str(exc).upper():
            raise HTTPException(status_code=409, detail=f"Camera ID '{camera_id}' already exists") from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        _assign_camera_area(camera_id, area_id, payload.name or camera_id)
    except ValueError as exc:
        with connect() as conn:
            conn.execute("DELETE FROM cameras WHERE camera_id = ?", (camera_id,))
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    def attach_stream() -> None:
        try:
            # Metadata creation and stream startup can both contend with event
            # writers; keep them off the HTTP request path.
            _assign_camera_area(camera_id, area_id, payload.name or camera_id)
            engine = get_engine()
            service = getattr(engine, "onboarding_service", None) if engine else None
            if service is None:
                raise RuntimeError("Onboarding service not initialized")
            service.register_camera(
                camera_id=camera_id,
                rtsp_uri=rtsp_url,
                codec=payload.codec,
                decoder=payload.decoder,
                live_path=payload.live_path,
            )
            logger.info("camera_stream_attach_started camera_id=%s", camera_id)
        except Exception as exc:
            with connect() as conn:
                conn.execute(
                    "UPDATE cameras SET status = ?, updated_at = ? WHERE camera_id = ?",
                    ("offline", time.time(), camera_id),
                )
            logger.exception("camera_stream_attach_failed camera_id=%s error=%s", camera_id, exc)

    threading.Thread(target=attach_stream, name=f"camera-attach-{camera_id}", daemon=True).start()
    return {"camera_id": camera_id, "status": "connecting", "message": "Camera saved; connecting to stream."}


@router.post("/api/cameras/import")
async def import_cameras(request: Request):
    """Import camera configurations from a CSV file.

    Required columns: camera_number, camera_name, rtsp_url, codec, decoder,
    decoding_fps, and area. Area may be an existing area ID/name; an unknown
    non-empty area name is created automatically for convenience.
    """
    try:
        raw_content = await request.body()
        if len(raw_content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="CSV file is too large (maximum 10 MB)")
        content = raw_content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded") from exc

    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV has no header row")

    def key(value: str) -> str:
        return "".join(ch for ch in value.strip().casefold() if ch.isalnum())

    aliases = {
        "camera_number": {"cameranumber", "cameraid", "id", "number"},
        "name": {"cameraname", "name", "displayname"},
        "rtsp_url": {"rtspurl", "uri", "url"},
        "codec": {"codec"},
        "decoder": {"decoder"},
        "decoding_fps": {"decodingfps", "fps"},
        "area": {"area", "areaname", "areaid"},
    }
    header_map = {key(header): header for header in reader.fieldnames if header}
    missing = [name for name, names in aliases.items() if not any(item in header_map for item in names)]
    if missing:
        labels = {"camera_number": "Camera Number", "name": "Camera Name", "rtsp_url": "RTSP URL"}
        raise HTTPException(status_code=400, detail="Missing CSV columns: " + ", ".join(labels.get(item, item) for item in missing))

    def value(row: dict[str, str], field: str) -> str:
        for alias in aliases[field]:
            header = header_map.get(alias)
            if header is not None:
                return (row.get(header) or "").strip()
        return ""

    results: list[dict[str, Any]] = []
    for row_number, row in enumerate(reader, start=2):
        camera_id = value(row, "camera_number")
        name = value(row, "name")
        uri = value(row, "rtsp_url")
        try:
            if not camera_id or not name or not uri:
                raise ValueError("Camera Number, Camera Name, and RTSP URL are required")
            raw_fps = value(row, "decoding_fps")
            fps = float(raw_fps) if raw_fps else None
            if fps is not None and fps <= 0:
                raise ValueError("Decoding FPS must be greater than zero")
            area_id = _resolve_area_id(value(row, "area"), create=True)
            payload = CameraRegisterRequest(
                camera_id=camera_id,
                name=name,
                rtsp_url=uri,
                codec=value(row, "codec") or "h264",
                decoder=value(row, "decoder") or "auto",
                decoding_fps=fps,
                area_id=area_id,
            )
            register_camera(payload)
            results.append({"row": row_number, "camera_id": camera_id, "status": "accepted"})
        except HTTPException as exc:
            results.append({"row": row_number, "camera_id": camera_id or None, "status": "failed", "error": str(exc.detail)})
        except Exception as exc:
            results.append({"row": row_number, "camera_id": camera_id or None, "status": "failed", "error": str(exc)})

    imported = sum(item["status"] == "accepted" for item in results)
    return {"imported": imported, "failed": len(results) - imported, "results": results}


@router.delete("/api/cameras/{camera_id}")
def delete_camera(camera_id: str):
    engine = get_engine()
    with connect() as conn:
        row = conn.execute("SELECT camera_id FROM cameras WHERE camera_id = ?", (camera_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown camera: {camera_id}")
    service = getattr(engine, "onboarding_service", None) if engine else None
    if service is not None and hasattr(service, "unregister_camera"):
        service.unregister_camera(camera_id)
    remover = getattr(engine, "unregister_camera", None) if engine else None
    if remover is not None:
        remover(camera_id)
    with connect() as conn:
        conn.execute("DELETE FROM cameras WHERE camera_id = ?", (camera_id,))
    get_state_store().delete_camera(camera_id)
    return {"camera_id": camera_id, "deleted": True}


@router.get("/api/cameras/{camera_id}/onboarding/status")
def get_camera_onboarding_status(camera_id: str):
    """Get onboarding analysis progress and health status for camera."""
    engine = get_engine()
    service = getattr(engine, "onboarding_service", None) if engine else None
    if service is None:
        raise HTTPException(status_code=500, detail="Onboarding service not initialized")
    try:
        return service.get_status(camera_id)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@router.get("/api/cameras/{camera_id}/recommendations")
def get_camera_recommendations(camera_id: str):
    """Get AI-generated capability recommendations based on scene analysis."""
    engine = get_engine()
    service = getattr(engine, "onboarding_service", None) if engine else None
    if service is None:
        raise HTTPException(status_code=500, detail="Onboarding service not initialized")
    try:
        return service.get_recommendations(camera_id)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@router.get("/api/cameras/{camera_id}/capabilities")
def get_camera_active_capabilities(camera_id: str):
    """Get currently active capabilities and configuration for camera."""
    engine = get_engine()
    service = getattr(engine, "onboarding_service", None) if engine else None
    if service is None:
        raise HTTPException(status_code=500, detail="Onboarding service not initialized")
    active = service.capability_manager.get_active_capabilities(camera_id)
    cfg = service.config_store.get(camera_id)
    return {
        "camera_id": camera_id,
        "active_capabilities": active,
        "config_version": cfg.version if cfg else 1,
        "configurations": cfg.configurations if cfg else {},
    }


@router.put("/api/cameras/{camera_id}/capabilities")
def apply_camera_capabilities(
    camera_id: str,
    payload: ApplyCapabilitiesRequest,
    request: Request,
):
    """Apply updated capability selection and configuration to camera."""
    engine = get_engine()
    service = getattr(engine, "onboarding_service", None) if engine else None
    if service is None:
        raise HTTPException(status_code=500, detail="Onboarding service not initialized")

    user_ip = request.client.host if request.client else "127.0.0.1"
    try:
        return service.apply_capabilities(
            camera_id=camera_id,
            selected_capabilities=payload.capabilities,
            expected_config_version=payload.expected_version,
            configurations=payload.configurations,
            user_ip=user_ip,
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except RuntimeError as re_err:
        status_code = 409 if "conflict" in str(re_err).lower() else 500
        raise HTTPException(status_code=status_code, detail=str(re_err))
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@router.post("/api/cameras/{camera_id}/onboarding/analyze", status_code=status.HTTP_202_ACCEPTED)
def start_camera_analysis(camera_id: str, payload: CameraAnalyzeRequest):
    """Trigger background scene analysis for capability recommendation."""
    engine = get_engine()
    service = getattr(engine, "onboarding_service", None) if engine else None
    if service is None:
        raise HTTPException(status_code=500, detail="Onboarding service not initialized")
    try:
        return service.start_analysis(
            camera_id=camera_id,
            sample_count=payload.sample_count,
            sample_duration_seconds=payload.sample_duration_seconds,
            force_fresh=payload.force_fresh,
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@router.post("/api/cameras/{camera_id}/onboarding/reset")
def reset_camera_onboarding(camera_id: str):
    """Reset onboarding state machine for camera."""
    engine = get_engine()
    service = getattr(engine, "onboarding_service", None) if engine else None
    if service is not None:
        with service._lock:
            if camera_id in service._camera_states:
                service._camera_states[camera_id]["status"] = "CONNECTED"
                service._camera_states[camera_id]["error"] = None
                service._camera_states[camera_id]["progress_percent"] = 0
    return {"camera_id": camera_id, "status": "RESET"}

