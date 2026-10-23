"""GPU-native frame abstraction, GStreamer CUDAMemory mapping, and GPU preprocessing."""

import ctypes
import logging
from time import monotonic, monotonic_ns
from typing import Any

import torch
import torch.nn.functional as F

from .types import FrameMeta, FramePath, GpuFrame, InferenceBatch

logger = logging.getLogger(__name__)

GST_MAP_CUDA = (1 << 16) << 1

# C types and structures for GStreamer VideoFrame mapping
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

assert ctypes.sizeof(GstVideoFrameC) == 664, f"GstVideoFrameC size mismatch: {ctypes.sizeof(GstVideoFrameC)} != 664"


class GstCudaInterop:
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
        except Exception as exc:
            logger.warning("GstCudaInterop initialization failed: %s", exc)
            self.available = False

    @classmethod
    def get(cls) -> "GstCudaInterop":
        if cls._instance is None:
            cls._instance = GstCudaInterop()
        return cls._instance


class CudaBufferWrapper:
    """Implements __cuda_array_interface__ for zero-copy view of CUDA memory."""

    def __init__(self, ptr: int, shape: tuple[int, ...], strides: tuple[int, ...], typestr: str = "|u1") -> None:
        self.__cuda_array_interface__ = {
            "shape": shape,
            "typestr": typestr,
            "data": (ptr, False),
            "version": 3,
            "strides": strides,
        }


