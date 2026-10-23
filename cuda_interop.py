# apps/ingest/cuda_interop.py
"""Zero-copy CUDA memory interop — map GStreamer CUDA buffers to PyTorch tensors.

Pipeline: NVDEC (CUDAMemory NV12) -> appsink -> CUDA pointers ->
torch tensors -> NV12->RGB + resize on GPU -> YOLO tensor batch.
No CPU download in the hot path.
"""
import ctypes
import logging
from typing import Any

import torch
import torch.nn.functional as F

log = logging.getLogger("ingest")

GST_MAP_CUDA = (1 << 16) << 1


class GstVideoFrameC(ctypes.Structure):
    _fields_ = [
        ("raw_info", ctypes.c_byte * 152),
        ("flags", ctypes.c_uint32),
        ("padding1", ctypes.c_uint32),
        ("buffer", ctypes.c_void_p),
        ("meta", ctypes.c_void_p),
        ("id", ctypes.c_int32),
        ("padding2", ctypes.c_uint32),
        ("data", ctypes.c_void_p * 4),
        ("map", ctypes.c_byte * (4 * 104)),
        ("_gst_reserved", ctypes.c_void_p * 4),
    ]


assert ctypes.sizeof(GstVideoFrameC) == 664, (
    f"GstVideoFrameC size mismatch: {ctypes.sizeof(GstVideoFrameC)} != 664"
)


class GstCudaInterop:
    """Singleton access to libgstvideo / libgstcuda for CUDA buffer mapping."""

    _instance = None

    def __init__(self) -> None:
        self.available = False
        self.libgstvideo = None
        self.libgstcuda = None
        try:
            self.libgstvideo = ctypes.CDLL("libgstvideo-1.0.so.0")
            self.libgstvideo.gst_video_frame_map.restype = ctypes.c_int
            self.libgstvideo.gst_video_frame_map.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_int,
            ]
            self.libgstvideo.gst_video_frame_unmap.restype = None
            self.libgstvideo.gst_video_frame_unmap.argtypes = [ctypes.c_void_p]

            self.libgstvideo.gst_video_info_new.restype = ctypes.c_void_p
            self.libgstvideo.gst_video_info_from_caps.restype = ctypes.c_int
            self.libgstvideo.gst_video_info_from_caps.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            self.libgstvideo.gst_video_info_free.restype = None
            self.libgstvideo.gst_video_info_free.argtypes = [ctypes.c_void_p]

            try:
                self.libgstcuda = ctypes.CDLL("libgstcuda-1.0.so.0")
                self.libgstcuda.gst_is_cuda_memory.restype = ctypes.c_int
                self.libgstcuda.gst_is_cuda_memory.argtypes = [ctypes.c_void_p]
                self.libgstcuda.gst_cuda_memory_sync.restype = ctypes.c_int
                self.libgstcuda.gst_cuda_memory_sync.argtypes = [ctypes.c_void_p]
            except Exception:
                self.libgstcuda = None

            self.available = torch.cuda.is_available()
            if self.available:
                log.info("CUDA interop: libgstvideo loaded, GPU mapping available")
        except Exception as exc:
            log.warning(f"CUDA interop unavailable: {exc}")
            self.available = False

    @classmethod
    def get(cls) -> "GstCudaInterop":
        if cls._instance is None:
            cls._instance = GstCudaInterop()
        return cls._instance


class CudaBufferWrapper:
    """Implements __cuda_array_interface__ for zero-copy view of CUDA memory."""

    def __init__(self, ptr: int, shape: tuple, strides: tuple):
        self.__cuda_array_interface__ = {
            "shape": shape,
            "strides": strides,
            "typestr": "|u1",
            "data": (ptr, False),
            "version": 3,
        }


