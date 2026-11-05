"""Telemetry, Detections, Tracks and Batch frame endpoints.

Serves:
- /api/status
- /api/tracks and /api/tracks/{camera_id}
- /api/detections and /api/detections/{camera_id}
- /api/frames/batch
"""

import base64
import json
import os
import platform
import shutil
import subprocess
from datetime import datetime
from typing import Any, Optional
from fastapi import APIRouter, Query, Response

from ..dependencies import get_engine, get_cache, get_camera_ids
from ..database import connect

router = APIRouter(tags=["Telemetry & Detections"])


@router.get("/api/system-info")
def get_system_info():
    """Return host information used by the Settings > About screen."""
    engine = get_engine()
    root = shutil.disk_usage(os.path.abspath(os.sep))
    ram_total = ram_available = None
    try:
        values = {}
        with open("/proc/meminfo", encoding="utf-8") as meminfo:
            for line in meminfo:
                key, value = line.split(":", 1)
                values[key] = int(value.strip().split()[0]) * 1024
        ram_total = values.get("MemTotal")
        ram_available = values.get("MemAvailable")
    except (OSError, ValueError):
        pass
    gpu = "Unavailable"
    try:
        result = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], capture_output=True, text=True, timeout=2)
        if result.returncode == 0 and result.stdout.strip():
            gpu = result.stdout.strip().splitlines()[0]
    except (OSError, subprocess.SubprocessError):
        pass
    return {
        "os": f"{platform.system()} {platform.release()}",
        "ram": {"total_bytes": ram_total, "available_bytes": ram_available},
        "cpu": platform.processor() or platform.machine() or "Unavailable",
        "gpu": gpu,
        "storage": {"total_bytes": root.total, "free_bytes": root.free, "used_bytes": root.used},
        "time_zone": datetime.now().astimezone().tzname() or "Local time",
        "current_time": datetime.now().astimezone().isoformat(),
        "camera_count": len(getattr(engine, "cameras", []) or []) if engine else 0,
        "software_version": "2.0.0",
    }


def _storage_payload(engine):
    usage = shutil.disk_usage(os.path.abspath(os.sep))
    retention = 1
    with connect() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = 'retention_days'").fetchone()
        if row:
            retention = int(row["value"])
        events = conn.execute("SELECT COUNT(*) AS c FROM inference_events").fetchone()["c"]
    return {"retention_days": retention, "total_bytes": usage.total, "used_bytes": usage.used, "free_bytes": usage.free, "event_count": events}


@router.get("/api/storage")
def get_storage_info():
    return _storage_payload(get_engine())


@router.put("/api/storage")
def update_storage(payload: dict[str, Any]):
    days = int(payload.get("retention_days", 1))
    if days < 1 or days > 3650:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="retention_days must be between 1 and 3650")
    engine = get_engine()
    if engine is not None and getattr(engine, "event_db", None) is not None:
        event_db = engine.event_db
        object.__setattr__(event_db.config, "retention_days", days)
        if getattr(engine, "clip_recorder", None) is not None:
            object.__setattr__(engine.clip_recorder.config, "retention_days", days)
        event_db.cleanup_old_events(days)
        if getattr(engine, "clip_recorder", None) is not None:
            engine.clip_recorder.cleanup_old_clips(days)
    with connect() as conn:
        conn.execute("INSERT INTO app_settings(key, value, updated_at) VALUES('retention_days', ?, strftime('%s','now')) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at", (str(days),))
    return _storage_payload(engine)


@router.get("/api/status")
def get_system_status():
    """Retrieve full system metrics, GPU resources, and active detections."""
    engine = get_engine()
    if engine is None:
        return {"status": "offline", "cameras": {}, "resources": {}}

    status = engine.metrics.view()
    status["mode"] = getattr(getattr(engine, "config", None), "runtime", None) and engine.config.runtime.mode or "production"
    status["resources"] = engine.latest_resources() if hasattr(engine, "latest_resources") else {}
    status["tracking"] = engine.tracking_metrics() if hasattr(engine, "tracking_metrics") else {}
    latest_res = engine.latest_results() if hasattr(engine, "latest_results") else {}

    status["detections"] = {
        cam_id: [
            {
                "class": d.label,
                "confidence": round(d.confidence, 2),
                "track_id": getattr(d, "track_id", None),
                "bbox": [
                    round(d.x1 * (getattr(res, "source_width", 0) or 1280), 1),
                    round(d.y1 * (getattr(res, "source_height", 0) or 720), 1),
                    round(d.x2 * (getattr(res, "source_width", 0) or 1280), 1),
                    round(d.y2 * (getattr(res, "source_height", 0) or 720), 1),
                ],
            }
            for d in res.detections
        ]
        for cam_id, res in latest_res.items()
    }
    return status


