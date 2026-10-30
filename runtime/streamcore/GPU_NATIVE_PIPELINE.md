# AIVISRA StreamCore — Stage 4: GPU-Native Pipeline Documentation

## 1. Executive Summary & Objective

Stage 4 transitions AIVISRA StreamCore from CPU-buffered ingestion to an end-to-end **GPU-native frame pipeline**.

### The Problem in Legacy Architectures
In typical multi-stream video analytics pipelines, frames undergo expensive back-and-forth PCIe bus transfers:
$$\text{NVDEC (GPU)} \xrightarrow{\text{PCIe Download}} \text{CPU Host (BGR / NumPy)} \xrightarrow{\text{RAM Copy}} \text{LatestFrameStore} \xrightarrow{\text{PCIe Upload}} \text{YOLO (GPU)}$$
At 30–50 cameras and 25–30 FPS, these transfers choke host memory bandwidth, consume excess CPU cores, and inflate frame latency.

### The Stage 4 GPU-Native Architecture
The new pipeline eliminates the GPU $\to$ CPU $\to$ GPU round-trip for production AI inference:
$$\text{RTSP} \to \text{NVDEC} \to \text{GstCudaMemory (NV12)} \to \text{Zero-Copy PyTorch Tensor} \to \text{CUDA FP16 Preprocess} \to \text{Batched YOLO11} \to \text{Detections}$$

**Strict Zero-Copy Guarantee**: In production AI inference mode, `cpu_frame_download_count == 0`. Host memory transfers are strictly quarantined to low-frequency diagnostic previews (1 FPS) or explicit forensic snapshots on demand.

---

## 2. Memory Flow & Pipeline Architecture

```
                    ┌──────────────────────────────────────────────┐
                    │               RTSP / NVR Ingest              │
                    └──────────────────────┬───────────────────────┘
                                           │
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │           NVIDIA NVDEC (nvh264dec)           │
                    │        Hardware Decode directly on GPU       │
                    └──────────────────────┬───────────────────────┘
                                           │
                                           │  video/x-raw(memory:CUDAMemory), format=NV12
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │                   appsink                    │
                    │  Mapped via gst_video_frame_map + MAP_CUDA   │
                    └──────────────────────┬───────────────────────┘
                                           │
                                           │  Direct CUDA Device Pointers:
                                           │  Y Plane: ptr0, UV Plane: ptr1
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │               GpuFrame (CUDA)                │
                    │       Wrapped via __cuda_array_interface__   │
                    │         Zero CPU Memory Allocation           │
                    └──────────────────────┬───────────────────────┘
                                           │
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │               LatestFrameStore               │
                    │      Atomic slot swap; release callback      │
                    └──────────────────────┬───────────────────────┘
                                           │
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │             LatestFrameScheduler             │
                    │      Latency-aware dynamic batching          │
                    │  (max_batch_size: 8, max_batch_wait_ms: 15)  │
                    └──────────────────────┬───────────────────────┘
                                           │
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │               GpuPreprocessor                │
                    │  1. BT.601 NV12 → RGB Float16 on CUDA        │
                    │  2. Bilinear aspect-ratio resize on CUDA     │
                    │  3. Symmetrical letterbox pad (114/255)      │
                    │  4. Zero-allocation copy into preallocated   │
                    │     CUDA batch pool: (N, 3, 640, 640) FP16   │
                    └──────────────────────┬───────────────────────┘
                                           │
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │            Ultralytics YOLO11 FP16           │
                    │          Direct CUDA Forward Pass            │
                    └──────────────────────┬───────────────────────┘
                                           │
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │             unletterbox_boxes                │
                    │  Exact coordinate mapping back to orig W x H │
                    └──────────────────────┬───────────────────────┘
                                           │
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │          Interactive Technical Demo          │
                    │  WebRTC Video + HTML5 Canvas BBox Overlay    │
                    │  GET /api/detections/{id} at 30-60 Hz        │
                    └──────────────────────────────────────────────┘
```

---

## 3. GPU Memory Interop: Technical Details

### 3.1 GStreamer CUDAMemory Mapping
GStreamer `nvh264dec` outputs buffers tagged with `memory:CUDAMemory`.
By utilizing `libgstvideo-1.0.so.0` and flags `GST_MAP_READ | GST_MAP_CUDA` ($0x20000$):
```python
flags = int(Gst.MapFlags.READ) | (1 << 17) # GST_MAP_CUDA
ok = libgstvideo.gst_video_frame_map(byref(frame_c), info_ptr, buf_ptr, flags)
```
This populates the C struct `_GstVideoFrame` with real 64-bit CUDA device pointers:
- `frame.data[0]`: CUDA pointer to Luminance ($Y$) plane.
- `frame.data[1]`: CUDA pointer to Chrominance ($UV$) interleaved plane.

### 3.2 Zero-Copy PyTorch Wrapping via `__cuda_array_interface__`
PyTorch wraps these device pointers without any intermediate copies or host transfers:
```python
class CudaBufferWrapper:
    def __init__(self, ptr: int, shape: tuple[int, ...], strides: tuple[int, ...], typestr: str = "|u1"):
        self.__cuda_array_interface__ = {
            "shape": shape,
            "typestr": typestr,
            "data": (ptr, False),
            "version": 3,
            "strides": strides,
        }

t_y = torch.as_tensor(CudaBufferWrapper(y_ptr, (height, stride_y), (stride_y, 1)), device="cuda:0")[:, :width]
t_uv = torch.as_tensor(CudaBufferWrapper(uv_ptr, (height // 2, stride_uv), (stride_uv, 1)), device="cuda:0")[:, :width]
```

