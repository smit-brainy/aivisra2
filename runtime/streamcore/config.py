import math
import os
import re
from dataclasses import dataclass, fields, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from ..tracking.types import TrackingConfig


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    mode: str = "production"
    # Legacy compatibility. New deployments should use ai.target_fps.
    target_ai_fps: float = 5
    max_frame_age_seconds: float = 2


@dataclass(frozen=True, slots=True)
class StreamsConfig:
    rtsp_latency_ms: int = 200
    reconnect_initial_seconds: float = 1
    reconnect_max_seconds: float = 15
    frame_timeout_seconds: float = 10
    reconnect_reset_seconds: float = 30
    startup_batch_size: int = 5
    startup_batch_delay_ms: int = 250
    reconnect_jitter_ratio: float = 0.25


@dataclass(frozen=True, slots=True)
class BenchmarkConfig:
    warmup_seconds: float = 10.0
    sample_interval_seconds: float = 5.0
    require_all_streams_online: bool = True
    max_reconnects_per_camera: int = 2
    max_frame_age_p99_ms: float = 500.0
    max_process_cpu_percent: float = 90.0
    max_host_cpu_percent: float = 95.0
    max_gpu_decode_percent: float = 95.0
    max_rss_growth_mib: float = 150.0


@dataclass(frozen=True, slots=True)
class HealthConfig:
    stale_after_ms: float = 2000.0
    degraded_fps_ratio: float = 0.7


@dataclass(frozen=True, slots=True)
class InferenceConfig:
    detector: str = "none"
    max_batch_size: int = 8
    model_path: str = "yolo11n.pt"
    device: str = "0"
    imgsz: int = 640
    half: bool = True
    gpu_native: bool = True
    fallback_cpu_frames: bool = True
    max_batch_wait_ms: float = 15.0
    frame_path: str = "gpu"
    detection_classes: list[int] = field(default_factory=lambda: [0])
    person_conf_threshold: float = 0.5


@dataclass(frozen=True, slots=True)
class PreviewConfig:
    enabled: bool = False
    fps: float = 1
    width: int = 480
    height: int = 270
    jpeg_quality: int = 65


@dataclass(frozen=True, slots=True)
class MonitoringConfig:
    print_interval_seconds: float = 5


@dataclass(frozen=True, slots=True)
class LiveViewConfig:
    enabled: bool = True
    provider: str = "mediamtx"
    protocol: str = "webrtc"
    mediamtx_api_url: str = "http://127.0.0.1:9997"
    mediamtx_webrtc_base_url: str = "http://127.0.0.1:8889"
    request_timeout_seconds: float = 2


@dataclass(frozen=True, slots=True)
class DecodeConfig:
    prefer_hardware: bool = True
    fallback_software: bool = True


@dataclass(frozen=True, slots=True)
class AIConfig:
    enabled: bool = False
    target_fps: float = 8
    max_total_fps: float = 350.0
    poll_interval_ms: float | None = None


@dataclass(frozen=True, slots=True)
class EvidenceConfig:
    enabled: bool = True
    key_frames_per_track: int = 3
    local_output_dir: str = "runtime/streamcore/output"


@dataclass(frozen=True, slots=True)
class EventsConfig:
    enabled: bool = True
    clip_duration_seconds: int = 10
    clip_storage_dir: str = "runtime/streamcore/output/clips"
    retention_days: int = 1
    max_concurrent_recordings: int = 2
    record_on_track_confirmed: bool = True


@dataclass(frozen=True, slots=True)
class Config:
    runtime: RuntimeConfig
    streams: StreamsConfig
    inference: InferenceConfig
    monitoring: MonitoringConfig
    diagnostic_preview: PreviewConfig = PreviewConfig()
    live_view: LiveViewConfig = LiveViewConfig()
    decode: DecodeConfig = DecodeConfig()
    ai: AIConfig = AIConfig()
    evidence: EvidenceConfig = EvidenceConfig()
    events: EventsConfig = EventsConfig()
    benchmark: BenchmarkConfig = BenchmarkConfig()
    health: HealthConfig = HealthConfig()
    tracking: TrackingConfig = TrackingConfig()

    @property
    def preview(self) -> PreviewConfig:
        """Compatibility alias; JPEG output is diagnostic-only."""
        return self.diagnostic_preview


@dataclass(frozen=True, slots=True)
class CameraConfig:
    id: str
    uri: str
    codec: str = "h264"
    decoder: str = "auto"
    enabled: bool = True
    live_path: str | None = None
    target_ai_fps: float | None = None
    expected_fps: float | None = None


def _mapping(path: str | Path) -> dict[str, Any]:
    with Path(path).open() as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Configuration must be a mapping: {path}")
    return data


def _positive(name: str, value: Any, *, integer: bool = False, zero: bool = False) -> None:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or (value < 0 if zero else value <= 0)
            or (integer and not isinstance(value, int))):
        raise ValueError(f"Invalid numeric setting: {name}")