@router.get("/api/object-counts")
def get_object_counts(date: str | None = None):
    engine = get_engine()
    event_db = getattr(engine, "event_db", None) if engine else None
    if event_db is None:
        return {"date": date, "classes": [], "totals": {}, "cameras": [], "updated_at": None}
    return event_db.query_object_counts(date)


@router.get("/api/tracks/{camera_id}")
def get_camera_tracks(camera_id: str):
    """Retrieve active object tracks and trajectories for a specific camera."""
    engine = get_engine()
    tracks = engine.latest_tracks(camera_id) if (engine and hasattr(engine, "latest_tracks")) else []
    return {
        "camera_id": camera_id,
        "tracks": [
            {
                "track_id": t.global_track_id,
                "class_name": t.class_name,
                "state": str(t.state),
                "bbox_xyxy": [round(v, 1) for v in t.bbox_xyxy],
                "confidence": round(t.confidence, 2),
                "duration_ms": round(t.duration_ms, 1),
                "direction": str(t.direction),
                "best_crop_score": round(t.best_crop_score, 2),
                "trajectory": [[round(p[0], 1), round(p[1], 1)] for p in list(t.trajectory)[-20:]],
            }
            for t in tracks
        ],
    }


@router.get("/api/tracks")
def get_all_tracks():
    """Retrieve active object tracks across all cameras."""
    engine = get_engine()
    c_ids = get_camera_ids()
    all_tracks: dict[str, Any] = {}
    for cid in c_ids:
        tracks = engine.latest_tracks(cid) if (engine and hasattr(engine, "latest_tracks")) else []
        all_tracks[cid] = [
            {
                "track_id": t.global_track_id,
                "class_name": t.class_name,
                "state": str(t.state),
                "bbox_xyxy": [round(v, 1) for v in t.bbox_xyxy],
                "confidence": round(t.confidence, 2),
                "duration_ms": round(t.duration_ms, 1),
                "direction": str(t.direction),
                "best_crop_score": round(t.best_crop_score, 2),
                "trajectory": [[round(p[0], 1), round(p[1], 1)] for p in list(t.trajectory)[-20:]],
            }
            for t in tracks
        ]
    return all_tracks


@router.get("/api/detections/{camera_id}")
def get_camera_detections(camera_id: str):
    """Retrieve latest inference frame detections with bounding boxes and tracks."""
    engine = get_engine()
    cache = get_cache()
    if cache is not None and hasattr(cache, "touch"):
        cache.touch(camera_id, 3.0)

    latest_res = engine.latest_results() if (engine and hasattr(engine, "latest_results")) else {}
    res = latest_res.get(camera_id)
    status = engine.metrics.view() if (engine and hasattr(engine, "metrics")) else {}
    cam_m = status.get("cameras", {}).get(camera_id, {})
    w = getattr(res, "source_width", 0) or 1280
    h = getattr(res, "source_height", 0) or 720
    tracks_map = (
        {t.global_track_id: t for t in engine.latest_tracks(camera_id)}
        if (engine and hasattr(engine, "latest_tracks"))
        else {}
    )

    if res is None:
        return {
            "camera_id": camera_id,
            "sequence": 0,
            "timestamp": 0.0,
            "inference_ms": 0.0,
            "total_latency_ms": 0.0,
            "frame_path": cam_m.get("frame_path", "GPU_NATIVE"),
            "cpu_frame_downloads": cam_m.get("cpu_frame_downloads", 0),
            "width": w,
            "height": h,
            "detections": [],
        }

    dets_list = []
    for d in res.detections:
        tid = getattr(d, "track_id", None)
        trk = tracks_map.get(tid)
        traj = [[round(p[0], 1), round(p[1], 1)] for p in list(trk.trajectory)[-20:]] if trk else []
        dets_list.append({
            "label": d.label,
            "class_id": d.class_id,
            "confidence": round(d.confidence, 3),
            "track_id": tid,
            "direction": str(trk.direction) if trk else "STATIONARY",
            "trajectory": traj,
            "bbox": [
                round(d.x1 * w, 1),
                round(d.y1 * h, 1),
                round(d.x2 * w, 1),
                round(d.y2 * h, 1),
            ],
            "bbox_normalized": [
                round(d.x1, 4),
                round(d.y1, 4),
                round(d.x2, 4),
                round(d.y2, 4),
            ],
        })

    return {
        "camera_id": camera_id,
        "sequence": res.frame_sequence,
        "timestamp": res.timestamp,
        "inference_ms": round(res.inference_ms, 2),
        "total_latency_ms": round(res.total_latency_ms, 2),
        "frame_path": cam_m.get("frame_path", "GPU_NATIVE"),
        "cpu_frame_downloads": cam_m.get("cpu_frame_downloads", 0),
        "width": w,
        "height": h,
        "detections": dets_list,
    }


