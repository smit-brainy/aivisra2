import logging
import random
import socket
from threading import Event, Thread
from time import monotonic, time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import numpy as np

from ..config import CameraConfig, StreamsConfig
from ..frame_store import LatestFrameStore
from ..metrics import MetricsRegistry
from ..types import CameraFrame, CameraState, GpuFrame


def sanitize_uri(uri: str) -> str:
    """Sanitize RTSP URI by masking any credentials (no password in logs)."""
    if not uri:
        return uri
    try:
        parsed = urlsplit(uri)
        if parsed.password:
            user = parsed.username or ""
            host = parsed.hostname or ""
            port = f":{parsed.port}" if parsed.port else ""
            netloc = f"{user}:***@{host}{port}"
            return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
        return uri
    except Exception:
        return uri


logger = logging.getLogger(__name__)


def load_gstreamer() -> tuple[Any, Any]:
    try:
        import gi

        gi.require_version("Gst", "1.0")
        gi.require_version("GstVideo", "1.0")

        from gi.repository import Gst, GstVideo

        Gst.init(None)

        return Gst, GstVideo

    except (ImportError, ValueError) as exc:
        raise RuntimeError(
            "GStreamer Python bindings unavailable; see StreamCore README"
        ) from exc


class StreamFailure(RuntimeError):
    """
    Sanitized stream failure.

    Never include the RTSP URI because it may contain
    camera credentials.
    """