### 3.3 CUDA FP16 Preprocessing & Letterbox
Color conversion ($BT.601$) is executed directly as tensor arithmetic on CUDA:
$$R = Y + 1.402(V - 128)$$
$$G = Y - 0.344136(U - 128) - 0.714136(V - 128)$$
$$B = Y + 1.772(U - 128)$$
Followed by bilinear interpolation and symmetrical letterbox padding into a preallocated CUDA batch buffer $(N, 3, 640, 640)$ in $\text{float16}$. Execution time is $<0.6\text{ ms}$ per frame on NVIDIA RTX 5070.

---

## 4. Latency-Aware Dynamic Batching

The scheduling system in [`LatestFrameScheduler`](runtime/streamcore/scheduling/frame_scheduler.py) and [`StreamCore.process_tick()`](runtime/streamcore/engine.py) guarantees:
1. **Configurable Batching**: `max_batch_size: 8`, `max_batch_wait_ms: 15.0`.
2. **Immediate Dispatch**: If $N \ge \text{max\_batch\_size}$ frames are ready, the batch dispatches immediately with zero wait time.
3. **Bounded Waiting**: If fewer streams are ready, the system accumulates ready streams up to `max_batch_wait_ms` (15 ms), then dispatches immediately.
4. **Fair Round-Robin**: Stream rotation ensures that no stream suffers starvation when stream count exceeds batch capacity.
5. **Freshness & Stale Frame Drop**: Frames exceeding `max_frame_age_seconds` are dropped before inference, maintaining freshness $<30\text{ ms}$.

---

## 5. Interactive Technical Demo

The preview server incorporates a multi-mode browser demonstration running on port `8765`:

### How to Run the Demo:
```bash
python -m mis.runtime.streamcore.main --config config/streamcore/app.yaml --demo
```

### Key Demo Capabilities:
- **Left Panel**: Camera selector list displaying live connectivity and decoded status.
- **Center Stage**: Live video stream (MediaMTX WebRTC with MJPEG fallback) overlaid with an HTML5 `<canvas>`.
  - The canvas queries `GET /api/detections/{camera_id}` at $\sim 30\text{ Hz}$.
  - Renders crisp color-coded bounding boxes, class names, and confidence scores mapped accurately to source video coordinates.
- **Right Panel (Real-Time Telemetry HUD)**:
  - Architecture: `GPU_NATIVE` (verified green badge)
  - CPU Host Downloads: `0 frames` (verified green badge)
  - Live Rates: Decoded FPS vs AI Inference FPS
  - Latencies: Batch wait ms, Preprocessing ms, Inference ms, Result latency ms
  - Hardware: GPU Core %, NVDEC Decode %, VRAM Used / Total, Host Process CPU %

### REST API Endpoints:
| Endpoint | Method | Description |
|---|---|---|
| `/` or `/demo` | `GET` | Interactive Live Video & Canvas AI Demo UI |
| `/api/detections/{camera_id}` | `GET` | Latest bounding boxes, normalized coordinates, latencies, and `GPU_NATIVE` badge |
| `/api/detections` | `GET` | Map of latest detections across all cameras |
| `/api/status` | `GET` | Complete metrics, resource utilization, and health status |
| `/api/frames/batch` | `GET` | Single-connection batch thumbnail fetcher for grid view |

---

## 6. Verification and Empirical Benchmark Results

### 6.1 Unit Test Suite
- Total Tests: **55 / 55 Passing**
- Coverage:
  - Tests 1–35: Stage 3 Multi-RTSP, Reconnection, Ingest-only, Profiles, Isolation.
  - Tests 36–55: GpuFrame metadata, CUDAMemory interop, Zero CPU downloads, CUDA letterboxing, Coordinate unmapping, Dummy & Ultralytics infer_gpu interfaces, Latency-aware batching, Fairness rotation, Stale dropping, Detection REST APIs, CLI `--demo` and `--frame-path`.

```
============================== 55 passed in 2.42s ==============================
```

### 6.2 Physical 5-Camera Hardware Benchmark (Profile 5)
Tested with 5 physical independent RTSP streams (`CAM001`–`CAM005`) on NVIDIA GeForce RTX 5070 (12GB VRAM) and AMD Ryzen 7 9700X:

| Metric | Measured Value | Requirement / Threshold | Status |
|---|---|---|---|
| Active Physical Streams | **5 / 5 online** | 5 physical streams | PASS |
| Stream Health | **5 Healthy, 0 Degraded** | All healthy | PASS |
| Aggregate Decoded FPS | **125.0 FPS** (25.0 FPS / stream) | $\ge 120\text{ FPS}$ | PASS |
| AI Frame Path | **GPU_NATIVE** | No CPU transfers | PASS |
| CPU Frame Downloads (AI) | **0 frames** | Strictly 0 | PASS |
| Host Process CPU | **9.7%** | $<90.0\%$ | PASS |
| Host RAM (RSS) | **2458.2 MiB** | Stable | PASS |
| RSS Memory Growth | **0.0 MiB** | $<150\text{ MiB}$ | PASS |
| Memory Leak Detected | **False** | False | PASS |
| GPU Core Utilization | **5.0%** | $<95.0\%$ | PASS |
| NVDEC Decoder Utilization | **3.0%** | $<95.0\%$ | PASS |
| GPU VRAM Usage | **2.1 GiB / 12.0 GiB** | $<10.0\text{ GiB}$ | PASS |
| Frame Age (Freshness) | **avg 26.5 ms \| p95 28.3 ms** | $<500\text{ ms}$ | PASS |
| Reconnect Total | **0** | Isolated | PASS |
| Benchmark Result | **PASS** | PASS | PASS |
