"""Surveillance Query Resolution Tools.

Exposes the class-based TimeAndQueryResolver as QueryTools.
"""

from .time_resolver import (
    TimeAndQueryResolver,
    TimeAndQueryResolver as QueryTools,
    resolve_camera_id,
    resolve_vague_time_window,
)

__all__ = [
    "QueryTools",
    "TimeAndQueryResolver",
    "resolve_camera_id",
    "resolve_vague_time_window",
]