@router.get("/api/detections")
def get_all_detections():
    """Retrieve latest inference detections across all configured cameras."""
    engine = get_engine()
    c_ids = get_camera_ids()
    latest_res = engine.latest_results() if (engine and hasattr(engine, "latest_results")) else {}
    status = engine.metrics.view() if (engine and hasattr(engine, "metrics")) else {}
    all_dets: dict[str, Any] = {}

    for cam_id in c_ids:
        res = latest_res.get(cam_id)
        cam_m = status.get("cameras", {}).get(cam_id, {})
        w = getattr(res, "source_width", 0) or 1280
        h = getattr(res, "source_height", 0) or 720
        tracks_map = (
            {t.global_track_id: t for t in engine.latest_tracks(cam_id)}
            if (engine and hasattr(engine, "latest_tracks"))
            else {}
        )

        if res is None:
            all_dets[cam_id] = {
                "camera_id": cam_id,
                "sequence": 0,
                "inference_ms": 0.0,
                "frame_path": cam_m.get("frame_path", "GPU_NATIVE"),
                "detections": [],
            }
        else:
            dets_list = []
            for d in res.detections:
                tid = getattr(d, "track_id", None)
                trk = tracks_map.get(tid)
                traj = [[round(p[0], 1), round(p[1], 1)] for p in list(trk.trajectory)[-20:]] if trk else []
                dets_list.append({
                    "label": d.label,
                    "class_id": d.class_id,
                    "confidence": round(d.confidence, 3),
                    "track_id": tid,
                    "direction": str(trk.direction) if trk else "STATIONARY",
                    "trajectory": traj,
                    "bbox": [
                        round(d.x1 * w, 1),
                        round(d.y1 * h, 1),
                        round(d.x2 * w, 1),
                        round(d.y2 * h, 1),
                    ],
                })
            all_dets[cam_id] = {
                "camera_id": cam_id,
                "sequence": res.frame_sequence,
                "timestamp": res.timestamp,
                "inference_ms": round(res.inference_ms, 2),
                "total_latency_ms": round(res.total_latency_ms, 2),
                "frame_path": cam_m.get("frame_path", "GPU_NATIVE"),
                "cpu_frame_downloads": cam_m.get("cpu_frame_downloads", 0),
                "detections": dets_list,
            }
    return all_dets


@router.get("/api/frames/batch")
def get_frames_batch(since: Optional[str] = Query(None)):
    """Batch poll newest JPEG frames across all cameras."""
    cache = get_cache()
    c_ids = get_camera_ids()
    if cache is not None and hasattr(cache, "touch"):
        for cid in c_ids:
            cache.touch(cid, 2.0)

    since_seqs = {}
    if since:
        try:
            since_seqs = json.loads(since)
        except Exception:
            pass

    all_cached = cache.all_latest() if cache is not None else {}
    payload = {}
    for cam_id in c_ids:
        prev = all_cached.get(cam_id)
        if prev is None:
            payload[cam_id] = {"seq": 0, "has_frame": False}
            continue
        last_seen = since_seqs.get(cam_id, -1)
        if prev.sequence > last_seen:
            payload[cam_id] = {
                "seq": prev.sequence,
                "has_frame": True,
                "jpeg": base64.b64encode(prev.jpeg).decode("ascii"),
            }
        else:
            payload[cam_id] = {
                "seq": prev.sequence,
                "has_frame": True,
            }
    return payload

