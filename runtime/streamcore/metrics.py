"""Bounded, thread-safe counters for ingest, inference, and preview benchmarks."""

from collections import deque
from dataclasses import dataclass
from threading import Lock
from time import monotonic, time
from typing import Any

from .types import CameraHealth, CameraState, DetectionResult


def compute_percentiles(values: list[float] | deque) -> dict[str, float | None]:
    if not values:
        return {"avg": None, "p50": None, "p95": None, "p99": None, "max": None}
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    avg_val = sum(sorted_vals) / n
    p50 = sorted_vals[int(n * 0.50)] if n else None
    p95 = sorted_vals[min(int(n * 0.95), n - 1)] if n else None
    p99 = sorted_vals[min(int(n * 0.99), n - 1)] if n else None
    max_val = sorted_vals[-1] if n else None
    return {"avg": avg_val, "p50": p50, "p95": p95, "p99": p99, "max": max_val}


@dataclass(slots=True)
class CameraMetrics:
    state: CameraState = CameraState.OFFLINE
    health: CameraHealth = CameraHealth.OFFLINE
    codec: str = "h264"
    last_error: str | None = None
    frames_received: int = 0  # Decoded buffers, also in fakesink mode.
    frames_inferred: int = 0  # Legacy counter; always zero in benchmark modes.
    reconnect_count: int = 0
    last_frame_time: float | None = None
    last_received_monotonic: float | None = None
    total_latency_ms: float = 0.0
    preview_frames: int = 0
    last_preview_monotonic: float | None = None
    last_preview_sequence: int = 0
    frames_replaced_before_preview: int = 0
    ai_frames_replaced: int = 0
    decoder_name: str = "unselected"
    decoder_type: str = "unknown"
    decoder_errors: int = 0
    startup_time_ms: float | None = None
    last_disconnect_monotonic: float | None = None
    last_reconnect_monotonic: float | None = None
    recovery_time_ms: float | None = None
    expected_fps: float | None = None
    actual_fps: float = 0.0
    fps_ratio: float | None = None
    frame_age_reservoir: deque = None  # type: ignore
    frame_path: str = "GPU_NATIVE"
    cpu_frame_downloads: int = 0
    ai_fps: float = 0.0


