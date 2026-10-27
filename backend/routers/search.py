"""Visual search, SQLite event queries, FAISS re-indexing, and snapshot retrieval.

Serves:
- /api/search-visual (GET, POST)
- /api/events (GET)
- /api/events/{event_id} (GET)
- /api/events/reindex (GET, POST)
- /api/status/search and /api/settings/gemini (GET)
- /api/snapshots/{filename} (GET)
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Response

from ..dependencies import get_engine
from ..schemas.models import VisualSearchRequest
from runtime.streamcore.events.visual_search_manager import VisualSearchManager

router = APIRouter(tags=["Visual Search & Events"])


def _get_or_create_vsm(engine):
    vsm = getattr(engine, "visual_search_manager", None)
    if vsm is None:
        ev_cfg = getattr(getattr(engine, "config", None), "events", None)
        vsm = VisualSearchManager(
            event_db=getattr(engine, "event_db", None),
            settings=ev_cfg,
        )
        engine.visual_search_manager = vsm
    return vsm


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


@router.get("/api/search-visual")
def search_visual_get(
    query: str = Query(""),
    camera_id: Optional[str] = Query(None),
    start: Optional[str] = Query(None),
    start_utc: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    end_utc: Optional[str] = Query(None),
    top_k: int = Query(2),
):
    """Execute natural language visual search using local VLM embeddings (GET)."""
    engine = get_engine()
    vsm = _get_or_create_vsm(engine)
    effective_start = start or start_utc
    effective_end = end or end_utc
    results = vsm.search(
        query=query,
        top_k=top_k,
        camera_id=camera_id,
        start_utc=effective_start,
        end_utc=effective_end,
    )
    return {
        "query": query,
        "count": len(results),
        "has_api_key": vsm.has_api_key,
        "results": results,
    }


@router.post("/api/search-visual")
def search_visual_post(payload: VisualSearchRequest):
    """Execute natural language visual search using local VLM embeddings (POST)."""
    engine = get_engine()
    vsm = _get_or_create_vsm(engine)
    effective_start = payload.start or payload.start_utc
    effective_end = payload.end or payload.end_utc
    results = vsm.search(
        query=payload.query,
        top_k=payload.top_k,
        camera_id=payload.camera_id,
        start_utc=effective_start,
        end_utc=effective_end,
    )
    return {
        "query": payload.query,
        "count": len(results),
        "has_api_key": vsm.has_api_key,
        "results": results,
    }


@router.get("/api/status/search")
@router.get("/api/settings/gemini")
def get_search_status():
    """Retrieve local VLM and embedding engine diagnostics."""
    engine = get_engine()
    vsm = getattr(engine, "visual_search_manager", None) if engine else None
    has_vlm = False
    vlm_model = ""
    embed_model = ""
    ollama_url = ""

    if vsm and vsm.local_models:
        has_vlm = bool(vsm.local_models.has_vlm and vsm.local_models.has_embedder)
        vlm_model = vsm.local_models.config.vlm_model
        embed_model = vsm.local_models.config.embed_model
        ollama_url = vsm.local_models.config.ollama_url
    elif vsm:
        has_vlm = vsm.has_api_key

    return {
        "has_api_key": has_vlm,
        "backend": "local",
        "vlm_model": vlm_model,
        "embed_model": embed_model,
        "ollama_url": ollama_url,
        "total_vectors": vsm.vector_store.total_items if vsm else 0,
    }


@router.get("/api/events/reindex")
@router.post("/api/events/reindex")
def reindex_events():
    """Trigger synchronous FAISS vector re-indexing of stored events."""
    engine = get_engine()
    vsm = _get_or_create_vsm(engine)
    count = vsm.index_existing_clips_sync(max_items=500)
    return {
        "status": "OK",
        "indexed_count": count,
        "total_vectors": vsm.vector_store.total_items,
    }


@router.get("/api/snapshots/{filename:path}")
def get_snapshot(filename: str):
    """Serve crop snapshot JPEG image."""
    engine = get_engine()
    vsm = getattr(engine, "visual_search_manager", None) if engine else None
    base_dir = (vsm.base_dir if vsm else Path("runtime/streamcore/output")).resolve()
    snap_dir = (vsm.snapshots_dir if vsm else (base_dir / "snapshots")).resolve()

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

