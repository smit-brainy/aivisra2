"""Admin-only, bounded ONVIF camera discovery for private local networks.

Discovery results deliberately live only in process memory.  Credentials are
kept only while the worker runs and never appear in a candidate, response,
audit entry, or log message.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import ipaddress
import json
import logging
from pathlib import Path
import re
import shutil
import socket
import subprocess
from threading import RLock, Thread
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4
from xml.etree import ElementTree as ET

from fastapi import APIRouter, HTTPException, Request, status

from ..auth.audit import get_audit_log
from ..auth.sessions import SESSION_COOKIE_NAME, get_session_store
from ..database import connect
from ..schemas.models import (
    CameraRegisterRequest,
    NetworkDiscoveryRegisterRequest,
    NetworkDiscoveryStartRequest,
)
from .cameras import register_camera

logger = logging.getLogger("streamcore.backend.discovery")
router = APIRouter(prefix="/api/network-discovery", tags=["Network Discovery"])

CAMERA_PORTS = (80, 443, 554, 8554, 8000, 8080, 8899)
ONVIF_PORTS = (80, 8000, 8080, 8899)
MAX_ADDRESSES = 4096
NMAP_TIMEOUT_SECONDS = 20 * 60
FFPROBE_TIMEOUT_SECONDS = 12
WS_DISCOVERY_TIMEOUT_SECONDS = 3
_CREDENTIALS_RE = re.compile(r"(://)([^/@:]+(?::[^/@]*)?@)")


def _request_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _require_admin(request: Request) -> dict[str, Any]:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    resolved = get_session_store().resolve_session(token) if token else None
    if not resolved or resolved["user"].get("role") != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    return resolved["user"]


def validate_private_cidr(value: str) -> ipaddress.IPv4Network:
    """Permit only a reasonably sized RFC1918 IPv4 network."""
    try:
        network = ipaddress.ip_network(value.strip(), strict=False)
    except ValueError as exc:
        raise ValueError("cidr must be a valid IPv4 CIDR") from exc
    if not isinstance(network, ipaddress.IPv4Network):
        raise ValueError("Only IPv4 private networks may be scanned")
    if not network.is_private or network.is_loopback or network.is_link_local or network.is_multicast:
        raise ValueError("cidr must be an RFC1918 private network")
    if network.num_addresses > MAX_ADDRESSES:
        raise ValueError("cidr is too large; the maximum scan size is /20 (4,096 addresses)")
    return network


def redact_rtsp_url(value: str | None) -> str | None:
    if not value:
        return value
    return _CREDENTIALS_RE.sub(r"\\1***:***@", value)


def endpoint_fingerprint(value: str | None) -> tuple[str, str, int | None, str] | None:
    if not value:
        return None
    parsed = urlsplit(value)
    if not parsed.hostname:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    return (parsed.scheme.casefold(), parsed.hostname.casefold(), port, parsed.path or "/")


def _safe_error(error: Exception | str) -> str:
    text = redact_rtsp_url(str(error)) or "Unknown error"
    return text[:300]


def _nmap_command(cidr: str) -> list[str]:
    return [
        "nmap", "-n", "-Pn", "-sT", "--open", "--max-retries", "1",
        "--host-timeout", "8s", "--max-parallelism", "32",
        "-p", ",".join(map(str, CAMERA_PORTS)), "-oX", "-", cidr,
    ]


def parse_nmap_xml(payload: bytes) -> list[dict[str, Any]]:
    """Return only up hosts that expose one or more camera-relevant ports."""
    root = ET.fromstring(payload)
    results: list[dict[str, Any]] = []
    for host in root.findall("host"):
        status_node = host.find("status")
        if status_node is None or status_node.get("state") != "up":
            continue
        address = next((node.get("addr") for node in host.findall("address") if node.get("addrtype") == "ipv4"), None)
        if not address:
            continue
        ports = []
        for port in host.findall("./ports/port"):
            state = port.find("state")
            if state is None or state.get("state") != "open":
                continue
            service = port.find("service")
            ports.append({
                "port": int(port.get("portid", "0")),
                "protocol": port.get("protocol", "tcp"),
                "service": service.get("name") if service is not None else None,
                "product": service.get("product") if service is not None else None,
            })
        if ports:
            results.append({"host": address, "ports": ports})
    return results


def _ws_discovery_hosts() -> list[dict[str, Any]]:
    """Send a minimal ONVIF WS-Discovery Probe and extract advertised XAddrs."""
    message_id = f"uuid:{uuid4()}"
    probe = f'''<?xml version="1.0" encoding="UTF-8"?>
<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"
 xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"
 xmlns:d="http://docs.oasis-open.org/ws-dd/ns/discovery">
 <e:Header><w:MessageID>{message_id}</w:MessageID><w:To>urn:docs-xmlsoap-org:ws:2005:04:discovery</w:To><w:Action>http://docs.oasis-open.org/ws-dd/ns/discovery/Probe</w:Action></e:Header>
 <e:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></e:Body>
</e:Envelope>'''.encode("utf-8")
    found: dict[str, dict[str, Any]] = {}
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            sock.settimeout(0.4)
            sock.sendto(probe, ("239.255.255.250", 3702))
            deadline = time.monotonic() + WS_DISCOVERY_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                try:
                    body, _ = sock.recvfrom(65535)
                except socket.timeout:
                    continue
                try:
                    xml = ET.fromstring(body)
                except ET.ParseError:
                    continue
                for node in xml.iter():
                    if node.tag.endswith("XAddrs") and node.text:
                        for address in node.text.split():
                            parsed = urlsplit(address)
                            if parsed.hostname:
                                found[parsed.hostname] = {"host": parsed.hostname, "onvif_endpoint": address}
    except OSError as exc:
        logger.info("ws_discovery_unavailable reason=%s", _safe_error(exc))
    return list(found.values())


def _probe_onvif(host: str, ports: list[dict[str, Any]], username: str | None, password: str | None) -> list[dict[str, Any]]:
    """Retrieve ONVIF profile stream URLs. Raises an exception per host only."""
    try:
        from onvif import ONVIFCamera
    except ImportError as exc:  # Guard remains useful if dependencies are partially installed.
        raise RuntimeError("ONVIF support is unavailable; install onvif-zeep") from exc

    details: list[dict[str, Any]] = []
    candidate_ports = [p["port"] for p in ports if p.get("port") in ONVIF_PORTS] or list(ONVIF_PORTS)
    last_error: Exception | None = None
    for port in candidate_ports:
        try:
            camera = ONVIFCamera(host, port, username or "", password or "")
            device = camera.create_devicemgmt_service()
            info = device.GetDeviceInformation()
            media = camera.create_media_service()
            for profile in media.GetProfiles():
                uri = media.GetStreamUri({
                    "StreamSetup": {"Stream": "RTP-Unicast", "Transport": {"Protocol": "RTSP"}},
                    "ProfileToken": profile.token,
                }).Uri
                codec = getattr(getattr(profile, "VideoEncoderConfiguration", None), "Encoding", None)
                details.append({
                    "rtsp_url": str(uri), "profile_token": str(profile.token),
                    "codec": str(codec).lower() if codec else None,
                    "manufacturer": getattr(info, "Manufacturer", None), "model": getattr(info, "Model", None),
                    "onvif_port": port,
                })
            if details:
                return details
        except Exception as exc:  # Individual device failures must not abort the job.
            last_error = exc
    if last_error is not None:
        raise last_error
    return details


def _validate_rtsp(rtsp_url: str) -> tuple[bool, dict[str, Any], str | None]:
    command = [
        "ffprobe", "-v", "error", "-rtsp_transport", "tcp", "-show_streams",
        "-of", "json", rtsp_url,
    ]
    try:
        result = subprocess.run(command, capture_output=True, timeout=FFPROBE_TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired:
        return False, {}, "RTSP validation timed out"
    if result.returncode != 0:
        return False, {}, _safe_error(result.stderr.decode("utf-8", "replace") or "RTSP validation failed")
    try:
        data = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False, {}, "RTSP validator returned invalid metadata"
    stream = next((item for item in data.get("streams", []) if item.get("codec_type") == "video"), None)
    if not stream:
        return False, {}, "No video stream was found"
    return True, {"codec": stream.get("codec_name"), "width": stream.get("width"), "height": stream.get("height")}, None


def _existing_camera_fingerprints() -> set[tuple[str, str, int | None, str]]:
    with connect() as conn:
        rows = conn.execute("SELECT uri FROM cameras").fetchall()
    return {fingerprint for row in rows if (fingerprint := endpoint_fingerprint(row["uri"])) is not None}


@dataclass
class DiscoveryCandidate:
    candidate_id: str
    host: str
    ports: list[dict[str, Any]]
    status: str
    onvif_endpoint: str | None = None
    rtsp_url: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    codec: str | None = None
    profile_token: str | None = None
    validation: dict[str, Any] = field(default_factory=dict)
    duplicate: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id, "host": self.host, "ports": self.ports,
            "status": self.status, "onvif_endpoint": redact_rtsp_url(self.onvif_endpoint),
            "rtsp_url": redact_rtsp_url(self.rtsp_url), "manufacturer": self.manufacturer,
            "model": self.model, "codec": self.codec, "profile_token": self.profile_token,
            "validation": self.validation, "duplicate": self.duplicate, "error": self.error,
        }


@dataclass
class DiscoveryJob:
    job_id: str
    cidr: str
    state: str = "queued"
    stage: str = "queued"
    progress: int = 0
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    error: str | None = None
    cancel_requested: bool = False
    candidates: list[DiscoveryCandidate] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for candidate in self.candidates:
            counts[candidate.status] = counts.get(candidate.status, 0) + 1
        return {
            "job_id": self.job_id, "cidr": self.cidr, "state": self.state, "stage": self.stage,
            "progress": self.progress, "created_at": self.created_at, "started_at": self.started_at,
            "completed_at": self.completed_at, "error": self.error, "counts": counts,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


class DiscoveryJobManager:
    def __init__(self) -> None:
        self._lock = RLock()
        self._jobs: dict[str, DiscoveryJob] = {}

    def start(self, cidr: ipaddress.IPv4Network, username: str | None, password: str | None) -> DiscoveryJob:
        job = DiscoveryJob(job_id=f"discovery-{uuid4().hex[:12]}", cidr=str(cidr))
        with self._lock:
            self._jobs[job.job_id] = job
        Thread(target=self._run, args=(job.job_id, username, password), name=job.job_id, daemon=True).start()
        return job

    def get(self, job_id: str) -> DiscoveryJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> DiscoveryJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.state in {"queued", "running"}:
                job.cancel_requested = True
            return job

    def _cancelled(self, job: DiscoveryJob) -> bool:
        with self._lock:
            if not job.cancel_requested:
                return False
            job.state, job.stage, job.completed_at = "cancelled", "cancelled", time.time()
            return True

    def _run(self, job_id: str, username: str | None, password: str | None) -> None:
        job = self.get(job_id)
        if job is None:
            return
        try:
            with self._lock:
                job.state, job.stage, job.progress, job.started_at = "running", "port_scan", 5, time.time()
            result = subprocess.run(_nmap_command(job.cidr), capture_output=True, timeout=NMAP_TIMEOUT_SECONDS, check=False)
            if self._cancelled(job):
                return
            if result.returncode not in (0, 1):
                raise RuntimeError(_safe_error(result.stderr.decode("utf-8", "replace") or "Nmap scan failed"))
            hosts = {entry["host"]: entry for entry in parse_nmap_xml(result.stdout)}
            with self._lock:
                job.stage, job.progress = "ws_discovery", 25
            for entry in _ws_discovery_hosts():
                try:
                    in_scope = ipaddress.ip_address(entry["host"]) in ipaddress.ip_network(job.cidr)
                except ValueError:
                    in_scope = False
                if in_scope:
                    hosts.setdefault(entry["host"], {"host": entry["host"], "ports": [], **entry})
            existing = _existing_camera_fingerprints()
            host_items = list(hosts.values())
            with self._lock:
                job.stage, job.progress = "onvif_validation", 35
            for index, host_info in enumerate(host_items, start=1):
                if self._cancelled(job):
                    return
                candidate = self._discover_host(host_info, username, password, existing)
                with self._lock:
                    job.candidates.append(candidate)
                    job.progress = min(95, 35 + int(index * 60 / max(1, len(host_items))))
            with self._lock:
                job.state, job.stage, job.progress, job.completed_at = "completed", "completed", 100, time.time()
        except subprocess.TimeoutExpired:
            with self._lock:
                job.state, job.stage, job.error, job.completed_at = "failed", "failed", "Network scan timed out", time.time()
        except Exception as exc:
            with self._lock:
                job.state, job.stage, job.error, job.completed_at = "failed", "failed", _safe_error(exc), time.time()
        finally:
            # Ensure the worker cannot retain caller credentials after completion.
            username = None
            password = None

    @staticmethod
    def _discover_host(host_info: dict[str, Any], username: str | None, password: str | None, existing: set[tuple[str, str, int | None, str]]) -> DiscoveryCandidate:
        host, ports = host_info["host"], host_info.get("ports", [])
        candidate = DiscoveryCandidate(candidate_id=f"candidate-{uuid4().hex[:12]}", host=host, ports=ports, status="not_onvif", onvif_endpoint=host_info.get("onvif_endpoint"))
        try:
            streams = _probe_onvif(host, ports, username, password)
        except Exception as exc:
            message = _safe_error(exc)
            lowered = message.casefold()
            if any(token in lowered for token in ("401", "unauthor", "auth")):
                candidate.status = "requires_credentials"
            elif any(token in lowered for token in ("timeout", "refused", "unreachable")):
                candidate.status = "unreachable"
            else:
                candidate.status = "not_onvif"
            candidate.error = message
            return candidate
        if not streams:
            return candidate
        stream = streams[0]
        raw_rtsp_url = stream["rtsp_url"]
        # Candidates survive until process restart, so retain only a redacted
        # endpoint. The raw URI exists only during this validation call.
        candidate.rtsp_url = redact_rtsp_url(raw_rtsp_url)
        candidate.manufacturer, candidate.model = stream.get("manufacturer"), stream.get("model")
        candidate.codec, candidate.profile_token = stream.get("codec"), stream.get("profile_token")
        candidate.onvif_endpoint = candidate.onvif_endpoint or f"http://{host}:{stream.get('onvif_port', 80)}/onvif/device_service"
        candidate.duplicate = endpoint_fingerprint(candidate.rtsp_url) in existing
        ok, metadata, error = _validate_rtsp(raw_rtsp_url)
        candidate.validation = metadata
        if ok:
            candidate.status = "validated"
            candidate.codec = metadata.get("codec") or candidate.codec
        else:
            candidate.status, candidate.error = "invalid_stream", error
        return candidate


_manager = DiscoveryJobManager()


def _ensure_prerequisites() -> None:
    missing = [binary for binary in ("nmap", "ffprobe") if shutil.which(binary) is None]
    try:
        import onvif  # noqa: F401
    except ImportError:
        missing.append("onvif-zeep")
    if missing:
        raise HTTPException(status_code=503, detail="Network discovery prerequisites unavailable: " + ", ".join(missing))


@router.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
def start_job(payload: NetworkDiscoveryStartRequest, request: Request):
    actor = _require_admin(request)
    try:
        network = validate_private_cidr(payload.cidr)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _ensure_prerequisites()
    job = _manager.start(network, payload.username, payload.password)
    get_audit_log().record("network_discovery.start", user_id=actor["user_id"], resource=f"network-discovery/{job.job_id}", detail={"cidr": str(network)}, ip=_request_ip(request))
    return {"job_id": job.job_id, "state": job.state, "cidr": job.cidr}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request):
    _require_admin(request)
    job = _manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Discovery job not found")
    return job.to_dict()


@router.delete("/jobs/{job_id}")
def cancel_job(job_id: str, request: Request):
    actor = _require_admin(request)
    job = _manager.cancel(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Discovery job not found")
    get_audit_log().record("network_discovery.cancel", user_id=actor["user_id"], resource=f"network-discovery/{job_id}", ip=_request_ip(request))
    return {"job_id": job_id, "state": "cancelling" if job.state in {"queued", "running"} else job.state}


@router.post("/jobs/{job_id}/candidates/{candidate_id}/register", status_code=status.HTTP_201_CREATED)
def register_candidate(job_id: str, candidate_id: str, payload: NetworkDiscoveryRegisterRequest, request: Request):
    actor = _require_admin(request)
    job = _manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Discovery job not found")
    candidate = next((item for item in job.candidates if item.candidate_id == candidate_id), None)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Discovery candidate not found")
    if candidate.status != "validated":
        raise HTTPException(status_code=400, detail="Only validated candidates can be registered")
    if candidate.duplicate:
        raise HTTPException(status_code=409, detail="This camera endpoint is already registered")
    rtsp_host = urlsplit(payload.rtsp_url).hostname
    if rtsp_host != candidate.host:
        raise HTTPException(status_code=400, detail="RTSP URL host must match the selected discovery candidate")
    if endpoint_fingerprint(payload.rtsp_url) in _existing_camera_fingerprints():
        raise HTTPException(status_code=409, detail="This RTSP endpoint is already registered")
    result = register_camera(CameraRegisterRequest(
        camera_id=payload.camera_id, name=payload.name or candidate.model or candidate.host,
        rtsp_url=payload.rtsp_url, codec=payload.codec or candidate.codec or "h264",
        decoder=payload.decoder, decoding_fps=payload.decoding_fps, area_id=payload.area_id,
        live_path=payload.live_path,
    ))
    get_audit_log().record("network_discovery.register", user_id=actor["user_id"], resource=f"network-discovery/{job_id}/{candidate_id}", detail={"camera_id": payload.camera_id, "host": candidate.host}, ip=_request_ip(request))
    return result