class MetricsRegistry:
    """Cumulative counters and report-window rates; bounded history for percentiles."""

    def __init__(self, camera_ids: list[str], requested_ai_fps: float = 0,
                 stale_after_ms: float = 2000.0, degraded_fps_ratio: float = 0.7) -> None:
        self._lock = Lock()
        self._cameras = {cid: CameraMetrics() for cid in camera_ids}
        for m in self._cameras.values():
            m.frame_age_reservoir = deque(maxlen=500)
        self._physical_sources = len(camera_ids)
        self._source_groups = {cid: cid for cid in camera_ids}
        self._stale_after_ms = stale_after_ms
        self._degraded_fps_ratio = degraded_fps_ratio
        self._batches = 0
        self._batch_frames = 0
        self._batch_ms = 0.0
        self._batch_sizes = deque(maxlen=500)
        self._batch_waits = deque(maxlen=500)
        self._preprocess_times = deque(maxlen=500)
        self._inference_times = deque(maxlen=500)
        self._postprocess_times = deque(maxlen=500)
        self._result_latencies = deque(maxlen=500)
        self._preview_encodes = 0
        self._preview_encode_ms = 0.0
        self._previous = {cid: (0, 0, 0.0, 0) for cid in camera_ids}
        self._previous_batches = (0, 0, 0.0)
        self._previous_preview = (0, 0.0)
        self._reported_at = monotonic()
        self._requested_ai_fps = requested_ai_fps
        self._mediamtx_available = False
        self._webrtc_sessions = 0
        self._active_live_viewers = 0
        self._global_frame_age_reservoir = deque(maxlen=1000)

    def set_target_ai_fps(self, target_fps: float) -> None:
        with self._lock:
            self._requested_ai_fps = target_fps

    def register_camera(self, camera_id: str) -> None:
        with self._lock:
            if camera_id not in self._cameras:
                cm = CameraMetrics()
                cm.frame_age_reservoir = deque(maxlen=500)
                self._cameras[camera_id] = cm
                self._previous[camera_id] = (0, 0, 0.0, 0)
                self._source_groups[camera_id] = camera_id
                self._physical_sources += 1

    def configure_sources(self, source_for: dict[str, str]) -> None:
        with self._lock:
            self._source_groups = dict(source_for)
            self._physical_sources = len(set(source_for.values()))

    def configure_decoder(self, camera_id: str, name: str, decoder_type: str) -> None:
        with self._lock:
            m = self._cameras.get(camera_id)
            if m:
                m.decoder_name = name
                m.decoder_type = decoder_type

    def configure_camera(self, camera_id: str, codec: str, expected_fps: float | None = None) -> None:
        with self._lock:
            m = self._cameras.get(camera_id)
            if m:
                m.codec = codec
                if expected_fps is not None:
                    m.expected_fps = expected_fps

    def configure_expected_fps(self, camera_id: str, expected_fps: float | None) -> None:
        with self._lock:
            m = self._cameras.get(camera_id)
            if m:
                m.expected_fps = expected_fps

    def record_error(self, camera_id: str, error: str) -> None:
        with self._lock:
            m = self._cameras.get(camera_id)
            if m:
                m.last_error = error

    def decoder_error(self, camera_id: str) -> None:
        with self._lock:
            m = self._cameras.get(camera_id)
            if m:
                m.decoder_errors += 1

    def ai_replaced(self, camera_id: str, count: int) -> None:
        if count <= 0:
            return
        with self._lock:
            m = self._cameras.get(camera_id)
            if m:
                m.ai_frames_replaced += count

    def live_view(self, *, mediamtx_available: bool, webrtc_sessions: int,
                  active_live_viewers: int) -> None:
        with self._lock:
            self._mediamtx_available = mediamtx_available
            self._webrtc_sessions = max(0, webrtc_sessions)
            self._active_live_viewers = max(0, active_live_viewers)

    def state(self, camera_id: str, state: CameraState) -> None:
        with self._lock:
            m = self._cameras.get(camera_id)
            if m:
                m.state = state
                if state == CameraState.CONNECTED:
                    m.health = CameraHealth.HEALTHY
                elif state == CameraState.RECONNECTING:
                    m.health = CameraHealth.RECONNECTING
                elif state == CameraState.OFFLINE:
                    m.health = CameraHealth.OFFLINE

    set_state = state

    def reconnect(self, camera_id: str, now_mono: float | None = None) -> None:
        with self._lock:
            m = self._cameras.get(camera_id)
            if m:
                m.reconnect_count += 1
                if now_mono is not None:
                    m.last_reconnect_monotonic = now_mono
                m.state = CameraState.RECONNECTING
                m.health = CameraHealth.RECONNECTING

    record_reconnect = reconnect

    def record_disconnect(self, camera_id: str, now_mono: float) -> None:
        with self._lock:
            m = self._cameras.get(camera_id)
            if m:
                m.last_disconnect_monotonic = now_mono
                m.state = CameraState.OFFLINE
                m.health = CameraHealth.RECONNECTING

    def record_startup_time(self, camera_id: str, startup_ms: float) -> None:
        with self._lock:
            m = self._cameras.get(camera_id)
            if m:
                m.startup_time_ms = startup_ms

    def record_recovery(self, camera_id: str, recovery_ms: float) -> None:
        with self._lock:
            m = self._cameras.get(camera_id)
            if m:
                m.recovery_time_ms = recovery_ms

    def received(self, camera_id: str, timestamp: float, received_monotonic: float,
                 count: int = 1) -> None:
        with self._lock:
            m = self._cameras.get(camera_id)
            if not m:
                return
            m.frames_received += count
            m.last_frame_time = timestamp
            m.last_received_monotonic = received_monotonic
            m.state = CameraState.CONNECTED
            if m.last_disconnect_monotonic is not None:
                m.recovery_time_ms = (received_monotonic - m.last_disconnect_monotonic) * 1000
                m.last_disconnect_monotonic = None

    def record_frame(self, camera_id: str, received_monotonic: float, timestamp: float | None = None,
                     count: int = 1) -> None:
        self.received(camera_id, timestamp if timestamp is not None else time(), received_monotonic, count)

    def preview_encoded(self, elapsed_ms: float) -> None:
        with self._lock:
            self._preview_encodes += 1
            self._preview_encode_ms += elapsed_ms

    def preview_published(self, camera_id: str, sequence: int, generated_monotonic: float) -> None:
        with self._lock:
            m = self._cameras.get(camera_id)
            if not m:
                return
            if sequence <= m.last_preview_sequence:
                return
            if m.last_preview_sequence:
                m.frames_replaced_before_preview += sequence - m.last_preview_sequence - 1
            else:
                m.frames_replaced_before_preview += max(0, sequence - 1)
            m.last_preview_sequence = sequence
            m.last_preview_monotonic = generated_monotonic
            m.preview_frames += 1

    def batch(self, results: list[DetectionResult], elapsed_ms: float,
              batch_wait_ms: float = 0.0, preprocess_ms: float = 0.0,
              postprocess_ms: float = 0.0) -> None:
        with self._lock:
            self._batches += 1
            n = len(results)
            self._batch_frames += n
            self._batch_ms += elapsed_ms
            self._batch_sizes.append(n)
            self._batch_waits.append(batch_wait_ms)
            self._preprocess_times.append(preprocess_ms)
            self._inference_times.append(elapsed_ms)
            self._postprocess_times.append(postprocess_ms)
            for result in results:
                m = self._cameras.get(result.camera_id)
                if m:
                    m.frames_inferred += 1
                    m.total_latency_ms += result.total_latency_ms
                    self._result_latencies.append(result.total_latency_ms)

    def record_frame_path(self, camera_id: str, path: str) -> None:
        with self._lock:
            m = self._cameras.get(camera_id)
            if m:
                m.frame_path = path

    def record_cpu_download(self, camera_id: str, count: int = 1) -> None:
        with self._lock:
            m = self._cameras.get(camera_id)
            if m:
                m.cpu_frame_downloads += count

    def _compute_health(self, m: CameraMetrics, now: float, actual_fps: float) -> str:
        if m.state == CameraState.OFFLINE:
            return CameraHealth.OFFLINE.value
        if m.state == CameraState.RECONNECTING:
            return CameraHealth.RECONNECTING.value
        if m.last_received_monotonic is not None:
            age_ms = (now - m.last_received_monotonic) * 1000.0
            if age_ms > self._stale_after_ms:
                return CameraHealth.STALE.value
        if m.expected_fps is not None and m.expected_fps > 0:
            if actual_fps < m.expected_fps * self._degraded_fps_ratio:
                return CameraHealth.DEGRADED.value
        if m.state == CameraState.CONNECTED:
            return CameraHealth.HEALTHY.value
        return CameraHealth.OFFLINE.value

    def _camera(self, m: CameraMetrics, now: float, actual_fps: float = 0.0) -> dict[str, Any]:
        age = (now - m.last_received_monotonic) * 1000 if m.last_received_monotonic is not None else None
        if age is not None:
            if m.frame_age_reservoir is not None:
                m.frame_age_reservoir.append(age)
            self._global_frame_age_reservoir.append(age)
        preview_age = (now - m.last_preview_monotonic) * 1000 if m.last_preview_monotonic is not None else None
        health = self._compute_health(m, now, actual_fps)
        m.health = CameraHealth(health)
        m.actual_fps = actual_fps
        m.fps_ratio = (actual_fps / m.expected_fps) if (m.expected_fps and m.expected_fps > 0) else None

        age_stats = compute_percentiles(m.frame_age_reservoir) if m.frame_age_reservoir else {}

        return {"state": m.state.value,
                "health": health,
                "codec": m.codec,
                "frames_received": m.frames_received,
                "received_frames": m.frames_received,
                "frames_inferred": m.frames_inferred,
                "reconnect_count": m.reconnect_count,
                "last_error": m.last_error,
                "last_frame_time": m.last_frame_time,
                "frame_age_ms": age,
                "last_frame_age_ms": age,
                "last_frame_age_seconds": age / 1000 if age is not None else None,
                "frame_age_avg_ms": age_stats.get("avg"),
                "frame_age_p50_ms": age_stats.get("p50"),
                "frame_age_p95_ms": age_stats.get("p95"),
                "frame_age_p99_ms": age_stats.get("p99"),
                "frame_age_max_ms": age_stats.get("max"),
                "preview_frames": m.preview_frames,
                "preview_age_ms": preview_age,
                "frames_replaced_before_preview": m.frames_replaced_before_preview,
                "replaced_frames": m.frames_replaced_before_preview,
                "ai_frames_replaced": m.ai_frames_replaced,
                "decoder_name": m.decoder_name,
                "decoder_type": m.decoder_type,
                "decoder_errors": m.decoder_errors,
                "startup_time_ms": m.startup_time_ms,
                "recovery_time_ms": m.recovery_time_ms,
                "expected_fps": m.expected_fps,
                "actual_fps": actual_fps,
                "input_fps": actual_fps,
                "decode_fps": actual_fps,
                "decoded_fps": actual_fps,
                "ai_fps": m.ai_fps,
                "fps_ratio": m.fps_ratio,
                "frame_path": m.frame_path,
                "cpu_frame_downloads": m.cpu_frame_downloads}

    def _physical_online(self) -> int:
        return len({source for cid, source in self._source_groups.items()
                    if cid in self._cameras and self._cameras[cid].state == CameraState.CONNECTED})

    def view(self) -> dict[str, Any]:
        """Read without resetting the terminal report's rate window."""
        now = monotonic()
        with self._lock:
            cameras = {cid: self._camera(m, now, m.actual_fps) for cid, m in self._cameras.items()}
            healthy_count = sum(c["health"] == "HEALTHY" for c in cameras.values())
            degraded_count = sum(c["health"] == "DEGRADED" for c in cameras.values())
            stale_count = sum(c["health"] == "STALE" for c in cameras.values())
            offline_count = sum(c["health"] == "OFFLINE" for c in cameras.values())
            reconnecting_count = sum(c["health"] == "RECONNECTING" for c in cameras.values())
            global_age = compute_percentiles(self._global_frame_age_reservoir)
            return {"total_streams": len(cameras),
                    "online_streams": sum(c["state"] == "CONNECTED" for c in cameras.values()),
                    "healthy_streams": healthy_count,
                    "degraded_streams": degraded_count,
                    "stale_streams": stale_count,
                    "offline_streams": offline_count,
                    "reconnecting_streams": reconnecting_count,
                    "logical_streams_total": len(cameras),
                    "logical_streams_online": sum(c["state"] == "CONNECTED" for c in cameras.values()),
                    "physical_streams": self._physical_sources,
                    "physical_streams_total": self._physical_sources,
                    "source_for": dict(self._source_groups),
                    "physical_online_streams": self._physical_online(),
                    "preview_encode_count": self._preview_encodes,
                    "preview_encode_total_ms": self._preview_encode_ms,
                    "frames_replaced_before_preview": sum(m.frames_replaced_before_preview for m in self._cameras.values()),
                    "frames_replaced_before_preview_physical": sum(self._cameras[src].frames_replaced_before_preview for src in set(self._source_groups.values()) if src in self._cameras),
                    "requested_ai_fps": self._requested_ai_fps,
                    "ai_target_fps": self._requested_ai_fps,
                    "ai_frames_replaced": sum(m.ai_frames_replaced for m in self._cameras.values()),
                    "cpu_frame_download_count": sum(m.cpu_frame_downloads for m in self._cameras.values()),
                    "frame_path": "GPU_NATIVE" if all(m.frame_path == "GPU_NATIVE" for m in self._cameras.values()) else "MIXED",
                    "reconnect_total": sum(m.reconnect_count for m in self._cameras.values()),
                    "mediamtx_available": self._mediamtx_available,
                    "webrtc_session_count": self._webrtc_sessions,
                    "active_live_viewers": self._active_live_viewers,
                    "frame_age_avg_ms": global_age.get("avg"),
                    "frame_age_p50_ms": global_age.get("p50"),
                    "frame_age_p95_ms": global_age.get("p95"),
                    "frame_age_p99_ms": global_age.get("p99"),
                    "frame_age_max_ms": global_age.get("max"),
                    "cameras": cameras}

    def snapshot(self) -> dict[str, Any]:
        now = monotonic()
        with self._lock:
            interval = max(now - self._reported_at, 1e-9)
            cameras = {}
            for cid, m in self._cameras.items():
                received, inferred, latency, previews = self._previous[cid]
                n_received = m.frames_received - received
                n_inferred = m.frames_inferred - inferred
                act_fps = n_received / interval
                ai_fps = n_inferred / interval
                m.ai_fps = ai_fps
                row = self._camera(m, now, act_fps)
                row.update(input_fps=act_fps,
                           decode_fps=act_fps,
                           decoded_fps=act_fps,
                           ai_fps=ai_fps,
                           preview_fps=(m.preview_frames - previews) / interval,
                           average_total_latency_ms=(m.total_latency_ms - latency) / n_inferred if n_inferred else 0)
                cameras[cid] = row
                self._previous[cid] = (m.frames_received, m.frames_inferred, m.total_latency_ms, m.preview_frames)

            batches, frames, ms = self._previous_batches
            n_batches = self._batches - batches
            encodes, encode_ms = self._previous_preview
            n_encodes = self._preview_encodes - encodes

            healthy_count = sum(c["health"] == "HEALTHY" for c in cameras.values())
            degraded_count = sum(c["health"] == "DEGRADED" for c in cameras.values())
            stale_count = sum(c["health"] == "STALE" for c in cameras.values())
            offline_count = sum(c["health"] == "OFFLINE" for c in cameras.values())
            reconnecting_count = sum(c["health"] == "RECONNECTING" for c in cameras.values())
            global_age = compute_percentiles(self._global_frame_age_reservoir)

            b_sizes = compute_percentiles(self._batch_sizes)
            b_waits = compute_percentiles(self._batch_waits)
            prep_stats = compute_percentiles(self._preprocess_times)
            infer_stats = compute_percentiles(self._inference_times)
            post_stats = compute_percentiles(self._postprocess_times)
            lat_stats = compute_percentiles(self._result_latencies)

            report = {
                "timestamp": time(), "interval_seconds": interval,
                "total_streams": len(cameras),
                "online_streams": sum(c["state"] == "CONNECTED" for c in cameras.values()),
                "healthy_streams": healthy_count,
                "degraded_streams": degraded_count,
                "stale_streams": stale_count,
                "offline_streams": offline_count,
                "reconnecting_streams": reconnecting_count,
                "logical_streams_total": len(cameras),
                "logical_streams_online": sum(c["state"] == "CONNECTED" for c in cameras.values()),
                "physical_streams": self._physical_sources,
                "physical_streams_total": self._physical_sources,
                "physical_online_streams": self._physical_online(),
                "total_input_fps_logical": sum(c["input_fps"] for c in cameras.values()),
                "total_input_fps_physical": sum(cameras[src]["input_fps"] for src in set(self._source_groups.values()) if src in cameras),
                "input_fps_total": sum(c["input_fps"] for c in cameras.values()),
                "decode_fps_total": sum(c["decoded_fps"] for c in cameras.values()),
                "requested_ai_fps": self._requested_ai_fps,
                "ai_target_fps": self._requested_ai_fps,
                "total_actual_ai_fps": sum(c["ai_fps"] for c in cameras.values()),
                "ai_actual_fps": sum(c["ai_fps"] for c in cameras.values()),
                "ai_frames_replaced": sum(m.ai_frames_replaced for m in self._cameras.values()),
                "cpu_frame_download_count": sum(m.cpu_frame_downloads for m in self._cameras.values()),
                "frame_path": "GPU_NATIVE" if all(m.frame_path == "GPU_NATIVE" for m in self._cameras.values()) else "MIXED",
                "reconnect_total": sum(m.reconnect_count for m in self._cameras.values()),
                "total_preview_fps_logical": sum(c["preview_fps"] for c in cameras.values()),
                "preview_encode_fps": n_encodes / interval,
                "diagnostic_jpeg_per_sec": n_encodes / interval,
                "preview_encode_count": self._preview_encodes,
                "average_preview_encode_ms": (self._preview_encode_ms - encode_ms) / n_encodes if n_encodes else 0,
                "diagnostic_jpeg_encode_ms": (self._preview_encode_ms - encode_ms) / n_encodes if n_encodes else 0,
                "frames_replaced_before_preview": sum(m.frames_replaced_before_preview for m in self._cameras.values()),
                "frames_replaced_before_preview_physical": sum(self._cameras[src].frames_replaced_before_preview for src in set(self._source_groups.values()) if src in cameras),
                "average_batch_size": b_sizes.get("avg", 0.0),
                "batch_size_p95": b_sizes.get("p95"),
                "batch_wait_avg_ms": b_waits.get("avg", 0.0),
                "batch_wait_p95_ms": b_waits.get("p95"),
                "preprocess_avg_ms": prep_stats.get("avg", 0.0),
                "inference_avg_ms": infer_stats.get("avg", 0.0),
                "postprocess_avg_ms": post_stats.get("avg", 0.0),
                "result_latency_p50_ms": lat_stats.get("p50"),
                "result_latency_p95_ms": lat_stats.get("p95"),
                "result_latency_p99_ms": lat_stats.get("p99"),
                "average_batch_inference_ms": (self._batch_ms - ms) / n_batches if n_batches else 0,
                "frame_age_avg_ms": global_age.get("avg"),
                "frame_age_p50_ms": global_age.get("p50"),
                "frame_age_p95_ms": global_age.get("p95"),
                "frame_age_p99_ms": global_age.get("p99"),
                "frame_age_max_ms": global_age.get("max"),
                "mediamtx_available": self._mediamtx_available,
                "webrtc_session_count": self._webrtc_sessions,
                "active_live_viewers": self._active_live_viewers,
                "cameras": cameras,
            }
            self._previous_batches = (self._batches, self._batch_frames, self._batch_ms)
            self._previous_preview = (self._preview_encodes, self._preview_encode_ms)
            self._reported_at = now
            return report


