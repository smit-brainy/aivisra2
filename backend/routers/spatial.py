"""Spatial intelligence, zones, lines, rules, and occupancy endpoints.

Serves:
- /api/cameras/{camera_id}/zones (GET, PUT)
- /api/cameras/{camera_id}/lines (GET, PUT)
- /api/cameras/{camera_id}/rules (GET, PUT)
- /api/cameras/{camera_id}/occupancy (GET)
- /api/cameras/{camera_id}/events/active (GET)
- /api/cameras/{camera_id}/events (GET)
- /api/intelligence/metrics (GET)
- /api/evidence/{filename} (GET)
"""

from pathlib import Path
from typing import Any
from fastapi import APIRouter, HTTPException, Response

from ..dependencies import get_engine
from ..schemas.models import UpdateZonesRequest, UpdateLinesRequest, UpdateRulesRequest

router = APIRouter(tags=["Spatial Intelligence"])


@router.get("/api/cameras/{camera_id}/zones")
def get_camera_zones(camera_id: str):
    """Retrieve spatial detection polygon zones for a camera."""
    engine = get_engine()
    sp = getattr(engine, "spatial_manager", None) if engine else None
    if sp:
        zones = sp.zone_mgr.get_zones(camera_id)
        return {
            "camera_id": camera_id,
            "version": sp.get_config_version(camera_id),
            "zones": [z.to_dict() for z in zones],
        }
    return {"camera_id": camera_id, "version": 1, "zones": []}


@router.put("/api/cameras/{camera_id}/zones")
def update_camera_zones(camera_id: str, payload: UpdateZonesRequest):
    """Update spatial polygon zones for a camera."""
    engine = get_engine()
    sp = getattr(engine, "spatial_manager", None) if engine else None
    if sp is None:
        raise HTTPException(status_code=500, detail="Spatial manager not initialized")

    ok, msg, ver = sp.update_zones(camera_id, payload.zones, payload.expected_version)
    if ok:
        return {"status": "OK", "message": msg, "version": ver}
    status_code = 409 if "conflict" in msg.lower() else 400
    raise HTTPException(status_code=status_code, detail={"error": msg, "version": ver})


@router.get("/api/cameras/{camera_id}/lines")
def get_camera_lines(camera_id: str):
    """Retrieve spatial tripwire crossing lines for a camera."""
    engine = get_engine()
    sp = getattr(engine, "spatial_manager", None) if engine else None
    if sp:
        lines = sp.line_mgr.get_lines(camera_id)
        return {
            "camera_id": camera_id,
            "version": sp.get_config_version(camera_id),
            "lines": [l.to_dict() for l in lines],
        }
    return {"camera_id": camera_id, "version": 1, "lines": []}


@router.put("/api/cameras/{camera_id}/lines")
def update_camera_lines(camera_id: str, payload: UpdateLinesRequest):
    """Update spatial tripwire crossing lines for a camera."""
    engine = get_engine()
    sp = getattr(engine, "spatial_manager", None) if engine else None
    if sp is None:
        raise HTTPException(status_code=500, detail="Spatial manager not initialized")

    ok, msg, ver = sp.update_lines(camera_id, payload.lines, payload.expected_version)
    if ok:
        return {"status": "OK", "message": msg, "version": ver}
    status_code = 409 if "conflict" in msg.lower() else 400
    raise HTTPException(status_code=status_code, detail={"error": msg, "version": ver})


@router.get("/api/cameras/{camera_id}/rules")
def get_camera_rules(camera_id: str):
    """Retrieve spatial alert rules for a camera."""
    engine = get_engine()
    sp = getattr(engine, "spatial_manager", None) if engine else None
    if sp:
        rules = sp.rule_engine.get_rules(camera_id)
        return {
            "camera_id": camera_id,
            "version": sp.get_config_version(camera_id),
            "rules": [r.to_dict() for r in rules],
        }
    return {"camera_id": camera_id, "version": 1, "rules": []}


@router.put("/api/cameras/{camera_id}/rules")
def update_camera_rules(camera_id: str, payload: UpdateRulesRequest):
    """Update spatial alert rules for a camera."""
    engine = get_engine()
    sp = getattr(engine, "spatial_manager", None) if engine else None
    if sp is None:
        raise HTTPException(status_code=500, detail="Spatial manager not initialized")

    ok, msg, ver = sp.update_rules(camera_id, payload.rules, payload.expected_version)
    if ok:
        return {"status": "OK", "message": msg, "version": ver}
    status_code = 409 if "conflict" in msg.lower() else 400
    raise HTTPException(status_code=status_code, detail={"error": msg, "version": ver})


@router.get("/api/cameras/{camera_id}/occupancy")
def get_camera_occupancy(camera_id: str):
    """Retrieve real-time occupancy and line passage counts."""
    engine = get_engine()
    sp = getattr(engine, "spatial_manager", None) if engine else None
    if sp:
        occ = sp.occupancy_mgr.get_flow_occupancy(camera_id)
        counts = sp.line_mgr.get_all_counts(camera_id)
        return {
            "camera_id": camera_id,
            "visible_occupancy": occ.visible_occupancy,
            "flow_occupancy": occ.flow_occupancy,
            "baseline": occ.baseline,
            "total_in": occ.total_in,
            "total_out": occ.total_out,
            "is_uncertain": occ.is_uncertain,
            "line_counts": counts,
            "last_reconciled_utc": occ.last_reconciled_utc,
        }
    return {"camera_id": camera_id, "visible_occupancy": 0, "flow_occupancy": 0}


@router.get("/api/cameras/{camera_id}/events/active")
def get_camera_active_events(camera_id: str):
    """Retrieve currently active unclosed spatial events."""
    engine = get_engine()
    sp = getattr(engine, "spatial_manager", None) if engine else None
    if sp:
        evts = sp.store.get_active_events(camera_id)
        return {"camera_id": camera_id, "events": [e.to_dict() for e in evts]}
    return {"camera_id": camera_id, "events": []}


@router.get("/api/cameras/{camera_id}/events")
def get_camera_recent_spatial_events(camera_id: str):
    """Retrieve recent spatial events for a camera."""
    engine = get_engine()
    sp = getattr(engine, "spatial_manager", None) if engine else None
    if sp:
        evts = sp.store.get_recent_events(camera_id, limit=50)
        return {"camera_id": camera_id, "events": [e.to_dict() for e in evts]}
    return {"camera_id": camera_id, "events": []}


@router.get("/api/intelligence/metrics")
def get_intelligence_metrics():
    """Retrieve spatial intelligence telemetry snapshot."""
    engine = get_engine()
    sp = getattr(engine, "spatial_manager", None) if engine else None
    if sp:
        return sp.get_telemetry_snapshot()
    return {}


@router.get("/api/evidence/{filename}")
def get_evidence_image(filename: str):
    """Serve spatial rule breach evidence JPEG image."""
    engine = get_engine()
    sp = getattr(engine, "spatial_manager", None) if engine else None
    evidence_dir = (
        Path(sp.config.evidence_storage_dir) if sp else Path("runtime/streamcore/output/evidence")
    )
    file_path = evidence_dir / filename.strip("/")
    if file_path.is_file():
        return Response(content=file_path.read_bytes(), media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Evidence image not found")

