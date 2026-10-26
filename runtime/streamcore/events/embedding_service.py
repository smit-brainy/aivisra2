"""Gemini multimodal vision and embedding service for person surveillance search.

Provides:
1. Gemini Vision attribute extraction (or local computer-vision fallback)
2. Gemini Text Embedding (text-embedding-004) to 768-dim vectors (or local semantic vectorizer fallback)
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np
import requests

import time

logger = logging.getLogger("events.embedding")

VECTOR_DIM = 768
DEFAULT_GEMINI_MODEL = "gemini-flash-lite-latest"
FALLBACK_GEMINI_MODELS = ["gemini-flash-latest"]
EMBEDDING_MODELS = ["gemini-embedding-001", "text-embedding-004"]


class EmbeddingService:
    """Generates visual descriptions and 768-dim embeddings for surveillance queries."""

    def __init__(self, api_key: str | None = None) -> None:
        if (api_key or "").strip().lower() in ("disabled", "none", "off", "local"):
            self._api_key = ""
        else:
            self._api_key = (api_key or "").strip() or self._resolve_api_key()
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self._quota_cooldown_until: float = 0.0
        self._embed_quota_cooldown_until: float = 0.0

    def _resolve_api_key(self) -> str:
        """Resolve API key securely from environment variables or .env file."""
        # 1. Check existing environment variables
        env_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if env_key and env_key.strip():
            return env_key.strip()

        # 2. Search root and local .env files
        candidates = [
            Path(".env"),
            Path(__file__).resolve().parents[3] / ".env",
            Path("runtime/streamcore/.env"),
        ]
        for env_path in candidates:
            if env_path.is_file():
                try:
                    for raw in env_path.read_text(encoding="utf-8").splitlines():
                        line = raw.strip()
                        if not line or line.startswith("#"):
                            continue
                        k, sep, v = line.partition("=")
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k in ("GEMINI_API_KEY", "GOOGLE_API_KEY") and v:
                            os.environ[k] = v
                            return v
                except Exception:
                    pass

        return ""

    @property
    def api_key(self) -> str:
        if not self._api_key:
            self._api_key = self._resolve_api_key()
        return self._api_key

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 5)

    def analyze_image_and_embed(self, image_path: str | Path) -> tuple[str, np.ndarray]:
        """Analyze person crop image, extract description and generate 768-dim embedding."""
        img_path = Path(image_path)
        if not img_path.exists():
            desc = "Unknown person detection"
            return desc, self._local_text_embed(desc)

        description = ""
        # 1. Try Gemini Vision if API key is present
        if self.has_api_key:
            try:
                description = self._gemini_vision_describe(img_path)
            except Exception as exc:
                logger.warning("gemini_vision_failed_fallback_to_local", extra={"reason": str(exc)})

        # 2. Fallback to local CV attribute extraction
        if not description:
            description = self._local_analyze_person_crop(img_path)

        # 3. Generate embedding
        embedding = self.embed_text(description)
        return description, embedding

    def embed_text(self, text: str) -> np.ndarray:
        """Generate 768-dimensional normalized embedding for text."""
        cleaned = (text or "").strip()
        if not cleaned:
            return np.zeros(VECTOR_DIM, dtype=np.float32)

        if self.has_api_key:
            try:
                vec = self._gemini_embed_text(cleaned)
                if vec is not None:
                    return vec
            except Exception as exc:
                logger.warning("gemini_embed_failed_fallback_to_local", extra={"reason": str(exc)})

        return self._local_text_embed(cleaned)

    def parse_query_intent(self, query: str) -> dict[str, Any]:
        """Parse natural language query into visual description and temporal/camera filters.
        
        Uses Gemini LLM (Approach B) when available, with fast deterministic fallback.
        """
        raw = (query or "").strip()
        if not raw:
            return {"visual_query": "", "start_utc": None, "end_utc": None, "camera_id": None}

        # Check for potential time or camera keywords to avoid unnecessary API calls
        time_triggers = [
            "today", "yesterday", "tomorrow", "hour", "minute", "sec", "morning",
            "afternoon", "evening", "night", "between", "from", "to", "after",
            "before", "around", "am", "pm", "clock", "camera", "cam", "recent", "past"
        ]
        has_cue = any(t in raw.lower() for t in time_triggers)
        if not has_cue:
            return {"visual_query": raw, "start_utc": None, "end_utc": None, "camera_id": None}

        # Try Gemini LLM extraction (Approach B)
        if self.has_api_key and (not self._quota_cooldown_until or time.time() >= self._quota_cooldown_until):
            try:
                from datetime import datetime, timezone, timedelta
                now_utc = datetime.now(timezone.utc)
                now_ist = now_utc + timedelta(hours=5, minutes=30)
                now_ist_str = now_ist.strftime("%Y-%m-%d %H:%M:%S")

                prompt = (
                    f"You are a surveillance search query parser.\n"
                    f"Current reference time in local IST (UTC+05:30): {now_ist_str}.\n"
                    f"Current reference time in UTC: {now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}.\n\n"
                    f"Analyze this security search query: \"{raw}\"\n\n"
                    f"Extract the following into a valid JSON object ONLY (no markdown fences, no extra text):\n"
                    f'{{\n'
                    f'  "visual_query": "<only the visual description of person, clothing, color, objects with all time/date/camera words removed>",\n'
                    f'  "start_utc": "<ISO-8601 UTC timestamp e.g. YYYY-MM-DDTHH:MM:SSZ, or null>",\n'
                    f'  "end_utc": "<ISO-8601 UTC timestamp e.g. YYYY-MM-DDTHH:MM:SSZ, or null>",\n'
                    f'  "camera_id": "<camera id like CAM001 if mentioned, or null>"\n'
                    f'}}\n'
                )

                url = f"https://generativelanguage.googleapis.com/v1beta/models/{DEFAULT_GEMINI_MODEL}:generateContent?key={self.api_key}"
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.0,
                        "maxOutputTokens": 200,
                        "responseMimeType": "application/json"
                    }
                }
                resp = self.session.post(url, json=payload, timeout=4.0)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        raw_json = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        parsed = json.loads(raw_json)
                        visual = (parsed.get("visual_query") or "").strip()
                        return {
                            "visual_query": visual if visual else raw,
                            "start_utc": parsed.get("start_utc") or None,
                            "end_utc": parsed.get("end_utc") or None,
                            "camera_id": parsed.get("camera_id") or None,
                        }
                elif resp.status_code == 429:
                    self._quota_cooldown_until = time.time() + 60.0
            except Exception as exc:
                logger.debug("gemini_query_intent_parse_failed", extra={"reason": str(exc)})

        return self._local_parse_query_intent(raw)

    def _local_parse_query_intent(self, raw: str) -> dict[str, Any]:
        """Local regex rule-based parser fallback for relative times."""
        import re
        from datetime import datetime, timezone, timedelta

        now_utc = datetime.now(timezone.utc)
        ist_offset = timedelta(hours=5, minutes=30)
        now_ist = now_utc + ist_offset

        visual = raw
        start_utc = None
        end_utc = None
        camera_id = None

        cam_match = re.search(r'\b(cam(?:era)?\s*0*(\d+))\b', visual, re.IGNORECASE)
        if cam_match:
            cam_num = int(cam_match.group(2))
            camera_id = f"CAM{cam_num:03d}"
            visual = visual[:cam_match.start()] + visual[cam_match.end():]

        hrs_match = re.search(r'\b(?:last|past)\s+(\d+)\s*(?:hours|hour|hrs|hr)\b', visual, re.IGNORECASE)
        if hrs_match:
            h = int(hrs_match.group(1))
            start_utc = (now_utc - timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ")
            end_utc = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            visual = visual[:hrs_match.start()] + visual[hrs_match.end():]

        mins_match = re.search(r'\b(?:last|past)\s+(\d+)\s*(?:minutes|minute|mins|min)\b', visual, re.IGNORECASE)
        if mins_match and not start_utc:
            m = int(mins_match.group(1))
            start_utc = (now_utc - timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%SZ")
            end_utc = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            visual = visual[:mins_match.start()] + visual[mins_match.end():]

        if re.search(r'\btoday\b', visual, re.IGNORECASE) and not start_utc:
            today_start_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
            start_utc = (today_start_ist - ist_offset).strftime("%Y-%m-%dT%H:%M:%SZ")
            visual = re.sub(r'\btoday\b', '', visual, flags=re.IGNORECASE)

        if re.search(r'\byesterday\b', visual, re.IGNORECASE) and not start_utc:
            yest_start_ist = (now_ist - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            today_start_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
            start_utc = (yest_start_ist - ist_offset).strftime("%Y-%m-%dT%H:%M:%SZ")
            end_utc = (today_start_ist - ist_offset).strftime("%Y-%m-%dT%H:%M:%SZ")
            visual = re.sub(r'\byesterday\b', '', visual, flags=re.IGNORECASE)

        visual = re.sub(r'\b(?:in the|at|between|around|from|to)\b', ' ', visual, flags=re.IGNORECASE)
        visual = ' '.join(visual.split())
        return {
            "visual_query": visual if visual else raw,
            "start_utc": start_utc,
            "end_utc": end_utc,
            "camera_id": camera_id,
        }

    # ------------------ Gemini REST API Implementations ------------------

    def _gemini_vision_describe(self, img_path: Path) -> str:
        """Use Gemini Vision to describe clothing, colors, and accessories."""
        with open(img_path, "rb") as f:
            b64_img = base64.b64encode(f.read()).decode("utf-8")

        prompt = (
            "Analyze this surveillance CCTV person snapshot concisely for security retrieval. "
            "Describe:\n"
            "1. Upper body clothing type and colors (e.g., white shirt, red jacket, black t-shirt).\n"
            "2. Lower body clothing type and colors (e.g., blue jeans, black shorts, dark trousers).\n"
            "3. Any accessories (e.g., backpack, bag, hat, glasses, umbrella).\n"
            "4. Overall appearance.\n"
            "Output 1-2 concise sentences followed by relevant search keywords."
        )

        if self._quota_cooldown_until and time.time() < self._quota_cooldown_until:
            return ""

        models = [DEFAULT_GEMINI_MODEL] + FALLBACK_GEMINI_MODELS
        last_error = None

        for model in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": b64_img
                            }
                        }
                    ]
                }],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 200
                }
            }

            try:
                resp = self.session.post(url, json=payload, timeout=5.0)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        if text.strip():
                            return text.strip()
                elif resp.status_code == 429:
                    logger.warning("gemini_vision_quota_exceeded_activating_cooldown")
                    self._quota_cooldown_until = time.time() + 60.0
                    return ""
                else:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:120]}"
            except Exception as exc:
                last_error = str(exc)

        logger.warning("gemini_vision_all_models_failed", extra={"error": last_error})
        return ""

    def _gemini_embed_text(self, text: str) -> np.ndarray | None:
        """Call Gemini embedContent REST API with fallback models."""
        if self._embed_quota_cooldown_until and time.time() < self._embed_quota_cooldown_until:
            return None

        for emb_model in EMBEDDING_MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{emb_model}:embedContent?key={self.api_key}"
            payload = {
                "model": f"models/{emb_model}",
                "content": {
                    "parts": [{"text": text}]
                },
                "outputDimensionality": VECTOR_DIM,
            }

            try:
                resp = self.session.post(url, json=payload, timeout=5.0)
                if resp.status_code == 200:
                    data = resp.json()
                    values = data.get("embedding", {}).get("values")
                    if values:
                        vec = np.asarray(values, dtype=np.float32)
                        if len(vec) != VECTOR_DIM:
                            # Project or interpolate to VECTOR_DIM (768)
                            if len(vec) > VECTOR_DIM:
                                vec = vec[:VECTOR_DIM]
                            else:
                                indices = np.linspace(0, len(vec) - 1, VECTOR_DIM).astype(int)
                                vec = vec[indices]
                        norm = np.linalg.norm(vec)
                        return vec / norm if norm > 0 else vec
                elif resp.status_code == 429:
                    logger.warning("gemini_embed_quota_exceeded_activating_cooldown")
                    self._embed_quota_cooldown_until = time.time() + 60.0
                    break
                else:
                    logger.debug("gemini_embed_model_not_ready", extra={"model": emb_model, "status": resp.status_code})
            except Exception as exc:
                logger.debug("gemini_embed_model_error", extra={"model": emb_model, "error": str(exc)})
        return None

    # ------------------ Local CV & Semantic Fallback ------------------

    def _local_analyze_person_crop(self, img_path: Path) -> str:
        """Analyze person crop using OpenCV for upper/lower colors and brightness."""
        try:
            import cv2
            img = cv2.imread(str(img_path))
            if img is None:
                return "Person detection"

            h, w = img.shape[:2]
            upper = img[:int(h * 0.55), :]
            lower = img[int(h * 0.55):, :]

            def extract_colors(crop: np.ndarray) -> list[str]:
                hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
                h_c, s_c, v_c = cv2.split(hsv)
                total = max(1, crop.shape[0] * crop.shape[1])

                white = np.sum((v_c > 175) & (s_c < 65)) / total
                black = np.sum(v_c < 60) / total
                gray = np.sum((v_c >= 60) & (v_c <= 175) & (s_c < 55)) / total
                blue = np.sum((h_c >= 95) & (h_c <= 135) & (s_c >= 50) & (v_c >= 50)) / total
                red = np.sum(((h_c < 10) | (h_c > 170)) & (s_c >= 65) & (v_c >= 60)) / total
                green = np.sum((h_c >= 35) & (h_c <= 85) & (s_c >= 50) & (v_c >= 50)) / total
                yellow = np.sum((h_c >= 20) & (h_c <= 35) & (s_c >= 60) & (v_c >= 60)) / total

                detected = []
                # Check dominant colors in order of prominence
                color_scores = [
                    ("white", white),
                    ("black", black),
                    ("gray", gray),
                    ("blue", blue),
                    ("red", red),
                    ("green", green),
                    ("yellow", yellow),
                ]
                for name, score in sorted(color_scores, key=lambda x: x[1], reverse=True):
                    if score >= 0.18:
                        detected.append(name)
                return detected[:2]

            up_colors = extract_colors(upper)
            low_colors = extract_colors(lower)

            up_str = f"{'/'.join(up_colors)} clothing" if up_colors else "dark/neutral clothing"
            low_str = f"{'/'.join(low_colors)} trousers/pants" if low_colors else "dark trousers"

            keywords = set(up_colors + low_colors + ["person", "human", "clothes"])
            return f"Person wearing {up_str} and {low_str}. Keywords: {', '.join(keywords)}"
        except Exception as exc:
            logger.error("local_person_crop_analysis_failed", extra={"reason": str(exc)})
            return "Person detected on surveillance camera"

    def _local_text_embed(self, text: str) -> np.ndarray:
        """Deterministic 768-dim semantic vector projection for visual surveillance tokens.
        
        Maps surveillance concepts (clothing colors, garment types, bags, actions)
        into dense orthogonal vectors so that queries like 'person with white clothes'
        match person snapshots with white clothing tags accurately.
        """
        import re
        vec = np.zeros(VECTOR_DIM, dtype=np.float32)
        clean_text = re.sub(r"[^a-zA-Z0-9\s/_-]", " ", (text or "").lower())
        clean_text = clean_text.replace("/", " ").replace("_", " ")

        raw_words = clean_text.split()
        words = []
        for w in raw_words:
            w_strip = w.strip(" -")
            if not w_strip:
                continue
            words.append(w_strip)
            if "-" in w_strip:
                words.extend([p for p in w_strip.split("-") if p])

        # Semantic base cluster offsets (0-767)
        SEMANTIC_CLUSTERS = {
            "white": 0, "light": 0,
            "black": 48, "dark": 48,
            "blue": 96, "denim": 96, "navy": 96,
            "red": 144, "crimson": 144, "maroon": 144,
            "green": 192, "olive": 192,
            "yellow": 240, "orange": 240,
            "gray": 288, "grey": 288, "silver": 288,
            "clothes": 336, "clothing": 336, "shirt": 336, "t-shirt": 336, "tshirt": 336, "tee": 336, "top": 336,
            "polo": 336, "dress": 336, "suit": 336, "blouse": 336,
            "pants": 384, "trousers": 384, "jeans": 384, "shorts": 384, "bottom": 384,
            "backpack": 432, "bag": 432, "carrying": 432, "handbag": 432, "umbrella": 432, "purse": 432,
            "person": 480, "someone": 480, "human": 480, "man": 480, "woman": 480,
            "male": 480, "female": 480, "girl": 480, "boy": 480,
            "jacket": 528, "coat": 528, "hoodie": 528, "sweater": 528,
            "hat": 576, "cap": 576, "helmet": 576, "glasses": 576, "sunglasses": 576, "mask": 576,
            "pink": 624, "purple": 624, "violet": 624,
            "brown": 672, "tan": 672, "khaki": 672,
            "phone": 720, "mobile": 720, "shoes": 720, "sneakers": 720, "boots": 720, "footwear": 720,
        }

        for word in words:
            # 1. Cluster activation
            if word in SEMANTIC_CLUSTERS:
                base = SEMANTIC_CLUSTERS[word]
                # Distribute energy in this concept's sub-band
                for i in range(32):
                    idx = (base + i) % VECTOR_DIM
                    vec[idx] += 1.5

            # 2. General token n-gram hashing for vocabulary generalization
            h = int(hashlib.md5(word.encode("utf-8")).hexdigest()[:8], 16)
            slot = (h % VECTOR_DIM)
            sign = 1.0 if ((h >> 4) & 1) else -1.0
            vec[slot] += sign * 0.8
            vec[(slot + 127) % VECTOR_DIM] += sign * 0.4

        norm = np.linalg.norm(vec)
        if norm > 1e-6:
            vec /= norm
        return vec