def load_config(path: str | Path) -> Config:
    data = _mapping(path)
    if "preview" in data and "diagnostic_preview" in data:
        raise ValueError("Use diagnostic_preview, not both preview and diagnostic_preview")
    if "preview" in data:
        data = dict(data)
        data["diagnostic_preview"] = data.pop("preview")
    sections = {"runtime": RuntimeConfig, "streams": StreamsConfig,
                "inference": InferenceConfig, "monitoring": MonitoringConfig,
                "diagnostic_preview": PreviewConfig,
                "live_view": LiveViewConfig, "decode": DecodeConfig,
                "ai": AIConfig, "evidence": EvidenceConfig,
                "events": EventsConfig,
                "benchmark": BenchmarkConfig, "health": HealthConfig,
                "tracking": TrackingConfig}
    if set(data) - (sections.keys() | {"cameras"}):
        raise ValueError("Unknown runtime configuration section")
    objects: dict[str, Any] = {}
    for name, cls in sections.items():
        values = data.get(name, {})
        if not isinstance(values, dict) or set(values) - {f.name for f in fields(cls)}:
            raise ValueError(f"Unknown or invalid settings in {name}")
        objects[name] = cls(**values)
    config = Config(**objects)
    if config.runtime.mode not in ("production", "ingest_only", "decoded_frame", "preview", "demo"):
        raise ValueError("runtime.mode must be production, ingest_only, decoded_frame, preview or demo")
    if not isinstance(config.preview.enabled, bool):
        raise ValueError("preview.enabled must be a boolean")
    if config.runtime.mode == "preview" and not config.preview.enabled:
        raise ValueError("preview mode requires diagnostic_preview.enabled: true")
    for field in fields(config.preview):
        if field.name != "enabled":
            _positive(field.name, getattr(config.preview, field.name),
                      integer=field.name in ("width", "height", "jpeg_quality"))
    if config.preview.jpeg_quality > 100:
        raise ValueError("preview.jpeg_quality must be <= 100")
    for group in (config.runtime, config.streams, config.monitoring):
        for field in fields(group):
            if field.name == "mode":
                continue
            _positive(field.name, getattr(group, field.name),
                      integer=field.name == "rtsp_latency_ms",
                      zero=field.name == "rtsp_latency_ms")
    if config.streams.reconnect_max_seconds < config.streams.reconnect_initial_seconds:
        raise ValueError("reconnect_max_seconds must be >= reconnect_initial_seconds")
    inf = config.inference
    if inf.detector not in ("none", "dummy", "ultralytics"):
        raise ValueError("detector must be none, dummy or ultralytics")
    _positive("max_batch_size", inf.max_batch_size, integer=True)
    _positive("imgsz", inf.imgsz, integer=True)
    if not isinstance(inf.half, bool):
        raise ValueError("half must be a boolean")
    if not isinstance(inf.device, str) or not inf.device:
        raise ValueError('device must be a nonempty string, e.g. "0" or "cpu"')
    if not isinstance(inf.model_path, str) or not inf.model_path:
        raise ValueError("model_path must be a nonempty string")
    if inf.detector == "ultralytics" and inf.device == "cpu" and inf.half:
        raise ValueError("CPU inference requires half: false")
    if not isinstance(inf.detection_classes, list) or not all(isinstance(c, int) for c in inf.detection_classes):
        raise ValueError("detection_classes must be a list of integers")
    if not isinstance(inf.person_conf_threshold, (int, float)) or not (0 <= inf.person_conf_threshold <= 1):
        raise ValueError("person_conf_threshold must be a float between 0 and 1")
    if not isinstance(config.live_view.enabled, bool):
        raise ValueError("live_view.enabled must be a boolean")
    if config.live_view.provider != "mediamtx" or config.live_view.protocol != "webrtc":
        raise ValueError("Only MediaMTX WebRTC live view is supported")
    for name in ("mediamtx_api_url", "mediamtx_webrtc_base_url"):
        value = getattr(config.live_view, name)
        parsed = urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"Invalid live_view.{name}")
    _positive("request_timeout_seconds", config.live_view.request_timeout_seconds)
    if not isinstance(config.decode.prefer_hardware, bool) or not isinstance(config.decode.fallback_software, bool):
        raise ValueError("decode preferences must be booleans")
    if not config.decode.prefer_hardware and not config.decode.fallback_software:
        raise ValueError("decode must allow hardware preference or software fallback")
    if not isinstance(config.ai.enabled, bool):
        raise ValueError("ai.enabled must be a boolean")
    _positive("ai.target_fps", config.ai.target_fps)
    if config.ai.enabled and inf.detector == "none":
        raise ValueError("ai.enabled requires a configured inference.detector")
    if not isinstance(config.evidence.enabled, bool):
        raise ValueError("evidence.enabled must be a boolean")
    _positive("evidence.key_frames_per_track", config.evidence.key_frames_per_track, integer=True)
    if not 1 <= config.evidence.key_frames_per_track <= 5:
        raise ValueError("evidence.key_frames_per_track must be between 1 and 5")
    if not isinstance(config.evidence.local_output_dir, str) or not config.evidence.local_output_dir:
        raise ValueError("evidence.local_output_dir must be nonempty")
    if not isinstance(config.events.enabled, bool):
        raise ValueError("events.enabled must be a boolean")
    _positive("events.clip_duration_seconds", config.events.clip_duration_seconds, integer=True)
    _positive("events.retention_days", config.events.retention_days, integer=True)
    _positive("events.max_concurrent_recordings", config.events.max_concurrent_recordings, integer=True)
    if not isinstance(config.events.record_on_track_confirmed, bool):
        raise ValueError("events.record_on_track_confirmed must be a boolean")
    if not isinstance(config.events.clip_storage_dir, str) or not config.events.clip_storage_dir:
        raise ValueError("events.clip_storage_dir must be nonempty")
    return config


