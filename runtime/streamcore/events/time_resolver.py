"""Surveillance Query Resolution Tools & Helper Methods.

A modular, class-based toolset serving different search resolution tasks:
- resolve_camera: Normalizes camera expressions ('in Cam 57', 'cam6' -> 'CAM057')
- resolve_calendar_date: Resolves days of the week, weekends, yesterday, today
- resolve_relative_time: Handles 'just now', 'earlier today', 'last X hours'
- resolve_clock_range: Parses 'around 3pm', 'after 4pm', 'between 9:00AM to 11:00AM'
- resolve_named_period: Handles colloquial periods like 'lunch time', 'sunset', 'late night'
- extract_visual_attributes: Extracts colors, garments, objects, and actions
- clean_visual_query: Strips temporal, camera, and noise tokens from visual search text
- parse_query: Master pipeline coordinating all methods into a structured query record
- get_tool_schemas: Exposes formal JSON schemas for local LLM function calling
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any


class TimeAndQueryResolver:
    """Class-based toolset for natural language surveillance query resolution."""

    # Natural named periods mapped to ((start_hour, start_min), (end_hour, end_min))
    NAMED_PERIODS: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {
        "dawn": ((5, 30), (7, 0)),
        "sunrise": ((5, 30), (7, 0)),
        "early morning": ((5, 0), (8, 30)),
        "morning": ((6, 0), (12, 0)),
        "late morning": ((10, 30), (12, 30)),
        "noon": ((11, 30), (13, 0)),
        "midday": ((11, 30), (13, 30)),
        "lunch time": ((12, 0), (14, 30)),
        "lunch hour": ((12, 0), (14, 30)),
        "lunch": ((12, 0), (14, 30)),
        "afternoon": ((12, 0), (17, 0)),
        "late afternoon": ((15, 30), (17, 30)),
        "sunset": ((17, 45), (19, 15)),
        "dusk": ((18, 0), (19, 30)),
        "evening": ((17, 0), (21, 0)),
        "late evening": ((20, 0), (22, 30)),
        "night": ((21, 0), (23, 59)),
        "tonight": ((20, 0), (23, 59)),
        "late night": ((23, 0), (4, 0)),  # Crosses midnight into next morning
        "midnight": ((23, 30), (1, 0)),   # Crosses midnight
        "office hours": ((9, 0), (18, 0)),
        "working hours": ((9, 0), (18, 0)),
        "rush hour": ((8, 0), (10, 30)),
        "evening rush hour": ((17, 0), (19, 30)),
    }

    WEEKDAYS: dict[str, int] = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6,
    }

    # Common surveillance attributes for structured extraction
    COLOR_KEYWORDS: list[str] = [
        "black", "white", "gray", "grey", "blue", "red", "green",
        "yellow", "pink", "purple", "orange", "brown", "dark", "light",
    ]
    GARMENT_KEYWORDS: list[str] = [
        "shirt", "t-shirt", "tshirt", "top", "pants", "trousers", "jeans",
        "jacket", "hoodie", "sweater", "coat", "shorts", "dress", "suit",
    ]
    ACTION_KEYWORDS: list[str] = [
        "using mobile", "on phone", "calling", "drinking", "eating",
        "holding", "carrying", "walking", "running", "seated", "sitting", "typing",
    ]

    def __init__(self, ist_offset_hours: float = 5.5, default_padding_mins: int = 15) -> None:
        self.ist_offset_hours = float(ist_offset_hours)
        self.offset = timedelta(hours=self.ist_offset_hours)
        self.default_padding_mins = max(0, int(default_padding_mins))

    # -------------------------------------------------------------------------
    # Method 1: Camera Resolution
    # -------------------------------------------------------------------------
    def resolve_camera(self, text: str) -> tuple[str | None, str]:
        """Extract and normalize camera identifiers (e.g. 'in Cam 57' -> ('CAM057', cleaned_text))."""
        match = re.search(r"\b(?:in|on|at)?\s*cam(?:era)?\s*#?\s*0*(\d+)\b", text, re.IGNORECASE)
        if match:
            cam_num = int(match.group(1))
            cleaned = text[: match.start()] + " " + text[match.end() :]
            return f"CAM{cam_num:03d}", " ".join(cleaned.split())
        return None, text

    # -------------------------------------------------------------------------
    # Method 2: Calendar & Relative Day Resolution
    # -------------------------------------------------------------------------
    def resolve_calendar_date(self, text: str, ref_local: datetime) -> tuple[date, str, tuple[datetime, datetime] | None]:
        """Resolve days of week, weekends, yesterday, today.
        
        Returns:
            (target_date, cleaned_text, explicit_weekend_range)
        """
        visual = text
        # Over the weekend (explicit 48-hour range)
        if re.search(r"\b(?:over the\s+|last\s+|past\s+)?weekend\b", visual, re.IGNORECASE):
            days_since_sunday = (ref_local.weekday() + 1) % 7
            last_sunday = ref_local.date() - timedelta(days=days_since_sunday if days_since_sunday > 0 else 7)
            last_saturday = last_sunday - timedelta(days=1)
            start_dt = datetime(last_saturday.year, last_saturday.month, last_saturday.day, 0, 0, 0)
            end_dt = datetime(last_sunday.year, last_sunday.month, last_sunday.day, 23, 59, 59)
            visual = re.sub(r"\b(?:over the\s+|last\s+|past\s+)?weekend\b", " ", visual, flags=re.IGNORECASE)
            return last_saturday, " ".join(visual.split()), (start_dt, end_dt)

        target_date = ref_local.date()
        # Day of week (e.g. 'on wednesday evening')
        day_match = re.search(r"\b(?:on\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", visual, re.IGNORECASE)
        if day_match:
            w_name = day_match.group(1).lower()
            w_idx = self.WEEKDAYS[w_name]
            days_back = (ref_local.weekday() - w_idx) % 7
            if days_back == 0 and ("last" in visual.lower() or "past" in visual.lower()):
                days_back = 7
            target_date = ref_local.date() - timedelta(days=days_back)
            visual = visual[: day_match.start()] + " " + visual[day_match.end() :]
        elif re.search(r"\bday before yesterday\b", visual, re.IGNORECASE):
            target_date = ref_local.date() - timedelta(days=2)
            visual = re.sub(r"\bday before yesterday\b", " ", visual, flags=re.IGNORECASE)
        elif re.search(r"\byesterday\b", visual, re.IGNORECASE):
            target_date = ref_local.date() - timedelta(days=1)
            visual = re.sub(r"\byesterday\b", " ", visual, flags=re.IGNORECASE)
        elif re.search(r"\btoday\b", visual, re.IGNORECASE):
            target_date = ref_local.date()
            visual = re.sub(r"\btoday\b", " ", visual, flags=re.IGNORECASE)

        return target_date, " ".join(visual.split()), None

    # -------------------------------------------------------------------------
    # Method 3: Relative Time Resolution
    # -------------------------------------------------------------------------
    def resolve_relative_time(
        self, text: str, ref_local: datetime, target_date: date
    ) -> tuple[datetime | None, datetime | None, str]:
        """Resolve colloquial relative phrases ('just now', 'earlier today', 'last 2 hours')."""
        visual = text

        # 'just now' / 'recently' / 'moments ago'
        if re.search(r"\b(just now|moments ago|few minutes (?:ago|back)|recently)\b", visual, re.IGNORECASE):
            cleaned = re.sub(r"\b(just now|moments ago|few minutes (?:ago|back)|recently)\b", " ", visual, flags=re.IGNORECASE)
            return ref_local - timedelta(minutes=25), ref_local, " ".join(cleaned.split())

        # 'earlier today' / 'earlier'
        if re.search(r"\bearlier(?:\s+today)?\b", visual, re.IGNORECASE):
            cleaned = re.sub(r"\bearlier(?:\s+today)?\b", " ", visual, flags=re.IGNORECASE)
            start_dt = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0)
            return start_dt, ref_local, " ".join(cleaned.split())

        # 'last X hours'
        hrs_match = re.search(r"\b(?:last|past)\s+(\d+)\s*(?:hours|hour|hrs|hr)\b", visual, re.IGNORECASE)
        if hrs_match:
            h = int(hrs_match.group(1))
            cleaned = visual[: hrs_match.start()] + " " + visual[hrs_match.end() :]
            return ref_local - timedelta(hours=h), ref_local, " ".join(cleaned.split())

        # 'last X minutes'
        mins_match = re.search(r"\b(?:last|past)\s+(\d+)\s*(?:minutes|minute|mins|min)\b", visual, re.IGNORECASE)
        if mins_match:
            mins = int(mins_match.group(1))
            cleaned = visual[: mins_match.start()] + " " + visual[mins_match.end() :]
            return ref_local - timedelta(minutes=mins), ref_local, " ".join(cleaned.split())

        return None, None, visual

    # -------------------------------------------------------------------------
    # Method 4: Clock Range & Fuzzy Prepositions Resolution
    # -------------------------------------------------------------------------
    def resolve_clock_range(
        self, text: str, target_date: date, padding_minutes: int | None = None
    ) -> tuple[datetime | None, datetime | None, str]:
        """Parse explicit or fuzzy clock ranges ('around 3pm', 'after 4pm', 'between 9:00AM to 11:00AM')."""
        visual = text
        pad = self.default_padding_mins if padding_minutes is None else padding_minutes

        # 'around X' / 'about X' / 'approx X' (e.g. 'around 3pm', 'approx 10:30am')
        around_match = re.search(r"\b(?:around|about|approx(?:\.)?)\s+(\d{1,2})(?::(\d{2}))?\s*(:?[aApP][mM])?\b", visual, re.IGNORECASE)
        if around_match:
            h = int(around_match.group(1))
            mins = int(around_match.group(2) or 0)
            p = (around_match.group(3) or "").lower().replace(":", "")
            if p == "pm" and h < 12:
                h += 12
            if p == "am" and h == 12:
                h = 0
            center_dt = datetime(target_date.year, target_date.month, target_date.day, min(23, h), min(59, mins), 0)
            cleaned = visual[: around_match.start()] + " " + visual[around_match.end() :]
            return center_dt - timedelta(minutes=45), center_dt + timedelta(minutes=45), " ".join(cleaned.split())

        # 'after X' (e.g. 'after 4pm')
        after_match = re.search(r"\bafter\s+(\d{1,2})(?::(\d{2}))?\s*(:?[aApP][mM])?\b", visual, re.IGNORECASE)
        if after_match:
            h = int(after_match.group(1))
            mins = int(after_match.group(2) or 0)
            p = (after_match.group(3) or "").lower().replace(":", "")
            if p == "pm" and h < 12:
                h += 12
            if p == "am" and h == 12:
                h = 0
            start_dt = datetime(target_date.year, target_date.month, target_date.day, min(23, h), min(59, mins), 0)
            end_dt = datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59)
            cleaned = visual[: after_match.start()] + " " + visual[after_match.end() :]
            return start_dt, end_dt, " ".join(cleaned.split())

        # 'before X' (e.g. 'before 11am')
        before_match = re.search(r"\bbefore\s+(\d{1,2})(?::(\d{2}))?\s*(:?[aApP][mM])?\b", visual, re.IGNORECASE)
        if before_match:
            h = int(before_match.group(1))
            mins = int(before_match.group(2) or 0)
            p = (before_match.group(3) or "").lower().replace(":", "")
            if p == "pm" and h < 12:
                h += 12
            if p == "am" and h == 12:
                h = 0
            start_dt = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0)
            end_dt = datetime(target_date.year, target_date.month, target_date.day, min(23, h), min(59, mins), 0)
            cleaned = visual[: before_match.start()] + " " + visual[before_match.end() :]
            return start_dt, end_dt, " ".join(cleaned.split())

        # 'between X and Y' / 'from X to Y'
        range_match = re.search(
            r"\b(?:between|from)\s+(\d{1,2})(?::(\d{2}))?\s*(:?[aApP][mM])?\s*(?:to|and|-)\s*(\d{1,2})(?::(\d{2}))?\s*(:?[aApP][mM])?\b",
            visual,
            re.IGNORECASE,
        )
        if range_match:
            h1, m1, p1 = int(range_match.group(1)), int(range_match.group(2) or 0), (range_match.group(3) or "").lower().replace(":", "")
            h2, m2, p2 = int(range_match.group(4)), int(range_match.group(5) or 0), (range_match.group(6) or "").lower().replace(":", "")
            if p1 == "pm" and h1 < 12:
                h1 += 12
            if p1 == "am" and h1 == 12:
                h1 = 0
            if p2 == "pm" and h2 < 12:
                h2 += 12
            if p2 == "am" and h2 == 12:
                h2 = 0
            start_dt = datetime(target_date.year, target_date.month, target_date.day, min(23, h1), min(59, m1), 0) - timedelta(minutes=pad)
            end_dt = datetime(target_date.year, target_date.month, target_date.day, min(23, h2), min(59, m2), 0) + timedelta(minutes=pad)
            cleaned = visual[: range_match.start()] + " " + visual[range_match.end() :]
            return start_dt, end_dt, " ".join(cleaned.split())

        return None, None, visual

    # -------------------------------------------------------------------------
    # Method 5: Colloquial & Named Period Resolution
    # -------------------------------------------------------------------------
    def resolve_named_period(
        self, text: str, target_date: date
    ) -> tuple[datetime | None, datetime | None, str]:
        """Resolve colloquial periods like 'lunch time', 'morning', 'sunset', 'late night'."""
        visual = text
        for period_name, (t1, t2) in sorted(self.NAMED_PERIODS.items(), key=lambda kv: len(kv[0]), reverse=True):
            pat = rf"\b(?:around\s+|during\s+|at\s+)?{re.escape(period_name)}\b"
            m = re.search(pat, visual, re.IGNORECASE)
            if m:
                start_dt = datetime(target_date.year, target_date.month, target_date.day, t1[0], t1[1], 0)
                if t2[0] < t1[0]:  # Crosses midnight into next calendar day
                    next_d = target_date + timedelta(days=1)
                    end_dt = datetime(next_d.year, next_d.month, next_d.day, t2[0], t2[1], 0)
                else:
                    end_dt = datetime(target_date.year, target_date.month, target_date.day, t2[0], t2[1], 0)
                cleaned = visual[: m.start()] + " " + visual[m.end() :]
                return start_dt, end_dt, " ".join(cleaned.split())
        return None, None, visual

    # -------------------------------------------------------------------------
    # Method 6: Noise & Temporal Token Stripper
    # -------------------------------------------------------------------------
    def clean_visual_query(self, text: str) -> str:
        """Strip filler, temporal, and camera words, returning pure visual semantics."""
        noise_pat = r"\b(?:detected|captured|seen|recorded|around|during|at|on|in|between|from|to|today|yesterday)\b"
        cleaned = re.sub(noise_pat, " ", text, flags=re.IGNORECASE)
        return " ".join(cleaned.split())

    # -------------------------------------------------------------------------
    # Method 7: Visual Entity & Attribute Extractor
    # -------------------------------------------------------------------------
    def extract_visual_attributes(self, text: str) -> dict[str, list[str]]:
        """Extract detected colors, garments, and actions from the visual query."""
        low = text.lower()
        colors = [c for c in self.COLOR_KEYWORDS if re.search(rf"\b{c}\b", low)]
        garments = [g for g in self.GARMENT_KEYWORDS if re.search(rf"\b{g}\b", low)]
        actions = [a for a in self.ACTION_KEYWORDS if a in low]
        return {
            "colors": colors,
            "garments": garments,
            "actions": actions,
        }

    # -------------------------------------------------------------------------
    # Method 8: Master Resolution Method
    # -------------------------------------------------------------------------
    def parse_query(self, query: str, ref_utc: datetime | None = None) -> dict[str, Any]:
        """Execute the full tool pipeline: camera resolution, time windowing, and visual cleaning."""
        raw = (query or "").strip()
        if not raw:
            return {
                "visual_query": "", "camera_id": None, "start_utc": None, "end_utc": None,
                "attributes": {"colors": [], "garments": [], "actions": []},
            }

        now_utc = ref_utc or datetime.now(timezone.utc)
        ref_local = now_utc + self.offset

        # 1. Camera
        camera_id, rem_text = self.resolve_camera(raw)

        # 2. Date
        target_date, rem_text, explicit_range = self.resolve_calendar_date(rem_text, ref_local)

        start_local: datetime | None = None
        end_local: datetime | None = None

        if explicit_range:
            start_local, end_local = explicit_range
        else:
            # 3. Relative Time ('just now', 'earlier today')
            start_local, end_local, rem_text = self.resolve_relative_time(rem_text, ref_local, target_date)

            # 4. Clock Ranges ('around 3pm', 'between 9:00AM to 11:00AM')
            if start_local is None:
                start_local, end_local, rem_text = self.resolve_clock_range(rem_text, target_date)

            # 5. Named Periods ('lunch time', 'evening', 'late night')
            if start_local is None:
                start_local, end_local, rem_text = self.resolve_named_period(rem_text, target_date)

        # 6. Clean Visual Query
        pure_visual = self.clean_visual_query(rem_text) or raw

        # 7. Extract Visual Attributes
        attributes = self.extract_visual_attributes(pure_visual)

        # 8. Convert to UTC ISO-8601
        start_utc = (start_local - self.offset).strftime("%Y-%m-%dT%H:%M:%SZ") if start_local else None
        end_utc = (end_local - self.offset).strftime("%Y-%m-%dT%H:%M:%SZ") if end_local else None

        return {
            "visual_query": pure_visual,
            "camera_id": camera_id,
            "start_utc": start_utc,
            "end_utc": end_utc,
            "start_local": start_local.strftime("%Y-%m-%d %H:%M:%S") if start_local else None,
            "end_local": end_local.strftime("%Y-%m-%d %H:%M:%S") if end_local else None,
            "has_temporal_filter": bool(start_utc or end_utc),
            "attributes": attributes,
        }

    # -------------------------------------------------------------------------
    # Method 9: LLM Tool Schemas
    # -------------------------------------------------------------------------
    @classmethod
    def get_tool_schemas(cls) -> list[dict[str, Any]]:
        """Return function calling tool definitions formatted for local Ollama models."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "resolve_temporal_window",
                    "description": "Resolves vague or colloquial natural time phrases ('earlier today', 'around 3pm', 'lunch time', 'on wednesday evening') into exact UTC ISO-8601 timestamps.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "time_phrase": {"type": "string", "description": "The natural language time phrase."},
                        },
                        "required": ["time_phrase"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "resolve_camera_id",
                    "description": "Normalizes camera mentions ('in Cam 57', 'cam6') into standard identifiers ('CAM057').",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "camera_phrase": {"type": "string", "description": "The camera identifier phrase."},
                        },
                        "required": ["camera_phrase"],
                    },
                },
            },
        ]


# Backward compatibility aliases
resolve_camera_id = lambda text: TimeAndQueryResolver().resolve_camera(text)
resolve_vague_time_window = lambda text, **kwargs: TimeAndQueryResolver(
    ist_offset_hours=kwargs.get("ist_offset_hours", 5.5)
).parse_query(text, ref_utc=kwargs.get("ref_utc"))

# Backward compatibility aliases
resolve_camera_id = lambda text: TimeAndQueryResolver().resolve_camera(text)
resolve_vague_time_window = lambda text, **kwargs: TimeAndQueryResolver(
    ist_offset_hours=kwargs.get("ist_offset_hours", 5.5)
).parse_query(text, ref_utc=kwargs.get("ref_utc"))

