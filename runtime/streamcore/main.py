import argparse
import json
import logging
import math
import os
import signal
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

# Ensure user site packages (~/.local/lib/python3.12/site-packages) are always discovered
user_site = Path.home() / f".local/lib/python3.{sys.version_info.minor}/site-packages"
if user_site.is_dir() and str(user_site) not in sys.path:
    sys.path.insert(0, str(user_site))

# Enable running directly as script (python3 main.py) or as module (python3 -m runtime.streamcore.main)
if __package__ is None or __package__ == "":
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    __package__ = "runtime.streamcore"

from .config import load_cameras, load_config, load_local_env
from .engine import StreamCore


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {"timestamp": record.created, "level": record.levelname,
                                   "logger": record.name, "event": record.getMessage()}
        for key in ("camera_id", "reason", "retry_seconds", "report", "resources", "exception_type", "traceback"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["traceback"] = self.formatException(record.exc_info)
            if "exception_type" not in payload and record.exc_info[0]:
                payload["exception_type"] = record.exc_info[0].__name__
            if "reason" not in payload and record.exc_info[1]:
                payload["reason"] = str(record.exc_info[1])
        return json.dumps(payload)


def main() -> int:
    from time import monotonic
    root = Path(__file__).resolve().parents[3]
    local_config = Path(__file__).resolve().parent / "app.yaml"
    default_config = local_config if local_config.is_file() else root / "config/streamcore/app.yaml"
    local_env = Path(__file__).resolve().parent / ".env.local"
    default_env = local_env if local_env.is_file() else root / "config/streamcore/.env.local"
    parser = argparse.ArgumentParser(description="AIVISRA isolated multi-stream detection benchmark")
    parser.add_argument("--config", type=Path, default=default_config,
                        help="One-file runtime and camera configuration")
    parser.add_argument("--runtime-config", type=Path, help="Optional legacy runtime-only override")
    parser.add_argument("--cameras", type=Path, help="Optional legacy camera-only override")
    parser.add_argument("--env-file", type=Path, default=default_env,
                        help="Optional local camera URL file")
    parser.add_argument("--duration", type=float, help="Stop after N benchmark seconds")
    parser.add_argument("--mode", choices=("production", "ingest_only", "decoded_frame", "preview", "demo"),
                        help="Override runtime.mode for a benchmark stage")
    parser.add_argument("--demo", action="store_true",
                        help="Launch interactive GPU-native AI demonstration on preview port (default: 8765)")
    parser.add_argument("--frame-path", choices=("gpu", "cpu"), default=None,
                        help="Frame pipeline path: gpu (GPU-native zero CPU transfer) or cpu (legacy CPU transfer)")
    parser.add_argument("--summary-json", type=Path, help="Write a JSON benchmark summary")
    parser.add_argument("--metrics-csv", type=Path, help="Write per-interval metrics CSV")
    parser.add_argument("--preview-port", type=int, help="Serve diagnostic JPEGs at 127.0.0.1:PORT when enabled")
    parser.add_argument("--preview-fps", type=float, default=5.0,
                        help="Target FPS for preview server (default: 5)")
    parser.add_argument("--share-identical-sources", action="store_true",
                        help="One reader for identical URI/codec/decoder entries; fan out frames to all IDs")
    parser.add_argument("--profile", type=int,
                        help="Select first N enabled cameras for profile validation (e.g. 5, 15, 25, 30, 50)")
    parser.add_argument("--detector", choices=("none", "dummy", "ultralytics"),
                        help="Override inference detector (e.g. dummy, ultralytics)")
    parser.add_argument("--verbose-cameras", action="store_true",
                        help="Print detailed per-camera console metrics every interval")
    parser.add_argument("--validate-pipeline", nargs="?", const="first",
                        help="Validate one camera pipeline programmatically, e.g. CAM001")
    parser.add_argument("--validate-all-pipelines", action="store_true",
                        help="Validate all camera pipelines programmatically per Stage A")
    parser.add_argument("--tracks-json", type=Path,
                        help="Export detection and tracking results to JSON or JSONL file")
    args = parser.parse_args()
    if args.duration is not None and (not math.isfinite(args.duration) or args.duration <= 0):
        parser.error("--duration must be positive and finite")
    if args.preview_port is not None and not 1 <= args.preview_port <= 65535:
        parser.error("--preview-port must be between 1 and 65535")
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    logger = logging.getLogger(__name__)
    try:
        runtime_path = args.runtime_config or args.config
        cameras_path = args.cameras or args.config
        config = load_config(runtime_path)
        if args.mode is not None:
            config = replace(config, runtime=replace(config.runtime, mode=args.mode))
        if args.demo or args.mode == "demo":
            config = replace(config, runtime=replace(config.runtime, mode="demo"))
            config = replace(config, diagnostic_preview=replace(config.diagnostic_preview, enabled=True, fps=args.preview_fps, width=640, height=360))
            config = replace(config, ai=replace(config.ai, enabled=True))
            if config.inference.detector == "none":
                config = replace(config, inference=replace(config.inference, detector="ultralytics"))
        if args.mode == "preview":
            config = replace(config, diagnostic_preview=replace(config.diagnostic_preview, enabled=True))
        if args.frame_path is not None:
            gpu_native = (args.frame_path == "gpu")
            config = replace(config, inference=replace(config.inference, frame_path=args.frame_path, gpu_native=gpu_native))
        if args.detector is not None:
            config = replace(config, inference=replace(config.inference, detector=args.detector))
            if args.detector != "none":
                config = replace(config, ai=replace(config.ai, enabled=True))
        if args.preview_port is not None:
            target_fps = max(config.preview.fps, args.preview_fps)
            config = replace(config, diagnostic_preview=replace(config.diagnostic_preview, enabled=True, fps=target_fps, width=640, height=360))
        for candidate in (root / ".env", Path(".env")):
            if candidate.is_file():
                load_local_env(candidate)
        load_local_env(args.env_file)
        cameras = load_cameras(cameras_path)

        if args.profile is not None:
            enabled_cams = [c for c in cameras if c.enabled]
            if len(enabled_cams) < args.profile:
                print(f"Expected physical streams: {args.profile}")
                print(f"Reachable: {len(enabled_cams)}")
                print(f"Benchmark not valid for {args.profile}-stream capacity testing.")
                return 1
            cameras = enabled_cams[:args.profile]

    except (ValueError, OSError, TypeError, AttributeError) as exc:
        logger.exception("configuration_error", extra={"reason": str(exc), "exception_type": type(exc).__name__})
        return 2
    except Exception as exc:
        logger.exception("configuration_parse_error", extra={"reason": str(exc), "exception_type": type(exc).__name__})
        return 2

    if args.validate_all_pipelines:
        from .ingest.gstreamer_reader import load_gstreamer, validate_all_pipelines
        gst = load_gstreamer()
        results = validate_all_pipelines(cameras, config.streams, gst, timeout_seconds=12.0, mode=config.runtime.mode)
        all_ok = all(r.get("ok", False) for r in results)
        return 0 if all_ok else 1

    if args.validate_pipeline:
        from .ingest.gstreamer_reader import load_gstreamer, validate_single_source_pipeline
        target_cam_id = args.validate_pipeline if args.validate_pipeline != "first" else cameras[0].id
        cam = next((c for c in cameras if c.id == target_cam_id), None)
        if cam is None:
            logger.error("validate_pipeline_failed", extra={"reason": f"Camera {target_cam_id} not found"})
            return 1
        gst = load_gstreamer()
        ok, error_msg = validate_single_source_pipeline(cam, config.streams, gst, mode=config.runtime.mode)
        if ok:
            print(f"Pipeline validation PASSED for {cam.id} ({cam.codec}/{cam.decoder})")
            return 0
        else:
            print(f"Pipeline validation FAILED for {cam.id}: {error_msg}")
            return 1

    engine = StreamCore(
        config, cameras,
        share_identical_sources=args.share_identical_sources,
        metrics_csv=args.metrics_csv,
        verbose_cameras=args.verbose_cameras,
        expected_streams=args.profile or len(cameras),
        profile=args.profile,
        tracks_json=args.tracks_json,
    )
    preview = None
    previous = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        previous[sig] = signal.signal(sig, lambda _signal, _frame: engine.stop())
    try:
        if config.preview.enabled and config.runtime.mode not in ("ingest_only", "decoded_frame"):
            from .preview.preview_server import start_preview
            port = args.preview_port or 8765
            preview = start_preview(engine, engine.preview_cache, port)
            logger.info("diagnostic_preview_ready", extra={"reason": f"http://127.0.0.1:{port}"})
        logger.info("runtime_starting", extra={"reason": config.runtime.mode})
        engine.run(args.duration)
        if args.summary_json is not None:
            args.summary_json.parent.mkdir(parents=True, exist_ok=True)
            if engine.summary is not None:
                args.summary_json.write_text(json.dumps(engine.summary, indent=2) + "\n")
        if engine.summary is not None and not engine.summary.get("benchmark_pass", False):
            return 1
        return 0
    except Exception as exc:
        logger.exception("runtime_failed", extra={"reason": str(exc), "exception_type": type(exc).__name__})
        if args.summary_json is not None:
            args.summary_json.parent.mkdir(parents=True, exist_ok=True)
            failed_summary = {
                "status": "failed",
                "benchmark_pass": False,
                "failure_reasons": [str(exc)],
                "mode": config.runtime.mode,
                "duration_seconds": monotonic() - engine.benchmark.started,
                "samples": engine.benchmark.samples,
                "failure_type": type(exc).__name__,
                "failure_reason": str(exc),
            }
            args.summary_json.write_text(json.dumps(failed_summary, indent=2) + "\n")
        return 1
    finally:
        if preview is not None:
            preview.shutdown()
            preview.server_close()
        for sig, callback in previous.items():
            signal.signal(sig, callback)


if __name__ == "__main__":
    raise SystemExit(main())
