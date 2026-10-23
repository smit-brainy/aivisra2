from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LiveStream:
    camera_id: str
    live_protocol: str
    live_url: str
    status: str
    active_live_viewers: int = 0