class ResourceMonitor:
    """Process, host network, host RAM, and multi-GPU metrics via NVML."""

    def __init__(self) -> None:
        import psutil
        self._process = psutil.Process()
        self._process.cpu_percent(None)
        psutil.cpu_percent(None)
        network = psutil.net_io_counters()
        self._network_at = monotonic()
        self._network_rx_bytes = network.bytes_recv
        self._network_tx_bytes = network.bytes_sent
        self._nvml: Any = None
        try:
            import pynvml
            pynvml.nvmlInit()
            self._nvml = pynvml
        except Exception:
            pass

    def sample(self) -> dict[str, Any]:
        import psutil
        now = monotonic()
        network = psutil.net_io_counters()
        rx_diff = max(0, network.bytes_recv - self._network_rx_bytes)
        tx_diff = max(0, network.bytes_sent - self._network_tx_bytes)
        dt = max(now - self._network_at, 1e-9)
        rx_mib_s = rx_diff / 1024**2 / dt
        tx_mib_s = tx_diff / 1024**2 / dt
        total_network_mib_s = (rx_diff + tx_diff) / 1024**2 / dt
        self._network_rx_bytes = network.bytes_recv
        self._network_tx_bytes = network.bytes_sent
        self._network_at = now

        result: dict[str, Any] = {
            "process_cpu_percent": self._process.cpu_percent(None),
            "host_cpu_percent": psutil.cpu_percent(None),
            "rss_mib": self._process.memory_info().rss / 1024**2,
            "host_ram_percent": psutil.virtual_memory().percent,
            "threads": self._process.num_threads(),
            "host_network_rx_mib_s": rx_mib_s,
            "host_network_tx_mib_s": tx_mib_s,
            "host_network_mib_s": total_network_mib_s,
            "gpus": [],
        }
        if self._nvml is not None:
            try:
                for index in range(self._nvml.nvmlDeviceGetCount()):
                    handle = self._nvml.nvmlDeviceGetHandleByIndex(index)
                    name = self._nvml.nvmlDeviceGetName(handle)
                    if isinstance(name, bytes):
                        name = name.decode("utf-8", errors="ignore")
                    util = self._nvml.nvmlDeviceGetUtilizationRates(handle)
                    memory = self._nvml.nvmlDeviceGetMemoryInfo(handle)
                    gpu = {
                        "index": index,
                        "name": str(name),
                        "utilization_percent": util.gpu,
                        "used_mib": memory.used / 1024**2,
                        "total_mib": memory.total / 1024**2,
                        "decoder_percent": None,
                    }
                    try:
                        gpu["decoder_percent"] = self._nvml.nvmlDeviceGetDecoderUtilization(handle)[0]
                    except Exception:
                        pass
                    result["gpus"].append(gpu)
            except Exception:
                result["gpu_status"] = "unavailable"
        else:
            result["gpu_status"] = "unavailable"
        return result

    def close(self) -> None:
        if self._nvml is not None:
            try:
                self._nvml.nvmlShutdown()
            except Exception:
                pass
            self._nvml = None


