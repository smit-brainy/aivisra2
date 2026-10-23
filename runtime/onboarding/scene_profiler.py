from __future__ import annotations

from collections import Counter
import json
import logging
from typing import Any
import urllib.request
import urllib.error

from .types import FrameSample, SceneProfile, SceneType

logger = logging.getLogger(__name__)


class SceneProfiler:
    """Analyzes representative frames using existing YOLO detector and optional local VLM."""

    def __init__(
        self,
        detector: Any = None,
        local_vlm_url: str = "http://localhost:11434",
        vlm_model: str = "llava",
        enable_vlm: bool = True,
    ) -> None:
        self.detector = detector
        self.local_vlm_url = local_vlm_url
        self.vlm_model = vlm_model
        self.enable_vlm = enable_vlm

    def analyze(
        self,
        samples_or_camera_id: Any,
        camera_id_or_samples: Any = None,
        camera_id: str | None = None,
    ) -> SceneProfile:
        """Analyze sampled frames to extract objects, scene type, and attributes."""
        if isinstance(samples_or_camera_id, str):
            cam_id = samples_or_camera_id
            samples = camera_id_or_samples or []
        else:
            samples = samples_or_camera_id or []
            cam_id = camera_id or (camera_id_or_samples if isinstance(camera_id_or_samples, str) else (samples[0].camera_id if samples else "UNKNOWN"))

        if not samples:
            return SceneProfile(
                camera_id=cam_id,
                scene_type=SceneType.UNKNOWN,
                scene_confidence=0.0,
                frames_analyzed=0,
                objects=[],
                attributes=[],
                analysis_method="none",
                limitations=["No usable frames captured during observation window."],
            )

        # 1. Run object detection across samples
        detected_per_frame: list[list[dict[str, Any]]] = []
        for sample in samples:
            dets = self._detect_frame(sample)
            detected_per_frame.append(dets)

        # 2. Aggregate detected objects
        object_counts: Counter[str] = Counter()
        for frame_dets in detected_per_frame:
            frame_classes = {d["label"].lower() for d in frame_dets}
            for cls in frame_classes:
                object_counts[cls] += 1

        total_frames = len(samples)
        # Visible objects: observed in at least 15% of frames or top occurrences
        visible_objects = [
            cls for cls, count in object_counts.most_common()
            if (count / float(total_frames) >= 0.15) or count >= 2
        ]
        if not visible_objects and object_counts:
            visible_objects = [cls for cls, _ in object_counts.most_common(3)]

        # 3. Check for local VLM
        vlm_result = None
        if self.enable_vlm:
            vlm_result = self._try_local_vlm(samples[len(samples) // 2])

        if vlm_result is not None:
            scene_type = vlm_result.get("scene_type", SceneType.UNKNOWN)
            confidence = float(vlm_result.get("scene_confidence", 0.80))
            attributes = list(vlm_result.get("attributes", []))
            method = "local_vlm"
            combined_objects = sorted(list(set(visible_objects) | set(vlm_result.get("objects", []))))
        else:
            scene_type, confidence, attributes = self._classify_scene_heuristics(
                visible_objects, object_counts, detected_per_frame, total_frames
            )
            method = "yolo_heuristic"
            combined_objects = visible_objects

        limitations = [
            "Confidence is an automated estimate based on sampled frames.",
        ]
        if total_frames < 10:
            limitations.append(f"Insufficient usable frames captured ({total_frames} samples); confidence estimate degraded.")
            confidence = min(confidence, 0.65)
        if any(v in ("car", "truck", "motorcycle", "bus") for v in combined_objects):
            limitations.append("Vehicle presence does not guarantee readable license plates.")
        if "person" in combined_objects:
            limitations.append("Human presence does not prove mandatory PPE requirements.")
        if scene_type in (SceneType.ENTRANCE, SceneType.RETAIL):
            limitations.append("Entrance scene requires user tripwire/line setup for entry/exit counts.")
        if scene_type == SceneType.FACTORY:
            limitations.append("Factory environment requires configured hazard zones for restricted monitoring.")

        return SceneProfile(
            camera_id=cam_id,
            scene_type=scene_type,
            scene_confidence=round(confidence, 2),
            frames_analyzed=total_frames,
            objects=combined_objects,
            attributes=attributes,
            analysis_method=method,
            limitations=limitations,
        )

    def _detect_frame(self, sample: FrameSample) -> list[dict[str, Any]]:
        """Run detector on single frame sample or extract mock detections."""
        if self.detector is None:
            return []

        try:
            # If standard detector interface infer([CameraFrame])
            from ..streamcore.types import CameraFrame
            cf = CameraFrame(
                camera_id=sample.camera_id,
                sequence=sample.sequence,
                timestamp=sample.timestamp,
                received_monotonic=sample.timestamp,
                image=sample.image_bgr,
                width=sample.width,
                height=sample.height,
            )
            results = self.detector.infer([cf])
            if results and results[0].detections:
                return [
                    {"label": d.label, "confidence": d.confidence, "class_id": d.class_id}
                    for d in results[0].detections
                ]
        except Exception as exc:
            logger.debug("detector_infer_sample_failed", extra={"reason": str(exc)})

        return []

    def _classify_scene_heuristics(
        self,
        visible_objects: list[str],
        object_counts: Counter[str],
        detected_per_frame: list[list[dict[str, Any]]],
        total_frames: int,
    ) -> tuple[str, float, list[str]]:
        """Heuristic scene classification based on detected object signatures and attributes."""
        attributes: list[str] = []
        vehicles = {"car", "truck", "bus", "motorcycle"}
        office_items = {"chair", "laptop", "keyboard", "tv", "desk", "computer"}
        retail_items = {"bottle", "cup", "wine glass", "couch", "dining table", "refrigerator"}
        industrial_items = {"forklift", "truck", "machinery", "barrel", "box", "helmet"}

        has_vehicles = any(v in visible_objects for v in vehicles)
        has_people = "person" in visible_objects
        has_office = any(o in visible_objects for o in office_items)
        has_retail = any(r in visible_objects for r in retail_items)
        has_industrial = any(i in visible_objects for i in industrial_items)

        if has_people:
            attributes.append("people_present")
            # Movement check across frames
            if object_counts["person"] > 1:
                attributes.append("people_movement")

        if has_vehicles:
            attributes.append("vehicle_traffic")
            attributes.append("outdoor")

        # Heuristic rules
        if has_vehicles and not has_office:
            car_ratio = object_counts["car"] / float(total_frames) if "car" in object_counts else 0.0
            if car_ratio >= 0.6 and not has_people:
                attributes.append("parking_area")
                return SceneType.PARKING, 0.84, attributes
            attributes.append("traffic_way")
            return SceneType.ROAD, 0.81, attributes

        if has_industrial:
            attributes.extend(["indoor", "industrial_area", "machinery"])
            return SceneType.FACTORY, 0.78, attributes

        if has_people and has_office:
            attributes.extend(["indoor", "workstations"])
            return SceneType.OFFICE, 0.82, attributes

        if has_people and has_retail:
            attributes.extend(["indoor", "customer_area", "counter"])
            return SceneType.RETAIL, 0.76, attributes

        if has_people and not has_vehicles:
            # Person presence without heavy office/vehicles often entrance or lobby
            person_ratio = object_counts["person"] / float(total_frames)
            if person_ratio >= 0.5:
                attributes.extend(["indoor", "entrance/exit", "pedestrian_flow"])
                return SceneType.ENTRANCE, 0.79, attributes
            attributes.extend(["indoor", "common_area"])
            return SceneType.OFFICE, 0.65, attributes

        if not visible_objects:
            return SceneType.UNKNOWN, 0.25, ["empty_or_low_light"]

        attributes.append("general_environment")
        return SceneType.OUTDOOR if has_vehicles else SceneType.UNKNOWN, 0.60, attributes

    def _try_local_vlm(self, sample: FrameSample) -> dict[str, Any] | None:
        """Attempt querying a local Vision-Language Model if available and configured."""
        try:
            # 1. Query Ollama /api/tags to check if a vision model is loaded
            req = urllib.request.Request(f"{self.local_vlm_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                data = json.loads(resp.read().decode())
                models = [m.get("name", "") for m in data.get("models", [])]
                # Check for known vision models: llava, bakllava, minicpm-v, moondream
                vision_model = next((m for m in models if any(k in m.lower() for k in ("llava", "vision", "moondream", "minicpm"))), None)
                if not vision_model:
                    return None

            # 2. If vision model exists, send frame thumbnail
            import base64
            import cv2
            small = cv2.resize(sample.image_bgr, (320, 180))
            _, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 70])
            b64_img = base64.b64encode(buf.tobytes()).decode("ascii")

            prompt = (
                "Identify scene type (entrance, parking, road, factory, warehouse, retail, office, outdoor), "
                "visible objects, and attributes. Output strictly in JSON format with keys: "
                "scene_type, scene_confidence, objects, attributes."
            )
            payload = {
                "model": vision_model,
                "prompt": prompt,
                "images": [b64_img],
                "stream": False,
                "format": "json",
            }
            body = json.dumps(payload).encode("utf-8")
            post_req = urllib.request.Request(
                f"{self.local_vlm_url}/api/generate",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(post_req, timeout=5.0) as post_resp:
                res_data = json.loads(post_resp.read().decode())
                raw_response = res_data.get("response", "{}")
                parsed = json.loads(raw_response)
                return parsed
        except Exception:
            return None
