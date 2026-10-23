from __future__ import annotations

import datetime
import json
import logging
import os
from pathlib import Path
import tempfile
from threading import RLock
from typing import Any

from .types import CameraCapabilityConfig

logger = logging.getLogger(__name__)


class CameraConfigStore:
    """Thread-safe, atomic persistence store for camera capabilities configurations."""

    def __init__(self, path: str | Path = "config/streamcore/camera_capabilities.json") -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        if not self.path.exists():
            self._write_raw({})

    def get(self, camera_id: str) -> CameraCapabilityConfig | None:
        """Fetch active capability configuration for a camera."""
        with self._lock:
            data = self._read_raw()
            c_data = data.get(camera_id)
            if not c_data:
                return None
            return CameraCapabilityConfig(
                camera_id=camera_id,
                version=c_data.get("version", 1),
                enabled_capabilities=list(c_data.get("enabled_capabilities", [])),
                updated_at=c_data.get("updated_at", ""),
                status=c_data.get("status", "ACTIVE"),
                configurations=c_data.get("configurations", {}),
            )

    def get_all(self) -> dict[str, CameraCapabilityConfig]:
        """Fetch all stored camera capability configurations."""
        with self._lock:
            data = self._read_raw()
            res: dict[str, CameraCapabilityConfig] = {}
            for cid, c_data in data.items():
                res[cid] = CameraCapabilityConfig(
                    camera_id=cid,
                    version=c_data.get("version", 1),
                    enabled_capabilities=list(c_data.get("enabled_capabilities", [])),
                    updated_at=c_data.get("updated_at", ""),
                    status=c_data.get("status", "ACTIVE"),
                    configurations=c_data.get("configurations", {}),
                )
            return res

    def save(
        self,
        camera_id: str,
        enabled_capabilities: list[str],
        expected_version: int | None = None,
        configurations: dict[str, Any] | None = None,
    ) -> CameraCapabilityConfig:
        """Atomically persist approved capabilities for a camera with optimistic version checks."""
        with self._lock:
            data = self._read_raw()
            current = data.get(camera_id, {})
            current_ver = current.get("version", 0)

            if expected_version is not None and current_ver != expected_version:
                raise ValueError(
                    f"Config version conflict for {camera_id}: expected version {expected_version}, "
                    f"but current stored version is {current_ver}."
                )

            new_ver = current_ver + 1
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

            # Sanitize: capabilities list only, never store URIs or passwords
            clean_caps = sorted(list(set(enabled_capabilities)))

            data[camera_id] = {
                "version": new_ver,
                "enabled_capabilities": clean_caps,
                "configurations": configurations or {},
                "updated_at": now_iso,
                "status": "ACTIVE",
            }

            self._write_raw(data)

            cfg = CameraCapabilityConfig(
                camera_id=camera_id,
                version=new_ver,
                enabled_capabilities=clean_caps,
                updated_at=now_iso,
                status="ACTIVE",
                configurations=configurations or {},
            )
            logger.info(
                "camera_capabilities_persisted",
                extra={"camera_id": camera_id, "version": new_ver, "capabilities": clean_caps},
            )
            return cfg

    def delete(self, camera_id: str) -> bool:
        """Remove a camera's capability configuration."""
        with self._lock:
            data = self._read_raw()
            if camera_id in data:
                del data[camera_id]
                self._write_raw(data)
                return True
            return False

    def _read_raw(self) -> dict[str, Any]:
        """Read JSON file securely."""
        try:
            if not self.path.exists():
                return {}
            text = self.path.read_text(encoding="utf-8")
            if not text.strip():
                return {}
            return json.loads(text)
        except Exception as exc:
            logger.error("read_camera_capabilities_failed", extra={"reason": str(exc)})
            return {}

    def _write_raw(self, data: dict[str, Any]) -> None:
        """Write JSON file atomically using temporary replacement."""
        temp_dir = self.path.parent
        fd, temp_file = tempfile.mkstemp(dir=temp_dir, prefix="cam_caps_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file, self.path)
        except Exception:
            if os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except OSError:
                    pass
            raise
