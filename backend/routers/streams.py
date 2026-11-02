"""Video streaming endpoints.

Serves:
- Single JPEG diagnostics: /frame/{camera_id}.jpg
- MJPEG multipart stream: /stream/{camera_id}
- MP4 video clip playback with HTTP 206 Partial Content Range streaming: /api/clips/{clip_path}
- WebRTC proxy metadata: /api/webrtc/{camera_id}
"""

import time
import asyncio
import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from ..dependencies import get_engine, get_cache, get_camera_ids

router = APIRouter(tags=["Streams"])
logger = logging.getLogger("streamcore.backend.streams")
_active_mjpeg_streams = 0


def _encode_raw_frame(raw_frame):
    """Encode one raw frame without running this work on the async loop."""
    import cv2
    image = raw_frame.to_bgr_cpu() if hasattr(raw_frame, "to_bgr_cpu") else raw_frame.image
    encoded, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return buffer.tobytes() if encoded else None

# Minimal valid 1x1 black JPEG for empty frame placeholder
TINY_JPEG = (
    b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\x02\x01\x01\x01\x01\x01\x02\x01\x01\x01\x02\x02\x02\x02\x02\x04\x03\x02\x02\x02\x02\x05\x04\x04\x03\x04\x06\x05\x06\x06\x06\x05\x06\x06\x06\x07\t\x08\x06\x07\t\x07\x06\x06\x08\x0b\x08\t\n\n\n\n\n\x06\x08\x0b\x0c\x0b\n\x0c\t\n\n\n\xff\xdb\x00C\x01\x02\x02\x02\x02\x02\x02\x05\x03\x03\x05\n\x07\x06\x07\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x03\x01"\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a%&\'()*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xc4\x00\x1f\x01\x00\x03\x01\x01\x01\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x11\x00\x02\x01\x02\x04\x04\x03\x04\x07\x05\x04\x04\x00\x01\x02w\x00\x01\x02\x03\x11\x04\x05!1\x06\x12AQ\x07aq\x13"2\x81\x08\x14B\x91\xa1\xb1\xc1\t#3R\xf0\x15br\xd1\n\x16$4\xe1%\xf1\x17\x18\x19\x1a&\'()*56789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x82\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00?\x00\xfe\x7f\xe8\xa2\x8a\x00\xff\xd9'
)


@router.get("/frame/{camera_id}.jpg")
def get_camera_frame(camera_id: str):
    """Serve single latest JPEG frame for camera."""
    c_ids = get_camera_ids()
    if camera_id not in c_ids:
        raise HTTPException(status_code=404, detail="Unknown camera")

    cache = get_cache()
    if cache is not None and hasattr(cache, "touch"):
        cache.touch(camera_id, 3.0)

    preview = cache.latest(camera_id) if cache is not None else None
    if preview is None:
        logger.warning("preview_unavailable camera_id=%s", camera_id)
        return Response(
            content=TINY_JPEG,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "X-Frame-Sequence": "0",
            },
        )

    return Response(
        content=preview.jpeg,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Frame-Sequence": str(preview.sequence),
        },
    )


@router.get("/stream/{camera_id}")
async def stream_mjpeg(camera_id: str, inference: bool = True):
    """Multipart MJPEG video stream with optional inference overlays."""
    if camera_id.endswith(".mjpg"):
        camera_id = camera_id[:-len(".mjpg")]

    c_ids = get_camera_ids()
    if camera_id not in c_ids:
        raise HTTPException(status_code=404, detail="Unknown camera")

    cache = get_cache()
    engine = get_engine()
    global _active_mjpeg_streams
    _active_mjpeg_streams += 1
    logger.info("stream_opened camera_id=%s inference=%s active_mjpeg_streams=%d", camera_id, inference, _active_mjpeg_streams)

    async def frame_generator():
        last_seq = -1
        last_touch = time.monotonic()
        while True:
            if engine is not None and getattr(engine, "stop_event", None) and engine.stop_event.is_set():
                break

            now_m = time.monotonic()
            if now_m - last_touch > 1.0:
                if cache is not None and hasattr(cache, "touch"):
                    cache.touch(camera_id, 10.0)
                last_touch = now_m

            if inference:
                preview = cache.latest(camera_id) if cache is not None else None
                jpeg = preview.jpeg if preview is not None else None
                sequence = preview.sequence if preview is not None else -1
            else:
                store = getattr(engine, "store", None)
                raw_frame = store.latest(camera_id, last_seq) if store is not None else None
                jpeg = None
                sequence = getattr(raw_frame, "sequence", -1)
                if raw_frame is not None:
                    try:
                        jpeg = await asyncio.to_thread(_encode_raw_frame, raw_frame)
                    except Exception as exc:
                        logger.warning("raw_preview_encode_failed camera_id=%s reason=%s", camera_id, type(exc).__name__)
            if jpeg is not None and sequence != last_seq:
                last_seq = sequence
                header = (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n"
                )
                yield header + jpeg + b"\r\n"
            await asyncio.sleep(0.015)

    async def logged_generator():
        global _active_mjpeg_streams
        try:
            async for chunk in frame_generator():
                yield chunk
        except asyncio.CancelledError:
            logger.info("stream_client_disconnected camera_id=%s", camera_id)
            raise
        finally:
            _active_mjpeg_streams = max(0, _active_mjpeg_streams - 1)
            logger.info("stream_closed camera_id=%s inference=%s", camera_id, inference)
            logger.info("stream_state active_mjpeg_streams=%d", _active_mjpeg_streams)

    return StreamingResponse(
        logged_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Connection": "close",
        },
    )


