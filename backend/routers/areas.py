"""Area management endpoints for camera grouping."""

from fastapi import APIRouter, HTTPException, status

from ..schemas.models import AreaCreateRequest, AreaUpdateRequest
from ..state_store import get_state_store

router = APIRouter(tags=["Areas"])


def _areas_with_counts():
    store = get_state_store()
    counts = {}
    for camera in store.list_cameras().values():
        if camera.get("area_id"):
            counts[camera["area_id"]] = counts.get(camera["area_id"], 0) + 1
    return [{**area, "camera_count": counts.get(area["area_id"], 0)} for area in store.list_areas()]


@router.get("/api/areas")
def list_areas():
    return _areas_with_counts()


@router.post("/api/areas", status_code=status.HTTP_201_CREATED)
def create_area(payload: AreaCreateRequest):
    try:
        return get_state_store().create_area(payload.name, payload.sort_order)
    except ValueError as exc:
        raise HTTPException(status_code=409 if "already exists" in str(exc) else 400, detail=str(exc)) from exc


@router.put("/api/areas/{area_id}")
def update_area(area_id: str, payload: AreaUpdateRequest):
    try:
        return get_state_store().update_area(area_id, name=payload.name, sort_order=payload.sort_order)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown area: {area_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409 if "already exists" in str(exc) else 400, detail=str(exc)) from exc


@router.delete("/api/areas/{area_id}")
def delete_area(area_id: str):
    store = get_state_store()
    areas = store.list_areas()
    target = next((area for area in areas if area["area_id"] == area_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"Unknown area: {area_id}")
    alternatives = [area for area in areas if area["area_id"] != area_id]
    if alternatives:
        destination = alternatives[0]
    else:
        existing_unzoned = next((area for area in areas if area["name"].casefold() == "unzoned" and area["area_id"] != area_id), None)
        destination = existing_unzoned or store.create_area("Unzoned")
    for camera_id, camera in store.list_cameras().items():
        if camera.get("area_id") == area_id:
            store.update_camera(camera_id, {"area_id": destination["area_id"]})
    store.delete_area(area_id)
    return {"area_id": area_id, "deleted": True, "transferred_to": destination["area_id"]}
