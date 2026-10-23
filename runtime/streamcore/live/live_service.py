from ..config import CameraConfig, LiveViewConfig
from .live_types import LiveStream
from .mediamtx_client import MediaMTXClient, MediaMTXUnavailable


class CameraNotFound(KeyError):
    pass


class LiveService:
    def __init__(self, config: LiveViewConfig, cameras: list[CameraConfig],
                 client: MediaMTXClient | None = None) -> None:
        self.config = config
        self.cameras = {camera.id: camera for camera in cameras}
        self.client = client or MediaMTXClient(
            config.mediamtx_api_url, config.mediamtx_webrtc_base_url,
            config.request_timeout_seconds,
        )

    def get(self, camera_id: str) -> LiveStream:
        camera = self.cameras.get(camera_id)
        if camera is None:
            raise CameraNotFound(camera_id)
        path = camera.live_path or camera.id.lower()
        if not self.config.enabled:
            return LiveStream(camera.id, self.config.protocol, "", "disabled")
        try:
            online, viewers = self.client.path_status(path)
            status = "online" if online else "offline"
        except MediaMTXUnavailable:
            status, viewers = "unavailable", 0
        return LiveStream(camera.id, self.config.protocol,
                          self.client.playback_url(path), status, viewers)
