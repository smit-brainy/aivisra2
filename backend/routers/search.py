"""SQLite event queries and snapshot retrieval.

Serves:
- /api/events (GET)
- /api/events/{event_id} (GET)
- /api/snapshots/{filename} (GET)
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Response

from ..dependencies import get_engine

router = APIRouter(tags=["Events & Snapshots"])

_DEFAULT_OUTPUT_DIR = Path("runtime/streamcore/output")


def _parse_to_utc(s: Optional[str]) -> Optional[str]:
    """Convert IST or unspecified ISO timestamp string to UTC string."""
    if not s:
        return None
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    try:
        s = s.strip()
        if s.endswith("Z"):
            dt = datetime.fromisoformat(s[:-1] + "+00:00")
        elif "+" in s or (s.rfind("-") > 10):
            dt = datetime.fromisoformat(s)
        else:
            dt = datetime.fromisoformat(s).replace(tzinfo=ist_tz)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


@router.get("/api/events")
def query_events(
    camera_id: Optional[str] = Query(None),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    obj_class: Optional[str] = Query(None, alias="class"),
    clip_only: bool = Query(False),
    limit: int = Query(50),
    offset: int = Query(0),
):
    """Query stored track events with IST->UTC date filtering."""
    engine = get_engine()
    event_db = getattr(engine, "event_db", None) if engine else None
    if not event_db:
        return {"events": [], "total": 0, "limit": limit, "offset": offset}

    start_utc = _parse_to_utc(start)
    end_utc = _parse_to_utc(end)

    events = event_db.query_events(
        camera_id=camera_id,
        start_utc=start_utc,
        end_utc=end_utc,
        object_class=obj_class,
        clip_only=clip_only,
        limit=limit,
        offset=offset,
    )
    return {
        "events": [e.to_dict() for e in events],
        "total": len(events),
        "limit": limit,
        "offset": offset,
    }


@router.get("/api/events/{event_id}")
def get_event_by_id(event_id: str):
    """Retrieve single track event by ID."""
    engine = get_engine()
    event_db = getattr(engine, "event_db", None) if engine else None
    if not event_db:
        raise HTTPException(status_code=404, detail="Event database not available")
    event = event_db.get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event.to_dict()


@router.get("/api/snapshots/{filename:path}")
def get_snapshot(filename: str):
    """Serve an event crop snapshot JPEG image."""
    engine = get_engine()
    event_cfg = getattr(getattr(engine, "config", None), "events", None)
    clip_dir = getattr(event_cfg, "clip_storage_dir", None)
    base_dir = (
        Path(clip_dir).parent if clip_dir else _DEFAULT_OUTPUT_DIR
    ).resolve()
    snap_dir = (base_dir / "snapshots").resolve()

    clean_name = filename.strip("/")
    if clean_name.startswith("snapshots/"):
        clean_name = clean_name[len("snapshots/"):]

    file_path = snap_dir / clean_name
    if not file_path.is_file():
        file_path = snap_dir.parent / clean_name
    if not file_path.is_file():
        file_path = snap_dir / Path(clean_name).name
    if not file_path.is_file() and Path(clean_name).name:
        matches = list(snap_dir.glob(f"**/{Path(clean_name).name}"))
        if matches:
            file_path = matches[0]

    try:
        if file_path.is_file() and (
            base_dir in file_path.resolve().parents
            or file_path.resolve().is_relative_to(base_dir)
        ):
            return Response(content=file_path.read_bytes(), media_type="image/jpeg")
    except Exception:
        pass

    raise HTTPException(status_code=404, detail="Snapshot image not found")