class CudaInterop:
    """Per-camera helper: map CUDA buffers, hold GPU double slots + motion state."""

    def __init__(self, device_id: int = 0) -> None:
        self.device_id = device_id
        self._gpu_slots: list[tuple[torch.Tensor, torch.Tensor] | None] = [None, None]
        self._gpu_shape: tuple[int, int] | None = None
        self._slot_index = 0
        self._prev_y: torch.Tensor | None = None
        self._frames_seen = 0

    def map_frame(
        self, buf: Any, caps: Any, width: int, height: int
    ) -> tuple[torch.Tensor, torch.Tensor] | None:
        """Map an NVDEC CUDAMemory buffer into owned GPU (Y, UV) tensors.

        Device-to-device copy into a reused double slot; unmaps immediately.
        Returns None if mapping is unavailable (caller falls back to CPU).
        """
        interop = GstCudaInterop.get()
        if not interop.available:
            return None
        try:
            from gi.repository import Gst, GstVideo

            if interop.libgstcuda is not None and hasattr(buf, "n_memory") and buf.n_memory() > 0:
                mem = buf.peek_memory(0)
                if mem:
                    interop.libgstcuda.gst_cuda_memory_sync(hash(mem))

            info_ptr = interop.libgstvideo.gst_video_info_new()
            interop.libgstvideo.gst_video_info_from_caps(info_ptr, hash(caps))

            frame = GstVideoFrameC()
            flags = int(Gst.MapFlags.READ) | GST_MAP_CUDA
            ok = interop.libgstvideo.gst_video_frame_map(
                ctypes.byref(frame), info_ptr, hash(buf), flags
            )
            if not ok:
                interop.libgstvideo.gst_video_info_free(info_ptr)
                return None

            y_ptr = frame.data[0]
            uv_ptr = frame.data[1]

            try:
                meta = GstVideo.buffer_get_video_meta(buf)
                if meta and meta.stride:
                    stride_y = int(meta.stride[0])
                    stride_uv = int(meta.stride[1]) if len(meta.stride) > 1 else stride_y
                else:
                    stride_y, stride_uv = width, width
            except Exception:
                stride_y, stride_uv = width, width

            dev = f"cuda:{self.device_id}"
            shape = (height, width)
            if self._gpu_shape != shape or self._gpu_slots[0] is None:
                self._gpu_slots = [
                    (
                        torch.empty((height, width), dtype=torch.uint8, device=dev),
                        torch.empty((height // 2, width), dtype=torch.uint8, device=dev),
                    )
                    for _ in range(2)
                ]
                self._gpu_shape = shape
                self._prev_y = None

            t_y, t_uv = self._gpu_slots[self._slot_index % 2]
            y_wrap = CudaBufferWrapper(y_ptr, (height, stride_y), (stride_y, 1))
            uv_wrap = CudaBufferWrapper(uv_ptr, (height // 2, stride_uv), (stride_uv, 1))
            t_y.copy_(torch.as_tensor(y_wrap, device=dev)[:, :width])
            t_uv.copy_(torch.as_tensor(uv_wrap, device=dev)[:, :width])

            torch.cuda.current_stream().synchronize()
            try:
                interop.libgstvideo.gst_video_frame_unmap(ctypes.byref(frame))
                interop.libgstvideo.gst_video_info_free(info_ptr)
            except Exception:
                pass

            self._slot_index += 1
            return t_y, t_uv
        except Exception as e:
            log.warning(f"CUDA buffer mapping failed: {e}")
            return None

    def has_motion(self, t_y: torch.Tensor, threshold: float = 0.02) -> tuple[bool, float]:
        """GPU frame differencing on the luminance plane."""
        self._frames_seen += 1
        if self._prev_y is None or self._prev_y.shape != t_y.shape:
            self._prev_y = t_y.clone()
            return False, 0.0
        with torch.no_grad():
            diff = (t_y.float() - self._prev_y.float()).abs().mean().item() / 255.0
        self._prev_y.copy_(t_y)
        if self._frames_seen <= 30:  # warmup
            return False, diff
        return diff > threshold, diff


def nv12_to_rgb_cuda(t_y: torch.Tensor, t_uv: torch.Tensor) -> torch.Tensor:
    """NV12 (Y + interleaved UV) uint8 tensors -> RGB uint8 (3, H, W) on CUDA."""
    y = t_y.float().unsqueeze(0)
    h, w = t_y.shape
    uv = t_uv.float().view(h // 2, w // 2, 2)
    u = F.interpolate(uv[:, :, 0].unsqueeze(0).unsqueeze(0), scale_factor=2, mode="nearest").squeeze()
    v = F.interpolate(uv[:, :, 1].unsqueeze(0).unsqueeze(0), scale_factor=2, mode="nearest").squeeze()
    r = (y + 1.402 * (v - 128)).clamp(0, 255)
    g = (y - 0.344136 * (u - 128) - 0.714136 * (v - 128)).clamp(0, 255)
    b = (y + 1.772 * (u - 128)).clamp(0, 255)
    return torch.stack([r.squeeze(0), g.squeeze(0), b.squeeze(0)], dim=0).byte()


class GpuBatchBuilder:
    """Preallocated GPU batch pool: NV12 tensors -> (N, 3, imgsz, imgsz) uint8."""

    def __init__(self, imgsz: int = 640, max_batch_size: int = 8, device: str = "0") -> None:
        self.imgsz = imgsz
        self.max_batch_size = max_batch_size
        self.device = torch.device(f"cuda:{device}" if torch.cuda.is_available() else "cpu")
        self._pool = torch.zeros(
            (max_batch_size, 3, imgsz, imgsz), dtype=torch.uint8, device=self.device
        )
        log.info(f"GPU batch builder: device={self.device}, imgsz={imgsz}, max_batch={max_batch_size}")

    def build(self, frames: list[tuple[torch.Tensor, torch.Tensor]]) -> torch.Tensor:
        n = min(len(frames), self.max_batch_size)
        for i in range(n):
            t_y, t_uv = frames[i]
            rgb = nv12_to_rgb_cuda(t_y, t_uv)
            resized = F.interpolate(
                rgb.unsqueeze(0).float(), size=(self.imgsz, self.imgsz),
                mode="bilinear", align_corners=False,
            ).squeeze(0).byte()
            self._pool[i].copy_(resized)
        return self._pool[:n]


# Backwards-compatible alias (old name used by ai_worker init).
GpuPreprocessor = GpuBatchBuilder