def extract_gpu_frame(
    buf: Any,
    caps: Any,
    camera_id: str,
    sequence: int,
    device_id: int = 0,
    target_tensors: tuple[torch.Tensor, torch.Tensor] | None = None,
) -> GpuFrame | None:
    """Extract zero-copy GpuFrame from GStreamer buffer with CUDAMemory caps."""
    interop = GstCudaInterop.get()
    if not interop.available:
        return None

    try:
        from gi.repository import Gst, GstVideo

        # Ensure CUDA memory has finished decoding before mapping
        if interop.libgstcuda is not None and hasattr(buf, "n_memory") and buf.n_memory() > 0:
            mem = buf.peek_memory(0)
            if mem:
                interop.libgstcuda.gst_cuda_memory_sync(hash(mem))

        structure = caps.get_structure(0)
        width = structure.get_value("width")
        height = structure.get_value("height")
        format_str = structure.get_value("format") or "NV12"

        info_ptr = interop.libgstvideo.gst_video_info_new()
        interop.libgstvideo.gst_video_info_from_caps(info_ptr, hash(caps))

        frame = GstVideoFrameC()
        flags = int(Gst.MapFlags.READ) | GST_MAP_CUDA
        ok = interop.libgstvideo.gst_video_frame_map(ctypes.byref(frame), info_ptr, hash(buf), flags)
        if not ok:
            logger.warning("Camera %s: gst_video_frame_map returned False! flags=%s", camera_id, flags)
            interop.libgstvideo.gst_video_info_free(info_ptr)
            return None

        if sequence == 1:
            logger.debug("Camera %s: mapped GPU frame #%d (flags=%s)", camera_id, sequence, flags)

        y_ptr = frame.data[0]
        uv_ptr = frame.data[1]

        # Use true hardware pitch / stride from VideoMeta if present, else default
        meta = GstVideo.buffer_get_video_meta(buf)
        if meta and meta.stride:
            stride_y = int(meta.stride[0])
            stride_uv = int(meta.stride[1]) if len(meta.stride) > 1 else stride_y
        else:
            info = GstVideo.VideoInfo.new_from_caps(caps)
            stride_y = int(info.stride[0]) if info and info.stride else width
            stride_uv = int(info.stride[1]) if info and len(info.stride) > 1 else width

        pts = buf.pts if hasattr(buf, "pts") else None
        now_ns = monotonic_ns()
        now_mono = monotonic()

        # Unmap function closes GstVideoFrame
        unmapped = False

        def release() -> None:
            nonlocal unmapped
            if not unmapped:
                unmapped = True
                try:
                    interop.libgstvideo.gst_video_frame_unmap(ctypes.byref(frame))
                    interop.libgstvideo.gst_video_info_free(info_ptr)
                except Exception:
                    pass

        # Create PyTorch CUDA tensors via GPU device-to-device copy
        y_wrap = CudaBufferWrapper(y_ptr, (height, stride_y), (stride_y, 1))
        uv_wrap = CudaBufferWrapper(uv_ptr, (height // 2, stride_uv), (stride_uv, 1))

        if target_tensors is not None:
            t_y, t_uv = target_tensors
            t_y.copy_(torch.as_tensor(y_wrap, device=f"cuda:{device_id}")[:, :width])
            t_uv.copy_(torch.as_tensor(uv_wrap, device=f"cuda:{device_id}")[:, :width])
        else:
            t_y = torch.as_tensor(y_wrap, device=f"cuda:{device_id}")[:, :width].clone()
            t_uv = torch.as_tensor(uv_wrap, device=f"cuda:{device_id}")[:, :width].clone()

        # Safely unmap GStreamer frame immediately on the ingest thread after D2D copy
        # to prevent asynchronous GMMU unmap collisions and NVIDIA driver kernel crashes
        torch.cuda.current_stream().synchronize()
        release()

        return GpuFrame(
            camera_id=camera_id,
            sequence=sequence,
            capture_monotonic_ns=now_ns,
            received_monotonic=now_mono,
            width=width,
            height=height,
            stride_y=stride_y,
            stride_uv=stride_uv,
            source_width=width,
            source_height=height,
            pixel_format=format_str,
            memory_type="cuda",
            device_id=device_id,
            pts=pts,
            cuda_tensor=(t_y, t_uv),
            release_callback=release,
            y_ptr=y_ptr,
            uv_ptr=uv_ptr,
        )
    except Exception as exc:
        logger.warning("Failed to extract GPU frame for %s: %s", camera_id, exc, exc_info=True)
        return None


@torch.inference_mode()
def nv12_to_rgb_cuda(t_y: torch.Tensor, t_uv: torch.Tensor) -> torch.Tensor:
    """Convert NV12 Y and UV tensors to RGB tensor directly on CUDA in float16."""
    h, w = t_y.shape
    u = t_uv[:, 0::2].unsqueeze(0).unsqueeze(0).float()
    v = t_uv[:, 1::2].unsqueeze(0).unsqueeze(0).float()

    u_up = F.interpolate(u, size=(h, w), mode="nearest").squeeze(0).squeeze(0)
    v_up = F.interpolate(v, size=(h, w), mode="nearest").squeeze(0).squeeze(0)
    y_f = t_y.float()

    # BT.601 conversion
    r = y_f + 1.402 * (v_up - 128.0)
    g = y_f - 0.344136 * (u_up - 128.0) - 0.714136 * (v_up - 128.0)
    b = y_f + 1.772 * (u_up - 128.0)

    rgb = torch.stack([r, g, b], dim=0).clamp(0, 255) / 255.0
    return rgb.to(torch.float16)


@torch.inference_mode()
def letterbox_gpu(
    rgb: torch.Tensor,
    target_size: int = 640,
) -> tuple[torch.Tensor, float, float, float]:
    """Letterbox (3, H, W) RGB tensor into (3, target_size, target_size) FP16 tensor on GPU.

    Returns:
        (letterboxed_tensor, scale, pad_x, pad_y)
    """
    _, h, w = rgb.shape
    scale = min(target_size / h, target_size / w)
    new_w = int(round(w * scale))
    new_h = int(round(h * scale))

    # Resize keeping aspect ratio
    resized = F.interpolate(
        rgb.unsqueeze(0),
        size=(new_h, new_w),
        mode="bilinear",
        align_corners=False,
    ).squeeze(0)

    pad_x = (target_size - new_w) / 2.0
    pad_y = (target_size - new_h) / 2.0

    pad_left = int(round(pad_x - 0.1))
    pad_right = target_size - new_w - pad_left
    pad_top = int(round(pad_y - 0.1))
    pad_bottom = target_size - new_h - pad_top

    padded = F.pad(resized, (pad_left, pad_right, pad_top, pad_bottom), value=114.0 / 255.0)
    return padded, scale, float(pad_left), float(pad_top)


def unletterbox_boxes(
    boxes: list[list[float]],
    scale: float,
    pad_x: float,
    pad_y: float,
    orig_w: int,
    orig_h: int,
) -> list[list[float]]:
    """Map letterbox 640x640 bounding box coordinates back to original frame (x1, y1, x2, y2)."""
    unletterboxed = []
    for x1, y1, x2, y2 in boxes:
        ux1 = max(0.0, min(float(orig_w), (x1 - pad_x) / scale))
        uy1 = max(0.0, min(float(orig_h), (y1 - pad_y) / scale))
        ux2 = max(0.0, min(float(orig_w), (x2 - pad_x) / scale))
        uy2 = max(0.0, min(float(orig_h), (y2 - pad_y) / scale))
        unletterboxed.append([ux1, uy1, ux2, uy2])
    return unletterboxed


class GpuPreprocessor:
    """Preallocates batch tensor on GPU and processes list of GpuFrames directly on CUDA."""

    def __init__(
        self,
        max_batch_size: int = 8,
        imgsz: int = 640,
        device_id: int = 0,
        dtype: torch.dtype = torch.float16,
    ) -> None:
        self.max_batch_size = max_batch_size
        self.imgsz = imgsz
        self.device = torch.device(f"cuda:{device_id}" if torch.cuda.is_available() else "cpu")
        self.dtype = dtype

        # Preallocated GPU batch tensor to avoid per-frame CUDA allocations
        if torch.cuda.is_available():
            self._batch_pool = torch.zeros(
                (max_batch_size, 3, imgsz, imgsz),
                dtype=dtype,
                device=self.device,
            )
        else:
            self._batch_pool = torch.zeros((max_batch_size, 3, imgsz, imgsz), dtype=dtype)

    @torch.inference_mode()
    def preprocess(self, gpu_frames: list[GpuFrame]) -> tuple[InferenceBatch, float]:
        """Preprocess frames into GPU batch tensor without CPU transfer.

        Returns (InferenceBatch, preprocess_time_ms).
        """
        n = min(len(gpu_frames), self.max_batch_size)
        meta_list: list[FrameMeta] = []
        start = monotonic()

        for i in range(n):
            gf = gpu_frames[i]
            if isinstance(gf.cuda_tensor, tuple):
                t_y, t_uv = gf.cuda_tensor
                rgb = nv12_to_rgb_cuda(t_y, t_uv)
            elif isinstance(gf.cuda_tensor, torch.Tensor):
                rgb = gf.cuda_tensor
            else:
                # Fallback if tensor format is unknown
                rgb = torch.zeros((3, gf.height, gf.width), dtype=self.dtype, device=self.device)

            padded, scale, pad_x, pad_y = letterbox_gpu(rgb, self.imgsz)
            self._batch_pool[i].copy_(padded)

            meta_list.append(
                FrameMeta(
                    camera_id=gf.camera_id,
                    sequence=gf.sequence,
                    timestamp=gf.received_monotonic,
                    received_monotonic=gf.received_monotonic,
                    width=gf.source_width,
                    height=gf.source_height,
                    scale=scale,
                    pad_x=pad_x,
                    pad_y=pad_y,
                    device_id=gf.device_id,
                )
            )

        duration_ms = (monotonic() - start) * 1000.0
        batch_slice = self._batch_pool[:n]
        batch = InferenceBatch(
            tensor=batch_slice,
            frames=meta_list,
            device_id=gf.device_id if n > 0 else 0,
            batch_size=n,
        )
        return batch, duration_ms