def format_report(report: dict[str, Any], resources: dict[str, Any], mode: str = "preview", verbose_cameras: bool = False) -> str:
    """Format compact terminal output per Stage N, with optional verbose per-camera listing."""
    gpu = resources["gpus"][0] if resources.get("gpus") else {}
    gpu_util = f"{gpu.get('utilization_percent', 0)}%" if gpu else "N/A"
    dec_val = gpu.get("decoder_percent") if gpu else None
    nvdec_util = f"{dec_val}%" if dec_val is not None else "N/A"
    vram_used = (gpu.get("used_mib", 0) / 1024.0) if gpu else 0.0
    vram_total = (gpu.get("total_mib", 0) / 1024.0) if gpu else 0.0

    age_avg = f"{report.get('frame_age_avg_ms', 0):.0f}" if report.get("frame_age_avg_ms") is not None else "N/A"
    age_p95 = f"{report.get('frame_age_p95_ms', 0):.0f}" if report.get("frame_age_p95_ms") is not None else "N/A"
    age_p99 = f"{report.get('frame_age_p99_ms', 0):.0f}" if report.get("frame_age_p99_ms") is not None else "N/A"

    ai_fps = report.get("ai_actual_fps")
    ai_fps_str = f"{ai_fps:.1f}" if ai_fps is not None else "0.0"

    bw = report.get("batch_wait_avg_ms")
    bw_str = f"{bw:.1f} ms" if bw is not None else "N/A"

    prep = report.get("preprocess_avg_ms")
    prep_str = f"{prep:.1f} ms" if prep is not None else "N/A"

    infer = report.get("inference_avg_ms")
    infer_str = f"{infer:.1f} ms" if infer is not None else "N/A"

    in_fps = report.get("input_fps_total") or 0.0
    dec_fps = report.get("decode_fps_total") or 0.0
    cpu_dl = report.get("cpu_frame_download_count") or 0

    lines = [
        "=" * 88,
        f"AIVISRA STREAMCORE | {mode}",
        "",
        f"Streams: {report['online_streams']}/{report['total_streams']}",
        f"Healthy: {report.get('healthy_streams', 0)}",
        f"Degraded: {report.get('degraded_streams', 0)}",
        f"Offline: {report.get('offline_streams', 0)}",
        f"Reconnect: {report.get('reconnecting_streams', 0)}",
        "",
        f"Input FPS: {in_fps:.1f}",
        f"Decode FPS: {dec_fps:.1f}",
        f"AI FPS: {ai_fps_str}",
        f"Frame Path: {report.get('frame_path', 'GPU_NATIVE')} | CPU Downloads: {cpu_dl}",
        "",
        f"CPU: process {resources['process_cpu_percent']:.0f}% | host {resources['host_cpu_percent']:.0f}%",
        f"RAM: {resources['rss_mib']:.0f} MiB",
        f"GPU: {gpu_util}",
        f"NVDEC: {nvdec_util}",
        f"VRAM: {vram_used:.1f} / {vram_total:.1f} GiB",
        "",
        "AI Inference Processing:",
        f"  Total AI FPS:   {ai_fps_str} FPS (Target: {report.get('ai_target_fps', 8.0)} FPS/cam)",
        f"  Preprocess:     {prep_str}",
        f"  Inference:      {infer_str}",
        f"  Batch Wait:     {bw_str}",
        f"  Frame Age:      avg {age_avg} ms | p95 {age_p95} ms | p99 {age_p99} ms",
    ]

    if verbose_cameras and "cameras" in report:
        lines.append("-" * 88)
        lines.append("Per-Camera Breakdown:")
        for cid, m in report["cameras"].items():
            age_str = f"{m['frame_age_ms']:.0f}ms" if m.get("frame_age_ms") is not None else "never"
            ai_val = f"{m.get('ai_fps', 0.0):4.1f}" if m.get('ai_fps') is not None else " 0.0"
            lines.append(
                f"{cid:<8} {m['state']:<11} {m['health']:<8} "
                f"DEC={m['input_fps']:4.1f} FPS  AI={ai_val} FPS  "
                f"AGE={age_str:>6}  DEC={m['decoder_name']}({m['decoder_type']})  "
                f"RECONN={m['reconnect_count']}"
            )
    lines.append("=" * 88)
    return "\n".join(lines)
