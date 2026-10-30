# AIVISRA StreamCore Architecture & Operations Guide

AIVISRA StreamCore (`mis.runtime.streamcore`) is an enterprise-grade, GPU-accelerated video ingestion, live streaming, and real-time AI inference runtime built for NVIDIA RTX GPUs and multi-RTSP camera environments.

---

## 1. System Architecture & Data Flow

StreamCore decouples video ingestion, AI inference, and live client viewing into three independent, non-blocking pipelines:

```text
                               ┌────────────────────────────────────────────────────────┐
                               │  RTSP Sources (Virtual CCTV / MediaMTX / IP Cameras)   │
                               │           rtsp://192.168.1.27:8554/cam001 ...          │
                               └──────────────┬───────────────────────────┬─────────────┘
                                              │                           │
                   [Direct WebRTC Path]       │                           │ [GStreamer Ingest Path]
                                              ▼                           ▼
                                    ┌───────────────────┐       ┌───────────────────┐
                                    │ MediaMTX (WebRTC) │       │  GStreamerReader  │
                                    │   Port 8889 HTTP  │       │  rtsp:// (TCP)    │
                                    │   Port 8189 UDP   │       └─────────┬─────────┘
                                    └─────────┬─────────┘                 │
                                              │                           ▼
                                              │                 ┌───────────────────┐
                                              │                 │  NVIDIA NVDEC HW  │
                                              │                 │    (nvh264dec)    │
                                              │                 └─────────┬─────────┘
                                              │                           │
                                              │              [Zero-Copy Double Buffer]
                                              │                           ▼
                                              │                 ┌───────────────────┐
                                              │                 │ LatestFrameStore  │
                                              │                 │  (Newest Frame)   │
                                              │                 └─────────┬─────────┘
                                              │                           │
                                              │                           ▼
                                              │                 ┌───────────────────┐
                                              │                 │  Frame Scheduler  │
                                              │                 │   (Ingest ──> AI) │
                                              │                 └─────────┬─────────┘
                                              │                           │
                                              │                           ▼
                                              │                 ┌───────────────────┐
                                              │                 │ YOLO11n AI Worker │
                                              │                 │ (RTX 5070 Tensor) │
                                              │                 └─────────┬─────────┘
                                              │                           │
                                              │                      [Detections]
                                              │                           │
                                              │       ┌───────────────────┴───────────────────┐
                                              │       ▼                                       ▼
                                              │ ┌───────────────┐                       ┌───────────────┐
                                              │ │ PreviewWorker │                       │KeyFrameStorage│
                                              │ │  (Overlays)   │                       │  (Evidence)   │
                                              │ └───────┬───────┘                       └───────────────┘
                                              │         │
                                              ▼         ▼
                               ┌──────────────────────────────────┐
                               │    StreamCore Preview Server     │
                               │        http://0.0.0.0:8765       │
                               │  - 🤖 GPU Decoded Ingest (MJPEG) │
                               │  - ⚡ WebRTC Direct Streaming     │
                               └──────────────────────────────────┘
```

---

## 2. Directory & Module Guide (`mis/runtime/streamcore/`)

| File / Folder | Role & Responsibility |
| :--- | :--- |
| **`main.py`** | Command-line entrypoint. Parses flags (`--config`, `--mode`, `--duration`, `--preview-port`), initializes logging, sets up signal handlers (`SIGINT`/`SIGTERM`), and orchestrates the runtime engine. |
| **`engine.py`** | Central orchestrator (`StreamCore`). Manages camera lifecycle, GStreamer reader threads, scheduling, AI batch inference loop, and background metric reporting. |
| **`config.py`** | Pydantic-style configuration loader with strict validation for `app.yaml`, RTSP URIs, hardware decoder settings, batch sizes, and thresholds. |
| **`types.py`** | Immutable dataclasses defining `CameraFrame`, `Detection`, `DetectionResult`, and `CameraState` (`CONNECTING`, `CONNECTED`, `OFFLINE`, `STOPPED`). |
| **`metrics.py`** | Lock-free high-frequency metrics registry. Tracks input FPS, decoded FPS, AI inference latency, frame age, and system resources (CPU, RSS, GPU utilization, VRAM). |
| **`frame_store.py`** | `LatestFrameStore`: Bounded storage ensuring each stream keeps only its latest decoded frame. Drops older stale frames without memory growth. |
| **`benchmark.py`** | Performance benchmarking accumulator. Records time-series samples and generates machine-readable benchmark summaries (`--summary-json`). |
| **`test_unit.py`** | Fast unit test suite covering configuration validation, decoder selection, buffer pooling, and scheduler logic. |
| **`ingest/`** | **Video Ingestion & Hardware Decoding** |
| `├─ gstreamer_reader.py` | Multi-threaded GStreamer pipeline worker. Uses `rtspsrc` (TCP), `rtph264depay`, `h264parse`, `nvh264dec` (NVIDIA hardware decode), pre-allocated double buffer pools, and exponential backoff reconnect logic. |
| `└─ decoder_selector.py` | Probes live GStreamer plugin registry to find and test available decoders (`nvh264dec` → `nvv4l2decoder` → `avdec_h264`), ensuring element reaches `READY` state. |
| **`inference/`** | **AI Inference Engine** |
| `├─ base.py` | Abstract `Detector` base class. |
| `├─ ultralytics_detector.py`| High-throughput YOLO11 GPU detector. Runs FP16 half-precision inference with dynamic batching on RTX 5070 Tensor Cores (~4.6 ms batch latency). |
| `└─ dummy.py` | Mock detector for dry-run performance and pipeline load testing without GPU. |
| **`preview/`** | **Web Preview & Visualization** |
| `├─ preview_server.py` | Built-in HTTP server hosting the multi-camera monitoring UI, REST API (`/api/status`), live WebRTC proxy, and non-blocking `/frame/<id>.jpg` updater. |
| `├─ preview_worker.py` | Background worker that samples latest frames, draws YOLO bounding boxes and confidence tags, and prepares scaled thumbnails. |
| `└─ preview_cache.py` | Thread-safe cache holding newest preview frames. |
| **`live/`** | **MediaMTX & WebRTC Integration** |
| `├─ mediamtx_client.py` | Client checking MediaMTX status and probing WebRTC HTTP/TCP availability (port 8889). |
| `├─ live_service.py` | Service tracking camera stream URLs and viewer counts. |
| `└─ live_types.py` | Dataclasses for live stream metadata. |
| **`scheduling/`** | **Decoupled Frame Scheduling** |
| `└─ frame_scheduler.py` | Decouples camera intake frame rate (e.g. 25 FPS) from inference rate (e.g. 8 FPS), ensuring AI processes only fresh frames and drops intermediate buffers. |
| **`evidence/`** | **Keyframe Evidence Archival** |
| `├─ keyframe_selector.py`| Selects highest quality keyframes per detection track. |
| `└─ local_storage.py` | Saves evidence frames to local storage directories. |

