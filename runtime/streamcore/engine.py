import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Lock, Thread
from time import monotonic
from typing import Any, Callable

from .benchmark import BenchmarkAccumulator, MetricsCsvWriter, format_failure_summary, format_summary
from .config import CameraConfig, Config
from .frame_store import LatestFrameStore
from .inference.base import Detector
from .metrics import MetricsRegistry, ResourceMonitor, format_report
from .scheduling.frame_scheduler import LatestFrameScheduler
from .types import CameraFrame, CameraState, DetectionResult, GpuFrame
from .gpu_frame import GpuPreprocessor
from .preview.preview_cache import PreviewCache
from .preview.preview_worker import PreviewWorker
from .events import EventDatabase, VisualSearchManager
from .events.clip_recorder import ClipRecorder

logger = logging.getLogger(__name__)


class StreamCore:
    def __init__(self, config: Config, cameras: list[CameraConfig],
                 detector: Detector | None = None,
                 on_results: Callable[[list[DetectionResult]], None] | None = None,
                 share_identical_sources: bool = False,
                 metrics_csv: str | Path | None = None,
                 verbose_cameras: bool = False,
                 expected_streams: int | None = None,
                 profile: int | None = None,
                 tracks_json: str | Path | None = None) -> None:
        self.config = config
        self.share_identical_sources = share_identical_sources
        self.cameras = cameras
        self.verbose_cameras = verbose_cameras
        self.store = LatestFrameStore([c.id for c in cameras])
        stale_ms = getattr(config.health, "stale_after_ms", 2000.0) if hasattr(config, "health") else 2000.0
        deg_ratio = getattr(config.health, "degraded_fps_ratio", 0.7) if hasattr(config, "health") else 0.7
        self.metrics = MetricsRegistry(
            [c.id for c in cameras], config.ai.target_fps,
            stale_after_ms=stale_ms, degraded_fps_ratio=deg_ratio
        )
        for c in cameras:
            if c.expected_fps is not None:
                self.metrics.configure_expected_fps(c.id, c.expected_fps)

        self.source_groups: dict[str, list[str]] = {}
        keys: dict[tuple[str, str, str], str] = {}
        source_for: dict[str, str] = {}
        for camera in cameras:
            key = (camera.uri, camera.codec, camera.decoder)
            source = (keys.setdefault(key, camera.id)
                      if share_identical_sources else camera.id)
            source_for[camera.id] = source
            self.source_groups.setdefault(source, []).append(camera.id)
        self.metrics.configure_sources(source_for)
        self.preview_cache = PreviewCache([c.id for c in cameras])
        self._resources_lock = Lock()
        self._last_resources: dict = {}

        warmup = getattr(config.benchmark, "warmup_seconds", 10.0) if hasattr(config, "benchmark") else 10.0
        bench_cfg = getattr(config, "benchmark", None)
        self.benchmark = BenchmarkAccumulator(
            warmup_seconds=warmup,
            benchmark_config=bench_cfg,
            expected_streams=expected_streams or len(cameras),
            profile=profile,
        )
        self.csv_writer = MetricsCsvWriter(metrics_csv) if metrics_csv else None
        self._readers_started_at: float | None = None

        self.summary: dict | None = None
        self._status_at_stop: dict | None = None
        self.stop_event = Event()
        self.detector = detector if detector is not None else self._detector()
        self.on_results = on_results  # Synchronous; consumers must be fast and bounded.
        target_fps_map = {c.id: (c.target_ai_fps if c.target_ai_fps is not None else config.ai.target_fps) for c in cameras}
        target_fps_map["default"] = config.ai.target_fps
        self.scheduler = LatestFrameScheduler(
            [c.id for c in cameras], target_fps_map,
            config.runtime.max_frame_age_seconds,
        )
        self._results: dict[str, DetectionResult] = {}
        self._results_lock = Lock()
        max_batch = getattr(config.inference, "max_batch_size", 8)
        imgsz = getattr(config.inference, "imgsz", 640)
        self._gpu_preprocessor = GpuPreprocessor(max_batch_size=max_batch, imgsz=imgsz)
        target_fps = float(getattr(config.ai, "target_fps", 8.0))
        poll_ms = getattr(config.ai, "poll_interval_ms", None)
        if poll_ms is not None and poll_ms > 0:
            self._ai_interval = max(0.001, float(poll_ms) / 1000.0)
        else:
            self._ai_interval = min(0.05, 1.0 / target_fps if target_fps > 0 else 0.05)
        if getattr(config, "tracking", None) and config.tracking.enabled:
            from ..tracking.tracker_manager import TrackerManager
            self.tracker_manager: TrackerManager | None = TrackerManager(config.tracking)
        else:
            self.tracker_manager = None

        tracks_output = tracks_json
        if tracks_output is None and getattr(config, "tracking", None) is not None:
            if getattr(config.tracking, "export_json", False) and getattr(config.tracking, "output_path", ""):
                tracks_output = config.tracking.output_path

        if tracks_output:
            from ..tracking.track_exporter import TracksJsonWriter
            self.tracks_writer: TracksJsonWriter | None = TracksJsonWriter(tracks_output)
        else:
            self.tracks_writer = None
        if config.live_view.enabled:
            from .live.live_service import LiveService
            self.live_service: LiveService | None = LiveService(config.live_view, cameras)
        else:
            self.live_service = None

        self._camera_capabilities: dict[str, set[str]] = {}
        self._active_readers: list[Any] = []
        try:
            from ..onboarding import OnboardingService
            self.onboarding_service: Any = OnboardingService(engine=self, detector=self.detector)
        except Exception as exc:
            logger.warning("onboarding_service_init_deferred", extra={"reason": str(exc)})
            self.onboarding_service = None

        try:
            from ..intelligence import SpatialManager
            self.spatial_manager: Any = SpatialManager()
        except Exception as exc:
            logger.warning("spatial_manager_init_deferred", extra={"reason": str(exc)})
            self.spatial_manager = None

        if getattr(self.config, "events", None) and self.config.events.enabled:
            self.event_db = EventDatabase(self.config.events)
            camera_urls = {c.id: c.uri for c in self.cameras}
            camera_live_paths = {c.id: getattr(c, "live_path", c.id.lower()) for c in self.cameras}
            self.clip_recorder = ClipRecorder(self.config.events, camera_urls, camera_live_paths=camera_live_paths)
            base_dir = Path(self.config.events.clip_storage_dir).parent
            self.visual_search_manager = VisualSearchManager(
                base_dir=base_dir,
                event_db=self.event_db,
                settings=self.config.events,
            )
        else:
            self.event_db = None
            self.clip_recorder = None
            self.visual_search_manager = None

    def register_camera(
        self,
        camera_id: str,
        uri: str,
        codec: str = "h264",
        decoder: str = "auto",
        live_path: str | None = None,
    ) -> Any:
        from dataclasses import replace
        from urllib.parse import urlsplit
        from .config import CameraConfig
        from .ingest.decoder_selector import select_decoder
        from .ingest.gstreamer_reader import GStreamerReader, load_gstreamer

        with self._resources_lock:
            if any(c.id == camera_id for c in self.cameras):
                raise ValueError(f"Camera '{camera_id}' already registered")

            new_cam = CameraConfig(
                id=camera_id,
                uri=uri,
                codec=codec,
                decoder=decoder,
                enabled=True,
                live_path=live_path or camera_id.lower(),
            )
            self.cameras.append(new_cam)
            self.source_groups[camera_id] = [camera_id]

            if hasattr(self.store, "register_camera"):
                self.store.register_camera(camera_id)
            if hasattr(self.preview_cache, "register_camera"):
                self.preview_cache.register_camera(camera_id)
            if hasattr(self.metrics, "register_camera"):
                self.metrics.register_camera(camera_id)
            if hasattr(self.scheduler, "register_camera"):
                self.scheduler.register_camera(camera_id, self.config.ai.target_fps)
            if getattr(self, "clip_recorder", None) is not None:
                self.clip_recorder.camera_urls[camera_id] = uri
                self.clip_recorder.camera_live_paths[camera_id] = live_path or camera_id.lower()

            # If engine is actively running and readers started, start reader for the newly added camera
            if hasattr(self, "_active_readers") and not self.stop_event.is_set() and self._readers_started_at is not None:
                gst = load_gstreamer()
                try:
                    scheme = urlsplit(uri).scheme
                    if scheme in ("rtsp", "rtsps"):
                        sel = select_decoder(
                            gst[0], codec, decoder,
                            prefer_hardware=self.config.decode.prefer_hardware,
                            fallback_software=self.config.decode.fallback_software,
                            camera_id=camera_id,
                        )
                        new_cam = replace(new_cam, decoder=sel.name)
                        self.metrics.configure_decoder(camera_id, sel.name, sel.decoder_type)
                    self.metrics.configure_camera(camera_id, codec)
                    gpu_native_enabled = getattr(self.config.inference, "gpu_native", True)
                    reader = GStreamerReader(
                        new_cam, self.config.streams, self.store, self.metrics, self.stop_event, gst,
                        alias_ids=(), mode=self.config.runtime.mode, gpu_native=gpu_native_enabled,
                        target_fps=self.config.ai.target_fps,
                    )
                    reader.start()
                    self._active_readers.append(reader)
                except Exception as exc:
                    self.metrics.state(camera_id, CameraState.OFFLINE)
                    self.metrics.record_error(camera_id, str(exc))
                    logger.error("dynamic_camera_reader_failed", extra={"camera_id": camera_id, "reason": str(exc)})

            return new_cam

    def set_camera_capabilities(self, camera_id: str, capabilities: set[str]) -> None:
        with self._results_lock:
            self._camera_capabilities[camera_id] = set(capabilities)

    def _detector(self) -> Detector | None:
        from .inference.registry import create_detector
        return create_detector(self.config.inference)

    def latest_results(self) -> dict[str, DetectionResult]:
        with self._results_lock:
            return dict(self._results)

    def latest_tracks(self, camera_id: str) -> list[Any]:
        if self.tracker_manager is not None:
            return self.tracker_manager.get_tracks(camera_id)
        return []

    def tracking_metrics(self) -> dict[str, Any]:
        if self.tracker_manager is not None:
            return self.tracker_manager.snapshot_metrics()
        return {}

    def stop(self) -> None:
        if not self.stop_event.is_set():
            self._status_at_stop = self.metrics.view()
            self.stop_event.set()
            if getattr(self, "spatial_manager", None) is not None:
                try:
                    self.spatial_manager.close()
                except Exception:
                    pass

    def latest_resources(self) -> dict:
        with self._resources_lock:
            return dict(self._last_resources)

    def process_tick(self, *, respect_rate: bool = False) -> None:
        """Infer newest frames only; latency-aware dynamic batching and GPU preprocessing."""
        if self.detector is None:
            return
        camera_ids = [camera.id for camera in self.cameras]
        before = dict(self.scheduler.replaced_frames)
        selected = self.scheduler.select(self.store, camera_ids, respect_rate=respect_rate)

        size = self.config.inference.max_batch_size
        max_batch_wait_ms = getattr(self.config.inference, "max_batch_wait_ms", 15.0)
        max_wait_s = max(0.0, max_batch_wait_ms / 1000.0)

        # Latency-aware batch accumulation: if fewer than max_batch_size are ready,
        # wait bounded up to max_batch_wait_ms for additional streams before dispatching
        if 0 < len(selected) < size and max_wait_s > 0 and not self.stop_event.is_set():
            start_wait = monotonic()
            while len(selected) < size and (monotonic() - start_wait) < max_wait_s:
                remaining_cams = [cid for cid in camera_ids if cid not in [f.camera_id for f in selected]]
                if not remaining_cams:
                    break
                time_left = max_wait_s - (monotonic() - start_wait)
                if time_left <= 0:
                    break
                self.stop_event.wait(min(0.002, time_left))
                more = self.scheduler.select(self.store, remaining_cams, respect_rate=respect_rate)
                if more:
                    selected.extend(more)

        for camera_id, total in self.scheduler.replaced_frames.items():
            self.metrics.ai_replaced(camera_id, total - before[camera_id])

        for offset in range(0, len(selected), size):
            if self.stop_event.is_set():
                break
            batch = []
            for scheduled in selected[offset:offset + size]:
                newest = self.store.latest(scheduled.camera_id) or scheduled
                if newest.sequence > scheduled.sequence:
                    skipped = newest.sequence - scheduled.sequence - 1
                    self.metrics.ai_replaced(scheduled.camera_id, skipped)
                    self.scheduler.replaced_frames[scheduled.camera_id] += skipped
                    self.scheduler.last_sequence[scheduled.camera_id] = newest.sequence
                batch.append(newest)
            self._infer(batch)

    def _ai_loop(self) -> None:
        if self.detector is None:
            return
        try:
            self.detector.load()
            self.detector.warmup()
            while not self.stop_event.is_set():
                try:
                    self.process_tick(respect_rate=True)
                except Exception as exc:
                    # AI failures are isolated from ingest and MediaMTX live video.
                    logger.error("ai_tick_failed", extra={"reason": type(exc).__name__})
                self.stop_event.wait(self._ai_interval)
        except Exception as exc:
            logger.error("ai_start_failed", extra={"reason": type(exc).__name__})
        finally:
            try:
                self.detector.close()
            except Exception:
                logger.warning("ai_close_failed")

    def _infer(self, batch: list[Any]) -> None:
        if self.detector is None:
            raise RuntimeError("Inference is disabled")
        if not batch:
            return

        now_mono = monotonic()
        first_mono = getattr(batch[0], "received_monotonic", now_mono)
        avg_wait = max(0.0, (now_mono - first_mono) * 1000.0)

        is_gpu_batch = isinstance(batch[0], GpuFrame) and hasattr(self.detector, "infer_gpu")

        if is_gpu_batch:
            gpu_batch, prep_dur = self._gpu_preprocessor.preprocess(batch)
            prep_ms = prep_dur
            infer_start = monotonic()
            results = self.detector.infer_gpu(gpu_batch)
            infer_ms = (monotonic() - infer_start) * 1000.0
        else:
            prep_ms = 0.0
            infer_start = monotonic()
            results = self.detector.infer(batch)
            infer_ms = (monotonic() - infer_start) * 1000.0

        now_mono = monotonic()
        from dataclasses import replace
        updated_results = []
        for r in results:
            matching = next((f for f in batch if f.camera_id == r.camera_id), None)
            if matching is not None:
                tot_lat = max(0.0, (now_mono - matching.received_monotonic) * 1000.0)
                updated_results.append(replace(r, total_latency_ms=tot_lat))
            else:
                updated_results.append(r)
        results = updated_results

        expected = {(f.camera_id, f.sequence, f.timestamp) for f in batch}
        actual = {(r.camera_id, r.frame_sequence, r.timestamp) for r in results}
        if len(results) != len(batch) or expected != actual:
            raise RuntimeError("Detector returned mismatched frame identities")

        # Filter detections by per-camera active capabilities
        if hasattr(self, "onboarding_service") and self.onboarding_service is not None:
            filtered_results = []
            for r in results:
                active_caps = self.onboarding_service.capability_manager.get_active_capabilities(r.camera_id)
                if active_caps:
                    allowed = self.onboarding_service.capability_manager.get_allowed_classes(r.camera_id)
                    f_dets = tuple(d for d in r.detections if d.label.lower() in allowed)
                    filtered_results.append(replace(r, detections=f_dets))
                else:
                    filtered_results.append(r)
            results = filtered_results

        if self.tracker_manager is not None:
            tracked_results = []
            for r in results:
                do_track = True
                if hasattr(self, "onboarding_service") and self.onboarding_service is not None:
                    active_caps = self.onboarding_service.capability_manager.get_active_capabilities(r.camera_id)
                    if active_caps and not any("tracking" in c for c in active_caps):
                        do_track = False

                if do_track:
                    matching_frame = next((f for f in batch if f.camera_id == r.camera_id), None)
                    cpu_img = None
                    if matching_frame is not None and not hasattr(matching_frame, "to_bgr_cpu"):
                        cpu_img = getattr(matching_frame, "image", None)
                    tracked_results.append(self.tracker_manager.process_result(r, frame_image=cpu_img))
                else:
                    tracked_results.append(r)
            results = tracked_results

            if getattr(self, "spatial_manager", None) is not None:
                for r in results:
                    try:
                        tracks = self.tracker_manager.get_tracks(r.camera_id)
                        sw = r.source_width or 1280
                        sh = r.source_height or 720
                        ts_ns = int(r.timestamp * 1_000_000_000)
                        self.spatial_manager.process_tracks(
                            camera_id=r.camera_id,
                            tracks=tracks,
                            frame_sequence=r.frame_sequence,
                            source_width=sw,
                            source_height=sh,
                            timestamp_ns=ts_ns,
                        )
                    except Exception as exc:
                        logger.error("spatial_manager_processing_failed", extra={"camera_id": r.camera_id, "reason": str(exc)})

            # Track lifecycle events for person detection
            if self.event_db is not None and self.config.events.enabled:
                self._process_track_events(results, batch)

        self.metrics.batch(results, infer_ms, batch_wait_ms=avg_wait, preprocess_ms=prep_ms)
        with self._results_lock:
            self._results.update((r.camera_id, r) for r in results)
        if self.tracks_writer is not None:
            try:
                tracks_by_camera = {}
                if self.tracker_manager is not None:
                    for r in results:
                        tracks_by_camera[r.camera_id] = self.tracker_manager.get_tracks(r.camera_id)
                self.tracks_writer.write_results(results, tracks_by_camera=tracks_by_camera)
            except Exception as exc:
                logger.error("tracks_export_failed", extra={"reason": str(exc)})
        if self.on_results is not None:
            self.on_results(results)

    def _process_track_events(self, results: list[DetectionResult], batch: list[Any]) -> None:
        """Create/update track lifecycle events for all tracked COCO classes."""
        if self.tracker_manager is None or self.event_db is None:
            return

        from ..tracking.types import TrackState

        tracked_filter = self.config.events.tracked_classes or []

        for result in results:
            camera_id = result.camera_id

            try:
                tracker = self.tracker_manager.get_or_create_tracker(camera_id)
                tracks = tracker.get_tracks()

                for track in tracks:
                    class_id = int(getattr(track, "class_id", -1))
                    if tracked_filter and class_id not in tracked_filter:
                        continue

                    # Check if track is CONFIRMED and event not created yet
                    if track.state == TrackState.CONFIRMED and not getattr(track, "_event_created", False):
                        self._create_track_event(track, result, camera_id, batch)
                        track._event_created = True

                    # Check if track ended and event not closed yet
                    if track.state == TrackState.ENDED and not getattr(track, "_event_closed", False):
                        self._close_track_event(track, camera_id)
                        track._event_closed = True

            except Exception as exc:
                logger.error("track_event_processing_failed", extra={"camera_id": camera_id, "reason": str(exc)})

    def _create_track_event(self, track: Any, result: DetectionResult, camera_id: str, batch: list[Any]) -> None:
        """Create a new track lifecycle event, capture snapshot, and trigger clip recording."""
        event_id = f"evt-{uuid.uuid4().hex[:12]}"
        track._event_id = event_id
        ts = result.timestamp if (result.timestamp and result.timestamp > 1_000_000_000) else time.time()
        started_at = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Extract and save snapshot crop for visual search
        snapshot_rel_path = None
        if self.visual_search_manager is not None:
            try:
                matching_frame = next((f for f in batch if f.camera_id == camera_id), None)
                if matching_frame is None and hasattr(self, "store"):
                    if hasattr(self.store, "latest"):
                        matching_frame = self.store.latest(camera_id)
                    elif hasattr(self.store, "get_latest"):
                        matching_frame = self.store.get_latest(camera_id)
                if matching_frame is not None:
                    frame_bgr = matching_frame.image if hasattr(matching_frame, "image") else None
                    if frame_bgr is None and hasattr(matching_frame, "to_bgr_cpu"):
                        frame_bgr = matching_frame.to_bgr_cpu()
                    if frame_bgr is not None:
                        bbox = getattr(track, "bbox_xyxy", ())
                        snapshot_rel_path = self.visual_search_manager.extract_and_save_snapshot(
                            frame_bgr=frame_bgr,
                            bbox_xyxy=bbox,
                            camera_id=camera_id,
                            timestamp_str=started_at,
                            event_id=event_id,
                        )
            except Exception as exc:
                logger.warning("snapshot_extraction_failed", extra={"event_id": event_id, "reason": str(exc)})

        # Find max confidence from detections for this track
        track_dets = [d for d in result.detections if getattr(d, "track_id", None) == track.global_track_id]
        max_conf = max((d.confidence for d in track_dets), default=getattr(track, "confidence", 0.5))

        metadata = {
            "bbox": list(track.bbox_xyxy) if hasattr(track, "bbox_xyxy") else [],
            "class": str(getattr(track, "class_name", "person")),
            "track_state": str(track.state),
            "snapshot_path": snapshot_rel_path or "",
        }

        object_class = str(getattr(track, "class_name", "person") or "person")

        track_session = "default"
        if getattr(self, "spatial_manager", None) is not None:
            try:
                track_session = self.spatial_manager.get_camera_session(camera_id)
            except Exception:
                pass

        self.event_db.create_track_event(
            event_id=event_id,
            track_id=track.global_track_id,
            track_session_id=track_session,
            camera_id=camera_id,
            started_at_utc=started_at,
            max_confidence=max_conf,
            metadata=metadata,
            object_class=object_class,
        )

        # Expected clip path convention
        valid_start = ts if ts > 1_000_000_000 else time.time()
        timestamp_str = datetime.fromtimestamp(valid_start, tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        expected_clip_path = f"clips/{camera_id}/{camera_id}_{timestamp_str}_{event_id}.mp4"

        # Index IMMEDIATELY into vector search so snapshot is instantly searchable
        if self.visual_search_manager is not None and snapshot_rel_path:
            self.visual_search_manager.index_event_async(
                event_id=event_id,
                camera_id=camera_id,
                snapshot_rel_path=snapshot_rel_path,
                clip_rel_path=expected_clip_path,
                started_at_utc=started_at,
                track_id=track.global_track_id,
                bbox=list(track.bbox_xyxy) if hasattr(track, "bbox_xyxy") else [],
                object_class=object_class,
            )

        # Trigger clip recording asynchronously
        if self.clip_recorder is not None and getattr(self.config.events, "record_on_track_confirmed", True):
            def on_clip_done(clip_path: str):
                self.event_db.update_track_event(
                    event_id=event_id,
                    clip_path=clip_path,
                    clip_recorded=True,
                )
            self.clip_recorder.record_clip(camera_id, event_id, ts, on_complete=on_clip_done)

    def _close_track_event(self, track: Any, camera_id: str) -> None:
        """Close a track lifecycle event when track ends."""
        event = None
        event_id = getattr(track, "_event_id", None)
        if event_id:
            event = self.event_db.get_event(event_id)
        if event is None:
            track_session = None
            if getattr(self, "spatial_manager", None) is not None:
                try:
                    track_session = self.spatial_manager.get_camera_session(camera_id)
                except Exception:
                    pass
            event = self.event_db.get_event_by_track(track.global_track_id, track_session)

        if event and event.ended_at_utc is None:
            ended_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            try:
                start_dt = datetime.fromisoformat(event.started_at_utc.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(ended_at.replace('Z', '+00:00'))
                duration = max(0.0, (end_dt - start_dt).total_seconds())
            except Exception:
                duration = 0.0

            self.event_db.update_track_event(
                event_id=event.event_id,
                ended_at_utc=ended_at,
                duration_seconds=duration,
            )

    def _monitor(self, resources: ResourceMonitor) -> None:
        while not self.stop_event.wait(self.config.monitoring.print_interval_seconds):
            if self.live_service is not None:
                try:
                    online_count = 0
                    total_viewers = 0
                    for camera in self.cameras:
                        try:
                            stream_info = self.live_service.get(camera.id)
                            if stream_info.status == "online":
                                online_count += 1
                            total_viewers += stream_info.active_live_viewers
                        except Exception:
                            pass
                    self.metrics.live_view(
                        mediamtx_available=(online_count > 0 or getattr(self.live_service.client, "is_webrtc_live", lambda: False)()),
                        webrtc_sessions=total_viewers,
                        active_live_viewers=total_viewers,
                    )
                except Exception:
                    pass
            report = self.metrics.snapshot()
            usage = resources.sample()
            with self._resources_lock:
                self._last_resources = usage
            self.benchmark.add(report, usage)

            if self._readers_started_at is not None and self.benchmark.all_streams_ready_time_ms is None:
                online_cams = [c for c in report.get("cameras", {}).values() if c.get("state") == "CONNECTED"]
                if online_cams and all(c.get("frames_received", 0) > 0 for c in online_cams):
                    self.benchmark.all_streams_ready_time_ms = (monotonic() - self._readers_started_at) * 1000.0

            if self.csv_writer is not None:
                self.csv_writer.write_sample(report, usage)

            print(format_report(report, usage, self.config.runtime.mode, verbose_cameras=self.verbose_cameras), flush=True)
            logger.info("metrics", extra={"report": report, "resources": usage})

    def run(self, duration_seconds: float | None = None) -> None:
        from dataclasses import replace
        from urllib.parse import urlsplit
        from .ingest.decoder_selector import select_decoder, validate_gstreamer_dependencies
        from .ingest.gstreamer_reader import GStreamerReader, load_gstreamer
        readers: list[GStreamerReader] = []
        self._active_readers = readers
        monitor: Thread | None = None
        timer: Thread | None = None
        preview_worker: PreviewWorker | None = None
        ai_worker: Thread | None = None
        resources: ResourceMonitor | None = None
        failure_exc: Exception | None = None
        try:
            gst = load_gstreamer()
            codecs = {c.codec for c in self.cameras if c.enabled}
            validate_gstreamer_dependencies(
                gst[0], codecs,
                prefer_hardware=self.config.decode.prefer_hardware,
                fallback_software=self.config.decode.fallback_software,
            )
            resources = ResourceMonitor()
            self.metrics.snapshot()  # Initialize first report window.

            startup_batch_size = max(1, getattr(self.config.streams, "startup_batch_size", 5))
            startup_delay_s = max(0.0, getattr(self.config.streams, "startup_batch_delay_ms", 250) / 1000.0)
            self._readers_started_at = monotonic()
            source_items = list(self.source_groups.items())

            for i in range(0, len(source_items), startup_batch_size):
                if self.stop_event.is_set():
                    break
                batch_items = source_items[i:i + startup_batch_size]
                for source_id, aliases in batch_items:
                    camera = next(c for c in self.cameras if c.id == source_id)
                    scheme = urlsplit(camera.uri).scheme
                    try:
                        if scheme in ("rtsp", "rtsps"):
                            selection = select_decoder(
                                gst[0], camera.codec, camera.decoder,
                                prefer_hardware=self.config.decode.prefer_hardware,
                                fallback_software=self.config.decode.fallback_software,
                                camera_id=camera.id,
                            )
                            camera = replace(camera, decoder=selection.name)
                        else:
                            selection = type("Selection", (), {
                                "name": "uridecodebin" if scheme == "file" else "videotestsrc",
                                "decoder_type": "automatic" if scheme == "file" else "synthetic",
                            })()
                        for camera_id in aliases:
                            self.metrics.configure_decoder(camera_id, selection.name, selection.decoder_type)
                            self.metrics.configure_camera(camera_id, camera.codec, camera.expected_fps)
                    except Exception as exc:
                        for camera_id in aliases:
                            self.metrics.decoder_error(camera_id)
                            self.metrics.state(camera_id, CameraState.OFFLINE)
                            self.metrics.record_error(camera_id, str(exc))
                        logger.error("decoder_selection_failed", extra={
                            "camera_id": camera.id, "reason": str(exc), "exception_type": type(exc).__name__})
                        continue
                    try:
                        gpu_native_enabled = getattr(self.config.inference, "gpu_native", True)
                        reader = GStreamerReader(camera, self.config.streams, self.store,
                                                 self.metrics, self.stop_event, gst,
                                                 alias_ids=tuple(aliases[1:]),
                                                 mode=self.config.runtime.mode,
                                                 gpu_native=gpu_native_enabled,
                                                 target_fps=(camera.target_ai_fps if camera.target_ai_fps is not None else self.config.ai.target_fps))
                        reader.start()
                        readers.append(reader)
                    except Exception as exc:
                        for camera_id in aliases:
                            self.metrics.state(camera_id, CameraState.OFFLINE)
                            self.metrics.record_error(camera_id, str(exc))
                        logger.error("reader_start_failed", extra={
                            "camera_id": camera.id, "reason": str(exc), "exception_type": type(exc).__name__})
                        continue
                if i + startup_batch_size < len(source_items) and not self.stop_event.is_set() and startup_delay_s > 0:
                    self.stop_event.wait(startup_delay_s)

            if not readers and self.cameras:
                raise RuntimeError("All camera streams failed initialization")
            if self.config.preview.enabled and self.config.runtime.mode not in ("ingest_only", "decoded_frame"):
                preview_worker = PreviewWorker(self.source_groups, self.store,
                                               self.preview_cache, self.metrics,
                                               self.config.preview, self.stop_event,
                                               results_fn=self.latest_results)
                preview_worker.start()
            if self.config.ai.enabled and self.detector is not None:
                ai_worker = Thread(target=self._ai_loop, name="ai-scheduler", daemon=True)
                ai_worker.start()
            monitor = Thread(target=self._monitor, args=(resources,),
                             name="metrics", daemon=True)
            monitor.start()
            if duration_seconds is not None:
                def expire() -> None:
                    if not self.stop_event.wait(duration_seconds):
                        self.stop()
                timer = Thread(target=expire, name="duration", daemon=True)
                timer.start()
            self.stop_event.wait()  # Ingest/decode readers run independently.
        except Exception as exc:
            failure_exc = exc
            raise
        finally:
            self.stop()
            deadline = monotonic() + self.config.streams.frame_timeout_seconds + 5
            for reader in list(self._active_readers):
                reader.join(timeout=max(0.0, deadline - monotonic()))
                if reader.is_alive():
                    logger.error("reader_shutdown_timeout", extra={"camera_id": reader.camera.id})
            if preview_worker is not None:
                if hasattr(preview_worker, "close"):
                    preview_worker.close()
                preview_worker.join(timeout=3)
                if preview_worker.is_alive():
                    logger.error("preview_shutdown_timeout")
            if ai_worker is not None:
                ai_worker.join(timeout=3)
                if ai_worker.is_alive():
                    logger.error("ai_shutdown_timeout")
            if monitor is not None:
                monitor.join(timeout=2)
            if timer is not None:
                timer.join(timeout=1)
            if resources is not None:
                resources.close()
            if self.csv_writer is not None:
                self.csv_writer.close()
            if self.tracks_writer is not None:
                self.tracks_writer.close()
            if self.clip_recorder is not None:
                self.clip_recorder.shutdown()
            if getattr(self, "visual_search_manager", None) is not None:
                self.visual_search_manager.shutdown()
            if self.event_db is not None:
                try:
                    self.event_db.close_active_events()
                except Exception:
                    pass
                self.event_db.cleanup_old_events()
                self.event_db.close_all_connections()

            status = self._status_at_stop or self.metrics.view()
            duration = monotonic() - self.benchmark.started

            if failure_exc is not None:
                print(format_failure_summary(str(failure_exc), duration, self.benchmark.samples), flush=True)
                self.summary = self.benchmark.finish(
                    self.config.runtime.mode, status,
                    status_label="failed",
                    failure_type=type(failure_exc).__name__,
                    failure_reason=str(failure_exc),
                )
                logger.error("benchmark_failed", extra={"report": self.summary, "reason": str(failure_exc)})
            elif self.benchmark.samples == 0:
                if resources is not None:
                    report = self.metrics.snapshot()
                    usage = resources.sample()
                    with self._resources_lock:
                        self._last_resources = usage
                    self.benchmark.add(report, usage)
                self.summary = self.benchmark.finish(self.config.runtime.mode, status, status_label="success")
                print(format_summary(self.summary), flush=True)
                logger.info("benchmark_summary", extra={"report": self.summary})
            else:
                self.summary = self.benchmark.finish(self.config.runtime.mode, status, status_label="success")
                print(format_summary(self.summary), flush=True)
                logger.info("benchmark_summary", extra={"report": self.summary})

            self.preview_cache.clear()
            self.store.clear()
