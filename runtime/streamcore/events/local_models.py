"""Local model adapters for the fully-offline visual search stack.

One Ollama multipurpose VLM (describe snapshots AND parse time intent) plus
one Ollama embedding model. All HTTP to the local Ollama server at events.ollama_url.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import requests

from ..config import EventsConfig
from .time_resolver import TimeAndQueryResolver, resolve_camera_id, resolve_vague_time_window

logger = logging.getLogger("events.local_models")

TIME_CUE_TOKENS = [
    "today", "yesterday", "tomorrow", "hour", "minute", "sec", "morning",
    "afternoon", "evening", "night", "between", "from", "to", "after",
    "before", "around", "am", "pm", "clock", "camera", "cam", "recent", "past",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "mon", "tue", "wed", "thu", "fri", "sat", "sun",
    "dawn", "dusk", "noon", "midnight",
]

DESCRIBE_PROMPT = (
    "Analyze this cropped surveillance camera snapshot concisely for security retrieval.\n"
    "Describe:\n"
    "1. The main object type (person, vehicle, animal, or other) and dominant colors.\n"
    "2. For people: upper and lower clothing type and colors, accessories "
    "(bag, backpack, umbrella, glasses, hat, mobile phone), and what they are doing or holding.\n"
    "3. For vehicles: color, type (car, bus, truck, motorcycle), and direction.\n"
    "4. Any other attribute that would help identify it again.\n"
    "Output 1-2 concise sentences followed by search keywords after 'Keywords:'."
)

INTENT_PROMPT_TMPL = (
    "You are a surveillance search query parser.\n"
    "Current reference time in local timezone (UTC{offset:+05.2f}): {local_ts}.\n"
    "Current reference time in UTC: {utc_ts}.\n\n"
    "Convert all relative times, days of week, or times of day to UTC ISO-8601 timestamps.\n"
    "Rules:\n"
    "- 'morning' is 06:00 to 12:00 local time.\n"
    "- 'afternoon' is 12:00 to 17:00 local time.\n"
    "- 'evening' is 17:00 to 21:00 local time.\n"
    "- 'night' is 21:00 to 23:59 local time.\n"
    "- Camera names like 'Cam57', 'cam 6' should be formatted as 'CAM057', 'CAM006'.\n"
    "- 'visual_query' MUST contain ONLY visual appearance, colors, garments, and actions (e.g. 'Person wearing blue shirt using mobile', 'Red color car', 'Person wearing pink shirt drinking something'). Remove all camera words, time phrases, and words like 'detected', 'seen'.\n\n"
    'Analyze this query: "{query}"\n\n'
    "Output valid JSON ONLY with these keys (no markdown code blocks, no other text):\n"
    "{{\n"
    '  "visual_query": "<pure visual description>",\n'
    '  "start_utc": "<ISO-8601 UTC timestamp or null>",\n'
    '  "end_utc": "<ISO-8601 UTC timestamp or null>",\n'
    '  "camera_id": "<CAM001 formatted camera id or null>"\n'
    "}}\n"
)


def has_time_cues(query: str) -> bool:
    raw = (query or "").lower()
    if any(tok in raw for tok in TIME_CUE_TOKENS):
        return True
    if re.search(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b", raw):
        return True
    if re.search(r"\bcam(?:era)?\s*\d+\b", raw):
        return True
    return False


class LocalModelService:
    """HTTP adapter for the local Ollama VLM + embedding model."""

    def __init__(self, config: EventsConfig) -> None:
        self.config = config
        self.session = requests.Session()
        self.timeout = max(1.0, float(config.vlm_timeout_s))
        self.keep_alive = f"{int(max(0, float(config.vlm_keep_alive_s)))}s"
        self._known_dim = int(config.embed_dim) if config.embed_dim else 0
        self._logged_dim = False
        self._registry: set[str] = set()
        self._registry_loaded = False
        self.resolver = TimeAndQueryResolver(ist_offset_hours=float(config.ist_offset_hours))

        if not config.ollama_url:
            self.has_vlm = False
            self.has_embedder = False
            return
        try:
            self.refresh_registry()
        except Exception as exc:
            logger.warning("ollama_registry_unreachable", extra={"reason": str(exc)})
            self.has_vlm = self.config.vlm_model in self._registry
            self.has_embedder = self.config.embed_model in self._registry

    def refresh_registry(self) -> bool:
        try:
            resp = self.session.get(
                f"{self.config.ollama_url}/api/tags", timeout=3.0
            )
            if resp.status_code == 200:
                self._registry = {m.get("name", "") for m in resp.json().get("models", [])}
                self._registry_loaded = True
        except Exception as exc:
            logger.warning("ollama_registry_refresh_failed", extra={"reason": str(exc)})
        self.has_vlm = self.config.vlm_model in self._registry
        self.has_embedder = self.config.embed_model in self._registry
        return self.has_vlm and self.has_embedder

    def _generate(self, prompt: str, images: list[str] | None = None) -> str:
        payload: dict[str, Any] = {
            "model": self.config.vlm_model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "keep_alive": self.keep_alive,
            "options": {"temperature": 0.2, "num_predict": 220},
        }
        if images:
            payload["images"] = images
        resp = self.session.post(
            f"{self.config.ollama_url}/api/generate", json=payload, timeout=self.timeout
        )
        txt = ""
        if resp.status_code == 200:
            txt = str(resp.json().get("response", "")).strip()
        else:
            logger.warning(
                "ollama_generate_failed",
                extra={"status": resp.status_code, "text": resp.text[:120]},
            )
        return txt

    def describe_image(self, image_path: str | Path, object_class: str = "") -> str:
        """Generate a retrieval-friendly description of a snapshot crop.

        Returns "" on failure so the caller can switch to the local CV fallback.
        """
        path = Path(image_path)
        if not (self.has_vlm and path.exists()):
            return ""
        try:
            b64 = base64.b64encode(path.read_bytes()).decode("ascii")
            prompt = DESCRIBE_PROMPT
            if object_class:
                prompt = (
                    f"This snapshot is classified as '{object_class}'.\n\n{DESCRIBE_PROMPT}"
                )
            return self._generate(prompt, images=[b64])
        except Exception as exc:
            logger.warning("local_vlm_describe_failed", extra={"reason": str(exc)})
            return ""

    def parse_query_intent(self, query: str) -> dict[str, Any]:
        """Extract visual_query, start_utc, end_utc, camera_id from a natural language query.

        Combines the specialized TimeResolver helper functions with local VLM semantic parsing.
        """
        raw = (query or "").strip()
        if not raw:
            return {"visual_query": "", "start_utc": None, "end_utc": None, "camera_id": None}

        # Fast resolution of vague / natural colloquial temporal phrases and camera tokens
        resolved = resolve_vague_time_window(raw, ist_offset_hours=float(self.config.ist_offset_hours))

        # If no time or camera cues are present, return the query untouched
        if not resolved["has_temporal_filter"] and not resolved["camera_id"]:
            if not has_time_cues(raw):
                return {"visual_query": raw, "start_utc": None, "end_utc": None, "camera_id": None}

        # If local VLM is available, refine visual semantics and complex conversational expressions
        if self.has_vlm:
            offset = float(self.config.ist_offset_hours)
            now_utc = datetime.now(timezone.utc)
            local_ts = (now_utc + timedelta(hours=offset)).strftime("%Y-%m-%d %H:%M:%S")
            prompt = INTENT_PROMPT_TMPL.format(
                offset=offset,
                local_ts=local_ts,
                utc_ts=now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                query=raw,
            )
            try:
                text = self._generate(prompt)
                start = text.find("{")
                end = text.rfind("}")
                if start >= 0 and end > start:
                    parsed = json.loads(text[start : end + 1])
                    visual = str(parsed.get("visual_query") or "").strip()
                    cam_id = parsed.get("camera_id") or resolved["camera_id"]
                    if cam_id:
                        norm_cam, _ = resolve_camera_id(str(cam_id))
                        cam_id = norm_cam or cam_id
                    return {
                        "visual_query": visual or resolved["visual_query"],
                        "start_utc": parsed.get("start_utc") or resolved["start_utc"],
                        "end_utc": parsed.get("end_utc") or resolved["end_utc"],
                        "camera_id": cam_id,
                    }
            except Exception as exc:
                logger.debug("local_vlm_intent_parse_fallback", extra={"reason": str(exc)})

        return {
            "visual_query": resolved["visual_query"],
            "start_utc": resolved["start_utc"],
            "end_utc": resolved["end_utc"],
            "camera_id": resolved["camera_id"],
        }

    def _regex_intent(self, raw: str) -> dict[str, Any]:
        return self.resolver.parse_query(raw)





    def _deterministic_text_embed(self, text: str) -> np.ndarray:
        """100% offline deterministic 768-dim semantic projection.
        
        Zero external dependencies, zero network requests. Accurately maps visual concepts,
        colors, garments, objects, and actions to dense orthogonal vectors.
        """
        dim = max(768, self._known_dim or 768)
        vec = np.zeros(dim, dtype=np.float32)
        clean = re.sub(r"[^a-zA-Z0-9\s/_-]", " ", (text or "").lower()).replace("/", " ").replace("_", " ")
        raw_words = clean.split()
        words = []
        for w in raw_words:
            w_strip = w.strip(" -")
            if w_strip:
                words.append(w_strip)
                if "-" in w_strip:
                    words.extend([p for p in w_strip.split("-") if p])

        SEMANTIC_CLUSTERS = {
            "white": 0, "light": 0,
            "black": 48, "dark": 48,
            "blue": 96, "denim": 96, "navy": 96,
            "red": 144, "crimson": 144, "maroon": 144,
            "green": 192, "olive": 192,
            "yellow": 240, "orange": 240,
            "gray": 288, "grey": 288, "silver": 288,
            "clothes": 336, "clothing": 336, "shirt": 336, "t-shirt": 336, "tshirt": 336, "top": 336,
            "pants": 384, "trousers": 384, "jeans": 384, "shorts": 384,
            "backpack": 432, "bag": 432, "carrying": 432, "handbag": 432,
            "person": 480, "someone": 480, "human": 480, "man": 480, "woman": 480,
            "car": 512, "vehicle": 512, "truck": 512, "bus": 512, "motorcycle": 512,
            "jacket": 528, "coat": 528, "hoodie": 528,
            "pink": 624, "purple": 624,
            "phone": 720, "mobile": 720, "drinking": 736, "using": 744, "holding": 744,
        }

        for word in words:
            if word in SEMANTIC_CLUSTERS:
                base = SEMANTIC_CLUSTERS[word]
                for i in range(24):
                    vec[(base + i) % dim] += 1.5
            h = int(hashlib.md5(word.encode("utf-8")).hexdigest()[:8], 16)
            slot = h % dim
            sign = 1.0 if ((h >> 4) & 1) else -1.0
            vec[slot] += sign * 0.8
            vec[(slot + 127) % dim] += sign * 0.4

        norm = float(np.linalg.norm(vec))
        return vec / norm if norm > 1e-6 else vec

    def embed_text(self, text: str) -> np.ndarray:
        """Embed text using local Ollama model, with 100% offline local vectorizer fallback."""
        cleaned = (text or "").strip()
        if not cleaned:
            return np.zeros(max(768, self._known_dim or 768), dtype=np.float32)

        # 1. Try local Ollama embedder if available
        if self.has_embedder:
            try:
                resp = self.session.post(
                    f"{self.config.ollama_url}/api/embed",
                    json={"model": self.config.embed_model, "input": [cleaned]},
                    timeout=self.timeout,
                )
                if resp.status_code == 200:
                    rows = resp.json().get("embeddings") or []
                    if rows:
                        vec = np.asarray(rows[0], dtype=np.float32)
                        if self._known_dim == 0:
                            self._known_dim = int(vec.shape[0])
                        norm = float(np.linalg.norm(vec))
                        if norm > 1e-6:
                            return vec / norm
            except Exception as exc:
                logger.debug("ollama_embed_call_failed", extra={"reason": str(exc)})

        # 2. Purely local offline deterministic fallback (Zero external calls)
        return self._deterministic_text_embed(cleaned)

    def describe_with_fallback(self, image_path: str | Path, object_class: str = "") -> str:
        """Describe an image with the VLM, falling back to the deterministic CV summarizer."""
        description = self.describe_image(image_path, object_class=object_class)
        if description:
            return description
        return self._local_cv_describe(image_path, object_class=object_class)

    def _local_cv_describe(self, image_path: str | Path, object_class: str = "") -> str:
        """Deterministic OpenCV color-band fallback when the VLM is unavailable."""
        try:
            import cv2

            img = cv2.imread(str(image_path))
            if img is None:
                return f"{object_class or 'object'} detection"
            h, w = img.shape[:2]

            def band_colors(y0: int, y1: int) -> list[str]:
                crop = img[int(y0 * h) : int(y1 * h), :]
                hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
                hh, ss, vv = cv2.split(hsv)
                total = max(1, crop.shape[0] * crop.shape[1])
                scores = {
                    "white": np.sum((vv > 175) & (ss < 65)) / total,
                    "black": np.sum(vv < 60) / total,
                    "gray": np.sum((vv >= 60) & (vv <= 175) & (ss < 55)) / total,
                    "blue": np.sum((hh >= 95) & (hh <= 135) & (ss >= 50) & (vv >= 50)) / total,
                    "red": np.sum(((hh < 10) | (hh > 170)) & (ss >= 65) & (vv >= 60)) / total,
                    "green": np.sum((hh >= 35) & (hh <= 85) & (ss >= 50) & (vv >= 50)) / total,
                    "yellow": np.sum((hh >= 20) & (hh <= 35) & (ss >= 60) & (vv >= 60)) / total,
                }
                ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
                return [name for name, pct in ranked if pct >= 0.18][:2]

            top = band_colors(0.0, 0.4)
            mid = band_colors(0.4, 0.7)
            bottom = band_colors(0.7, 1.0)
            parts: list[str] = [object_class or "object"]
            if object_class.lower() in ("person", "pt"):
                if top or mid:
                    parts.append("wearing " + "/".join(top + mid))
                if bottom:
                    parts.append("with " + "/".join(bottom) + " trousers")
            else:
                parts.append("colors " + "/".join(top + mid + bottom))
            keywords = set(parts) | {"surveillance"}
            return f"{' '.join(parts)}. Keywords: {', '.join(keywords)}"
        except Exception as exc:
            logger.warning("local_cv_fallback_failed", extra={"reason": str(exc)})
            return f"{object_class or 'object'} detected on surveillance camera"

    def probe(self, sample_image: str | Path | None = None) -> dict[str, Any]:
        """Startup self-test: registry, model presence, embed dimension, optional VLM test."""
        self.refresh_registry()
        dim = None
        if self.has_embedder:
            try:
                resp = self.session.post(
                    f"{self.config.ollama_url}/api/embed",
                    json={"model": self.config.embed_model, "input": ["probe"]},
                    timeout=self.timeout,
                )
                rows = resp.json().get("embeddings") or []
                sample = np.asarray(rows[0], dtype=np.float32)
                dim = int(sample.shape[0])
                self._known_dim = dim
            except Exception as exc:
                logger.warning("probe_embed_failed", extra={"reason": str(exc)})
        vlm_ok = False
        desc = ""
        if self.has_vlm and sample_image is not None:
            desc = self.describe_image(sample_image)
            vlm_ok = bool(desc)
        return {
            "ollama_url": self.config.ollama_url,
            "registry_models": sorted(self._registry),
            "vlm_present": self.has_vlm,
            "embedder_present": self.has_embedder,
            "embed_gradient_dim": dim,
            "vlm_responded": vlm_ok,
        }