---

## 3. How to Run: Standard Commands

All commands should be executed from the repository root:

### 1. Production Mode with Live Web UI & AI Overlays (Default)
Runs all configured cameras, performs hardware video decoding on RTX 5070, executes YOLO11n batch inference, and starts the web preview server on port `8765`:

```bash
python3 -m mis.runtime.streamcore.main \
  --config config/streamcore/app.yaml \
  --preview-port 8765 \
  --preview-fps 8
```

- **Open in Browser:** `http://192.168.1.9:8765`
- **Features:** Responsive camera grid, AI bounding boxes, and instant toggle between **DeepStream GPU Ingest** and **WebRTC (MediaMTX)**.

---

### 2. Pure Ingestion Benchmark (`ingest_only`)
Runs zero-copy video intake directly into `fakesink` without CPU memory copies, NumPy arrays, preview encoding, or AI inference. Measures maximum hardware decode FPS:

```bash
python3 -m mis.runtime.streamcore.main \
  --config config/streamcore/app.yaml \
  --mode ingest_only \
  --duration 120 \
  --summary-json ingest.json
```

---

### 3. Decoded Frame Benchmark (`decoded_frame`)
Decodes video on NVDEC, transfers frames to host memory using the pre-allocated double-buffer pool, and updates `LatestFrameStore`. Measures decode throughput and host memory efficiency:

```bash
python3 -m mis.runtime.streamcore.main \
  --config config/streamcore/app.yaml \
  --mode decoded_frame \
  --duration 120 \
  --summary-json decoded.json
```

---

### 4. Single-Camera Pipeline Validator
Quickly test and validate a single RTSP stream without starting the full engine:

```bash
# Validate CAM001 pipeline
python3 -m mis.runtime.streamcore.main \
  --config config/streamcore/app.yaml \
  --validate-pipeline CAM001
```

---

### 5. Running Unit Tests
Fast unit testing covering all core algorithms (decoder selection, buffer reuse, scheduling, config parsing):

```bash
python3 -m unittest mis/runtime/streamcore/test_unit.py -v
```

---

## 4. Key Performance Characteristics

1. **Hardware Video Decoding (NVDEC):**
   - StreamCore offloads H.264/H.265 decompression entirely to NVIDIA NVDEC silicon.
   - CPU load remains low (~5–15%) because the host CPU does zero pixel math.
2. **Zero-Copy Reusable Double-Buffer Pool:**
   - Instead of allocating fresh 6.2 MB NumPy arrays 25 times per second for every camera (which causes severe memory fragmentation and garbage collection spikes), StreamCore pre-allocates a reusable double-buffer pool per camera using `np.copyto`.
   - Python heap image footprint is bounded to under ~40 MB.
3. **High-Speed YOLO11 GPU Inference:**
   - Ingested frames are dynamically batched and inferred in FP16 half-precision on NVIDIA Tensor Cores.
   - Batch inference latency is **~4.6 ms**, achieving throughput exceeding 1,000 FPS.
4. **Bypassing Browser 6-Connection Limit:**
   - Web browsers (Chrome, Edge, Brave) limit persistent HTTP/1.1 streaming connections to 6 per domain.
   - StreamCore's web interface uses a non-blocking frame update loop (`/frame/<id>.jpg`) that completes each request in **0.4 ms**, allowing 20+ cameras to stream simultaneously without connection stalls.
