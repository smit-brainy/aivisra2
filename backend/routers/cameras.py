"""Camera management and onboarding endpoints.

Serves:
- /api/cameras (GET, POST)
- /api/capabilities (GET)
- /api/cameras/{camera_id}/onboarding/status (GET)
- /api/cameras/{camera_id}/recommendations (GET)
- /api/cameras/{camera_id}/capabilities (GET, PUT)
- /api/cameras/{camera_id}/onboarding/analyze (POST)
- /api/cameras/{camera_id}/onboarding/reset (POST)
"""

from typing import Any
from fastapi import APIRouter, HTTPException, Request, Response, status

from ..dependencies import get_engine, get_camera_ids
from ..schemas.models import CameraRegisterRequest, CameraAnalyzeRequest, ApplyCapabilitiesRequest
from runtime.onboarding.onboarding_service import sanitize_rtsp_url

router = APIRouter(tags=["Cameras & Onboarding"])


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
    """List all currently configured camera streams with sanitized RTSP URLs."""
    engine = get_engine()
    if engine is None or not getattr(engine, "cameras", None):
        return []
    cams = []
    for c in engine.cameras:
        sanitized = sanitize_rtsp_url(c.uri)
        cams.append({
            "camera_id": c.id,
            "name": c.id,
            "rtsp_url": sanitized,
            "codec": c.codec,
            "decoder": c.decoder,
        })
    return cams


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
        return service.register_camera(
            camera_id=camera_id,
            rtsp_uri=rtsp_url,
            codec=payload.codec,
            decoder=payload.decoder,
            live_path=payload.live_path,
        )
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

