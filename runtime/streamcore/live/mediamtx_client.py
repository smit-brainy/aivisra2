"""Small dependency-free MediaMTX control API client."""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen


class MediaMTXUnavailable(RuntimeError):
    pass


class MediaMTXClient:
    def __init__(self, api_url: str, webrtc_base_url: str, timeout: float = 2) -> None:
        self.api_url = api_url.rstrip("/")
        self.webrtc_base_url = webrtc_base_url.rstrip("/")
        self.timeout = timeout

    def playback_url(self, path: str) -> str:
        return f"{self.webrtc_base_url}/{quote(path, safe='_.~-')}"

    def path_status(self, path: str) -> tuple[bool, int]:
        try:
            with urlopen(f"{self.api_url}/v3/paths/get/{quote(path, safe='_.~-')}",
                         timeout=self.timeout) as response:
                payload = json.load(response)
        except HTTPError as exc:
            if exc.code == 404:
                return False, 0
            raise MediaMTXUnavailable("mediamtx-api-error") from exc
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            if self.is_webrtc_live():
                return True, 0
            raise MediaMTXUnavailable("mediamtx-unavailable") from exc
        ready = bool(payload.get("ready", False))
        readers = payload.get("readers") or []
        return ready, len(readers) if isinstance(readers, list) else 0

    def is_webrtc_live(self) -> bool:
        import socket
        from urllib.parse import urlsplit
        try:
            parts = urlsplit(self.webrtc_base_url)
            host = parts.hostname or "127.0.0.1"
            port = parts.port or 8889
            with socket.create_connection((host, port), timeout=self.timeout):
                return True
        except Exception:
            return False
