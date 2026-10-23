"""Generate Stage W hardware capacity report from tested benchmark summaries."""

import json
import os
from pathlib import Path
from typing import Any


def get_cpu_model() -> str:
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if "model name" in line:
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return "Unknown CPU"


def get_hardware_info() -> dict[str, Any]:
    import psutil
    info: dict[str, Any] = {
        "cpu_model": get_cpu_model(),
        "cpu_cores": os.cpu_count() or 1,
        "ram_gib": round(psutil.virtual_memory().total / (1024 ** 3), 1),
        "gpu_name": "N/A",
        "driver_version": "N/A",
    }
    try:
        import pynvml
        pynvml.nvmlInit()
        info["driver_version"] = pynvml.nvmlSystemGetDriverVersion()
        if pynvml.nvmlDeviceGetCount() > 0:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode("utf-8", errors="ignore")
            info["gpu_name"] = str(name)
        pynvml.nvmlShutdown()
    except Exception:
        pass
    return info


def generate_capacity_report(results_dir: str | Path = "results", output_file: str | Path = "results/streamcore-capacity-report.json") -> dict[str, Any]:
    results_path = Path(results_dir)
    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    hw = get_hardware_info()
    ladder_levels = [5, 15, 25, 30, 50]
    tests: dict[str, Any] = {}
    highest_stable = 0

    for level in ladder_levels:
        summary_file = results_path / f"ingest-{level}.json"
        if summary_file.is_file():
            try:
                data = json.loads(summary_file.read_text())
                tests[str(level)] = {
                    "expected_streams": data.get("expected_streams", level),
                    "online_streams": data.get("online_streams", 0),
                    "aggregate_input_fps": data.get("aggregate_input_fps"),
                    "aggregate_decode_fps": data.get("aggregate_decode_fps"),
                    "cpu_avg": data.get("process_cpu_avg_percent"),
                    "cpu_peak": data.get("process_cpu_peak_percent"),
                    "rss_avg": data.get("rss_avg_mib"),
                    "rss_growth": data.get("rss_growth_measurement_mib"),
                    "gpu_util": data.get("gpu_util_avg_percent"),
                    "gpu_decode": data.get("gpu_decode_avg_percent"),
                    "vram": data.get("vram_avg_mib"),
                    "frame_age_p50": data.get("frame_age_p50_ms"),
                    "frame_age_p95": data.get("frame_age_p95_ms"),
                    "frame_age_p99": data.get("frame_age_p99_ms"),
                    "frame_age_max": data.get("frame_age_max_ms"),
                    "reconnects": data.get("reconnect_total", 0),
                    "startup_time": data.get("all_streams_ready_time_ms"),
                    "benchmark_pass": data.get("benchmark_pass", False),
                }
                if data.get("benchmark_pass", False) and data.get("online_streams", 0) >= level:
                    highest_stable = max(highest_stable, level)
            except Exception as e:
                tests[str(level)] = {"status": f"error reading {summary_file}: {e}"}
        else:
            tests[str(level)] = "NOT TESTED — insufficient independent physical RTSP endpoints"

    report = {
        "hardware": hw,
        "tests": tests,
        "highest_physically_proven_stable_stream_count": highest_stable,
    }
    out_path.write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    rep = generate_capacity_report()
    print(json.dumps(rep, indent=2))
