"""Compare saved StreamCore benchmark summaries (profiles or modes); run from the repository root."""

import argparse
import json
from pathlib import Path


def display(value: float | None, unit: str = "", precision: int = 1) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{precision}f}{unit}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare StreamCore benchmark summaries")
    parser.add_argument("summaries", nargs="+", type=Path, help="Paths to --summary-json files")
    args = parser.parse_args()
    rows = [json.loads(path.read_text()) for path in args.summaries]

    print("Streams | Online | FPS    | CPU  | RSS   | GPU Decode | VRAM   | p95 Age | p99 Age | Reconnects | Pass")
    print("-" * 105)
    for item in sorted(rows, key=lambda r: (r.get("profile", r.get("configured_streams", 0)), r.get("mode", ""))):
        streams = str(item.get("profile") or item.get("configured_streams", item.get("physical_sources", "N/A")))
        online = str(item.get("online_streams", item.get("physical_online_at_last_sample", "N/A")))
        fps = display(item.get("aggregate_input_fps", item.get("average_physical_input_fps")))
        cpu = display(item.get("process_cpu_avg_percent", item.get("cpu_avg_percent")), "%", precision=0)
        rss = display(item.get("rss_avg_mib"), "M", precision=0)
        gpu_dec = display(item.get("gpu_decode_avg_percent"), "%", precision=0)
        vram_mb = item.get("gpu_vram_avg_mib")
        vram = f"{vram_mb / 1024:.1f}G" if vram_mb is not None else "N/A"
        p95 = display(item.get("frame_age_p95_ms"), "ms", precision=0)
        p99 = display(item.get("frame_age_p99_ms"), "ms", precision=0)
        reconnects = str(item.get("reconnect_total", item.get("reconnect_count", 0)))
        pass_val = item.get("benchmark_pass")
        pass_str = "PASS" if pass_val is True else ("FAIL" if pass_val is False else item.get("status", "N/A").upper())

        print(
            f"{streams:<7} | {online:<6} | {fps:<6} | {cpu:<4} | {rss:<5} | "
            f"{gpu_dec:<10} | {vram:<6} | {p95:<7} | {p99:<7} | {reconnects:<10} | {pass_str}"
        )
    print("-" * 105)


if __name__ == "__main__":
    main()
