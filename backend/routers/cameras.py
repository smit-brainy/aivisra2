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

from typing import Any
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
from runtime.onboarding.onboarding_service import sanitize_rtsp_url

router = APIRouter(tags=["Cameras & Onboarding"])


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
    """Collapse engine state/health into the UI's online/degraded/offline wording."""
    if not health:
        return "unknown"
    value = str(health.get("health") or "").upper()
    state = str(health.get("state") or "").upper()
    if value == "HEALTHY":
        return "online"
    if value in ("DEGRADED", "STALE"):
        return "degraded"
    if value == "RECONNECTING":
        return "reconnecting"
    if value == "OFFLINE":
        return "offline"
    # Fall back to the stream state when health has not been computed yet.
    if state == "CONNECTED":
        return "online"
    if state == "DEGRADED":
        return "degraded"
    if state == "RECONNECTING":
        return "reconnecting"
    return "offline"


def _camera_payload(camera: Any, meta: dict[str, Any], areas: dict[str, dict[str, Any]],
                    health: dict[str, Any] | None) -> dict[str, Any]:
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
        "rtsp_url": sanitize_rtsp_url(camera.uri),
        "codec": camera.codec,
        "decoder": camera.decoder,
        "enabled": camera.enabled,
        "live_path": camera.live_path,
        "stream_url": f"/stream/{camera.id}",
        "frame_url": f"/frame/{camera.id}.jpg",
        "status": status_value,
        "health": health.get("health"),
        "state": health.get("state"),
        "online": status_value == "online",
        "fps": health.get("actual_fps"),
        "expected_fps": health.get("expected_fps"),
        "frame_age_ms": health.get("frame_age_ms"),
        "last_frame_time": health.get("last_frame_time"),
        "last_error": health.get("last_error"),
        "reconnect_count": health.get("reconnect_count", 0),
    }


def _configured_cameras(engine: Any) -> list[Any]:
    return list(getattr(engine, "cameras", None) or [])


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
    cameras = _configured_cameras(engine)
    if not cameras:
        return []

    store = get_state_store()
    areas = {area["area_id"]: area for area in store.list_areas()}
    health_by_camera = _camera_health(engine)
    return [
        _camera_payload(
            camera,
            store.ensure_camera(camera.id, camera.id),
            areas,
            health_by_camera.get(camera.id),
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
    """Update operator-editable camera metadata (name, area, kind, level, notes)."""
    engine = get_engine()
    if not any(c.id == camera_id for c in _configured_cameras(engine)):
        raise HTTPException(status_code=404, detail=f"Unknown camera: {camera_id}")

    fields = payload.model_dump(exclude_unset=True)
    store = get_state_store()
    try:
        store.update_camera(camera_id, fields)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    camera = next(c for c in engine.cameras if c.id == camera_id)
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
    """Register and onboard a new camera stream."""
    camera_id = (payload.camera_id or payload.name or "").strip()
    rtsp_url = (payload.rtsp_url or payload.uri or "").strip()
    if not camera_id or not rtsp_url:
        raise HTTPException(
            status_code=400,
            detail="Missing camera_id or rtsp_url in request payload.",
        )

    engine = get_engine()
    service = getattr(engine, "onboarding_service", None) if engine else None
    if service is None:
        raise HTTPException(status_code=500, detail="Onboarding service not initialized")

    try:
        result = service.register_camera(
            camera_id=camera_id,
            rtsp_uri=rtsp_url,
            codec=payload.codec,
            decoder=payload.decoder,
            live_path=payload.live_path,
        )
        get_state_store().ensure_camera(camera_id, payload.name or camera_id)
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except RuntimeError as re_err:
        raise HTTPException(status_code=500, detail=str(re_err))
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


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

