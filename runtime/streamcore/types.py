import numpy as np
from numpy.typing import NDArray

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

class CameraState(StrEnum):
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"
    STOPPED = "STOPPED"


class CameraHealth(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    OFFLINE = "OFFLINE"
    RECONNECTING = "RECONNECTING"


@dataclass(frozen=True, slots=True)
class CameraFrame:
    camera_id: str
    sequence: int
    timestamp: float  # UTC Unix seconds at decoded-frame receipt; not camera PTS
    received_monotonic: float
    image: NDArray[np.uint8]  # Owned, contiguous BGR image; treat as immutable
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class Detection:
    class_id: int
    label: str
    confidence: float
    x1: float  # Normalized 0..1 source coordinate
    y1: float
    x2: float
    y2: float
    track_id: str | None = None
    attributes: tuple[tuple[str, str], ...] = ()
    normalized: bool = True


@dataclass(frozen=True, slots=True)
class DetectionResult:
    camera_id: str
    frame_sequence: int
    timestamp: float
    detections: tuple[Detection, ...]
    inference_ms: float  # Shared batch wall time, not an apportioned per-image time
    total_latency_ms: float  # Decoded-frame receipt to result completion
    source_width: int = 0
    source_height: int = 0

    @property
    def frame_id(self) -> int:
        return self.frame_sequence


class FramePath(StrEnum):
    GPU_NATIVE = "GPU_NATIVE"
    CPU_FALLBACK = "CPU_FALLBACK"


@dataclass(slots=True)
class GpuFrame:
    camera_id: str
    sequence: int
    capture_monotonic_ns: int
    received_monotonic: float
    width: int
    height: int
    pixel_format: str  # "NV12"
    memory_type: str   # "cuda"
    device_id: int = 0
    pts: int | None = None
    stride_y: int = 0
    stride_uv: int = 0
    source_width: int = 0
    source_height: int = 0
    cuda_tensor: Any = None
    release_callback: Any = None
    y_ptr: int | None = None
    uv_ptr: int | None = None

    @property
    def timestamp(self) -> float:
        return self.received_monotonic

    def to_bgr_cpu(self) -> Any:
        """Explicit CPU download only for diagnostic preview, evidence snapshot, or debugging."""
        import numpy as np
        import torch
        from .gpu_frame import nv12_to_rgb_cuda

        with torch.inference_mode():
            if isinstance(self.cuda_tensor, tuple):
                t_y, t_uv = self.cuda_tensor
                rgb = nv12_to_rgb_cuda(t_y, t_uv)
            elif isinstance(self.cuda_tensor, torch.Tensor):
                rgb = self.cuda_tensor
            else:
                return np.zeros((self.height, self.width, 3), dtype=np.uint8)

            # Convert RGB (3, H, W) float16 [0, 1] to BGR (H, W, 3) uint8 [0, 255] on CPU
            rgb_hwc = (rgb.permute(1, 2, 0) * 255.0).clamp(0, 255).to(torch.uint8).cpu().numpy()
            return rgb_hwc[:, :, ::-1].copy()

    @property
    def image(self) -> Any:
        """Diagnostic preview image compatibility; explicitly downloads to CPU."""
        return self.to_bgr_cpu()

    def release(self) -> None:
        if self.release_callback is not None:
            cb = self.release_callback
            self.release_callback = None
            try:
                cb()
            except Exception:
                pass


@dataclass(slots=True)
class FrameMeta:
    camera_id: str
    sequence: int
    timestamp: float
    received_monotonic: float
    width: int
    height: int
    scale: float = 1.0
    pad_x: float = 0.0
    pad_y: float = 0.0
    device_id: int = 0


@dataclass(slots=True)
class InferenceBatch:
    tensor: Any  # torch.Tensor (N x 3 x imgsz x imgsz)
    frames: list[FrameMeta]
    device_id: int
    batch_size: int