@router.get("/api/webrtc/{camera_id}")
def get_webrtc_stream(camera_id: str):
    """Proxy live WebRTC session to MediaMTX."""
    engine = get_engine()
    if engine is not None and getattr(engine, "live_service", None) is not None:
        try:
            stream = engine.live_service.get(camera_id)
            return {
                "camera_id": stream.camera_id,
                "protocol": stream.protocol,
                "live_url": stream.live_url,
                "status": stream.status,
                "viewers": stream.active_live_viewers,
            }
        except Exception:
            pass
    raise HTTPException(status_code=404, detail="not found")


@router.get("/api/event-clips/{event_id}")
def get_event_clip(event_id: str, range: Optional[str] = Header(None)):
    """Resolve an event's clip path from the central database, then stream it."""
    engine = get_engine()
    event_db = getattr(engine, "event_db", None) if engine else None
    event = event_db.get_event(event_id) if event_db else None
    if event is None or not event.clip_path:
        raise HTTPException(status_code=404, detail="Clip is not available for this event")
    logger.info("event_clip_requested event_id=%s clip_path=%s", event_id, event.clip_path)
    return get_clip_video(event.clip_path, range)


@router.get("/api/clips/{clip_path:path}")
def get_clip_video(clip_path: str, range: Optional[str] = Header(None)):
    """Serve MP4 video clips with Range request support for seeking and scrubbing."""
    clip_clean = clip_path.strip("/")
    if clip_clean.startswith("clips/"):
        clip_clean = clip_clean[len("clips/"):]

    engine = get_engine()
    event_db = getattr(engine, "event_db", None) if engine else None
    if event_db and getattr(event_db, "config", None):
        clips_dir = Path(event_db.config.clip_storage_dir).resolve()
    else:
        clips_dir = Path("runtime/streamcore/output/clips").resolve()
    base_dir = clips_dir.parent

    file_path = clips_dir / clip_clean
    if not file_path.is_file():
        file_path = base_dir / clip_clean
    if not file_path.is_file():
        file_path = clips_dir / Path(clip_clean).name
    if not file_path.is_file() and Path(clip_clean).name:
        matches = list(clips_dir.glob(f"**/{Path(clip_clean).name}"))
        if matches:
            file_path = matches[0]
    if not file_path.is_file():
        legacy_candidate = Path("runtime/streamcore/output/clips").resolve() / Path(clip_clean).name
        if legacy_candidate.is_file():
            file_path = legacy_candidate

    if not file_path.is_file() or not (base_dir in file_path.resolve().parents or file_path.resolve().is_relative_to(base_dir)):
        raise HTTPException(status_code=404, detail="Clip not found")

    file_size = file_path.stat().st_size
    start = 0
    end = file_size - 1

    norm_range = (range or "").strip()
    is_range = False

    if norm_range.lower().startswith("bytes="):
        is_range = True
        try:
            range_spec = norm_range[6:].strip()
            if "," in range_spec:
                range_spec = range_spec.split(",", 1)[0].strip()
            if "-" in range_spec:
                start_str, end_str = range_spec.split("-", 1)
                start_str = start_str.strip()
                end_str = end_str.strip()
                if start_str and end_str:
                    start = int(start_str)
                    end = int(end_str)
                elif start_str:
                    start = int(start_str)
                    end = file_size - 1
                elif end_str:
                    suffix_len = int(end_str)
                    start = max(0, file_size - suffix_len)
                    end = file_size - 1

            if file_size == 0 or start >= file_size or start > end:
                return Response(
                    status_code=416,
                    headers={
                        "Content-Range": f"bytes */{file_size}",
                        "Content-Length": "0",
                        "Accept-Ranges": "bytes",
                    },
                )
        except Exception:
            start = 0
            end = file_size - 1
            is_range = False

    chunk_size = end - start + 1

    def iter_file():
        with open(file_path, "rb") as f:
            f.seek(start)
            remaining = chunk_size
            while remaining > 0:
                read_bytes = min(remaining, 64 * 1024)
                data = f.read(read_bytes)
                if not data:
                    break
                remaining -= len(data)
                yield data

    status_code = 206 if is_range else 200
    headers = {
        "Content-Type": "video/mp4",
        "Content-Length": str(chunk_size),
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-cache",
    }
    if is_range:
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

    return StreamingResponse(iter_file(), status_code=status_code, headers=headers)