class GStreamerReader(Thread):

    def __init__(
        self,
        camera: CameraConfig,
        config: StreamsConfig,
        store: LatestFrameStore,
        metrics: MetricsRegistry,
        stop: Event,
        gst: tuple[Any, Any],
        alias_ids: tuple[str, ...] = (),
        mode: str = "preview",
        gpu_native: bool = True,
        target_fps: float | None = None,
    ) -> None:

        super().__init__(
            name=f"stream-{camera.id}",
            daemon=True,
        )

        self.camera = camera
        self.mode = mode
        self.gpu_native = gpu_native
        if target_fps is not None:
            self.target_fps = float(target_fps)
        elif camera.target_ai_fps is not None:
            self.target_fps = float(camera.target_ai_fps)
        else:
            self.target_fps = float(getattr(config, "target_fps", 8.0) if hasattr(config, "target_fps") else 8.0)

        self.camera_ids = (
            camera.id,
            *alias_ids,
        )

        self.config = config
        self.store = store
        self.metrics = metrics
        self.stop_event = stop

        self.Gst, self.GstVideo = gst

        self.sequence = 0
        self._started_monotonic = monotonic()
        self._first_frame_recorded = False
        self._reconnect_jitter_ratio = getattr(config, "reconnect_jitter_ratio", 0.25)

        self._last_decoded_at = monotonic()
        self._last_decoded_timestamp = time()
        self._buffer_pool: list[np.ndarray] = []
        self._buffer_shape: tuple[int, int, int] | None = None
        self._gpu_buffer_pool: list[Any] = []
        self._gpu_buffer_shape: tuple[int, int] | None = None

    def _element(
        self,
        name: str,
    ) -> Any:

        element = self.Gst.ElementFactory.make(name)

        if element is None:
            raise StreamFailure(
                f"missing-plugin-{name}"
            )

        return element

    def _decoded_probe(
        self,
        pad: Any,
        info: Any,
    ) -> Any:

        del pad, info

        now_mono = monotonic()
        now_wall = time()

        self._last_decoded_at = now_mono
        self._last_decoded_timestamp = now_wall

        if not self._first_frame_recorded:
            self._first_frame_recorded = True
            startup_time_ms = (now_mono - self._started_monotonic) * 1000
            for camera_id in self.camera_ids:
                self.metrics.record_startup_time(camera_id, startup_time_ms)

        for camera_id in self.camera_ids:
            self.metrics.received(
                camera_id,
                now_wall,
                now_mono,
            )

        return self.Gst.PadProbeReturn.OK

    def _on_sample(
        self,
        sink: Any,
    ) -> Any:

        sample = sink.emit("pull-sample")

        if sample is None:
            return self.Gst.FlowReturn.ERROR

        buffer = sample.get_buffer()
        caps = sample.get_caps()

        if buffer is None or caps is None:
            return self.Gst.FlowReturn.ERROR

        structure = caps.get_structure(0)

        width = structure.get_value("width")
        height = structure.get_value("height")

        success, map_info = buffer.map(
            self.Gst.MapFlags.READ
        )

        if not success:
            return self.Gst.FlowReturn.ERROR

        try:

            array = np.frombuffer(
                map_info.data,
                dtype=np.uint8,
            )

            expected_size = (
                int(width)
                * int(height)
                * 3
            )

            if array.size < expected_size:
                return self.Gst.FlowReturn.ERROR

            shape = (int(height), int(width), 3)
            if self._buffer_shape != shape or len(self._buffer_pool) < 2:
                self._buffer_pool = [np.empty(shape, dtype=np.uint8) for _ in range(2)]
                self._buffer_shape = shape

            frame_array = self._buffer_pool[self.sequence % 2]
            np.copyto(frame_array, array[:expected_size].reshape(shape))

        finally:
            buffer.unmap(map_info)

        self.sequence += 1

        now_mono = monotonic()
        now_wall = time()

        frame = CameraFrame(
            camera_id=self.camera.id,
            sequence=self.sequence,
            timestamp=now_wall,
            received_monotonic=now_mono,
            image=frame_array,
            width=int(width),
            height=int(height),
        )

        self.store.put(
            frame,
        )

        for alias_id in self.camera_ids[1:]:
            alias_frame = CameraFrame(
                camera_id=alias_id,
                sequence=self.sequence,
                timestamp=now_wall,
                received_monotonic=now_mono,
                image=frame_array,
                width=int(width),
                height=int(height),
            )

            self.store.put(
                alias_frame,
            )

        self._last_decoded_at = now_mono
        self._last_decoded_timestamp = now_wall

        if not self._first_frame_recorded:
            self._first_frame_recorded = True
            startup_time_ms = (now_mono - self._started_monotonic) * 1000
            for camera_id in self.camera_ids:
                self.metrics.record_startup_time(camera_id, startup_time_ms)

        for camera_id in self.camera_ids:
            self.metrics.received(
                camera_id,
                now_wall,
                now_mono,
            )
            self.metrics.record_cpu_download(camera_id, 1)
            self.metrics.record_frame_path(camera_id, "CPU_FALLBACK")

        return self.Gst.FlowReturn.OK

    def _on_sample_gpu(
        self,
        sink: Any,
    ) -> Any:
        sample = sink.emit("pull-sample")
        if sample is None:
            return self.Gst.FlowReturn.ERROR

        buffer = sample.get_buffer()
        caps = sample.get_caps()
        if buffer is None or caps is None:
            return self.Gst.FlowReturn.ERROR

        self.sequence += 1
        now_mono = monotonic()
        now_wall = time()
        self._last_decoded_at = now_mono
        self._last_decoded_timestamp = now_wall

        if self.sequence == 1:
            logger.debug("CAM %s: _on_sample_gpu called (seq=%d)", self.camera.id, self.sequence)

        structure = caps.get_structure(0)
        width = structure.get_value("width")
        height = structure.get_value("height")
        shape = (int(height), int(width))
        if self._gpu_buffer_shape != shape or len(self._gpu_buffer_pool) < 2:
            import torch
            dev = "cuda:0"
            self._gpu_buffer_pool = [
                (
                    torch.empty((shape[0], shape[1]), dtype=torch.uint8, device=dev),
                    torch.empty((shape[0] // 2, shape[1]), dtype=torch.uint8, device=dev),
                )
                for _ in range(2)
            ]
            self._gpu_buffer_shape = shape

        target_tensors = self._gpu_buffer_pool[self.sequence % 2]
        from ..gpu_frame import extract_gpu_frame
        gframe = extract_gpu_frame(
            buffer,
            caps,
            camera_id=self.camera.id,
            sequence=self.sequence,
            target_tensors=target_tensors,
        )
        if gframe is None:
            return self.Gst.FlowReturn.OK

        self.store.put(gframe)

        for alias_id in self.camera_ids[1:]:
            alias_gframe = GpuFrame(
                camera_id=alias_id,
                sequence=self.sequence,
                capture_monotonic_ns=gframe.capture_monotonic_ns,
                received_monotonic=gframe.received_monotonic,
                width=gframe.width,
                height=gframe.height,
                stride_y=gframe.stride_y,
                stride_uv=gframe.stride_uv,
                source_width=gframe.source_width,
                source_height=gframe.source_height,
                pixel_format=gframe.pixel_format,
                memory_type=gframe.memory_type,
                device_id=gframe.device_id,
                pts=gframe.pts,
                cuda_tensor=gframe.cuda_tensor,
                release_callback=None,
                y_ptr=gframe.y_ptr,
                uv_ptr=gframe.uv_ptr,
            )
            self.store.put(alias_gframe)

        self._last_decoded_at = now_mono
        self._last_decoded_timestamp = now_wall

        if not self._first_frame_recorded:
            self._first_frame_recorded = True
            startup_time_ms = (now_mono - self._started_monotonic) * 1000
            for camera_id in self.camera_ids:
                self.metrics.record_startup_time(camera_id, startup_time_ms)

        for camera_id in self.camera_ids:
            self.metrics.received(camera_id, now_wall, now_mono)
            self.metrics.record_frame_path(camera_id, "GPU_NATIVE")

        return self.Gst.FlowReturn.OK

    def _pipeline(
        self,
    ) -> tuple[Any, Any]:

        Gst = self.Gst

        pipeline = Gst.Pipeline.new(None)

        if pipeline is None:
            raise StreamFailure(
                "pipeline-create-failed"
            )

        scheme = urlsplit(
            self.camera.uri
        ).scheme

        # -----------------------------------------
        # OUTPUT BRANCH
        # -----------------------------------------

        if self.mode == "ingest_only":

            # Important:
            # Hardware decoder output goes directly
            # to fakesink.
            #
            # No videoconvert.
            # No BGR.
            # No NumPy.
            # No OpenCV.
            # No Python frame copying.
            #
            # This is the clean ingest/decode benchmark.

            sink = self._element(
                "fakesink"
            )

            sink.set_property(
                "sync",
                False,
            )

            sink.set_property(
                "enable-last-sample",
                False,
            )

            pipeline.add(sink)

            post_decode = sink

            sink_pad = sink.get_static_pad(
                "sink"
            )

            sink_pad.add_probe(
                Gst.PadProbeType.BUFFER,
                self._decoded_probe,
            )

        else:

            # AI / decoded-frame path.
            #
            # For now we still convert into BGR
            # because LatestFrameStore and current
            # detector pipeline expect NumPy arrays.
            #
            # This CPU conversion is intentionally
            # isolated here so it can later be
            # replaced with NVMM/CUDA zero-copy.

            sink = self._element(
                "appsink"
            )

            sink.set_property(
                "max-buffers",
                1,
            )

            sink.set_property(
                "drop",
                True,
            )

            sink.set_property(
                "enable-last-sample",
                False,
            )

            sink.set_property(
                "wait-on-eos",
                False,
            )

            sink.set_property(
                "emit-signals",
                True,
            )

            sink.set_property(
                "sync",
                scheme == "file",
            )

            is_gpu_native = (
                self.gpu_native
                and self.camera.decoder in ("nvh264dec", "nvh265dec", "cudadec")
            )
            from ..gpu_frame import GstCudaInterop

            if is_gpu_native and GstCudaInterop.get().available:
                # GPU-native path: NVDEC outputs CUDAMemory NV12 directly to appsink
                sink.set_property(
                    "caps",
                    Gst.Caps.from_string("video/x-raw(memory:CUDAMemory), format=NV12"),
                )
                sink.connect(
                    "new-sample",
                    self._on_sample_gpu,
                )
                pipeline.add(sink)
                post_decode = sink
            else:
                # CPU fallback path: videoconvert to BGR
                sink.set_property(
                    "caps",
                    Gst.Caps.from_string("video/x-raw,format=BGR"),
                )
                sink.connect(
                    "new-sample",
                    self._on_sample,
                )
                pipeline.add(sink)

                if self.camera.decoder == "nvv4l2decoder":
                    post_decode = sink
                else:
                    converter = self._element(
                        "videoconvert"
                    )
                    pipeline.add(converter)
                    if not converter.link(sink):
                        raise StreamFailure(
                            "sink-link-failed"
                        )
                    post_decode = converter

        # -----------------------------------------
        # DYNAMIC SOURCE PAD LINKER
        # -----------------------------------------

        def link_video(
            source: Any,
            pad: Any,
            target: Any,
            rtsp: bool,
        ) -> None:

            del source

            caps = (
                pad.get_current_caps()
                or pad.query_caps(None)
            )

            if (
                caps is None
                or caps.get_size() == 0
            ):
                return

            structure = caps.get_structure(0)

            if rtsp:

                if self.camera.codec == "h264":
                    encoding = "H264"
                elif self.camera.codec == "h265":
                    encoding = "H265"
                elif self.camera.codec == "mpeg4":
                    encoding = "MP4V-ES"
                else:
                    encoding = self.camera.codec.upper()

                accepted = (
                    structure.get_name()
                    == "application/x-rtp"
                    and structure.get_string(
                        "media"
                    )
                    == "video"
                    and structure.get_string(
                        "encoding-name"
                    )
                    == encoding
                )

                if (
                    structure.get_name() == "application/x-rtp"
                    and structure.get_string("media") == "video"
                    and not accepted
                ):
                    logger.warning(
                        "Camera %s: codec mismatch! Configured '%s' (expected RTP %s), but incoming stream has RTP encoding '%s'",
                        self.camera.id,
                        self.camera.codec,
                        encoding,
                        structure.get_string("encoding-name"),
                    )

            else:

                accepted = (
                    structure.get_name()
                    == "video/x-raw"
                )

            destination = (
                target.get_static_pad(
                    "sink"
                )
            )

            if (
                accepted
                and not destination.is_linked()
            ):

                result = pad.link(
                    destination
                )

                if (
                    result
                    != Gst.PadLinkReturn.OK
                ):
                    logger.warning(
                        "Pad link failed for %s",
                        self.camera.id,
                    )

        # -----------------------------------------
        # RTSP SOURCE
        # -----------------------------------------

        if scheme in (
            "rtsp",
            "rtsps",
        ):

            source = self._element(
                "rtspsrc"
            )

            source.set_property(
                "location",
                self.camera.uri,
            )

            # TCP
            source.set_property(
                "protocols",
                4,
            )

            source.set_property(
                "latency",
                self.config.rtsp_latency_ms,
            )

            source.set_property(
                "drop-on-latency",
                True,
            )

            source.set_property(
                "tcp-timeout",
                int(
                    self.config.frame_timeout_seconds
                    * 1_000_000
                ),
            )

            if self.camera.codec == "h264":
                depay_name = "rtph264depay"
                parse_name = "h264parse"
            elif self.camera.codec == "h265":
                depay_name = "rtph265depay"
                parse_name = "h265parse"
            elif self.camera.codec == "mpeg4":
                depay_name = "rtpmp4vdepay"
                parse_name = "mpeg4videoparse"
            else:
                depay_name = f"rtp{self.camera.codec}depay"
                parse_name = f"{self.camera.codec}parse"

            depay = self._element(
                depay_name
            )

            parser = self._element(
                parse_name
            )

            decoder = self._element(
                self.camera.decoder
            )

            pipeline.add(source)
            pipeline.add(depay)
            pipeline.add(parser)
            pipeline.add(decoder)

            linked = (
                depay.link(parser)
                and parser.link(decoder)
            )

            if not linked:
                raise StreamFailure(
                    "decode-input-link-failed"
                )


            decoder_output = decoder

            # nvv4l2decoder can require NVIDIA
            # conversion before standard GStreamer
            # CPU elements.
            if (
                self.camera.decoder
                == "nvv4l2decoder"
                and self.mode != "ingest_only"
            ):

                nv_converter = self._element(
                    "nvvideoconvert"
                )

                pipeline.add(
                    nv_converter
                )

                if not decoder.link(
                    nv_converter
                ):
                    raise StreamFailure(
                        "nvidia-converter-link-failed"
                    )

                decoder_output = nv_converter

            if not decoder_output.link(
                post_decode
            ):
                raise StreamFailure(
                    "decode-output-link-failed"
                )

            source.connect(
                "pad-added",
                link_video,
                depay,
                True,
            )

        # -----------------------------------------
        # LOCAL FILE SOURCE
        # -----------------------------------------

        elif scheme == "file":

            source = self._element(
                "uridecodebin"
            )

            source.set_property(
                "uri",
                self.camera.uri,
            )

            source.set_property(
                "caps",
                Gst.Caps.from_string(
                    "video/x-raw"
                ),
            )

            pipeline.add(source)

            source.connect(
                "pad-added",
                link_video,
                post_decode,
                False,
            )

        # -----------------------------------------
        # TEST SOURCE
        # -----------------------------------------

        elif scheme == "test":

            source = self._element(
                "videotestsrc"
            )

            source.set_property(
                "is-live",
                True,
            )

            capsfilter = self._element(
                "capsfilter"
            )

            capsfilter.set_property(
                "caps",
                Gst.Caps.from_string(
                    "video/x-raw,"
                    "width=640,"
                    "height=360,"
                    "framerate=25/1"
                ),
            )

            pipeline.add(source)
            pipeline.add(capsfilter)

            if not (
                source.link(capsfilter)
                and capsfilter.link(
                    post_decode
                )
            ):
                raise StreamFailure(
                    "test-source-link-failed"
                )

        else:
            raise StreamFailure(
                "unsupported-source-scheme"
            )

        return pipeline, sink

    def _set_state(
        self,
        state: CameraState,
    ) -> None:

        for camera_id in self.camera_ids:
            self.metrics.state(
                camera_id,
                state,
            )

    def run(
        self,
    ) -> None:

        Gst = self.Gst

        reconnect_delay = (
            self.config.reconnect_initial_seconds
        )

        try:
            while not self.stop_event.is_set():

                pipeline = None

                try:

                    self._set_state(
                        CameraState.CONNECTING
                    )

                    pipeline, sink = (
                        self._pipeline()
                    )

                    result = pipeline.set_state(
                        Gst.State.PLAYING
                    )

                    if (
                        result
                        == Gst.StateChangeReturn.FAILURE
                    ):
                        raise StreamFailure(
                            "pipeline-start-failed"
                        )

                    self._set_state(
                        CameraState.CONNECTED
                    )

                    connected_at = monotonic()
                    bus = pipeline.get_bus()
                    self._last_decoded_at = monotonic()

                    while not self.stop_event.is_set():
                        if monotonic() - connected_at >= self.config.reconnect_reset_seconds:
                            reconnect_delay = self.config.reconnect_initial_seconds

                        message = bus.timed_pop_filtered(
                            int(
                                200
                                * Gst.MSECOND
                            ),
                            Gst.MessageType.ERROR
                            | Gst.MessageType.EOS,
                        )

                        if message is not None:

                            if (
                                message.type
                                == Gst.MessageType.ERROR
                            ):
                                err, debug = message.parse_error()
                                err_msg = err.message if err else "gstreamer-error"
                                logger.error(
                                    "Camera %s GStreamer error: %s (debug: %s)",
                                    self.camera.id,
                                    err_msg,
                                    debug,
                                )
                                raise StreamFailure(
                                    err_msg
                                )

                            if (
                                message.type
                                == Gst.MessageType.EOS
                            ):

                                raise StreamFailure(
                                    "stream-eos"
                                )

                        age = (
                            monotonic()
                            - self._last_decoded_at
                        )

                        if (
                            age
                            > self.config.frame_timeout_seconds
                        ):

                            raise StreamFailure(
                                "frame-timeout"
                            )

                except Exception as exc:
                    now_mono = monotonic()
                    self._set_state(
                        CameraState.OFFLINE
                    )

                    for camera_id in self.camera_ids:
                        self.metrics.record_disconnect(
                            camera_id,
                            now_mono,
                        )
                        self.metrics.reconnect(
                            camera_id
                        )
                        self.metrics.record_error(
                            camera_id,
                            str(exc),
                        )

                    base_delay = reconnect_delay
                    jitter = random.uniform(0, base_delay * self._reconnect_jitter_ratio)
                    actual_delay = base_delay + jitter

                    logger.warning(
                        "Camera %s reconnecting (error: %s, backoff: %.2f s [base %.2f, jitter %.2f])",
                        self.camera.id,
                        exc,
                        actual_delay,
                        base_delay,
                        jitter,
                    )

                    if self.stop_event.wait(
                        actual_delay
                    ):
                        break

                    for camera_id in self.camera_ids:
                        self.metrics.record_reconnect(
                            camera_id,
                            monotonic(),
                        )

                    reconnect_delay = min(
                        reconnect_delay * 2,
                        self.config.reconnect_max_seconds,
                    )

                finally:

                    if pipeline is not None:

                        try:
                            pipeline.set_state(
                                Gst.State.NULL
                            )
                        except Exception:
                            pass
        finally:
            self._set_state(
                CameraState.STOPPED
            )


def validate_single_source_pipeline(
    camera: CameraConfig,
    config: StreamsConfig,
    gst: tuple[Any, Any],
    timeout_seconds: float = 12.0,
    mode: str = "ingest_only",
    return_details: bool = False,
) -> Any:
    """Test building one camera pipeline, moving to READY then PLAYING, waiting for first frame, and stopping cleanly."""
    from dataclasses import replace
    from .decoder_selector import select_decoder

    details: dict[str, Any] = {
        "camera_id": camera.id,
        "codec": camera.codec,
        "decoder": camera.decoder,
        "sanitized_uri": sanitize_uri(camera.uri),
        "startup_time_ms": None,
        "first_frame": False,
    }

    # 1. Check URI reachability for RTSP
    parsed = urlsplit(camera.uri)
    if parsed.scheme in ("rtsp", "rtsps"):
        host = parsed.hostname
        port = parsed.port or 554
        if host:
            try:
                with socket.create_connection((host, port), timeout=2.0):
                    pass
            except Exception as e:
                err = f"Could not connect to {host}:{port}: {e}"
                return (False, err, details) if return_details else (False, f"Camera {camera.id}: {err}")

    Gst, _ = gst
    if camera.decoder == "auto":
        selection = select_decoder(Gst, camera.codec, prefer_hardware=True, fallback_software=True, camera_id=camera.id)
        camera = replace(camera, decoder=selection.name)
    details["decoder"] = camera.decoder

    store = LatestFrameStore([camera.id])
    metrics = MetricsRegistry([camera.id])
    stop_event = Event()
    reader = GStreamerReader(camera, config, store, metrics, stop_event, gst, mode=mode)
    pipeline = None
    try:
        pipeline, sink = reader._pipeline()
        ret = pipeline.set_state(Gst.State.READY)
        if ret == Gst.StateChangeReturn.FAILURE:
            err = "failed to reach READY state"
            return (False, err, details) if return_details else (False, f"Camera {camera.id} ({camera.codec}/{camera.decoder}): {err}")
        ret = pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            err = "failed to reach PLAYING state"
            return (False, err, details) if return_details else (False, f"Camera {camera.id} ({camera.codec}/{camera.decoder}): {err}")
        bus = pipeline.get_bus()
        start = monotonic()
        saw_frame = False
        while monotonic() - start < timeout_seconds:
            msg = bus.timed_pop_filtered(int(50 * Gst.MSECOND), Gst.MessageType.ERROR | Gst.MessageType.EOS)
            if msg is not None:
                if msg.type == Gst.MessageType.ERROR:
                    err, _debug = msg.parse_error()
                    err_msg = err.message if err else "GStreamer pipeline error"
                    return (False, err_msg, details) if return_details else (False, f"Camera {camera.id} ({camera.codec}/{camera.decoder}): {err_msg}")
                if msg.type == Gst.MessageType.EOS:
                    return (False, "unexpected EOS", details) if return_details else (False, f"Camera {camera.id} ({camera.codec}/{camera.decoder}): unexpected EOS")
            if metrics.view()["cameras"][camera.id]["frames_received"] > 0:
                saw_frame = True
                details["first_frame"] = True
                details["startup_time_ms"] = (monotonic() - start) * 1000
                break
        if not saw_frame:
            err = f"timeout ({timeout_seconds:.1f}s) waiting for first frame"
            return (False, err, details) if return_details else (False, f"Camera {camera.id} ({camera.codec}/{camera.decoder}): {err}")
        return (True, None, details) if return_details else (True, None)
    except Exception as exc:
        return (False, str(exc), details) if return_details else (False, f"Camera {camera.id} ({camera.codec}/{camera.decoder}): {exc}")
    finally:
        if pipeline is not None:
            try:
                pipeline.set_state(Gst.State.NULL)
            except Exception:
                pass


def validate_all_pipelines(
    cameras: list[CameraConfig],
    config: StreamsConfig,
    gst: tuple[Any, Any],
    timeout_seconds: float = 12.0,
    mode: str = "ingest_only",
) -> list[dict[str, Any]]:
    """Validate all cameras sequentially, printing exact output per Stage A."""
    results = []
    print("=" * 88, flush=True)
    print("AIVISRA STREAMCORE — PIPELINE VALIDATION", flush=True)
    print("=" * 88, flush=True)
    for cam in cameras:
        if not cam.enabled:
            continue
        ok, err, details = validate_single_source_pipeline(
            cam, config, gst, timeout_seconds=timeout_seconds, mode=mode, return_details=True
        )
        details["ok"] = ok
        details["error"] = err
        results.append(details)
        if ok:
            ms_str = f"{details['startup_time_ms']:.0f}ms" if details.get("startup_time_ms") is not None else "OK"
            print(f"{cam.id:<8} PASS {cam.codec} {details['decoder']} first_frame={ms_str}", flush=True)
        else:
            print(f"{cam.id:<8} FAIL {details['sanitized_uri']} GStreamer error: {err}", flush=True)
    print("=" * 88, flush=True)
    return results