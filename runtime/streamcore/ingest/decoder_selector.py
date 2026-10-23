import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DecoderSelection:
    codec: str
    name: str
    decoder_type: str
    provider: str


# Ordered by preferred zero-copy potential. A name is selected only when the
# running GStreamer registry actually contains that element factory and can reach READY.
_HARDWARE_CANDIDATES = {
    "h264": (
        ("nvh264dec", "nvidia-nvcodec"),
        ("nvv4l2decoder", "nvidia-deepstream"),
        ("vah264dec", "va-api"),
        ("vaapih264dec", "va-api"),
    ),
    "h265": (
        ("nvh265dec", "nvidia-nvcodec"),
        ("nvv4l2decoder", "nvidia-deepstream"),
        ("vah265dec", "va-api"),
        ("vaapih265dec", "va-api"),
    ),
    "mpeg4": (
        ("nvmpeg4videodec", "nvidia-nvcodec"),
        ("nvv4l2decoder", "nvidia-deepstream"),
    ),
}

_SOFTWARE = {"h264": "avdec_h264", "h265": "avdec_h265", "mpeg4": "avdec_mpeg4"}


def check_element_status(Gst: Any, element_name: str) -> tuple[bool, str]:
    """Check registry find and ability to create/reach READY."""
    try:
        if Gst.ElementFactory.find(element_name) is None:
            return False, "MISSING"
        element = Gst.ElementFactory.make(element_name)
        if element is None:
            return False, "CREATION_FAILED"
        if hasattr(Gst, "State") and hasattr(element, "set_state"):
            ret = element.set_state(Gst.State.READY)
            element.set_state(Gst.State.NULL)
            if ret == Gst.StateChangeReturn.FAILURE:
                return False, "READY_FAILED"
        return True, "OK"
    except Exception as exc:
        return False, f"ERROR({exc})"


def _available(Gst: Any, element_name: str) -> bool:
    """Require both registry presence and successful plugin-backed construction."""
    ok, _ = check_element_status(Gst, element_name)
    return ok


def validate_gstreamer_dependencies(
    Gst: Any,
    codecs: set[str],
    *,
    prefer_hardware: bool = True,
    fallback_software: bool = True,
) -> dict[str, str]:
    """Validate required GStreamer elements for configured codecs and print a concise capability report."""
    results: dict[str, str] = {}
    # Common required elements
    for el in ("rtspsrc", "fakesink"):
        ok, status = check_element_status(Gst, el)
        results[el] = status
        if not ok:
            raise RuntimeError(f"Missing required GStreamer element: {el}")

    # Codec-specific parsers/depayers
    for codec in sorted(codecs):
        codec_clean = codec.lower().replace("hevc", "h265")
        if codec_clean in ("raw", "none", "synthetic", "test"):
            continue
        if codec_clean == "h264":
            depay, parse = "rtph264depay", "h264parse"
            decoders = ["nvh264dec", "nvv4l2decoder", "avdec_h264"]
        elif codec_clean == "h265":
            depay, parse = "rtph265depay", "h265parse"
            decoders = ["nvh265dec", "nvv4l2decoder", "avdec_h265"]
        elif codec_clean == "mpeg4":
            depay, parse = "rtpmp4vdepay", "mpeg4videoparse"
            decoders = ["nvmpeg4videodec", "nvv4l2decoder", "avdec_mpeg4"]
        else:
            depay, parse = f"rtp{codec_clean}depay", f"{codec_clean}parse"
            decoders = [f"avdec_{codec_clean}"]

        for el in (depay, parse):
            ok, status = check_element_status(Gst, el)
            results[el] = status
            if not ok:
                raise RuntimeError(f"Missing required GStreamer element for {codec_clean}: {el}")

        has_usable_decoder = False
        has_hw_decoder = False
        for dec in decoders:
            ok, status = check_element_status(Gst, dec)
            results[dec] = status
            if ok:
                has_usable_decoder = True
                if not dec.startswith("avdec_"):
                    has_hw_decoder = True

        if prefer_hardware and not fallback_software and not has_hw_decoder:
            raise RuntimeError(f"No hardware decoder available for {codec_clean} and software fallback is disabled")
        if not has_usable_decoder:
            raise RuntimeError(f"No usable decoder available for {codec_clean} (candidates: {', '.join(decoders)})")

    lines = ["GStreamer:"]
    for el, status in results.items():
        lines.append(f"  {el}: {status}")
    print("\n".join(lines), flush=True)
    return results


def select_decoder(Gst: Any, codec: str, requested: str = "auto", *,
                   prefer_hardware: bool = True,
                   fallback_software: bool = True,
                   camera_id: str | None = None) -> DecoderSelection:
    """Select only factories present in Gst's live plugin registry that reach READY."""
    codec = codec.lower().replace("hevc", "h265")
    cam_tag = f"CAM {camera_id}: " if camera_id else ""
    if codec not in _SOFTWARE:
        raise RuntimeError(f"unsupported-codec-{codec}")

    if requested in ("deepstream", "nvds"):
        requested = "nvv4l2decoder"

    if requested != "auto":
        ok, status = check_element_status(Gst, requested)
        if not ok:
            raise RuntimeError(f"{cam_tag}missing-plugin-{requested}")
        software = requested == _SOFTWARE[codec] or requested.startswith("avdec_")
        provider = "nvidia-deepstream" if requested == "nvv4l2decoder" else ("libav" if software else "explicit")
        return DecoderSelection(codec, requested,
                                "software" if software else "hardware",
                                provider)

    if prefer_hardware:
        for name, provider in _HARDWARE_CANDIDATES.get(codec, ()):
            if name == "nvv4l2decoder":
                nvconv_ok, _ = check_element_status(Gst, "nvvideoconvert")
                if not nvconv_ok:
                    continue
            ok, status = check_element_status(Gst, name)
            if ok:
                return DecoderSelection(codec, name, "hardware", provider)
            logger.warning("%sdecoder %s failed READY (%s) -> trying next decoder", cam_tag, name, status)

    software = _SOFTWARE[codec]
    if fallback_software:
        ok, status = check_element_status(Gst, software)
        if ok:
            if prefer_hardware:
                logger.info("%sfalling back to software decoder %s", cam_tag, software)
            return DecoderSelection(codec, software, "software", "libav")
        logger.warning("%ssoftware decoder %s failed READY (%s)", cam_tag, software, status)

    raise RuntimeError(f"no-supported-{codec}-decoder")


def decoder_capabilities(Gst: Any) -> dict[str, list[DecoderSelection]]:
    """Return supported candidates for diagnostics without guessing support."""
    result: dict[str, list[DecoderSelection]] = {}
    for codec, candidates in _HARDWARE_CANDIDATES.items():
        found = [DecoderSelection(codec, name, "hardware", provider)
                 for name, provider in candidates if _available(Gst, name)]
        software = _SOFTWARE[codec]
        if _available(Gst, software):
            found.append(DecoderSelection(codec, software, "software", "libav"))
        result[codec] = found
    return result