def load_local_env(path: str | Path) -> None:
    """Load optional, Git-ignored camera URLs without exposing values in logs.

    Existing shell variables take precedence. This intentionally supports only
    simple KEY=VALUE lines; it does not execute shell code or expand substitutions.
    """
    env_path = Path(path)
    if not env_path.exists():
        return
    for line_number, raw in enumerate(env_path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or not value:
            raise ValueError(f"Invalid local environment entry on line {line_number}")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if not value:
            raise ValueError(f"Empty local environment value on line {line_number}")
        os.environ.setdefault(key, value)


def load_cameras(path: str | Path) -> list[CameraConfig]:
    data = _mapping(path)
    sections = {"runtime", "streams", "inference", "monitoring", "preview",
                "diagnostic_preview", "live_view", "decode", "ai", "evidence",
                "events", "benchmark", "health", "tracking", "cameras"}
    if (set(data) - sections or "cameras" not in data
            or not isinstance(data["cameras"], list)):
        raise ValueError("Camera configuration must contain a cameras list")
    cameras = []
    ids: set[str] = set()
    for entry in data["cameras"]:
        if not isinstance(entry, dict) or set(entry) - {f.name for f in fields(CameraConfig)}:
            raise ValueError("Invalid camera configuration fields")
        camera_id = entry.get("id")
        if not isinstance(camera_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", camera_id):
            raise ValueError("Camera IDs must use letters, digits, underscores or hyphens")
        if camera_id in ids:
            raise ValueError(f"Duplicate camera ID: {camera_id}")
        ids.add(camera_id)
        enabled = entry.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError(f"enabled must be a boolean: {camera_id}")
        if not enabled:
            continue  # Disabled cameras do not require URI environment variables.
        uri = entry.get("uri")
        if not isinstance(uri, str) or not uri:
            raise ValueError(f"Missing URI: {camera_id}")
        variables = re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)", uri)
        for a, b in variables:
            var_name = a or b
            if not os.environ.get(var_name):
                raise ValueError(f"Missing URI environment variable ${var_name} for camera {camera_id}")
        uri = os.path.expandvars(uri)
        try:
            parsed = urlsplit(uri)
            valid = parsed.scheme in ("rtsp", "rtsps", "file", "test")
            if parsed.scheme in ("rtsp", "rtsps"):
                valid = valid and bool(parsed.hostname) and bool(parsed.port or 554)
            if parsed.scheme == "file":
                valid = valid and bool(parsed.path) and parsed.netloc in ("", "localhost")
            if parsed.scheme == "test":
                valid = uri == "test://smpte"
        except ValueError:
            valid = False
        if not valid:
            raise ValueError(f"Unsupported or invalid URI for {camera_id}")
        codec = entry.get("codec", "h264")
        if not isinstance(codec, str):
            raise ValueError(f"Invalid codec for {camera_id}")
        codec = codec.lower()
        if codec == "hevc":
            codec = "h265"
        decoder = entry.get("decoder", "auto")
        if codec not in ("h264", "h265", "mpeg4") or not isinstance(decoder, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", decoder):
            raise ValueError(f"Invalid codec or decoder for {camera_id}")
        live_path = entry.get("live_path", camera_id.lower())
        if not isinstance(live_path, str) or not re.fullmatch(r"[A-Za-z0-9_.~-]+", live_path):
            raise ValueError(f"Invalid live_path for {camera_id}")
        target_ai_fps = entry.get("target_ai_fps")
        if target_ai_fps is not None:
            _positive(f"cameras.{camera_id}.target_ai_fps", target_ai_fps)
        expected_fps = entry.get("expected_fps")
        if expected_fps is not None:
            _positive(f"cameras.{camera_id}.expected_fps", expected_fps)
        cameras.append(CameraConfig(camera_id, uri, codec, decoder, True, live_path, target_ai_fps, expected_fps))
    if not cameras:
        raise ValueError("Enable at least one camera")
    return cameras
