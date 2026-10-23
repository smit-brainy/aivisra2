# apps/ingest/config.py
"""Constants for the ingest service — loaded from environment variables."""
import os

DATABASE_URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")

UPDATE_INTERVAL_S = 5
RECONCILE_INTERVAL_S = 10
PROBE_TIMEOUT_S = 15
WORKER_QUEUE_SIZE = 10

# Frame timeout (seconds without decoded frames → mark as degraded → reconcile restarts)
FRAME_TIMEOUT_S = float(os.environ.get("FRAME_TIMEOUT_S", "10"))

# JPEG viewer (writes BGR JPEGs to shared volume for host-side OpenCV viewer)
VIEWER_FRAMES_DIR = os.environ.get("VIEWER_FRAMES_DIR", "/app/frames")
VIEWER_JPEG_QUALITY = int(os.environ.get("VIEWER_JPEG_QUALITY", "70"))

# AI inference settings
DETECTOR_TYPE = os.environ.get("DETECTOR", "none")  # "none", "dummy", "ultralytics"
MODEL_PATH = os.environ.get("MODEL_PATH", "yolo11n.pt")
DEVICE = os.environ.get("DEVICE", "0")
IMGSZ = int(os.environ.get("IMGSZ", "640"))
HALF_PRECISION = os.environ.get("HALF", "true").lower() == "true"
AI_MAX_BATCH_SIZE = int(os.environ.get("AI_MAX_BATCH_SIZE", "8"))
AI_BATCH_TIMEOUT_MS = int(os.environ.get("AI_BATCH_TIMEOUT_MS", "100"))
AI_TARGET_FPS = float(os.environ.get("AI_TARGET_FPS", "5"))

# AI scheduler: fair rotation + per-camera rate limit + stale-frame drop.
# Mirrors StreamCore LatestFrameScheduler: each camera is inferred at most
# AI_TARGET_FPS, selected in rotating order, frames older than
# AI_MAX_FRAME_AGE_S are dropped instead of inferred.
AI_MAX_FRAME_AGE_S = float(os.environ.get("AI_MAX_FRAME_AGE_S", "2.0"))

# Decode <-> AI queue (Redis-backed with in-memory fallback).
# Bulk pixels stay in-process (zero-copy / numpy); Redis carries
# queue depth + result signals for backpressure visibility.
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
AI_QUEUE_MAX_PENDING = int(os.environ.get("AI_QUEUE_MAX_PENDING", "40"))

# VRAM watchdog: pause inference above this, resume below it.
VRAM_PAUSE_MB = float(os.environ.get("VRAM_PAUSE_MB", "10752"))  # 10.5 GB
VRAM_RESUME_MB = float(os.environ.get("VRAM_RESUME_MB", "10240"))  # 10.0 GB

# NVDEC session cap: consumer RTX cards wedge (MMU/TLB storm ->
# libnvcuvid segfault -> full-chip reset -> black screen) when dozens of
# concurrent nvh264dec sessions share the GPU with display + CUDA.
# Pipelines beyond this count fall back to CPU (avdec_*) automatically.
# 30 HW + rest CPU for 40 cameras on RTX 5070.
MAX_HW_DECODERS = int(os.environ.get("MAX_HW_DECODERS", "12"))
# Startup batching: start pipelines in small batches with a pause between
# batches so concurrent NVDEC allocs never storm the driver (the alloc
# burst, not the steady count, is what wedges the MMU/TLB path).
STARTUP_BATCH_SIZE = int(os.environ.get("STARTUP_BATCH_SIZE", "4"))
STARTUP_BATCH_DELAY_S = float(os.environ.get("STARTUP_BATCH_DELAY_S", "1.0"))
