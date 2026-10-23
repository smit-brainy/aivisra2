"""Production-grade benchmark accumulator, pass/fail evaluator, and CSV exporter."""

import csv
from collections import deque
from pathlib import Path
from time import monotonic, time
from typing import Any

from .config import BenchmarkConfig


class MetricsCsvWriter:
    """Exports per-sample interval camera and system metrics to CSV."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("w", newline="")
        self.writer = csv.writer(self.file)
        self.writer.writerow([
            "timestamp", "camera_id", "state", "health",
            "input_fps", "decode_fps", "scheduled_fps", "frame_age_ms",
            "decoder", "reconnects", "process_cpu", "host_cpu",
            "rss_mib", "gpu_util", "gpu_decode", "vram_mib",
        ])
        self.file.flush()

    def write_sample(self, report: dict[str, Any], resources: dict[str, Any]) -> None:
        now_ts = report.get("timestamp", time())
        proc_cpu = resources.get("process_cpu_percent", 0.0)
        host_cpu = resources.get("host_cpu_percent", 0.0)
        rss = resources.get("rss_mib", 0.0)

        gpu = resources.get("gpus", [{}])[0] if resources.get("gpus") else {}
        gpu_util = gpu.get("utilization_percent", 0.0)
        gpu_dec = gpu.get("decoder_percent", 0.0) or 0.0
        vram = gpu.get("used_mib", 0.0)

        cameras = report.get("cameras", {})
        for cid, cam in cameras.items():
            self.writer.writerow([
                f"{now_ts:.3f}",
                cid,
                cam.get("state", "UNKNOWN"),
                cam.get("health", "UNKNOWN"),
                f"{cam.get('input_fps', 0.0):.2f}",
                f"{cam.get('decoded_fps', 0.0):.2f}",
                f"{cam.get('ai_fps', 0.0):.2f}",
                f"{cam.get('frame_age_ms', 0.0):.1f}" if cam.get("frame_age_ms") is not None else "",
                cam.get("decoder_name", ""),
                cam.get("reconnect_count", 0),
                f"{proc_cpu:.1f}",
                f"{host_cpu:.1f}",
                f"{rss:.1f}",
                f"{gpu_util}",
                f"{gpu_dec}",
                f"{vram:.1f}",
            ])
        self.file.flush()

    def close(self) -> None:
        try:
            self.file.close()
        except Exception:
            pass


class BenchmarkAccumulator:
    """Accumulates warmup and steady-state measurement samples separately."""

    def __init__(self, warmup_seconds: float = 10.0, benchmark_config: BenchmarkConfig | None = None,
                 expected_streams: int | None = None, profile: int | None = None) -> None:
        self.started = monotonic()
        self.warmup_seconds = max(0.0, warmup_seconds)
        self.config = benchmark_config or BenchmarkConfig()
        self.expected_streams = expected_streams
        self.profile = profile

        self.samples = 0
        self.warmup_samples_count = 0
        self.measurement_samples_count = 0

        self.sums = {name: 0.0 for name in (
            "cpu", "host_cpu", "rss", "host_ram", "gpu", "gpu_decode", "gpu_vram", "network", "physical_fps",
            "logical_fps", "preview_fps", "preview_encode_ms")}
        self.peaks = {name: 0.0 for name in ("cpu", "rss", "frame_age_ms")}
        self.available = {"gpu": 0, "gpu_decode": 0, "gpu_vram": 0}

        self.frame_age_samples = deque(maxlen=2000)
        self.rss_history = []

        self.first_rss: float | None = None
        self.rss_after_warmup: float | None = None
        self.last_rss: float | None = None
        self.last_online = 0
        self.peak_online = 0
        self.all_streams_ready_time_ms: float | None = None

    def add(self, report: dict[str, Any], resources: dict[str, Any]) -> None:
        self.samples += 1
        now_mono = monotonic()
        elapsed = now_mono - self.started
        in_warmup = elapsed < self.warmup_seconds

        current_rss = resources.get("rss_mib", 0.0)
        if self.first_rss is None:
            self.first_rss = current_rss
        self.last_rss = current_rss
        self.last_online = report.get("physical_online_streams", 0)
        self.peak_online = max(self.peak_online, self.last_online)

        if in_warmup:
            self.warmup_samples_count += 1
            return

        if self.rss_after_warmup is None:
            self.rss_after_warmup = current_rss

        self.measurement_samples_count += 1
        self.rss_history.append(current_rss)

        values = {
            "cpu": resources.get("process_cpu_percent", 0.0),
            "host_cpu": resources.get("host_cpu_percent", 0.0),
            "rss": current_rss,
            "host_ram": resources.get("host_ram_percent", 0.0),
            "network": resources.get("host_network_mib_s", 0.0),
            "physical_fps": report.get("total_input_fps_physical", 0.0),
            "logical_fps": report.get("total_input_fps_logical", 0.0),
            "preview_fps": report.get("preview_encode_fps", 0.0),
            "preview_encode_ms": report.get("average_preview_encode_ms", 0.0),
        }
        for name, value in values.items():
            self.sums[name] += value
            if name in self.peaks:
                self.peaks[name] = max(self.peaks[name], value)

        cameras = report.get("cameras", {})
        for cam in cameras.values():
            age = cam.get("frame_age_ms")
            if age is not None:
                self.frame_age_samples.append(age)
                self.peaks["frame_age_ms"] = max(self.peaks["frame_age_ms"], age)

        gpus = resources.get("gpus", [])
        for gpu in gpus:
            self.sums["gpu_vram"] += gpu.get("used_mib", 0.0)
            self.available["gpu_vram"] += 1
            self.sums["gpu"] += gpu.get("utilization_percent", 0.0)
            self.available["gpu"] += 1
            if gpu.get("decoder_percent") is not None:
                self.sums["gpu_decode"] += gpu["decoder_percent"]
                self.available["gpu_decode"] += 1

    def _check_memory_leak(self, growth_mib: float) -> bool:
        """Memory leak suspected only if RSS trends upward continuously across measurement windows and does not plateau."""
        if len(self.rss_history) < 6 or growth_mib <= self.config.max_rss_growth_mib:
            return False
        # Split measurement history into 3 equal segments
        n = len(self.rss_history)
        chunk = n // 3
        c1 = sum(self.rss_history[:chunk]) / chunk
        c2 = sum(self.rss_history[chunk:2 * chunk]) / chunk
        c3 = sum(self.rss_history[2 * chunk:]) / (n - 2 * chunk)
        # Strict continuous upward trend without plateau
        return (c1 < c2 < c3) and ((c3 - c1) > (self.config.max_rss_growth_mib * 0.8))

    def finish(self, mode: str, status: dict[str, Any], *, status_label: str = "success",
               failure_type: str | None = None, failure_reason: str | None = None) -> dict[str, Any]:
        count = max(self.measurement_samples_count, 1)
        avg = lambda name: self.sums[name] / count
        available_avg = lambda name: self.sums[name] / self.available[name] if self.available[name] else None

        duration_total = monotonic() - self.started
        measurement_duration = max(0.0, duration_total - self.warmup_seconds)

        # Frame age percentiles
        from .metrics import compute_percentiles
        age_stats = compute_percentiles(self.frame_age_samples)

        rss_start = self.first_rss or 0.0
        rss_warmup = self.rss_after_warmup if self.rss_after_warmup is not None else rss_start
        rss_end = self.last_rss or 0.0
        rss_growth_meas = max(0.0, rss_end - rss_warmup)
        leak_suspected = self._check_memory_leak(rss_growth_meas)

        # Expected & Online streams
        configured_streams = status.get("total_streams", 0)
        expected_streams = self.expected_streams or configured_streams
        online_streams = status.get("online_streams", 0)
        reconnect_total = status.get("reconnect_total", 0)

        # Pass / Fail criteria evaluation per Stage R
        failure_reasons = []
        if status_label == "failed":
            failure_reasons.append(failure_reason or "Runtime failure")
        else:
            if self.config.require_all_streams_online and online_streams < expected_streams:
                failure_reasons.append(f"{expected_streams - online_streams} expected stream(s) offline ({online_streams}/{expected_streams} online)")
            max_reconnects_allowed = self.config.max_reconnects_per_camera * max(1, expected_streams)
            if reconnect_total > max_reconnects_allowed:
                failure_reasons.append(f"reconnect count ({reconnect_total}) exceeded maximum allowed ({max_reconnects_allowed})")
            p99_age = age_stats.get("p99")
            if p99_age is not None and p99_age > self.config.max_frame_age_p99_ms:
                failure_reasons.append(f"frame age p99 ({p99_age:.1f}ms) exceeded threshold ({self.config.max_frame_age_p99_ms}ms)")
            if self.measurement_samples_count == 0:
                failure_reasons.append("no samples collected during measurement window")
            proc_cpu = avg("cpu")
            if proc_cpu > self.config.max_process_cpu_percent:
                failure_reasons.append(f"process CPU avg ({proc_cpu:.1f}%) exceeded threshold ({self.config.max_process_cpu_percent}%)")
            host_cpu = avg("host_cpu")
            if host_cpu > self.config.max_host_cpu_percent:
                failure_reasons.append(f"host CPU avg ({host_cpu:.1f}%) exceeded threshold ({self.config.max_host_cpu_percent}%)")
            gpu_dec = available_avg("gpu_decode")
            if gpu_dec is not None and gpu_dec > self.config.max_gpu_decode_percent:
                failure_reasons.append(f"GPU decode ({gpu_dec:.1f}%) exceeded threshold ({self.config.max_gpu_decode_percent}%)")
            if rss_growth_meas > self.config.max_rss_growth_mib:
                failure_reasons.append(f"measurement RSS growth ({rss_growth_meas:.1f} MiB) exceeded threshold ({self.config.max_rss_growth_mib} MiB)")
            if leak_suspected:
                failure_reasons.append("memory leak suspected: continuous RSS growth across all measurement windows")

        benchmark_pass = (len(failure_reasons) == 0) and (status_label == "success")

        res: dict[str, Any] = {
            "status": status_label,
            "benchmark_pass": benchmark_pass,
            "failure_reasons": failure_reasons,
            "mode": mode,
            "profile": self.profile or configured_streams,
            "configured_streams": configured_streams,
            "expected_streams": expected_streams,
            "online_streams": online_streams,
            "healthy_streams": status.get("healthy_streams", 0),
            "degraded_streams": status.get("degraded_streams", 0),
            "stale_streams": status.get("stale_streams", 0),
            "offline_streams": status.get("offline_streams", 0),
            "reconnecting_streams": status.get("reconnecting_streams", 0),
            "duration_seconds": duration_total,
            "warmup_seconds": self.warmup_seconds,
            "measurement_seconds": measurement_duration,
            "samples_collected": self.measurement_samples_count,
            "aggregate_input_fps": avg("physical_fps"),
            "aggregate_decode_fps": avg("physical_fps"),
            "process_cpu_avg_percent": avg("cpu"),
            "process_cpu_peak_percent": self.peaks["cpu"],
            "rss_avg_mib": avg("rss"),
            "rss_peak_mib": self.peaks["rss"],
            "rss_start_mib": rss_start,
            "rss_after_warmup_mib": rss_warmup,
            "rss_end_mib": rss_end,
            "rss_growth_measurement_mib": rss_growth_meas,
            "memory_leak_suspected": leak_suspected,
            "host_network_avg_mib_s": avg("network"),
            "host_ram_avg_percent": avg("host_ram"),
            "gpu_util_avg_percent": available_avg("gpu"),
            "gpu_decode_avg_percent": available_avg("gpu_decode"),
            "vram_avg_mib": available_avg("gpu_vram"),
            "frame_age_avg_ms": age_stats.get("avg"),
            "frame_age_p50_ms": age_stats.get("p50"),
            "frame_age_p95_ms": age_stats.get("p95"),
            "frame_age_p99_ms": age_stats.get("p99"),
            "frame_age_max_ms": age_stats.get("max") or self.peaks["frame_age_ms"],
            "reconnect_total": reconnect_total,
            "all_streams_ready_time_ms": self.all_streams_ready_time_ms,
            "preview_encode_fps": avg("preview_fps"),
            "preview_encode_count": status.get("preview_encode_count", 0),
            "preview_encode_avg_ms": avg("preview_encode_ms"),
            "frames_replaced_before_preview": status.get("frames_replaced_before_preview_physical", 0),
        }

        # Add AI batch metrics if present
        for ai_key in ("batch_size_avg", "batch_size_p95", "batch_wait_avg_ms", "batch_wait_p95_ms",
                       "preprocess_avg_ms", "inference_avg_ms", "postprocess_avg_ms",
                       "result_latency_p50_ms", "result_latency_p95_ms", "result_latency_p99_ms"):
            if ai_key in status:
                res[ai_key] = status[ai_key]

        if status_label == "failed":
            res["failure_type"] = failure_type or "RuntimeError"
            res["failure_reason"] = failure_reason or "Unknown failure"
        return res


def format_summary(summary: dict[str, Any]) -> str:
    def val(name: str, suffix: str = "") -> str:
        item = summary.get(name)
        return "N/A" if item is None else f"{item:.1f}{suffix}"

    status_str = "PASS" if summary.get("benchmark_pass") else "FAIL"
    reasons = summary.get("failure_reasons", [])
    reasons_str = f" | Reasons: {', '.join(reasons)}" if reasons else ""

    lines = [
        "=" * 88,
        f"AIVISRA StreamCore Benchmark Summary — {status_str}{reasons_str}",
        f"Mode: {summary['mode']} | Profile: {summary.get('profile', 'N/A')}",
        f"Duration: {summary['duration_seconds']:.0f}s (Warmup: {summary['warmup_seconds']:.0f}s, Measurement: {summary['measurement_seconds']:.0f}s, Samples: {summary['samples_collected']})",
        f"Streams: {summary['online_streams']}/{summary['configured_streams']} online | Healthy: {summary.get('healthy_streams', 0)} | Degraded: {summary.get('degraded_streams', 0)} | Offline: {summary.get('offline_streams', 0)} | Reconnects: {summary.get('reconnect_total', 0)}",
        f"Aggregate Input/Decode FPS: {val('aggregate_input_fps')}",
        f"Process CPU: avg {val('process_cpu_avg_percent', '%')} | peak {val('process_cpu_peak_percent', '%')}",
        f"Process RSS: avg {val('rss_avg_mib', ' MiB')} | peak {val('rss_peak_mib', ' MiB')} | growth {val('rss_growth_measurement_mib', ' MiB')} (Leak suspected: {summary.get('memory_leak_suspected', False)})",
        f"GPU: {val('gpu_util_avg_percent', '%')} | NVDEC: {val('gpu_decode_avg_percent', '%')} | VRAM: {val('vram_avg_mib', ' MiB')}",
        f"Frame Age: avg {val('frame_age_avg_ms', 'ms')} | p50 {val('frame_age_p50_ms', 'ms')} | p95 {val('frame_age_p95_ms', 'ms')} | p99 {val('frame_age_p99_ms', 'ms')} | max {val('frame_age_max_ms', 'ms')}",
    ]
    if summary.get("all_streams_ready_time_ms") is not None:
        lines.append(f"All streams ready time: {summary['all_streams_ready_time_ms']:.0f} ms")
    lines.append("=" * 88)
    return "\n".join(lines)


def format_failure_summary(reason: str, duration: float, samples: int = 0) -> str:
    return "\n".join([
        "=" * 88,
        "AIVISRA StreamCore Benchmark FAILED",
        f"Reason: {reason}",
        f"Duration before failure: {duration:.3f} sec",
        f"Samples collected: {samples}",
        "=" * 88,
    ])
