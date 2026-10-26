"""Optional local-only preview and live AI demonstration server."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
from urllib.parse import urlsplit, parse_qs
from typing import Any

from ..engine import StreamCore
from .preview_cache import PreviewCache
from ...onboarding.onboarding_service import sanitize_rtsp_url


# Minimal valid 1x1 black JPEG for empty frame placeholder
TINY_JPEG = (
    b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\x02\x01\x01\x01\x01\x01\x02\x01\x01\x01\x02\x02\x02\x02\x02\x04\x03\x02\x02\x02\x02\x05\x04\x04\x03\x04\x06\x05\x06\x06\x06\x05\x06\x06\x06\x07\t\x08\x06\x07\t\x07\x06\x06\x08\x0b\x08\t\n\n\n\n\n\x06\x08\x0b\x0c\x0b\n\x0c\t\n\n\n\xff\xdb\x00C\x01\x02\x02\x02\x02\x02\x02\x05\x03\x03\x05\n\x07\x06\x07\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x03\x01"\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a%&\'()*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xc4\x00\x1f\x01\x00\x03\x01\x01\x01\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x11\x00\x02\x01\x02\x04\x04\x03\x04\x07\x05\x04\x04\x00\x01\x02w\x00\x01\x02\x03\x11\x04\x05!1\x06\x12AQ\x07aq\x13"2\x81\x08\x14B\x91\xa1\xb1\xc1\t#3R\xf0\x15br\xd1\n\x16$4\xe1%\xf1\x17\x18\x19\x1a&\'()*56789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x82\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00?\x00\xfe\x7f\xe8\xa2\x8a\x00\xff\xd9'
)


HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AIVISRA StreamCore — GPU-Native AI Pipeline & Demo</title>
<style>
:root { color-scheme: dark; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0b0f17; color: #e6edf3; }
body { margin: 0; padding: 20px 24px; }
header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; border-bottom: 1px solid #21262d; padding-bottom: 14px; }
h1 { margin: 0; font-size: 1.4rem; display: flex; align-items: center; gap: 10px; font-weight: 700; letter-spacing: -0.02em; }
.badge-tag { font-size: .75rem; background: #238636; color: #fff; padding: 3px 8px; border-radius: 12px; font-weight: 600; }
.subtitle { margin: 4px 0 0; color: #8b949e; font-size: .85rem; }

.toggle-bar { display: flex; gap: 10px; margin-bottom: 16px; align-items: center; flex-wrap: wrap; }
.toggle-title { font-size: .85rem; color: #8b949e; font-weight: 600; }
.btn { background: #161b22; border: 1px solid #30363d; color: #c9d1d9; padding: 7px 16px; border-radius: 6px; cursor: pointer; font-size: .85rem; font-weight: 600; transition: all .15s ease; }
.btn:hover { background: #21262d; border-color: #58a6ff; color: #58a6ff; }
.btn.active { background: #1f6feb; border-color: #388bfd; color: #fff; box-shadow: 0 0 12px rgba(56, 139, 253, 0.35); }
.btn.active-green { background: #238636; border-color: #3fb950; color: #fff; box-shadow: 0 0 12px rgba(63, 185, 80, 0.35); }

/* GRID VIEW */
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
.card { overflow: hidden; border: 1px solid #30363d; border-radius: 8px; background: #161b22; }
.card-head { display: flex; justify-content: space-between; padding: 9px 12px; font-weight: 600; font-size: .88rem; background: #1c2128; border-bottom: 1px solid #30363d; }
.state { font-size: .8rem; color: #d29922; font-weight: 600; }
.state.connected { color: #3fb950; }
.frame { position: relative; aspect-ratio: 16 / 9; background: #010409; display: grid; place-items: center; }
.frame img, .frame canvas, .frame iframe { width: 100%; height: 100%; object-fit: contain; }
.placeholder { position: absolute; color: #8b949e; pointer-events: none; font-size: .85rem; }
.stats { display: flex; flex-direction: column; gap: 3px; padding: 9px 12px; font-size: .78rem; color: #8b949e; border-top: 1px solid #21262d; }

/* DEMO VIEW (3-COLUMN) */
#demo-view { display: none; grid-template-columns: 240px 1fr 320px; gap: 16px; min-height: 560px; }
.demo-pane { background: #161b22; border: 1px solid #30363d; border-radius: 8px; overflow: hidden; display: flex; flex-direction: column; }
.demo-pane-head { padding: 10px 14px; font-weight: 600; font-size: .88rem; background: #1c2128; border-bottom: 1px solid #30363d; display: flex; justify-content: space-between; align-items: center; }

/* Camera Selector Sidebar */
.cam-list { overflow-y: auto; max-height: 600px; padding: 6px; display: flex; flex-direction: column; gap: 4px; }
.cam-item { padding: 9px 12px; border-radius: 6px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; font-size: .83rem; background: #0d1117; border: 1px solid transparent; transition: all .15s; }
.cam-item:hover { background: #21262d; border-color: #58a6ff; }
.cam-item.selected { background: #1f6feb22; border-color: #1f6feb; font-weight: 600; color: #58a6ff; }
.cam-dot { width: 8px; height: 8px; border-radius: 50%; background: #d29922; }
.cam-dot.online { background: #3fb950; box-shadow: 0 0 6px #3fb950; }

/* Main Stage Video Player with Overlay */
.stage-center { position: relative; display: flex; flex-direction: column; background: #010409; }
.stage-video-box { position: relative; width: 100%; aspect-ratio: 16 / 9; background: #000; overflow: hidden; }
.stage-video-box iframe, .stage-video-box img { width: 100%; height: 100%; border: none; object-fit: contain; }
#demo-canvas { position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 10; }
.stage-hud { position: absolute; top: 12px; left: 12px; display: flex; gap: 8px; pointer-events: none; z-index: 15; }
.hud-pill { background: rgba(13, 17, 23, 0.85); backdrop-filter: blur(4px); border: 1px solid #30363d; color: #e6edf3; padding: 4px 10px; border-radius: 14px; font-size: .75rem; font-weight: 600; }
.hud-pill.green { border-color: #3fb950; color: #3fb950; }
.hud-pill.cyan { border-color: #58a6ff; color: #58a6ff; }
.stage-bottom { padding: 12px 16px; background: #161b22; border-top: 1px solid #30363d; display: flex; justify-content: space-between; align-items: center; font-size: .82rem; }

/* Right Telemetry Sidebar */
.telemetry-body { padding: 12px 14px; overflow-y: auto; max-height: 600px; display: flex; flex-direction: column; gap: 14px; font-size: .82rem; }
.tele-group { display: flex; flex-direction: column; gap: 6px; }
.tele-label { font-size: .75rem; text-transform: uppercase; letter-spacing: .04em; color: #8b949e; font-weight: 700; margin-bottom: 2px; }
.tele-row { display: flex; justify-content: space-between; align-items: center; padding: 3px 0; border-bottom: 1px solid #21262d; }
.tele-val { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .85rem; font-weight: 600; color: #edf3f9; }
.tele-val.green { color: #3fb950; }
.tele-val.cyan { color: #79c0ff; }
.badge { padding: 2px 7px; border-radius: 4px; font-size: .75rem; font-weight: 700; font-family: ui-monospace, monospace; }
.badge-gpu { background: #23863622; border: 1px solid #238636; color: #3fb950; }
.badge-zero { background: #1f6feb22; border: 1px solid #1f6feb; color: #58a6ff; }

/* Detections List */
.dets-box { background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 8px; max-height: 140px; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; }
.det-row { display: flex; justify-content: space-between; font-size: .78rem; font-family: ui-monospace, monospace; }

footer { margin-top: 20px; color: #8b949e; font-size: .82rem; display: flex; justify-content: space-between; align-items: center; border-top: 1px solid #21262d; padding-top: 12px; }

/* ONBOARDING VIEW */
#onboarding-view { display: none; flex-direction: column; gap: 16px; max-width: 1100px; margin: 0 auto; width: 100%; }
.ob-card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; overflow: hidden; }
.ob-card-head { padding: 12px 16px; font-weight: 700; font-size: .95rem; background: #1c2128; border-bottom: 1px solid #30363d; display: flex; justify-content: space-between; align-items: center; }
.ob-card-body { padding: 16px; display: flex; flex-direction: column; gap: 14px; }
.form-row { display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap; }
.form-group { display: flex; flex-direction: column; gap: 6px; flex: 1; min-width: 180px; }
.form-label { font-size: .78rem; font-weight: 600; color: #8b949e; text-transform: uppercase; letter-spacing: 0.03em; }
.form-input, .form-select { background: #0d1117; border: 1px solid #30363d; color: #e6edf3; padding: 8px 12px; border-radius: 6px; font-size: .88rem; outline: none; }
.form-input:focus, .form-select:focus { border-color: #58a6ff; }
.progress-container { width: 100%; background: #0d1117; border: 1px solid #30363d; border-radius: 6px; height: 20px; overflow: hidden; position: relative; }
.progress-bar { background: linear-gradient(90deg, #1f6feb, #238636); height: 100%; width: 0%; transition: width .3s ease; }
.progress-text { position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; font-size: .75rem; font-weight: 700; color: #fff; text-shadow: 0 1px 2px rgba(0,0,0,0.8); }

.scene-summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
.scene-summary-box { background: #0d1117; border: 1px solid #21262d; border-radius: 6px; padding: 10px 14px; }
.scene-summary-label { font-size: .75rem; color: #8b949e; font-weight: 600; margin-bottom: 4px; }
.scene-summary-val { font-size: .95rem; font-weight: 700; color: #79c0ff; display: flex; align-items: center; gap: 6px; }

.caps-list { display: flex; flex-direction: column; gap: 10px; }
.cap-item { background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 12px 14px; display: flex; align-items: flex-start; gap: 12px; transition: border-color .15s; }
.cap-item:hover { border-color: #58a6ff; }
.cap-item.disabled { opacity: 0.5; }
.cap-checkbox { width: 18px; height: 18px; accent-color: #238636; cursor: pointer; margin-top: 2px; }
.cap-content { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.cap-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px; }
.cap-title { font-weight: 600; font-size: .9rem; color: #e6edf3; }
.cap-badges { display: flex; gap: 6px; align-items: center; }
.cap-badge { font-size: .7rem; padding: 2px 6px; border-radius: 4px; font-weight: 600; text-transform: uppercase; }
.cap-badge.available { background: #23863622; border: 1px solid #238636; color: #3fb950; }
.cap-badge.setup { background: #d2992222; border: 1px solid #d29922; color: #d29922; }
.cap-badge.not-implemented { background: #f8514922; border: 1px solid #f85149; color: #f85149; }
.cap-badge.score { background: #1f6feb22; border: 1px solid #1f6feb; color: #58a6ff; }
.cap-desc { font-size: .8rem; color: #8b949e; line-height: 1.4; }
.cap-reason { font-size: .78rem; color: #7ee787; font-style: italic; }
.cap-deps { font-size: .75rem; color: #8b949e; }

.action-bar { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 14px 18px; background: #1c2128; border-top: 1px solid #30363d; border-radius: 0 0 8px 8px; flex-wrap: wrap; }
.alert-box { padding: 10px 14px; border-radius: 6px; font-size: .85rem; font-weight: 600; display: none; }
.alert-box.success { background: #23863622; border: 1px solid #3fb950; color: #3fb950; display: block; }
.alert-box.error { background: #f8514922; border: 1px solid #f85149; color: #f85149; display: block; }
.alert-box.info { background: #1f6feb22; border: 1px solid #388bfd; color: #58a6ff; display: block; }

/* SPATIAL VIEW */
#spatial-view { display: none; grid-template-columns: 280px 1fr 340px; gap: 16px; min-height: 600px; }
.sp-card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; overflow: hidden; display: flex; flex-direction: column; }
.sp-card-head { padding: 10px 14px; font-weight: 600; font-size: .88rem; background: #1c2128; border-bottom: 1px solid #30363d; display: flex; justify-content: space-between; align-items: center; }
.sp-body { padding: 12px 14px; overflow-y: auto; max-height: 580px; display: flex; flex-direction: column; gap: 12px; font-size: .82rem; }
.sp-tool-btn { display: flex; align-items: center; justify-content: center; gap: 6px; padding: 8px 12px; border-radius: 6px; font-size: .82rem; font-weight: 600; cursor: pointer; border: 1px solid #30363d; background: #0d1117; color: #c9d1d9; transition: all .15s; }
.sp-tool-btn:hover { background: #21262d; border-color: #58a6ff; }
.sp-tool-btn.active { background: #1f6feb; border-color: #388bfd; color: #fff; }
.sp-list-item { background: #0d1117; border: 1px solid #21262d; border-radius: 6px; padding: 8px 10px; display: flex; justify-content: space-between; align-items: center; }
.sp-badge { font-size: .7rem; font-weight: 700; padding: 2px 6px; border-radius: 4px; }
.sp-badge.info { background: #1f6feb22; border: 1px solid #1f6feb; color: #58a6ff; }
.sp-badge.warning { background: #d2992222; border: 1px solid #d29922; color: #d29922; }
.sp-badge.critical { background: #f8514922; border: 1px solid #f85149; color: #f85149; }
.sp-canvas { position: absolute; top: 0; left: 0; width: 100%; height: 100%; cursor: crosshair; z-index: 10; }
.sp-event-item { background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 8px; display: flex; flex-direction: column; gap: 4px; }
.sp-event-top { display: flex; justify-content: space-between; align-items: center; font-size: .75rem; }
.sp-event-desc { font-size: .8rem; font-weight: 600; color: #e6edf3; }
.sp-event-thumb { width: 100%; max-height: 90px; object-fit: cover; border-radius: 4px; border: 1px solid #30363d; cursor: pointer; margin-top: 4px; }
</style>
</head>
<body>
<header>
  <div>
    <h1>AIVISRA StreamCore <span class="badge-tag">Stage 4: GPU-Native AI</span></h1>
    <p class="subtitle">End-to-End GPU Decode (NVDEC) → CUDA Preprocess (FP16) → Batched YOLO11 Inference · Zero CPU Copy</p>
  </div>
  <div id="runtime-mode-badge" style="font-size: .85rem; color: #79c0ff; font-weight: 600;">Mode: Production AI</div>
</header>

<div class="toggle-bar">
  <span class="toggle-title">View Mode:</span>
  <button id="btn-demo" class="btn active-green" onclick="switchView('demo')">🎯 Single-Camera Focus (Full Stage)</button>
  <button id="btn-mjpeg" class="btn" onclick="switchView('mjpeg')">🤖 Multi-Grid Overview (All Cameras)</button>
  <button id="btn-onboarding" class="btn" onclick="switchView('onboarding')">⚡ Smart Camera Onboarding & AI</button>
  <button id="btn-spatial" class="btn" onclick="switchView('spatial')">📐 Spatial Intelligence & Rules</button>
  <button id="btn-events" class="btn" onclick="switchView('events')">📋 Events & Clips</button>
</div>

<!-- DEMO VIEW -->
<section id="demo-view">
  <!-- Left Column: Camera List -->
  <aside class="demo-pane">
    <div class="demo-pane-head"><span>Cameras</span><span id="demo-cam-count">0</span></div>
    <div class="cam-list" id="cam-selector"></div>
  </aside>

  <!-- Center Column: Video Stage + Canvas Overlay -->
  <main class="demo-pane stage-center">
    <div class="stage-video-box" id="stage-box">
      <iframe id="stage-webrtc" allow="autoplay" style="display:none;"></iframe>
      <img id="stage-mjpeg" style="display:none;" alt="Live stream">
      <canvas id="demo-canvas"></canvas>
      <div class="stage-hud">
        <span class="hud-pill green" id="hud-cam-id">CAM001</span>
        <span class="hud-pill green">⚡ GPU_NATIVE (0 CPU Copies)</span>
        <span class="hud-pill" id="hud-res">1280x720</span>
        <button id="btn-stream-mode" class="hud-pill green" style="pointer-events:auto; cursor:pointer; background:rgba(35,134,54,0.25);" onclick="toggleStreamMode()">🎥 Feed: MJPEG (AI Overlay)</button>
      </div>
    </div>
    <div class="stage-bottom">
      <div>Active: <strong id="stage-active-cam">CAM001</strong> · <span id="stage-active-dec">nvh264dec</span></div>
      <div>Source Latency: <span id="stage-source-latency" style="color:#79c0ff; font-weight:600;">-- ms</span></div>
    </div>
  </main>

  <!-- Right Column: Real-Time Telemetry Dashboard -->
  <aside class="demo-pane">
    <div class="demo-pane-head"><span>GPU-Native Telemetry</span><span style="color:#3fb950;">● LIVE</span></div>
    <div class="telemetry-body">
      <!-- Pipeline Architecture -->
      <div class="tele-group">
        <div class="tele-label">Architecture Path</div>
        <div class="tele-row"><span>Decode Path</span><span class="tele-val">NVDEC Hardware</span></div>
        <div class="tele-row"><span>Frame Path</span><span class="badge badge-gpu" id="tele-frame-path">GPU_NATIVE</span></div>
        <div class="tele-row"><span>CPU Downloads</span><span class="badge badge-zero" id="tele-cpu-downloads">0 frames</span></div>
        <div class="tele-row"><span>Preprocess</span><span class="tele-val green">CUDA FP16 Letterbox</span></div>
      </div>

      <!-- Inference & Latency -->
      <div class="tele-group">
        <div class="tele-label">Live AI Performance</div>
        <div class="tele-row"><span>Ingest FPS</span><span class="tele-val" id="tele-ingest-fps">0.0</span></div>
        <div class="tele-row"><span>AI Inference FPS</span><span class="tele-val green" id="tele-ai-fps">0.0</span></div>
        <div class="tele-row"><span>Preprocess Time</span><span class="tele-val" id="tele-prep-ms">0.0 ms</span></div>
        <div class="tele-row"><span>Inference Time</span><span class="tele-val" id="tele-infer-ms">0.0 ms</span></div>
        <div class="tele-row"><span>Total AI Latency</span><span class="tele-val cyan" id="tele-lat-ms">0.0 ms</span></div>
      </div>

      <!-- Hardware Telemetry -->
      <div class="tele-group">
        <div class="tele-label">NVIDIA RTX 5070 Telemetry</div>
        <div class="tele-row"><span>GPU Utilization</span><span class="tele-val" id="tele-gpu-util">0%</span></div>
        <div class="tele-row"><span>NVDEC Utilization</span><span class="tele-val green" id="tele-nvdec-util">0%</span></div>
        <div class="tele-row"><span>VRAM Memory</span><span class="tele-val" id="tele-vram">0.0 / 12.0 GiB</span></div>
        <div class="tele-row"><span>Process CPU</span><span class="tele-val" id="tele-cpu">0%</span></div>
      </div>

      <!-- ByteTrack Telemetry -->
      <div class="tele-group">
        <div class="tele-label">ByteTrack Telemetry</div>
        <div class="tele-row"><span>Active Tracks</span><span class="tele-val green" id="tele-active-tracks">0</span></div>
        <div class="tele-row"><span>Confirmed Tracks</span><span class="tele-val" id="tele-conf-tracks">0</span></div>
        <div class="tele-row"><span>Track Updates/s</span><span class="tele-val" id="tele-track-rate">0.0</span></div>
        <div class="tele-row"><span>Assoc Latency (p95)</span><span class="tele-val cyan" id="tele-assoc-lat">0.0 ms</span></div>
      </div>

      <!-- Current Detections List -->
      <div class="tele-group">
        <div class="tele-label">Latest Detections (<span id="tele-det-count">0</span>)</div>
        <div class="dets-box" id="tele-dets-list">
          <div style="color:#8b949e; text-align:center; padding:10px;">Waiting for detections...</div>
        </div>
      </div>
    </div>
  </aside>
</section>

<!-- GRID VIEW -->
<main class="grid" id="grid"></main>

<!-- ONBOARDING VIEW -->
<section id="onboarding-view">
  <!-- Step 1: Camera Registration -->
  <div class="ob-card">
    <div class="ob-card-head">
      <span>1. Camera Registration & RTSP Ingestion</span>
      <span class="badge" style="background:#1f6feb22; border:1px solid #1f6feb; color:#58a6ff;">Step 1 of 3</span>
    </div>
    <div class="ob-card-body">
      <div class="form-row">
        <div class="form-group" style="max-width: 180px;">
          <label class="form-label">Camera Name / ID</label>
          <input type="text" id="ob-cam-id" class="form-input" placeholder="e.g. CAM021" value="CAM021">
        </div>
        <div class="form-group" style="flex: 2;">
          <label class="form-label">RTSP Stream URL</label>
          <input type="text" id="ob-rtsp-url" class="form-input" placeholder="rtsp://user:password@192.168.1.100:554/stream1" value="rtsp://127.0.0.1:8554/hotel_1">
        </div>
        <div class="form-group" style="max-width: 120px;">
          <label class="form-label">Codec</label>
          <select id="ob-codec" class="form-select">
            <option value="h264" selected>H.264</option>
            <option value="h265">H.265</option>
          </select>
        </div>
        <div class="form-group" style="max-width: 150px;">
          <label class="form-label">Decoder</label>
          <select id="ob-decoder" class="form-select">
            <option value="auto" selected>Auto (NVDEC)</option>
            <option value="nvh264dec">nvh264dec</option>
            <option value="avdec_h264">avdec_h264</option>
          </select>
        </div>
        <button id="btn-ob-connect" class="btn active-green" onclick="submitOnboarding()" style="padding: 9px 20px;">Connect & Analyze</button>
      </div>

      <div style="display:flex; align-items:center; gap:10px; margin-top:8px; border-top:1px solid #21262d; padding-top:12px;">
        <span style="font-size:.82rem; color:#8b949e;">Or select existing camera to re-profile:</span>
        <select id="ob-existing-cam" class="form-select" style="min-width: 180px;" onchange="onSelectExistingCam(this.value)">
          <option value="">-- Select Camera --</option>
        </select>
        <button class="btn" onclick="profileExistingCam()">Analyze Selected Camera</button>
      </div>
    </div>
  </div>

  <!-- Step 2: Sampling & Profiling Progress Card -->
  <div id="ob-sampling-card" class="ob-card" style="display:none;">
    <div class="ob-card-head">
      <span>2. Representative Frame Sampling Across Time</span>
      <span id="ob-sampling-tag" class="badge badge-gpu">Active</span>
    </div>
    <div class="ob-card-body">
      <div id="ob-sampling-msg" style="font-size:.88rem; color:#79c0ff; font-weight:600;">
        Collecting 20 representative frames over 8–10s observation window...
      </div>
      <div class="progress-container">
        <div id="ob-progress-bar" class="progress-bar"></div>
        <div id="ob-progress-text" class="progress-text">0 / 20 frames (0%)</div>
      </div>
      <div style="display:flex; gap:16px; font-size:.78rem; color:#8b949e;">
        <span>Observation Window: <strong>8.0s</strong></span>
        <span>Rejection: <strong>Duplicates & Blanks filtered</strong></span>
        <span>Resolution: <strong>≤640px bounded copy</strong></span>
        <span>Worker Status: <strong id="ob-worker-status" style="color:#3fb950;">Running</strong></span>
      </div>
    </div>
  </div>

  <!-- Step 3: Scene Profile Summary -->
  <div id="ob-profile-card" class="ob-card" style="display:none;">
    <div class="ob-card-head">
      <span>Scene Profile Summary</span>
      <span id="ob-scene-badge" class="badge" style="background:#23863622; border:1px solid #238636; color:#3fb950;">Analyzed</span>
    </div>
    <div class="ob-card-body">
      <div class="scene-summary-grid">
        <div class="scene-summary-box">
          <div class="scene-summary-label">Scene Type</div>
          <div class="scene-summary-val" id="ob-scene-type">--</div>
        </div>
        <div class="scene-summary-box">
          <div class="scene-summary-label">Confidence (Estimate)</div>
          <div class="scene-summary-val" id="ob-scene-conf" style="color:#3fb950;">--</div>
        </div>
        <div class="scene-summary-box">
          <div class="scene-summary-label">Analysis Method</div>
          <div class="scene-summary-val" id="ob-scene-method" style="color:#d29922;">--</div>
        </div>
        <div class="scene-summary-box">
          <div class="scene-summary-label">Usable Frames Analyzed</div>
          <div class="scene-summary-val" id="ob-scene-frames" style="color:#edf3f9;">--</div>
        </div>
      </div>

      <div style="display:flex; flex-direction:column; gap:6px;">
        <span class="scene-summary-label">Detected Objects</span>
        <div id="ob-scene-objects" style="display:flex; gap:6px; flex-wrap:wrap;"></div>
      </div>

      <div style="display:flex; flex-direction:column; gap:6px;">
        <span class="scene-summary-label">Scene Attributes</span>
        <div id="ob-scene-attrs" style="display:flex; gap:6px; flex-wrap:wrap;"></div>
      </div>

      <div id="ob-scene-limitations-box" style="display:none; font-size:.78rem; color:#8b949e; background:#0d1117; padding:8px 12px; border-radius:6px; border:1px solid #21262d;">
        <strong>Limitations & Heuristics:</strong> <span id="ob-scene-limitations"></span>
      </div>
    </div>
  </div>

  <!-- Step 4: Capability Recommendations & User Approval -->
  <div id="ob-caps-card" class="ob-card" style="display:none;">
    <div class="ob-card-head">
      <span>AI Capability Recommendations & Explicit User Approval</span>
      <span style="font-size:.78rem; color:#8b949e;">No automatic model activation</span>
    </div>
    <div class="ob-card-body">
      <div style="font-size:.82rem; color:#8b949e; line-height:1.4; border-left:3px solid #58a6ff; padding-left:10px;">
        Capabilities define business outcomes (e.g. tracking, occupancy). High-level selections automatically map to shared GPU models and trackers. Check the capabilities you wish to activate for this camera.
      </div>

      <div class="caps-list" id="ob-caps-list"></div>

      <div style="display:flex; align-items:center; gap:10px; margin-top:8px;">
        <select id="ob-add-cap-dropdown" class="form-select" style="max-width: 320px;" onchange="addSelectedCapability(this.value)">
          <option value="">+ Add Optional Capability from Registry...</option>
        </select>
        <button class="btn" onclick="resetCapsSelection()">↺ Reset Recommendations</button>
        <button class="btn" onclick="reAnalyzeCam()">↻ Re-Analyze Stream</button>
      </div>

      <div id="ob-alert" class="alert-box"></div>
    </div>
    <div class="action-bar">
      <div>
        <span style="font-size:.8rem; color:#8b949e;">Selected: </span>
        <strong id="ob-selected-count" style="color:#58a6ff;">0</strong>
        <span style="font-size:.8rem; color:#8b949e; margin-left: 12px;">Active on Camera: </span>
        <strong id="ob-active-count" style="color:#3fb950;">0</strong>
      </div>
      <button id="btn-apply-caps" class="btn active-green" onclick="applyCapabilities()" style="padding: 10px 24px; font-size: .92rem;">
        ✓ Apply Configuration & Activate
      </button>
    </div>
  </div>
</section>

<!-- SPATIAL INTELLIGENCE & RULE ENGINE VIEW -->
<section id="spatial-view">
  <!-- Left Column: Controls, Geometry Manager, Rules -->
  <aside class="sp-card">
    <div class="sp-card-head">
      <span>Spatial Intelligence</span>
      <span id="sp-cam-id-badge" class="badge badge-gpu">CAM001</span>
    </div>
    <div class="sp-body">
      <!-- Camera Selection -->
      <div class="form-group">
        <label class="form-label">Active Camera</label>
        <select id="sp-camera-select" class="form-select" onchange="onSpatialCamSelect(this.value)">
          <option value="">-- Choose Camera --</option>
        </select>
      </div>

      <!-- Drawing Mode Toolbar -->
      <div class="form-group">
        <label class="form-label">Drawing Mode</label>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:6px;">
          <button id="sp-tool-select" class="sp-tool-btn active" onclick="setSpatialTool('select')">🔍 Inspect</button>
          <button id="sp-tool-zone" class="sp-tool-btn" onclick="setSpatialTool('zone')">⬡ Draw Zone</button>
          <button id="sp-tool-line" class="sp-tool-btn" onclick="setSpatialTool('line')">➔ Draw Line</button>
          <button class="sp-tool-btn" onclick="clearActiveDrawing()" style="color:#f85149;">✕ Cancel</button>
        </div>
      </div>

      <!-- Active Drawing Status -->
      <div id="sp-drawing-help" style="font-size:.78rem; color:#79c0ff; background:#0d1117; padding:8px; border-radius:6px; border:1px solid #21262d;">
        Mode: Inspecting live detections & spatial geometry.
      </div>

      <!-- Configured Zones -->
      <div class="form-group">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <label class="form-label">Polygonal Zones (<span id="sp-zone-count">0</span>)</label>
          <button class="btn" style="padding:2px 8px; font-size:.75rem;" onclick="saveZonesToBackend()">💾 Save</button>
        </div>
        <div id="sp-zones-list" style="display:flex; flex-direction:column; gap:6px; max-height:160px; overflow-y:auto;">
          <div style="color:#8b949e; text-align:center; padding:10px;">No zones defined yet.</div>
        </div>
      </div>

      <!-- Configured Virtual Lines -->
      <div class="form-group">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <label class="form-label">Virtual Lines (<span id="sp-line-count">0</span>)</label>
          <button class="btn" style="padding:2px 8px; font-size:.75rem;" onclick="saveLinesToBackend()">💾 Save</button>
        </div>
        <div id="sp-lines-list" style="display:flex; flex-direction:column; gap:6px; max-height:160px; overflow-y:auto;">
          <div style="color:#8b949e; text-align:center; padding:10px;">No lines defined yet.</div>
        </div>
      </div>

      <!-- Rules Quick Management -->
      <div class="form-group">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <label class="form-label">Spatial Rules (<span id="sp-rule-count">0</span>)</label>
          <button class="btn" style="padding:2px 8px; font-size:.75rem;" onclick="promptAddRule()">+ Add Rule</button>
        </div>
        <div id="sp-rules-list" style="display:flex; flex-direction:column; gap:6px; max-height:140px; overflow-y:auto;">
          <div style="color:#8b949e; text-align:center; padding:10px;">No rules configured.</div>
        </div>
      </div>
    </div>
  </aside>

  <!-- Center Stage: Video View + Canvas Overlay with Drawing Handler -->
  <main class="stage-center" style="border-radius:8px; overflow:hidden; border:1px solid #30363d;">
    <div class="stage-video-box" id="sp-stage-box" style="aspect-ratio: 16/9; position:relative; background:#000;">
      <img id="sp-stage-mjpeg" src="" alt="Spatial Preview" style="width:100%; height:100%; object-fit:contain; display:block;">
      <canvas id="sp-canvas" class="sp-canvas"></canvas>
      <div class="stage-hud">
        <span class="hud-pill green" id="sp-hud-cam">CAM001</span>
        <span class="hud-pill" id="sp-hud-mode">MODE: INSPECT</span>
        <span class="hud-pill" id="sp-hud-coords">X: 0.000, Y: 0.000</span>
      </div>
    </div>
    <div class="stage-bottom">
      <div style="display:flex; gap:12px; align-items:center;">
        <span>Active Tracks: <strong id="sp-active-tracks-count" style="color:#3fb950;">0</strong></span>
        <span>|</span>
        <span>Visible Heads: <strong id="sp-visible-occ-count" style="color:#79c0ff;">0</strong></span>
        <span>|</span>
        <span>Flow Occupancy: <strong id="sp-flow-occ-count" style="color:#e6edf3;">0</strong></span>
      </div>
      <div>
        <button class="btn" onclick="saveAllSpatialConfig()" style="background:#238636; color:#fff; border-color:#3fb950;">Save All Configuration</button>
      </div>
    </div>
  </main>

  <!-- Right Column: Live Occupancy HUD & Live Events Stream -->
  <aside class="sp-card">
    <div class="sp-card-head">
      <span>Occupancy & Live Events</span>
      <span style="color:#3fb950;">● STREAMING</span>
    </div>
    <div class="sp-body">
      <!-- Occupancy HUD Card -->
      <div style="background:#0d1117; border:1px solid #21262d; border-radius:6px; padding:10px; display:flex; flex-direction:column; gap:8px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <span style="font-size:.78rem; font-weight:700; color:#8b949e; text-transform:uppercase;">Occupancy Telemetry</span>
          <button class="btn" style="padding:2px 8px; font-size:.72rem;" onclick="reconcileOccupancy()">Reconcile</button>
        </div>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px;">
          <div style="background:#161b22; border-radius:4px; padding:6px 8px;">
            <div style="font-size:.7rem; color:#8b949e;">Visible Heads</div>
            <div id="sp-stat-visible" style="font-size:1.1rem; font-weight:700; color:#79c0ff;">0</div>
          </div>
          <div style="background:#161b22; border-radius:4px; padding:6px 8px;">
            <div style="font-size:.7rem; color:#8b949e;">Flow Occupancy</div>
            <div id="sp-stat-flow" style="font-size:1.1rem; font-weight:700; color:#3fb950;">0</div>
          </div>
          <div style="background:#161b22; border-radius:4px; padding:6px 8px;">
            <div style="font-size:.7rem; color:#8b949e;">Total IN</div>
            <div id="sp-stat-in" style="font-size:.95rem; font-weight:600; color:#e6edf3;">0</div>
          </div>
          <div style="background:#161b22; border-radius:4px; padding:6px 8px;">
            <div style="font-size:.7rem; color:#8b949e;">Total OUT</div>
            <div id="sp-stat-out" style="font-size:.95rem; font-weight:600; color:#e6edf3;">0</div>
          </div>
        </div>
      </div>

      <!-- Real-Time Event Feed -->
      <div class="form-group" style="flex:1; display:flex; flex-direction:column;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
          <label class="form-label" style="margin:0;">Spatial Events (<span id="sp-event-count">0</span>)</label>
          <span style="font-size:.7rem; color:#8b949e;">Auto-refreshing</span>
        </div>
        <div id="sp-events-stream" style="background:#0d1117; border:1px solid #30363d; border-radius:6px; padding:8px; display:flex; flex-direction:column; gap:8px; max-height:300px; overflow-y:auto; flex:1;">
          <div style="color:#8b949e; text-align:center; padding:16px;">Waiting for spatial events...</div>
        </div>
      </div>

      <!-- Spatial Performance Metrics -->
      <div style="background:#0d1117; border:1px solid #21262d; border-radius:6px; padding:10px; font-size:.75rem; color:#8b949e; display:flex; flex-direction:column; gap:4px;">
        <div style="display:flex; justify-content:space-between;"><span>Spatial Eval Latency (p95):</span><strong id="sp-metric-lat" style="color:#79c0ff;">0.0 ms</strong></div>
        <div style="display:flex; justify-content:space-between;"><span>Events Generated:</span><strong id="sp-metric-evts" style="color:#e6edf3;">0</strong></div>
        <div style="display:flex; justify-content:space-between;"><span>Duplicate Filtered:</span><strong id="sp-metric-dedup" style="color:#3fb950;">0</strong></div>
      </div>
    </div>
  </aside>
</section>

<!-- EVENTS & CLIPS VIEW -->
<section id="events-view" style="display:none; flex-direction:column; gap:20px; max-width:960px; margin:0 auto; width:100%;">

  <!-- LEVEL 2: AI NATURAL LANGUAGE VISUAL SEARCH (FAISS) -->
  <div style="background:#161b22; border:1px solid #388bfd; border-radius:8px; overflow:hidden; box-shadow:0 4px 20px rgba(56,139,253,0.12);">
    <div style="padding:16px 20px; background:#1c2128; border-bottom:1px solid #30363d; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
      <div style="display:flex; align-items:center; gap:10px;">
        <span style="font-size:1.3rem;">🧠</span>
        <div>
          <div style="font-weight:700; font-size:1.05rem; color:#e6edf3;">AI Natural Language Video Search</div>
          <div style="font-size:.78rem; color:#8b949e;">Local VLM (Qwen 3.5 9B) & FAISS vector search across COCO detections & video clips</div>
        </div>
      </div>
      <div style="display:flex; gap:8px; align-items:center;">
        <span id="gemini-status-pill" class="badge" style="background:#23863622; border:1px solid #238636; color:#3fb950; font-size:.78rem;" title="100% Local VLM & FAISS Search">
          Checking Local VLM...
        </span>
        <button type="button" class="btn" style="padding:4px 10px; font-size:.78rem;" onclick="reindexExistingClips()" title="Index past clips in database">↻ Index Past Clips</button>
      </div>
    </div>

    <div style="padding:22px 24px;">
      <form id="vector-search-form" onsubmit="return queryVisualVector(event)">
        <div style="display:flex; gap:12px; margin-bottom:14px; flex-wrap:wrap;">
          <div style="flex:1; min-width:280px;">
            <label class="form-label" style="display:flex; justify-content:space-between; align-items:center;">
              <span>Describe the person / clothing / appearance <span style="color:#f85149;">*</span></span>
              <span style="font-size:.75rem; color:#58a6ff; cursor:pointer;" onclick="setSampleQuery('person with white clothes')">Example: "person with white clothes"</span>
            </label>
            <div style="position:relative;">
              <input type="text" id="vector-query-text" class="form-input" style="padding-left:36px; font-size:1rem; height:42px;" placeholder="e.g. person with white clothes, someone wearing blue jeans, dark jacket..." required>
              <span style="position:absolute; left:12px; top:11px; color:#8b949e; font-size:1.05rem;">🔍</span>
            </div>
          </div>

          <div style="width:170px;">
            <label class="form-label">Camera Filter</label>
            <select id="vector-camera-id" class="form-select" style="height:42px;">
              <option value="">-- All Cameras --</option>
            </select>
          </div>

          <div style="width:140px;">
            <label class="form-label">Matches</label>
            <select id="vector-top-k" class="form-select" style="height:42px;">
              <option value="2" selected>Top 2 (Recommended)</option>
              <option value="5">Top 5</option>
              <option value="10">Top 10</option>
            </select>
          </div>
        </div>

        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:12px; margin-bottom:14px;">
          <div>
            <label class="form-label" style="color:#8b949e;">Start Time (IST, Optional)</label>
            <input type="datetime-local" id="vector-start-time" class="form-input">
          </div>
          <div>
            <label class="form-label" style="color:#8b949e;">End Time (IST, Optional)</label>
            <input type="datetime-local" id="vector-end-time" class="form-input">
          </div>
        </div>

        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
          <div style="display:flex; gap:10px; align-items:center;">
            <button type="submit" class="btn active-green" style="padding:9px 24px; font-size:.92rem; font-weight:700;">
              ⚡ Search Clips
            </button>
            <button type="button" class="btn" onclick="resetVectorSearch()" style="padding:9px 18px; font-size:.92rem;">
              🔄 Reset
            </button>
          </div>

          <div style="display:flex; gap:6px; align-items:center; flex-wrap:wrap;">
            <span style="font-size:.75rem; color:#8b949e;">Quick prompts:</span>
            <button type="button" class="btn" style="padding:3px 8px; font-size:.75rem;" onclick="setSampleQuery('person with white clothes')">white clothes</button>
            <button type="button" class="btn" style="padding:3px 8px; font-size:.75rem;" onclick="setSampleQuery('person wearing dark jacket')">dark jacket</button>
            <button type="button" class="btn" style="padding:3px 8px; font-size:.75rem;" onclick="setSampleQuery('someone in blue jeans')">blue jeans</button>
            <button type="button" class="btn" style="padding:3px 8px; font-size:.75rem;" onclick="setSampleQuery('person carrying backpack')">backpack</button>
          </div>
        </div>
      </form>

      <!-- Vector Search Results Display -->
      <div id="vector-result-container" style="display:none; margin-top:20px; padding-top:16px; border-top:1px solid #21262d;">
        <div id="vector-result-content"></div>
      </div>
    </div>
  </div>
  <div style="background:#161b22; border:1px solid #30363d; border-radius:8px; overflow:hidden;">
    <div style="padding:16px 20px; font-weight:700; font-size:1rem; background:#1c2128; border-bottom:1px solid #30363d;">
      📋 Find Video Clip by Time Range
    </div>
    <div style="padding:24px;">
      <form id="clip-query-form" onsubmit="return queryClip(event)">
        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:16px; margin-bottom:16px;">
          <div class="form-group">
            <label class="form-label">Camera ID (Optional)</label>
            <select id="query-camera-id" class="form-select">
              <option value="">-- All Cameras --</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Start Time (IST) <span style="color:#f85149;">*</span></label>
            <input type="datetime-local" id="query-start-time" class="form-input" required>
          </div>
          <div class="form-group">
            <label class="form-label">End Time (IST) <span style="color:#f85149;">*</span></label>
            <input type="datetime-local" id="query-end-time" class="form-input" required>
          </div>
          <div class="form-group">
            <label class="form-label">Class (Optional)</label>
            <select id="query-class" class="form-select">
              <option value="">All Classes</option>
              <option value="person" selected>person</option>
              <option value="car">car</option>
              <option value="truck">truck</option>
              <option value="bus">bus</option>
              <option value="motorcycle">motorcycle</option>
              <option value="bicycle">bicycle</option>
            </select>
          </div>
        </div>
        <div style="display:flex; gap:12px; justify-content:flex-start;">
          <button type="submit" class="btn active-green" style="padding:10px 24px; font-size:.9rem;">
            🔍 Find Clip
          </button>
          <button type="button" class="btn" onclick="resetQueryForm()" style="padding:10px 24px; font-size:.9rem;">
            🔄 New Query
          </button>
        </div>
      </form>

      <!-- Result Area -->
      <div id="query-result" style="display:none; margin-top:24px; padding-top:16px; border-top:1px solid #21262d;">
        <div id="result-content"></div>
      </div>
    </div>
  </div>
</section>

<footer>
  <span>AIVISRA StreamCore · GPU-Native Ingest & Inference Engine</span>
  <span>Zero-Copy CUDA Frame Pipeline · Hardware Verified</span>
</footer>

<script id="camera-ids" type="application/json">__CAMERAS__</script>
<script id="source-ids" type="application/json">__SOURCES__</script>
<script id="live-paths" type="application/json">__LIVE_PATHS__</script>
<script id="webrtc-base" type="application/json">__WEBRTC_BASE__</script>
<script>
const ids = JSON.parse(document.getElementById('camera-ids').textContent);
const sourceFor = JSON.parse(document.getElementById('source-ids').textContent);
const livePaths = JSON.parse(document.getElementById('live-paths').textContent || '{}');
const webrtcBase = JSON.parse(document.getElementById('webrtc-base').textContent || '""');

const grid = document.getElementById('grid');
const demoView = document.getElementById('demo-view');
const camSelector = document.getElementById('cam-selector');
const stageBox = document.getElementById('stage-box');
const stageWebrtc = document.getElementById('stage-webrtc');
const stageMjpeg = document.getElementById('stage-mjpeg');
const canvas = document.getElementById('demo-canvas');
const ctx = canvas.getContext('2d');

let currentView = 'demo'; // 'demo', 'mjpeg', 'webrtc'
let selectedCam = ids.length > 0 ? ids[0] : 'CAM001';
const cards = new Map();
const previous = new Map();
let statusData = null;

// Populate Camera Selector
document.getElementById('demo-cam-count').textContent = ids.length;
for (const id of ids) {
  const item = document.createElement('div');
  item.className = 'cam-item' + (id === selectedCam ? ' selected' : '');
  item.id = 'sel-' + id;
  item.onclick = () => selectCamera(id);

  const nameSpan = document.createElement('span');
  nameSpan.textContent = id;
  const dot = document.createElement('span');
  dot.className = 'cam-dot';
  dot.id = 'dot-' + id;

  item.append(nameSpan, dot);
  camSelector.append(item);
}

// Populate Grid Cards
for (const id of ids) {
  const card = document.createElement('article'); card.className = 'card';
  card.style.cursor = 'pointer';
  card.onclick = () => { switchView('demo'); selectCamera(id); };
  const head = document.createElement('div'); head.className = 'card-head';
  const name = document.createElement('span'); name.textContent = id;
  const state = document.createElement('span'); state.className = 'state'; state.textContent = 'CONNECTING';
  head.append(name, state);
  const box = document.createElement('div'); box.className = 'frame';
  const source = sourceFor[id];
  const livePath = livePaths[id] || source.toLowerCase();

  const iframe = document.createElement('iframe');
  iframe.className = 'feed-webrtc';
  iframe.setAttribute('allow', 'autoplay');
  if (webrtcBase) {
    iframe.dataset.src = `${webrtcBase}/${livePath}/?controls=0&autoplay=1&muted=1`;
  }
  iframe.style.width = '100%'; iframe.style.height = '100%'; iframe.style.border = 'none'; iframe.style.background = '#000';
  iframe.style.display = 'none';

  const img = document.createElement('img');
  img.className = 'feed-mjpeg';
  img.style.width = '100%'; img.style.height = '100%'; img.style.objectFit = 'contain';
  img.style.display = 'block';

  const cardCanvas = document.createElement('canvas');
  cardCanvas.className = 'card-canvas';
  cardCanvas.style.position = 'absolute';
  cardCanvas.style.top = '0';
  cardCanvas.style.left = '0';
  cardCanvas.style.width = '100%';
  cardCanvas.style.height = '100%';
  cardCanvas.style.pointerEvents = 'none';
  cardCanvas.style.zIndex = '10';
  const cardCtx = cardCanvas.getContext('2d');

  const placeholder = document.createElement('span'); placeholder.className = 'placeholder'; placeholder.textContent = 'Connecting…';
  box.append(iframe, img, cardCanvas, placeholder);
  const stats = document.createElement('div'); stats.className = 'stats';
  card.append(head, box, stats); grid.append(card);
  cards.set(id, {state, iframe, img, cardCanvas, cardCtx, box, placeholder, stats, source});
}

let streamMode = 'mjpeg'; // 'mjpeg' or 'webrtc'
function toggleStreamMode() {
  setStreamMode(streamMode === 'mjpeg' ? 'webrtc' : 'mjpeg');
}

function setStreamMode(mode) {
  streamMode = mode;
  const btn = document.getElementById('btn-stream-mode');
  if (btn) {
    if (mode === 'webrtc') {
      btn.textContent = '⚡ Feed: WebRTC (Native 24 FPS)';
      btn.className = 'hud-pill cyan';
      btn.style.background = 'rgba(56,139,253,0.25)';
      btn.style.borderColor = '#58a6ff';
    } else {
      btn.textContent = '🎥 Feed: MJPEG (AI Overlay)';
      btn.className = 'hud-pill green';
      btn.style.background = 'rgba(35,134,54,0.25)';
      btn.style.borderColor = '#3fb950';
    }
  }
  selectCamera(selectedCam);
}

function selectCamera(id) {
  selectedCam = id;
  document.querySelectorAll('.cam-item').forEach(el => el.classList.remove('selected'));
  const activeEl = document.getElementById('sel-' + id);
  if (activeEl) activeEl.classList.add('selected');
  document.getElementById('hud-cam-id').textContent = id;
  document.getElementById('stage-active-cam').textContent = id;

  const source = sourceFor[id] || id;
  const livePath = livePaths[id] || source.toLowerCase();

  if (streamMode === 'webrtc' && webrtcBase) {
    stageMjpeg.src = '';
    stageMjpeg.style.display = 'none';
    stageWebrtc.src = `${webrtcBase}/${livePath}/?controls=0&autoplay=1&muted=1`;
    stageWebrtc.style.display = 'block';
  } else {
    stageWebrtc.src = 'about:blank';
    stageWebrtc.style.display = 'none';
    stageMjpeg.src = '';
    setTimeout(() => {
      stageMjpeg.src = `/stream/${id}.mjpg?t=` + Date.now();
      stageMjpeg.style.display = 'block';
    }, 10);
  }

  if (statusData && statusData.cameras && statusData.cameras[id]) {
    const m = statusData.cameras[id];
    document.getElementById('tele-ingest-fps').textContent = (m.input_fps || 0).toFixed(1);
    document.getElementById('tele-ai-fps').textContent = (m.ai_fps || 0).toFixed(1);
    document.getElementById('stage-active-dec').textContent = `${m.decoder_name || 'auto'} (${m.decoder_type || 'hw'})`;
  }
  detectionPollerActive = false;
  pollDetections();
}

let activeOnboardingCamId = '';
let activeOnboardingVersion = 1;
let rawRecommendations = [];
let capabilityRegistryList = [];
const onboardingView = document.getElementById('onboarding-view');
const eventsView = document.getElementById('events-view');

function switchView(view) {
  currentView = view;
  document.getElementById('btn-demo').className = 'btn' + (view === 'demo' ? ' active-green' : '');
  document.getElementById('btn-mjpeg').className = 'btn' + (view === 'mjpeg' ? ' active-green' : '');
  const btnOb = document.getElementById('btn-onboarding');
  if (btnOb) btnOb.className = 'btn' + (view === 'onboarding' ? ' active-green' : '');
  const btnSpatial = document.getElementById('btn-spatial');
  if (btnSpatial) btnSpatial.className = 'btn' + (view === 'spatial' ? ' active-green' : '');
  const btnEvents = document.getElementById('btn-events');
  if (btnEvents) btnEvents.className = 'btn' + (view === 'events' ? ' active-green' : '');

  const spatialView = document.getElementById('spatial-view');

  if (view === 'demo') {
    demoView.style.display = 'grid';
    grid.style.display = 'none';
    if (onboardingView) onboardingView.style.display = 'none';
    if (spatialView) spatialView.style.display = 'none';
    if (eventsView) eventsView.style.display = 'none';
    selectCamera(selectedCam);
  } else if (view === 'mjpeg') {
    demoView.style.display = 'none';
    grid.style.display = 'grid';
    if (onboardingView) onboardingView.style.display = 'none';
    if (spatialView) spatialView.style.display = 'none';
    if (eventsView) eventsView.style.display = 'none';
    stageMjpeg.src = '';
    stageWebrtc.src = 'about:blank';
    stageWebrtc.style.display = 'none';
    for (const card of cards.values()) {
      card.iframe.src = 'about:blank';
      card.iframe.style.display = 'none';
      card.img.style.display = 'block';
    }
  } else if (view === 'onboarding') {
    demoView.style.display = 'none';
    grid.style.display = 'none';
    if (onboardingView) onboardingView.style.display = 'flex';
    if (spatialView) spatialView.style.display = 'none';
    if (eventsView) eventsView.style.display = 'none';
    stageMjpeg.src = '';
    loadExistingCamerasForOnboarding();
    loadCapabilityRegistry();
  } else if (view === 'spatial') {
    demoView.style.display = 'none';
    grid.style.display = 'none';
    if (onboardingView) onboardingView.style.display = 'none';
    if (spatialView) spatialView.style.display = 'grid';
    if (eventsView) eventsView.style.display = 'none';
    stageMjpeg.src = '';
    if (typeof initSpatialView === 'function') initSpatialView();
  } else if (view === 'events') {
    demoView.style.display = 'none';
    grid.style.display = 'none';
    if (onboardingView) onboardingView.style.display = 'none';
    if (spatialView) spatialView.style.display = 'none';
    if (eventsView) eventsView.style.display = 'flex';
    stageMjpeg.src = '';
    stageWebrtc.src = 'about:blank';
    stageWebrtc.style.display = 'none';
    populateQueryCameraFilter();
    populateVectorCameraFilter();
    checkGeminiStatus();
    // Reset any previous result
    document.getElementById('query-result').style.display = 'none';
  }
}

async function loadExistingCamerasForOnboarding() {
  const sel = document.getElementById('ob-existing-cam');
  if (!sel) return;
  try {
    const res = await fetch('/api/cameras');
    if (res.ok) {
      const cams = await res.json();
      sel.innerHTML = '<option value="">-- Select Camera --</option>' +
        cams.map(c => `<option value="${c.camera_id}">${c.camera_id} (${c.codec || 'h264'})</option>`).join('');
    }
  } catch (e) {}
}

async function loadCapabilityRegistry() {
  try {
    const res = await fetch('/api/capabilities');
    if (res.ok) {
      capabilityRegistryList = await res.json();
      const drop = document.getElementById('ob-add-cap-dropdown');
      if (drop) {
        drop.innerHTML = '<option value="">+ Add Optional Capability from Registry...</option>' +
          capabilityRegistryList.map(c => `<option value="${c.id}">${c.display_name} (${c.implementation_status})</option>`).join('');
      }
    }
  } catch (e) {}
}

// ===== EVENTS & CLIPS VIEW FUNCTIONS =====

// Populate camera dropdown for vector search
async function populateVectorCameraFilter() {
  const select = document.getElementById('vector-camera-id');
  if (!select) return;
  try {
    const res = await fetch('/api/cameras');
    if (res.ok) {
      const cams = await res.json();
      select.innerHTML = '<option value="">-- All Cameras --</option>' +
        cams.map(c => `<option value="${c.camera_id}">${c.camera_id}</option>`).join('');
    }
  } catch (e) {}
}

// Check Gemini API Key status
async function checkGeminiStatus() {
  const pill = document.getElementById('gemini-status-pill');
  if (!pill) return;
  try {
    const res = await fetch('/api/settings/gemini');
    if (res.ok) {
      const data = await res.json();
      if (data.has_api_key) {
        pill.style.background = '#23863622';
        pill.style.borderColor = '#238636';
        pill.style.color = '#3fb950';
        pill.innerHTML = '🟢 Local VLM Active (Qwen 3.5 9B + EmbeddingGemma)';
      } else {
        pill.style.background = '#d2992222';
        pill.style.borderColor = '#d29922';
        pill.style.color = '#d29922';
        pill.innerHTML = '🟡 Local CV Fallback (Ollama Offline)';
      }
    }
  } catch (e) {}
}

function setSampleQuery(txt) {
  const input = document.getElementById('vector-query-text');
  if (input) {
    input.value = txt;
    input.focus();
  }
}

function resetVectorSearch() {
  const form = document.getElementById('vector-search-form');
  if (form) form.reset();
  const st = document.getElementById('vector-start-time');
  if (st) st.value = '';
  const et = document.getElementById('vector-end-time');
  if (et) et.value = '';
  const container = document.getElementById('vector-result-container');
  if (container) container.style.display = 'none';
  const inp = document.getElementById('vector-query-text');
  if (inp) inp.focus();
}

async function reindexExistingClips() {
  const pill = document.getElementById('gemini-status-pill');
  if (pill) pill.innerHTML = '⏳ Indexing past clips...';
  try {
    const res = await fetch('/api/events/reindex', { method: 'POST' });
    const data = await res.json();
    alert(`Indexed ${data.indexed_count || 0} clips into FAISS. Total indexed: ${data.total_vectors || 0}`);
    checkGeminiStatus();
  } catch (err) {
    alert('Failed to reindex: ' + err.message);
  }
}

async function queryVisualVector(event) {
  event.preventDefault();
  const query = document.getElementById('vector-query-text').value.trim();
  const cameraId = document.getElementById('vector-camera-id').value;
  const topK = parseInt(document.getElementById('vector-top-k').value || '2', 10);
  const startTime = document.getElementById('vector-start-time')?.value || '';
  const endTime = document.getElementById('vector-end-time')?.value || '';
  const startUtc = istToUtc(startTime);
  const endUtc = istToUtc(endTime);

  const container = document.getElementById('vector-result-container');
  const content = document.getElementById('vector-result-content');

  if (!query) return false;

  container.style.display = 'block';
  content.innerHTML = `
    <div style="color:#79c0ff; text-align:center; padding:30px;">
      <div style="font-size:1.6rem; margin-bottom:8px;">🔍</div>
      <div style="font-weight:600;">Searching FAISS vector index for "${query}"...</div>
      <div style="font-size:.8rem; color:#8b949e; margin-top:4px;">Retrieving top ${topK} matches in milliseconds</div>
    </div>
  `;

  try {
    const res = await fetch('/api/search-visual', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({query: query, camera_id: cameraId, top_k: topK, start: startUtc, end: endUtc})
    });
    if (!res.ok) throw new Error('Search failed: ' + res.statusText);
    const data = await res.json();

    const results = data.results || [];
    if (results.length === 0) {
      content.innerHTML = `
        <div style="background:#1c2128; border:1px solid #30363d; border-radius:8px; padding:30px; text-align:center; color:#8b949e;">
          <div style="font-size:1.6rem; margin-bottom:8px;">🔎</div>
          <div style="font-weight:600; color:#e6edf3; font-size:1.05rem;">No Matching Video Clips Found</div>
          <div style="margin-top:6px; font-size:.85rem;">No person detections in FAISS matched "${query}".</div>
          <div style="margin-top:14px; display:inline-flex; gap:8px;">
            <button type="button" class="btn" onclick="reindexExistingClips()">Index Past Clips</button>
            <button type="button" class="btn" onclick="setSampleQuery('person with dark clothes')">Try 'person with dark clothes'</button>
          </div>
        </div>
      `;
      return false;
    }

    const camLabel = cameraId ? `Camera <strong>${cameraId}</strong>` : '<strong>All Cameras</strong>';
    content.innerHTML = `
      <div style="margin-bottom:16px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
        <span style="font-weight:600; color:#e6edf3; font-size:1rem;">
          Top ${results.length} Match(es) for "<em>${data.query}</em>" on ${camLabel}
        </span>
        <span class="badge" style="background:#23863622; border:1px solid #3fb950; color:#3fb950;">
          ⚡ Retrieved from FAISS Vector DB
        </span>
      </div>
      <div style="display:flex; flex-direction:column; gap:20px;">
        ${results.map((item, idx) => {
          const started = item.started_at_utc ? new Date(item.started_at_utc.replace('Z', '+00:00')) : new Date();
          const matchPercent = item.similarity_percent || (item.similarity * 100).toFixed(1);
          const scoreColor = matchPercent >= 75 ? '#3fb950' : (matchPercent >= 60 ? '#58a6ff' : '#d29922');
          return `
            <div style="background:#0d1117; border:1px solid #30363d; border-radius:8px; overflow:hidden;">
              <div style="padding:12px 16px; background:#1c2128; border-bottom:1px solid #30363d; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                <div style="display:flex; align-items:center; gap:8px;">
                  <span class="badge" style="background:${scoreColor}22; border:1px solid ${scoreColor}; color:${scoreColor}; font-weight:700; font-size:.85rem;">
                    🎯 Match #${idx + 1} · ${matchPercent}% Similarity
                  </span>
                  <span style="font-weight:600; color:#58a6ff; font-size:1.05rem;">${item.camera_id}</span>
                  <span style="font-size:.8rem; color:#8b949e;">Event ${item.event_id}</span>
                </div>
                <div style="font-size:.8rem; color:#8b949e;">
                  ⏰ Started: ${started.toLocaleString()}
                </div>
              </div>

              <div style="padding:16px; display:grid; grid-template-columns: minmax(180px, 220px) 1fr; gap:18px;">
                <!-- Left: Snapshot Crop Preview -->
                <div style="display:flex; flex-direction:column; gap:8px;">
                  <div style="font-size:.75rem; color:#8b949e; font-weight:700; text-transform:uppercase;">\${(item.object_class || 'Object').toUpperCase()} Snapshot</div>
                  ${item.snapshot_url ? `
                    <a href="${item.snapshot_url}" target="_blank" title="Click to view full snapshot">
                      <img src="${item.snapshot_url}" alt="Person Snapshot" style="width:100%; max-height:260px; object-fit:contain; background:#010409; border-radius:6px; border:1px solid #30363d;">
                    </a>
                  ` : '<div style="background:#161b22; padding:30px; text-align:center; color:#8b949e; border-radius:6px;">No snapshot image</div>'}
                  <div style="font-size:.78rem; color:#8b949e; text-align:center;">Crop from detection event</div>
                </div>

                <!-- Right: Video Clip and AI Description -->
                <div style="display:flex; flex-direction:column; gap:12px;">
                  <div style="background:#161b22; border-left:3px solid #58a6ff; padding:10px 14px; border-radius:0 6px 6px 0; font-size:.85rem; color:#e6edf3;">
                    <div style="font-size:.75rem; color:#79c0ff; font-weight:700; margin-bottom:4px; text-transform:uppercase;">AI Visual Description</div>
                    <div>${item.description || 'Person detection indexed in FAISS vector store.'}</div>
                  </div>

                  <video controls style="width:100%; max-height:380px; background:#000; border-radius:6px; border:1px solid #30363d;" preload="metadata">
                    <source src="${item.clip_url}" type="video/mp4">
                    Your browser does not support the video tag.
                  </video>

                  <div style="display:flex; gap:8px; flex-wrap:wrap;">
                    <a href="${item.clip_url}" target="_blank" class="btn" style="text-decoration:none; padding:6px 14px; font-size:.82rem;">🔗 Open in New Tab</a>
                    <button class="btn" onclick="downloadClip('${item.clip_url}', '${item.camera_id}_${item.event_id}.mp4')" style="padding:6px 14px; font-size:.82rem;">⬇ Download Clip</button>
                  </div>
                </div>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;
  } catch (err) {
    content.innerHTML = `
      <div style="background:#1c2128; border:1px solid #f85149; border-radius:8px; padding:20px; text-align:center; color:#f85149;">
        <div style="font-weight:600; margin-bottom:6px;">Vector Search Error</div>
        <div style="font-size:.85rem; color:#8b949e;">${err.message}</div>
      </div>
    `;
  }
  return false;
}

// Populate camera dropdown for query form
async function populateQueryCameraFilter() {
  const select = document.getElementById('query-camera-id');
  if (!select) return;
  try {
    const res = await fetch('/api/cameras');
    if (res.ok) {
      const cams = await res.json();
      select.innerHTML = '<option value="">-- All Cameras --</option>' +
        cams.map(c => `<option value="${c.camera_id}">${c.camera_id}</option>`).join('');
    }
  } catch (e) {}
}

// Convert IST (naive or +05:30) to UTC for API query
function istToUtc(val) {
  if (!val) return null;
  try {
    let s = val.trim();
    if (s.indexOf('Z') === -1 && s.indexOf('+') === -1 && s.lastIndexOf('-') <= 10) {
      if (s.length === 16) s += ':00';
      s += '+05:30';
    }
    const dt = new Date(s);
    if (isNaN(dt.getTime())) return null;
    return dt.toISOString().replace('.000Z', 'Z');
  } catch (e) {
    return null;
  }
}

// Query for a clip matching the time range
async function queryClip(event) {
  event.preventDefault();

  const cameraId = document.getElementById('query-camera-id').value;
  const startTime = document.getElementById('query-start-time').value;
  const endTime = document.getElementById('query-end-time').value;
  const objClass = document.getElementById('query-class').value;

  const resultDiv = document.getElementById('query-result');
  const contentDiv = document.getElementById('result-content');

  if (!startTime || !endTime) {
    alert('Please fill in Start Time and End Time');
    return false;
  }

  // Show loading
  resultDiv.style.display = 'block';
  contentDiv.innerHTML = '<div style="color:#79c0ff; text-align:center; padding:20px;">🔍 Searching for clips...</div>';

  try {
    // Convert IST to UTC
    const startUtc = istToUtc(startTime);
    const endUtc = istToUtc(endTime);

    if (!startUtc || !endUtc) {
      throw new Error('Invalid time format');
    }

    const params = new URLSearchParams({
      start: startUtc,
      end: endUtc,
      clip_only: '1',
      limit: '50',
      offset: '0'
    });
    if (cameraId) {
      params.set('camera_id', cameraId);
    }
    if (objClass) {
      params.set('class', objClass);
    }

    const res = await fetch('/api/events?' + params.toString());
    if (!res.ok) throw new Error('Failed to query events');
    const data = await res.json();

    const eventsWithClips = data.events?.filter(ev => ev.clip_recorded && ev.clip_path) || [];

    if (eventsWithClips.length > 0) {
      const targetLabel = cameraId ? `Camera <strong>${cameraId}</strong>` : '<strong>All Cameras</strong>';
      contentDiv.innerHTML = `
        <div style="margin-bottom:16px; display:flex; justify-content:space-between; align-items:center;">
          <span style="font-weight:600; color:#e6edf3;">Found ${eventsWithClips.length} video clip(s) for ${targetLabel}</span>
          <span class="badge" style="background:#23863622; border:1px solid #238636; color:#3fb950;">${eventsWithClips.length} Clip(s)</span>
        </div>
        <div style="display:flex; flex-direction:column; gap:20px;">
          ${eventsWithClips.map((ev, idx) => {
            const clipUrl = `/api/clips/${ev.clip_path}`;
            const started = new Date(ev.started_at_utc.replace('Z', '+00:00'));
            const ended = ev.ended_at_utc ? new Date(ev.ended_at_utc.replace('Z', '+00:00')) : null;
            const duration = ev.duration_seconds ? formatDuration(ev.duration_seconds) : (ended ? formatDuration((ended - started) / 1000) : 'Ongoing');
            return `
              <div style="background:#0d1117; border:1px solid #30363d; border-radius:8px; overflow:hidden;">
                <div style="padding:12px 16px; background:#1c2128; border-bottom:1px solid #30363d; display:flex; justify-content:space-between; align-items:center;">
                  <div>
                    <span style="font-weight:600; color:#58a6ff; font-size:1.05rem;">${ev.camera_id}</span>
                    <span style="margin-left:8px; font-size:.8rem; color:#8b949e;">Track ${ev.track_id} · Event ${ev.event_id}</span>
                  </div>
                  <div style="display:flex; gap:8px; align-items:center;">
                    <span class="badge" style="background:#23863622; border:1px solid #238636; color:#3fb950;">${ev.object_class}</span>
                    <span class="badge" style="background:#1f6feb22; border:1px solid #1f6feb; color:#58a6ff;">📹 Clip #${idx + 1}</span>
                  </div>
                </div>
                <div style="padding:16px; display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap:12px; font-size:.85rem;">
                  <div><span style="color:#8b949e;">Camera</span><br><strong>${ev.camera_id}</strong></div>
                  <div><span style="color:#8b949e;">Track ID</span><br><strong>${ev.track_id}</strong></div>
                  <div><span style="color:#8b949e;">Started (IST)</span><br><strong>${started.toLocaleString()}</strong></div>
                  <div><span style="color:#8b949e;">Ended (IST)</span><br><strong>${ended ? ended.toLocaleString() : 'Active'}</strong></div>
                  <div><span style="color:#8b949e;">Duration</span><br><strong>${duration}</strong></div>
                  <div><span style="color:#8b949e;">Confidence</span><br><strong style="color:#79c0ff;">${(ev.max_confidence * 100).toFixed(1)}%</strong></div>
                </div>
                <div style="padding:0 16px 16px;">
                  <video controls style="width:100%; max-height:420px; background:#000; border-radius:4px; border:1px solid #30363d;" preload="metadata">
                    <source src="${clipUrl}" type="video/mp4">
                    Your browser does not support the video tag.
                  </video>
                  <div style="display:flex; gap:8px; margin-top:12px; flex-wrap:wrap;">
                    <a href="${clipUrl}" target="_blank" class="btn" style="text-decoration:none; padding:8px 16px;">🔗 Open in New Tab</a>
                    <button class="btn" onclick="downloadClip('${clipUrl}', '${ev.camera_id}_${ev.event_id}.mp4')" style="padding:8px 16px;">⬇ Download Clip</button>
                  </div>
                </div>
              </div>
            `;
          }).join('')}
        </div>
      `;
    } else {
      const targetLabel = cameraId ? `<strong>${cameraId}</strong>` : '<strong>any camera</strong>';
      contentDiv.innerHTML = `
        <div style="background:#1c2128; border:1px solid #30363d; border-radius:8px; padding:32px; text-align:center;">
          <div style="font-size:2.5rem; margin-bottom:12px;">📭</div>
          <div style="font-size:1.1rem; font-weight:600; color:#e6edf3; margin-bottom:8px;">No Video Clip Found</div>
          <div style="color:#8b949e; font-size:.9rem;">
            No clip recorded for ${targetLabel} between<br>
            <strong>${startTime}</strong> and <strong>${endTime}</strong> (IST)
            ${objClass ? ` for class <strong>${objClass}</strong>` : ''}
          </div>
        </div>
      `;
    }

  } catch (err) {
    console.error('queryClip error:', err);
    contentDiv.innerHTML = `
      <div style="background:#1c2128; border:1px solid #f85149; border-radius:8px; padding:24px; text-align:center; color:#f85149;">
        <div style="font-weight:600; margin-bottom:8px;">Error</div>
        <div style="color:#8b949e; font-size:.9rem;">${err.message}</div>
      </div>
    `;
  }

  return false;
}

function resetQueryForm() {
  document.getElementById('clip-query-form').reset();
  document.getElementById('query-result').style.display = 'none';
  document.getElementById('query-camera-id').focus();
}

function formatDuration(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function downloadClip(url, filename) {
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
}

function onSelectExistingCam(camId) {
  if (!camId) return;
  document.getElementById('ob-cam-id').value = camId;
}

async function submitOnboarding() {
  const camId = document.getElementById('ob-cam-id').value.trim();
  const rtspUrl = document.getElementById('ob-rtsp-url').value.trim();
  const codec = document.getElementById('ob-codec').value;
  const decoder = document.getElementById('ob-decoder').value;

  if (!camId) { alert('Please enter a camera ID.'); return; }
  if (!rtspUrl) { alert('Please enter an RTSP stream URL.'); return; }

  showObAlert('', 'none');
  const btn = document.getElementById('btn-ob-connect');
  btn.disabled = true;
  btn.textContent = 'Connecting...';

  try {
    const regRes = await fetch('/api/cameras', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ camera_id: camId, rtsp_url: rtspUrl, codec, decoder })
    });
    const regData = await regRes.json();
    if (!regRes.ok) {
      throw new Error(regData.error || 'Failed to register camera');
    }

    activeOnboardingCamId = camId;
    await startCameraAnalysis(camId);
  } catch (err) {
    showObAlert(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Connect & Analyze';
    loadExistingCamerasForOnboarding();
  }
}

async function profileExistingCam() {
  const camId = document.getElementById('ob-existing-cam').value || document.getElementById('ob-cam-id').value.trim();
  if (!camId) { alert('Please select or enter a camera ID.'); return; }
  activeOnboardingCamId = camId;
  await startCameraAnalysis(camId);
}

async function startCameraAnalysis(camId) {
  showObAlert('', 'none');
  const sCard = document.getElementById('ob-sampling-card');
  sCard.style.display = 'block';
  document.getElementById('ob-caps-card').style.display = 'none';
  document.getElementById('ob-profile-card').style.display = 'none';
  document.getElementById('ob-progress-bar').style.width = '5%';
  document.getElementById('ob-progress-text').textContent = 'Starting sampling...';

  try {
    const res = await fetch(`/api/cameras/${encodeURIComponent(camId)}/onboarding/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sample_count: 20, sample_duration_seconds: 8.0, force_fresh: true })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to start analysis');

    pollOnboardingStatus(camId);
  } catch (err) {
    showObAlert(err.message, 'error');
  }
}

async function pollOnboardingStatus(camId) {
  try {
    const res = await fetch(`/api/cameras/${encodeURIComponent(camId)}/onboarding/status`);
    if (!res.ok) throw new Error('Status poll failed');
    const st = await res.json();

    const bar = document.getElementById('ob-progress-bar');
    const txt = document.getElementById('ob-progress-text');
    const pct = Math.max(5, st.progress_percent || 0);
    bar.style.width = pct + '%';
    txt.textContent = `${st.sample_count || 0} / ${st.target_samples || 20} frames (${pct}%) — ${st.status}`;

    if (st.status === 'RECOMMENDATIONS_READY' || st.status === 'ACTIVE' || st.status === 'USER_APPLIES' || st.status === 'WAITING_FOR_USER') {
      document.getElementById('ob-sampling-card').style.display = 'none';
      await loadRecommendations(camId);
    } else if (st.status === 'ERROR') {
      showObAlert(st.error || 'Sampling or analysis error', 'error');
    } else {
      setTimeout(() => pollOnboardingStatus(camId), 600);
    }
  } catch (err) {
    setTimeout(() => pollOnboardingStatus(camId), 1000);
  }
}

async function loadRecommendations(camId) {
  try {
    const res = await fetch(`/api/cameras/${encodeURIComponent(camId)}/recommendations`);
    if (!res.ok) throw new Error('Failed to fetch recommendations');
    const data = await res.json();

    activeOnboardingCamId = camId;
    rawRecommendations = data.recommendations || [];

    // Render Scene Profile Card
    const profCard = document.getElementById('ob-profile-card');
    const prof = data.scene_profile;
    if (prof) {
      profCard.style.display = 'block';
      document.getElementById('ob-scene-type').textContent = (prof.scene_type || 'unknown').toUpperCase();
      document.getElementById('ob-scene-conf').textContent = `${Math.round((prof.scene_confidence || 0.5) * 100)}%`;
      document.getElementById('ob-scene-method').textContent = prof.analysis_method || 'yolo_heuristic';
      document.getElementById('ob-scene-frames').textContent = `${prof.frames_analyzed || 0} frames`;

      const objBox = document.getElementById('ob-scene-objects');
      const objs = prof.visible_objects || [];
      if (objs.length === 0) {
        objBox.innerHTML = '<span style="color:#8b949e; font-size:.8rem;">No prominent objects detected</span>';
      } else {
        objBox.innerHTML = objs.map(o => `<span class="badge" style="background:#1f6feb22; border:1px solid #1f6feb; color:#79c0ff;">${o}</span>`).join('');
      }

      const attrBox = document.getElementById('ob-scene-attrs');
      const attrs = prof.scene_attributes || [];
      if (attrs.length === 0) {
        attrBox.innerHTML = '<span style="color:#8b949e; font-size:.8rem;">Standard indoor/outdoor</span>';
      } else {
        attrBox.innerHTML = attrs.map(a => `<span class="badge" style="background:#23863622; border:1px solid #238636; color:#3fb950;">${a}</span>`).join('');
      }

      const limBox = document.getElementById('ob-scene-limitations-box');
      const lims = prof.limitations || [];
      if (lims.length > 0) {
        limBox.style.display = 'block';
        document.getElementById('ob-scene-limitations').textContent = lims.join('; ');
      } else {
        limBox.style.display = 'none';
      }
    } else {
      profCard.style.display = 'none';
    }

    // Render Capability Recommendations Card
    const capsCard = document.getElementById('ob-caps-card');
    capsCard.style.display = 'block';

    const activeCaps = new Set(data.active_capabilities || []);
    document.getElementById('ob-active-count').textContent = activeCaps.size;

    renderCapabilityList(data.recommendations || [], activeCaps);
  } catch (err) {
    showObAlert(err.message, 'error');
  }
}

function renderCapabilityList(recs, activeCaps) {
  const container = document.getElementById('ob-caps-list');
  container.innerHTML = '';

  let selectedCount = 0;
  for (const r of recs) {
    const isAvail = r.available !== false && r.status !== 'NOT_IMPLEMENTED';
    const isChecked = activeCaps.has(r.capability_id) || (isAvail && r.recommended_checked);
    if (isChecked) selectedCount++;

    const item = document.createElement('div');
    item.className = 'cap-item' + (!isAvail ? ' disabled' : '');
    item.id = `cap-row-${r.capability_id}`;

    const scorePct = Math.round((r.score || 0) * 100);
    const statusClass = r.status === 'AVAILABLE' ? 'available' : (r.status === 'REQUIRES_SETUP' ? 'setup' : 'not-implemented');

    item.innerHTML = `
      <input type="checkbox" id="chk-${r.capability_id}" class="cap-checkbox"
             data-cap-id="${r.capability_id}"
             ${isChecked ? 'checked' : ''}
             ${!isAvail ? 'disabled' : ''}
             onchange="updateSelectedCount()">
      <div class="cap-content">
        <div class="cap-header">
          <span class="cap-title">${r.display_name || r.capability_id}</span>
          <div class="cap-badges">
            <span class="cap-badge ${statusClass}">${r.status}</span>
            <span class="cap-badge score">${scorePct}% Match</span>
            <span class="badge" style="background:#21262d; color:#8b949e; font-size:.7rem;">Cost: ${r.estimated_compute_cost || 'low'}</span>
          </div>
        </div>
        <div class="cap-reason">${r.reason || ''}</div>
        <div class="cap-deps">Dependencies: ${r.dependencies && r.dependencies.length ? r.dependencies.join(', ') : 'None (Base)'}</div>
      </div>
    `;
    container.append(item);
  }
  document.getElementById('ob-selected-count').textContent = selectedCount;
}

function updateSelectedCount() {
  const checked = document.querySelectorAll('.cap-checkbox:checked');
  document.getElementById('ob-selected-count').textContent = checked.length;
}

function addSelectedCapability(capId) {
  if (!capId) return;
  const existing = document.getElementById(`chk-${capId}`);
  if (existing) {
    existing.checked = true;
    updateSelectedCount();
    return;
  }
  const def = capabilityRegistryList.find(c => c.id === capId);
  if (!def) return;

  const isAvail = def.implementation_status !== 'NOT_IMPLEMENTED';
  const item = document.createElement('div');
  item.className = 'cap-item' + (!isAvail ? ' disabled' : '');
  item.id = `cap-row-${def.id}`;
  const statusClass = def.implementation_status === 'AVAILABLE' ? 'available' : (def.implementation_status === 'REQUIRES_SETUP' ? 'setup' : 'not-implemented');

  item.innerHTML = `
    <input type="checkbox" id="chk-${def.id}" class="cap-checkbox"
           data-cap-id="${def.id}"
           ${isAvail ? 'checked' : ''}
           ${!isAvail ? 'disabled' : ''}
           onchange="updateSelectedCount()">
    <div class="cap-content">
      <div class="cap-header">
        <span class="cap-title">${def.display_name}</span>
        <div class="cap-badges">
          <span class="cap-badge ${statusClass}">${def.implementation_status}</span>
          <span class="cap-badge score">User Added</span>
          <span class="badge" style="background:#21262d; color:#8b949e; font-size:.7rem;">Cost: ${def.estimated_compute_cost || 'low'}</span>
        </div>
      </div>
      <div class="cap-reason">${def.description || 'Manually selected capability.'}</div>
      <div class="cap-deps">Dependencies: ${def.dependencies && def.dependencies.length ? def.dependencies.join(', ') : 'None'}</div>
    </div>
  `;
  document.getElementById('ob-caps-list').append(item);
  updateSelectedCount();
  document.getElementById('ob-add-cap-dropdown').value = '';
}

function resetCapsSelection() {
  if (activeOnboardingCamId) {
    loadRecommendations(activeOnboardingCamId);
  }
}

async function reAnalyzeCam() {
  if (activeOnboardingCamId) {
    await startCameraAnalysis(activeOnboardingCamId);
  }
}

async function applyCapabilities() {
  if (!activeOnboardingCamId) { alert('No active camera selected for onboarding.'); return; }
  const selected = [];
  document.querySelectorAll('.cap-checkbox:checked').forEach(cb => {
    if (!cb.disabled) selected.push(cb.getAttribute('data-cap-id'));
  });

  const btn = document.getElementById('btn-apply-caps');
  btn.disabled = true;
  btn.textContent = 'Applying Configuration...';
  showObAlert('', 'none');

  try {
    const res = await fetch(`/api/cameras/${encodeURIComponent(activeOnboardingCamId)}/capabilities`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        capabilities: selected,
        expected_version: activeOnboardingVersion
      })
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || 'Failed to apply capabilities');
    }

    activeOnboardingVersion = data.config_version || (activeOnboardingVersion + 1);
    document.getElementById('ob-active-count').textContent = (data.enabled_capabilities || []).length;

    showObAlert(`✓ Successfully activated capabilities: [${(data.enabled_capabilities || []).join(', ')}]. Version ${data.config_version} persisted to config.`, 'success');
  } catch (err) {
    showObAlert(`Application Error: ${err.message}`, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '✓ Apply Configuration & Activate';
  }
}

function showObAlert(msg, type) {
  const el = document.getElementById('ob-alert');
  if (!el) return;
  el.className = 'alert-box ' + type;
  el.textContent = msg;
  el.style.display = (type === 'none' || !msg) ? 'none' : 'block';
}

// Resize canvas to match display container
function resizeCanvas() {
  const rect = stageBox.getBoundingClientRect();
  const rw = Math.round(rect.width);
  const rh = Math.round(rect.height);
  if (canvas.width !== rw || canvas.height !== rh) {
    canvas.width = rw;
    canvas.height = rh;
  }
}
window.addEventListener('resize', resizeCanvas);

// High-frequency Detection Poller for Demo View and Multi-Grid View
let detectionPollerActive = false;
let currentDetectionsData = null;
let allDetectionsData = null;

async function pollDetections() {
  if (detectionPollerActive) return;
  detectionPollerActive = true;

  try {
    if (currentView === 'demo') {
      const res = await fetch(`/api/detections/${selectedCam}`, { cache: 'no-store' });
      if (res.ok) {
        const data = await res.json();
        currentDetectionsData = data;
        updateDetectionSidebar(data);
      }
    } else {
      const res = await fetch('/api/detections', { cache: 'no-store' });
      if (res.ok) {
        const data = await res.json();
        allDetectionsData = data;
      }
    }
  } catch (err) {
  } finally {
    detectionPollerActive = false;
    setTimeout(pollDetections, currentView === 'demo' ? 40 : 80);
  }
}

// Continuous render loop - avoid duplicate boxes since preview_worker burns them into the video
function renderLoop() {
  if (currentView === 'demo') {
    resizeCanvas();
    if (streamMode === 'webrtc' && currentDetectionsData) {
      drawDetections(currentDetectionsData);
    } else {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
  } else if (allDetectionsData) {
    for (const [camId, card] of cards.entries()) {
      if (!card.cardCanvas) continue;
      card.cardCtx.clearRect(0, 0, card.cardCanvas.width, card.cardCanvas.height);
    }
  }
  requestAnimationFrame(renderLoop);
}
requestAnimationFrame(renderLoop);

function updateDetectionSidebar(data) {
  const dets = data.detections || [];
  const srcW = data.width || 1280;
  const srcH = data.height || 720;

  document.getElementById('tele-det-count').textContent = dets.length;
  document.getElementById('tele-infer-ms').textContent = `${(data.inference_ms || 0).toFixed(1)} ms`;
  document.getElementById('tele-lat-ms').textContent = `${(data.total_latency_ms || 0).toFixed(1)} ms`;
  document.getElementById('stage-source-latency').textContent = `${(data.total_latency_ms || 0).toFixed(0)} ms`;
  document.getElementById('hud-res').textContent = `${srcW}x${srcH}`;
  document.getElementById('tele-frame-path').textContent = data.frame_path || 'GPU_NATIVE';
  document.getElementById('tele-cpu-downloads').textContent = `${data.cpu_frame_downloads || 0} frames`;

  const detList = document.getElementById('tele-dets-list');
  if (dets.length === 0) {
    detList.innerHTML = '<div style="color:#8b949e; text-align:center; padding:10px;">Waiting for detections...</div>';
  } else {
    detList.innerHTML = dets.map(d => `
      <div class="det-row">
        <span style="color:#58a6ff; font-weight:600;">${d.label}${d.track_id ? ' [ID ' + d.track_id.split(':').pop() + ']' : ''}</span>
        <span style="color:#3fb950;">${Math.round(d.confidence * 100)}%</span>
      </div>
    `).join('');
  }
}

function drawDetections(data) {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const dets = data.detections || [];
  const srcW = data.width || 1280;
  const srcH = data.height || 720;

  // Scale ratio matching object-fit: contain
  const scale = Math.min(canvas.width / srcW, canvas.height / srcH);
  const renderW = srcW * scale;
  const renderH = srcH * scale;
  const offsetX = (canvas.width - renderW) / 2;
  const offsetY = (canvas.height - renderH) / 2;

  // Draw Bounding Boxes on Canvas
  for (const det of dets) {
    const x1 = offsetX + det.bbox[0] * scale;
    const y1 = offsetY + det.bbox[1] * scale;
    const x2 = offsetX + det.bbox[2] * scale;
    const y2 = offsetY + det.bbox[3] * scale;
    const w = x2 - x1;
    const h = y2 - y1;

    // Colors: Green for person (class 0), Cyan for vehicles, Orange for others
    const color = (det.class_id === 0) ? '#3fb950' : ([2, 3, 5, 7].includes(det.class_id) ? '#79c0ff' : '#d29922');

    // Draw trajectory trail if available
    if (det.trajectory && det.trajectory.length > 1) {
      ctx.beginPath();
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.setLineDash([4, 4]);
      for (let i = 0; i < det.trajectory.length; i++) {
        const tx = offsetX + det.trajectory[i][0] * scale;
        const ty = offsetY + det.trajectory[i][1] * scale;
        if (i === 0) ctx.moveTo(tx, ty);
        else ctx.lineTo(tx, ty);
      }
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Box outline
    ctx.lineWidth = 2.5;
    ctx.strokeStyle = color;
    ctx.strokeRect(x1, y1, w, h);

    // Label tag badge: Person | ID 17 | 0.94
    const idPart = det.track_id ? ` | ID ${det.track_id.split(':').pop()}` : '';
    const tag = `${det.label}${idPart} | ${Number(det.confidence).toFixed(2)}`;
    ctx.font = 'bold 12px sans-serif';
    const tagW = ctx.measureText(tag).width + 8;
    const tagH = 18;
    ctx.fillStyle = color;
    ctx.fillRect(x1, Math.max(0, y1 - tagH), tagW, tagH);

    ctx.fillStyle = '#010409';
    ctx.fillText(tag, x1 + 4, Math.max(13, y1 - 4));
  }
}

function drawCardDetections(c, cCtx, dets, srcW, srcH) {
  cCtx.clearRect(0, 0, c.width, c.height);
  if (!dets || dets.length === 0) return;
  const scale = Math.min(c.width / srcW, c.height / srcH);
  const renderW = srcW * scale;
  const renderH = srcH * scale;
  const offsetX = (c.width - renderW) / 2;
  const offsetY = (c.height - renderH) / 2;

  for (const det of dets) {
    const x1 = offsetX + det.bbox[0] * scale;
    const y1 = offsetY + det.bbox[1] * scale;
    const x2 = offsetX + det.bbox[2] * scale;
    const y2 = offsetY + det.bbox[3] * scale;
    const w = x2 - x1;
    const h = y2 - y1;
    const color = (det.class_id === 0) ? '#3fb950' : ([2, 3, 5, 7].includes(det.class_id) ? '#79c0ff' : '#d29922');

    cCtx.lineWidth = 2;
    cCtx.strokeStyle = color;
    cCtx.strokeRect(x1, y1, w, h);

    const idPart = det.track_id ? ` | ID ${det.track_id.split(':').pop()}` : '';
    const tag = `${det.label}${idPart} | ${Number(det.confidence).toFixed(2)}`;
    cCtx.font = 'bold 10px sans-serif';
    const tagW = cCtx.measureText(tag).width + 6;
    const tagH = 14;
    cCtx.fillStyle = color;
    cCtx.fillRect(x1, Math.max(0, y1 - tagH), tagW, tagH);

    cCtx.fillStyle = '#010409';
    cCtx.fillText(tag, x1 + 2, Math.max(10, y1 - 3));
  }
}

// Single-connection batch poller for grid mode
const lastSeq = {};
let batchInFlight = false;
async function pollFramesBatch() {
  if (currentView !== 'mjpeg') {
    setTimeout(pollFramesBatch, 300);
    return;
  }
  if (batchInFlight) return;
  batchInFlight = true;

  try {
    const qs = encodeURIComponent(JSON.stringify(lastSeq));
    const res = await fetch('/api/frames/batch?since=' + qs, { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      requestAnimationFrame(() => {
        for (const [camId, item] of Object.entries(data)) {
          if (!item) continue;
          lastSeq[camId] = item.seq;
          const card = cards.get(camId);
          if (!card) continue;
          if (item.jpeg) {
            card.img.src = 'data:image/jpeg;base64,' + item.jpeg;
            card.placeholder.hidden = true;
          } else if (item.has_frame) {
            card.placeholder.hidden = true;
          }
        }
      });
    }
  } catch (err) {
  } finally {
    batchInFlight = false;
    if (currentView === 'mjpeg') {
      setTimeout(pollFramesBatch, 150);
    }
  }
}
pollFramesBatch();
pollDetections();

// Telemetry Status Poller (1 Hz)
async function refreshStatus() {
  try {
    const response = await fetch('/api/status', {cache: 'no-store'});
    if (!response.ok) return;
    const data = await response.json();
    statusData = data;

    // Update global resource gauges
    const res = data.resources || {};
    const gpu = (res.gpus && res.gpus[0]) || {};
    document.getElementById('tele-gpu-util').textContent = `${gpu.utilization_percent || 0}%`;
    document.getElementById('tele-nvdec-util').textContent = gpu.decoder_percent != null ? `${gpu.decoder_percent}%` : 'N/A';
    document.getElementById('tele-vram').textContent = `${((gpu.used_mib || 0)/1024).toFixed(1)} / ${((gpu.total_mib || 0)/1024).toFixed(1)} GiB`;
    document.getElementById('tele-cpu').textContent = `${(res.process_cpu_percent || 0).toFixed(0)}%`;
    document.getElementById('tele-prep-ms').textContent = `${(data.preprocess_avg_ms || 0).toFixed(1)} ms`;

    // Update ByteTrack telemetry
    const trk = data.tracking || {};
    const elActive = document.getElementById('tele-active-tracks');
    if (elActive) elActive.textContent = trk.active_tracks || 0;
    const elConf = document.getElementById('tele-conf-tracks');
    if (elConf) elConf.textContent = trk.confirmed_tracks || 0;
    const elRate = document.getElementById('tele-track-rate');
    if (elRate) elRate.textContent = (trk.tracking_updates_per_sec || 0).toFixed(1);
    const elLat = document.getElementById('tele-assoc-lat');
    if (elLat && trk.association_latency) elLat.textContent = `${(trk.association_latency.p95 || 0).toFixed(2)} ms`;

    // Update Camera status dots and grid cards
    for (const [id, m] of Object.entries(data.cameras || {})) {
      const dot = document.getElementById('dot-' + id);
      if (dot) dot.classList.toggle('online', m.state === 'CONNECTED');

      if (id === selectedCam) {
        document.getElementById('tele-ingest-fps').textContent = (m.input_fps || 0).toFixed(1);
        document.getElementById('tele-ai-fps').textContent = (m.ai_fps || 0).toFixed(1);
        document.getElementById('stage-active-dec').textContent = `${m.decoder_name || 'auto'} (${m.decoder_type || 'hw'})`;
      }

      const card = cards.get(id);
      if (!card) continue;
      card.state.textContent = m.state;
      card.state.classList.toggle('connected', m.state === 'CONNECTED');
      const age = m.frame_age_ms == null ? 'never' : `${m.frame_age_ms.toFixed(0)} ms`;
      card.stats.innerHTML = `<span>Decoded: ${(m.input_fps || 0).toFixed(1)} FPS | AI: ${(m.ai_fps || 0).toFixed(1)} FPS</span><span>Path: ${m.frame_path || 'GPU_NATIVE'} | Age: ${age}</span>`;
      card.placeholder.hidden = m.state === 'CONNECTED' && m.frames_received > 0;
    }
  } catch (err) {}
}
refreshStatus();
setInterval(refreshStatus, 1000);


// ==========================================
// SPATIAL INTELLIGENCE & RULE ENGINE JAVASCRIPT
// ==========================================
let activeSpatialCam = ids.length > 0 ? ids[0] : 'CAM001';
let currentSpatialTool = 'select'; // 'select', 'zone', 'line'
let tempDrawingPoints = [];
let configuredZones = [];
let configuredLines = [];
let configuredRules = [];
let spatialConfigVersion = 1;
let spatialDetections = [];
let spatialTracks = [];
let spatialPollerTimer = null;

const spCanvas = document.getElementById('sp-canvas');
const spCtx = spCanvas ? spCanvas.getContext('2d') : null;
const spStageMjpeg = document.getElementById('sp-stage-mjpeg');
const spStageBox = document.getElementById('sp-stage-box');

function resizeSpatialCanvas() {
  if (!spCanvas || !spStageBox) return;
  const rect = spStageBox.getBoundingClientRect();
  const rw = Math.round(rect.width);
  const rh = Math.round(rect.height);
  if (spCanvas.width !== rw || spCanvas.height !== rh) {
    spCanvas.width = rw;
    spCanvas.height = rh;
  }
}
window.addEventListener('resize', resizeSpatialCanvas);

function getLetterboxBounds(cw, ch, aspect = 16/9) {
  const caspect = cw / ch;
  let rw, rh, ox, oy;
  if (caspect > aspect) {
    rh = ch;
    rw = ch * aspect;
    ox = (cw - rw) / 2;
    oy = 0;
  } else {
    rw = cw;
    rh = cw / aspect;
    ox = 0;
    oy = (ch - rh) / 2;
  }
  return { rw, rh, ox, oy };
}

function getCanvasNormPoint(e) {
  const rect = spCanvas.getBoundingClientRect();
  const cx = e.clientX - rect.left;
  const cy = e.clientY - rect.top;
  const b = getLetterboxBounds(spCanvas.width, spCanvas.height);
  const nx = Math.max(0.0, Math.min(1.0, (cx - b.ox) / b.rw));
  const ny = Math.max(0.0, Math.min(1.0, (cy - b.oy) / b.rh));
  return { x: Math.round(nx * 1000) / 1000, y: Math.round(ny * 1000) / 1000 };
}

function normToCanvasPoint(nx, ny) {
  const b = getLetterboxBounds(spCanvas.width, spCanvas.height);
  return { x: b.ox + nx * b.rw, y: b.oy + ny * b.rh };
}

function initSpatialView() {
  const sel = document.getElementById('sp-camera-select');
  if (sel) {
    sel.innerHTML = ids.map(id => `<option value="${id}" ${id === activeSpatialCam ? 'selected' : ''}>${id}</option>`).join('');
  }
  onSpatialCamSelect(activeSpatialCam);
  resizeSpatialCanvas();
  setupSpatialCanvasEvents();
}

function onSpatialCamSelect(camId) {
  if (!camId) return;
  activeSpatialCam = camId;
  const badge = document.getElementById('sp-cam-id-badge');
  if (badge) badge.textContent = camId;
  const hudCam = document.getElementById('sp-hud-cam');
  if (hudCam) hudCam.textContent = camId;

  if (spStageMjpeg) {
    spStageMjpeg.src = `/stream/${camId}.mjpg?t=` + Date.now();
  }

  tempDrawingPoints = [];
  loadSpatialData(camId);
  startSpatialPoller();
}

function setSpatialTool(tool) {
  currentSpatialTool = tool;
  tempDrawingPoints = [];
  document.querySelectorAll('.sp-tool-btn').forEach(b => b.classList.remove('active'));
  const btn = document.getElementById('sp-tool-' + tool);
  if (btn) btn.classList.add('active');

  const hudMode = document.getElementById('sp-hud-mode');
  const help = document.getElementById('sp-drawing-help');
  if (tool === 'select') {
    if (hudMode) hudMode.textContent = 'MODE: INSPECT';
    if (help) help.textContent = 'Mode: Inspecting live detections & spatial geometry.';
  } else if (tool === 'zone') {
    if (hudMode) hudMode.textContent = 'MODE: DRAW ZONE';
    if (help) help.textContent = 'Click to place vertices (min 3). Double-click or click start point to close polygon.';
  } else if (tool === 'line') {
    if (hudMode) hudMode.textContent = 'MODE: DRAW LINE';
    if (help) help.textContent = 'Click start point, then click end point to create a directed tripwire line.';
  }
  renderSpatialCanvas();
}

function clearActiveDrawing() {
  tempDrawingPoints = [];
  setSpatialTool('select');
  renderSpatialCanvas();
}

let canvasEventsAttached = false;
function setupSpatialCanvasEvents() {
  if (!spCanvas || canvasEventsAttached) return;
  canvasEventsAttached = true;

  spCanvas.addEventListener('mousemove', (e) => {
    const pt = getCanvasNormPoint(e);
    const coords = document.getElementById('sp-hud-coords');
    if (coords) coords.textContent = `X: ${pt.x.toFixed(3)}, Y: ${pt.y.toFixed(3)}`;
    if (tempDrawingPoints.length > 0 && currentSpatialTool !== 'select') {
      renderSpatialCanvas(pt);
    }
  });

  spCanvas.addEventListener('click', (e) => {
    if (currentSpatialTool === 'select') return;
    const pt = getCanvasNormPoint(e);

    if (currentSpatialTool === 'zone') {
      if (tempDrawingPoints.length >= 3) {
        const start = tempDrawingPoints[0];
        const dist = Math.hypot(pt.x - start.x, pt.y - start.y);
        if (dist < 0.03) {
          finishZoneDrawing();
          return;
        }
      }
      tempDrawingPoints.push(pt);
      renderSpatialCanvas();
    } else if (currentSpatialTool === 'line') {
      tempDrawingPoints.push(pt);
      if (tempDrawingPoints.length === 2) {
        finishLineDrawing();
      } else {
        renderSpatialCanvas();
      }
    }
  });

  spCanvas.addEventListener('dblclick', (e) => {
    if (currentSpatialTool === 'zone' && tempDrawingPoints.length >= 3) {
      finishZoneDrawing();
    }
  });
}

function finishZoneDrawing() {
  if (tempDrawingPoints.length < 3) return;
  const name = prompt('Enter Zone ID / Name:', `Zone_${configuredZones.length + 1}`) || `Zone_${Date.now() % 1000}`;
  const colors = ['#388bfd', '#238636', '#d29922', '#a371f7', '#f85149'];
  const color = colors[configuredZones.length % colors.length];

  configuredZones.push({
    zone_id: name.toLowerCase().replace(/[^a-z0-9_]/g, '_'),
    name: name,
    polygon: tempDrawingPoints.map(p => [p.x, p.y]),
    color: color,
    severity: 'INFO',
    enabled: true
  });

  tempDrawingPoints = [];
  setSpatialTool('select');
  updateZonesUI();
  saveZonesToBackend();
}

function finishLineDrawing() {
  if (tempDrawingPoints.length < 2) return;
  const p1 = tempDrawingPoints[0];
  const p2 = tempDrawingPoints[1];
  const name = prompt('Enter Line ID / Name:', `Line_${configuredLines.length + 1}`) || `Line_${Date.now() % 1000}`;

  configuredLines.push({
    line_id: name.toLowerCase().replace(/[^a-z0-9_]/g, '_'),
    name: name,
    p1: [p1.x, p1.y],
    p2: [p2.x, p2.y],
    in_direction: 'RIGHT_OF_LINE',
    color: '#e3b341',
    enabled: true
  });

  tempDrawingPoints = [];
  setSpatialTool('select');
  updateLinesUI();
  saveLinesToBackend();
}

async function loadSpatialData(camId) {
  try {
    const [zRes, lRes, rRes, oRes, eRes, mRes] = await Promise.all([
      fetch(`/api/cameras/${encodeURIComponent(camId)}/zones`),
      fetch(`/api/cameras/${encodeURIComponent(camId)}/lines`),
      fetch(`/api/cameras/${encodeURIComponent(camId)}/rules`),
      fetch(`/api/cameras/${encodeURIComponent(camId)}/occupancy`),
      fetch(`/api/cameras/${encodeURIComponent(camId)}/events`),
      fetch(`/api/intelligence/metrics`)
    ]);

    if (zRes.ok) {
      const zd = await zRes.json();
      configuredZones = zd.zones || [];
      spatialConfigVersion = zd.version || 1;
      updateZonesUI();
    }
    if (lRes.ok) {
      const ld = await lRes.json();
      configuredLines = ld.lines || [];
      updateLinesUI();
    }
    if (rRes.ok) {
      const rd = await rRes.json();
      configuredRules = rd.rules || [];
      updateRulesUI();
    }
    if (oRes.ok) {
      const od = await oRes.json();
      updateOccupancyUI(od);
    }
    if (eRes.ok) {
      const ed = await eRes.json();
      renderSpatialEvents(ed.events || []);
    }
    if (mRes.ok) {
      const md = await mRes.json();
      updateMetricsUI(md);
    }
    renderSpatialCanvas();
  } catch (err) {
    console.error('Error loading spatial data:', err);
  }
}

function updateZonesUI() {
  const cnt = document.getElementById('sp-zone-count');
  if (cnt) cnt.textContent = configuredZones.length;
  const list = document.getElementById('sp-zones-list');
  if (!list) return;

  if (configuredZones.length === 0) {
    list.innerHTML = '<div style="color:#8b949e; text-align:center; padding:10px;">No zones defined yet.</div>';
    return;
  }

  list.innerHTML = configuredZones.map((z, idx) => `
    <div class="sp-list-item">
      <div style="display:flex; align-items:center; gap:8px;">
        <span style="display:inline-block; width:10px; height:10px; border-radius:50%; background:${z.color || '#388bfd'};"></span>
        <span style="font-weight:600; color:#e6edf3;">${z.name || z.zone_id}</span>
        <span class="sp-badge info">${(z.polygon || []).length} pts</span>
      </div>
      <button class="btn" style="padding:2px 6px; color:#f85149;" onclick="deleteZone(${idx})">✕</button>
    </div>
  `).join('');
}

function deleteZone(idx) {
  configuredZones.splice(idx, 1);
  updateZonesUI();
  saveZonesToBackend();
  renderSpatialCanvas();
}

function updateLinesUI() {
  const cnt = document.getElementById('sp-line-count');
  if (cnt) cnt.textContent = configuredLines.length;
  const list = document.getElementById('sp-lines-list');
  if (!list) return;

  if (configuredLines.length === 0) {
    list.innerHTML = '<div style="color:#8b949e; text-align:center; padding:10px;">No lines defined yet.</div>';
    return;
  }

  list.innerHTML = configuredLines.map((l, idx) => `
    <div class="sp-list-item">
      <div style="display:flex; align-items:center; gap:8px;">
        <span style="color:#e3b341;">➔</span>
        <span style="font-weight:600; color:#e6edf3;">${l.name || l.line_id}</span>
      </div>
      <button class="btn" style="padding:2px 6px; color:#f85149;" onclick="deleteLine(${idx})">✕</button>
    </div>
  `).join('');
}

function deleteLine(idx) {
  configuredLines.splice(idx, 1);
  updateLinesUI();
  saveLinesToBackend();
  renderSpatialCanvas();
}

function updateRulesUI() {
  const cnt = document.getElementById('sp-rule-count');
  if (cnt) cnt.textContent = configuredRules.length;
  const list = document.getElementById('sp-rules-list');
  if (!list) return;

  if (configuredRules.length === 0) {
    list.innerHTML = '<div style="color:#8b949e; text-align:center; padding:10px;">No rules configured.</div>';
    return;
  }

  list.innerHTML = configuredRules.map((r, idx) => `
    <div class="sp-list-item">
      <div>
        <div style="font-weight:600; color:#e6edf3;">${r.name || r.rule_id}</div>
        <div style="font-size:.72rem; color:#8b949e;">Type: ${r.rule_type} | Target: ${r.target_id}</div>
      </div>
      <button class="btn" style="padding:2px 6px; color:#f85149;" onclick="deleteRule(${idx})">✕</button>
    </div>
  `).join('');
}

function deleteRule(idx) {
  configuredRules.splice(idx, 1);
  updateRulesUI();
  saveRulesToBackend();
}

function promptAddRule() {
  const type = prompt('Rule Type:\n1. ZONE_ENTRY\n2. ZONE_EXIT\n3. LINE_CROSS\n4. DWELL_TIME\n5. OCCUPANCY_THRESHOLD', '1');
  if (!type) return;

  let ruleType = 'ZONE_ENTRY';
  let targetId = configuredZones.length > 0 ? configuredZones[0].zone_id : '';
  let dwellSec = 0;
  let occThreshold = 0;

  if (type === '1') {
    ruleType = 'ZONE_ENTRY';
    targetId = prompt('Target Zone ID:', targetId) || targetId;
  } else if (type === '2') {
    ruleType = 'ZONE_EXIT';
    targetId = prompt('Target Zone ID:', targetId) || targetId;
  } else if (type === '3') {
    ruleType = 'LINE_CROSS';
    targetId = configuredLines.length > 0 ? configuredLines[0].line_id : 'line_1';
    targetId = prompt('Target Line ID:', targetId) || targetId;
  } else if (type === '4') {
    ruleType = 'DWELL_TIME';
    targetId = prompt('Target Zone ID for dwell:', targetId) || targetId;
    dwellSec = parseInt(prompt('Dwell Threshold (seconds):', '10') || '10', 10);
  } else if (type === '5') {
    ruleType = 'OCCUPANCY_THRESHOLD';
    targetId = prompt('Target Zone ID:', targetId) || targetId;
    occThreshold = parseInt(prompt('Max Occupancy Threshold:', '5') || '5', 10);
  }

  const ruleName = prompt('Rule Display Name:', `${ruleType}_${targetId}`) || `${ruleType}_${Date.now()}`;
  configuredRules.push({
    rule_id: ruleName.toLowerCase().replace(/[^a-z0-9_]/g, '_'),
    name: ruleName,
    rule_type: ruleType,
    target_id: targetId,
    dwell_threshold_seconds: dwellSec,
    occupancy_threshold: occThreshold,
    severity: dwellSec > 0 ? 'WARNING' : 'INFO',
    cooldown_seconds: 5.0,
    enabled: true
  });

  updateRulesUI();
  saveRulesToBackend();
}

async function saveZonesToBackend() {
  try {
    const res = await fetch(`/api/cameras/${encodeURIComponent(activeSpatialCam)}/zones`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ zones: configuredZones, expected_version: spatialConfigVersion })
    });
    const d = await res.json();
    if (res.ok) {
      spatialConfigVersion = d.version || spatialConfigVersion + 1;
    } else {
      console.warn('Failed saving zones:', d.error);
    }
  } catch (err) {
    console.error('Error saving zones:', err);
  }
}

async function saveLinesToBackend() {
  try {
    const res = await fetch(`/api/cameras/${encodeURIComponent(activeSpatialCam)}/lines`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lines: configuredLines, expected_version: spatialConfigVersion })
    });
    const d = await res.json();
    if (res.ok) {
      spatialConfigVersion = d.version || spatialConfigVersion + 1;
    } else {
      console.warn('Failed saving lines:', d.error);
    }
  } catch (err) {
    console.error('Error saving lines:', err);
  }
}

async function saveRulesToBackend() {
  try {
    const res = await fetch(`/api/cameras/${encodeURIComponent(activeSpatialCam)}/rules`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rules: configuredRules, expected_version: spatialConfigVersion })
    });
    const d = await res.json();
    if (res.ok) {
      spatialConfigVersion = d.version || spatialConfigVersion + 1;
    } else {
      console.warn('Failed saving rules:', d.error);
    }
  } catch (err) {
    console.error('Error saving rules:', err);
  }
}

async function saveAllSpatialConfig() {
  await Promise.all([saveZonesToBackend(), saveLinesToBackend(), saveRulesToBackend()]);
  alert('All spatial intelligence configurations persisted successfully.');
}

function updateOccupancyUI(od) {
  const vis = document.getElementById('sp-stat-visible');
  const flw = document.getElementById('sp-stat-flow');
  const tin = document.getElementById('sp-stat-in');
  const tout = document.getElementById('sp-stat-out');
  const botVis = document.getElementById('sp-visible-occ-count');
  const botFlw = document.getElementById('sp-flow-occ-count');

  if (vis) vis.textContent = od.visible_occupancy || 0;
  if (flw) flw.textContent = od.flow_occupancy || 0;
  if (tin) tin.textContent = od.total_in || 0;
  if (tout) tout.textContent = od.total_out || 0;
  if (botVis) botVis.textContent = od.visible_occupancy || 0;
  if (botFlw) botFlw.textContent = od.flow_occupancy || 0;
}

function reconcileOccupancy() {
  const currentVis = document.getElementById('sp-stat-visible')?.textContent || '0';
  const val = prompt('Enter Reconciled Baseline Occupancy:', currentVis);
  if (val === null) return;
  const baseline = parseInt(val, 10);
  if (isNaN(baseline) || baseline < 0) {
    alert('Please enter a valid non-negative integer.');
    return;
  }
  // Immediately update UI
  const flw = document.getElementById('sp-stat-flow');
  if (flw) flw.textContent = baseline;
}

function renderSpatialEvents(events) {
  const cnt = document.getElementById('sp-event-count');
  if (cnt) cnt.textContent = events.length;
  const stream = document.getElementById('sp-events-stream');
  if (!stream) return;

  if (events.length === 0) {
    stream.innerHTML = '<div style="color:#8b949e; text-align:center; padding:16px;">Waiting for spatial events...</div>';
    return;
  }

  stream.innerHTML = events.slice(0, 30).map(e => {
    const sevClass = (e.severity || 'INFO').toLowerCase();
    const timeStr = new Date((e.timestamp_utc || 0) * 1000).toLocaleTimeString();
    const thumbHtml = e.evidence && e.evidence.crop_jpeg_url
      ? `<img class="sp-event-thumb" src="${e.evidence.crop_jpeg_url}" alt="Best Crop Evidence" onclick="window.open('${e.evidence.crop_jpeg_url}', '_blank')">`
      : '';
    return `
      <div class="sp-event-item">
        <div class="sp-event-top">
          <span class="sp-badge ${sevClass}">${e.severity || 'INFO'}</span>
          <span style="color:#8b949e;">${timeStr}</span>
        </div>
        <div class="sp-event-desc">${e.description || e.rule_type}</div>
        <div style="font-size:.72rem; color:#8b949e;">Track: <strong>${e.track_id}</strong> | Status: ${e.status}</div>
        ${thumbHtml}
      </div>
    `;
  }).join('');
}

function updateMetricsUI(md) {
  const lat = document.getElementById('sp-metric-lat');
  const evts = document.getElementById('sp-metric-evts');
  const dedup = document.getElementById('sp-metric-dedup');
  if (lat && md.geometry_latency_ms) lat.textContent = `${(md.geometry_latency_ms.p95 || 0).toFixed(2)} ms`;
  if (evts) evts.textContent = md.total_events_generated || 0;
  if (dedup) dedup.textContent = md.duplicate_events_suppressed || 0;
}

function startSpatialPoller() {
  if (spatialPollerTimer) clearInterval(spatialPollerTimer);
  spatialPollerTimer = setInterval(async () => {
    if (currentView !== 'spatial') {
      clearInterval(spatialPollerTimer);
      spatialPollerTimer = null;
      return;
    }
    try {
      const [detRes, occRes, evRes, metRes] = await Promise.all([
        fetch(`/api/detections/${encodeURIComponent(activeSpatialCam)}`, { cache: 'no-store' }),
        fetch(`/api/cameras/${encodeURIComponent(activeSpatialCam)}/occupancy`, { cache: 'no-store' }),
        fetch(`/api/cameras/${encodeURIComponent(activeSpatialCam)}/events`, { cache: 'no-store' }),
        fetch(`/api/intelligence/metrics`, { cache: 'no-store' })
      ]);

      if (detRes.ok) {
        const dd = await detRes.json();
        spatialDetections = dd.detections || [];
        const botTrk = document.getElementById('sp-active-tracks-count');
        if (botTrk) botTrk.textContent = spatialDetections.length;
      }
      if (occRes.ok) {
        const od = await occRes.json();
        updateOccupancyUI(od);
      }
      if (evRes.ok) {
        const ed = await evRes.json();
        renderSpatialEvents(ed.events || []);
      }
      if (metRes.ok) {
        const md = await metRes.json();
        updateMetricsUI(md);
      }
      renderSpatialCanvas();
    } catch (err) {}
  }, 600);
}

function renderSpatialCanvas(hoverPt = null) {
  if (!spCanvas || !spCtx) return;
  resizeSpatialCanvas();
  spCtx.clearRect(0, 0, spCanvas.width, spCanvas.height);

  // 1. Draw Configured Zones
  for (const zone of configuredZones) {
    const pts = (zone.polygon || []).map(p => normToCanvasPoint(p[0], p[1]));
    if (pts.length < 3) continue;

    spCtx.beginPath();
    spCtx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) {
      spCtx.lineTo(pts[i].x, pts[i].y);
    }
    spCtx.closePath();

    spCtx.fillStyle = zone.color ? `${zone.color}33` : 'rgba(56, 139, 253, 0.2)';
    spCtx.fill();
    spCtx.strokeStyle = zone.color || '#388bfd';
    spCtx.lineWidth = 2;
    spCtx.stroke();

    // Zone Label Pill
    const cx = pts.reduce((sum, p) => sum + p.x, 0) / pts.length;
    const cy = pts.reduce((sum, p) => sum + p.y, 0) / pts.length;
    spCtx.font = 'bold 11px system-ui, sans-serif';
    const text = zone.name || zone.zone_id;
    const tw = spCtx.measureText(text).width;
    spCtx.fillStyle = 'rgba(13, 17, 23, 0.85)';
    spCtx.fillRect(cx - tw / 2 - 6, cy - 10, tw + 12, 20);
    spCtx.strokeStyle = zone.color || '#388bfd';
    spCtx.lineWidth = 1;
    spCtx.strokeRect(cx - tw / 2 - 6, cy - 10, tw + 12, 20);
    spCtx.fillStyle = '#fff';
    spCtx.textAlign = 'center';
    spCtx.textBaseline = 'middle';
    spCtx.fillText(text, cx, cy);
  }

  // 2. Draw Configured Virtual Lines
  for (const line of configuredLines) {
    if (!line.p1 || !line.p2) continue;
    const p1 = normToCanvasPoint(line.p1[0], line.p1[1]);
    const p2 = normToCanvasPoint(line.p2[0], line.p2[1]);

    spCtx.beginPath();
    spCtx.moveTo(p1.x, p1.y);
    spCtx.lineTo(p2.x, p2.y);
    spCtx.strokeStyle = line.color || '#e3b341';
    spCtx.lineWidth = 3;
    spCtx.stroke();

    // Inward normal arrow indicator
    const mx = (p1.x + p2.x) / 2;
    const my = (p1.y + p2.y) / 2;
    const dx = p2.x - p1.x;
    const dy = p2.y - p1.y;
    const len = Math.hypot(dx, dy) || 1;
    // Normal vector pointing to the right of (p1 -> p2)
    const nx = dy / len * 20;
    const ny = -dx / len * 20;

    spCtx.beginPath();
    spCtx.moveTo(mx, my);
    spCtx.lineTo(mx + nx, my + ny);
    spCtx.strokeStyle = '#3fb950';
    spCtx.lineWidth = 2;
    spCtx.stroke();

    // Arrowhead
    const angle = Math.atan2(ny, nx);
    spCtx.beginPath();
    spCtx.moveTo(mx + nx, my + ny);
    spCtx.lineTo(mx + nx - 8 * Math.cos(angle - Math.PI / 6), my + ny - 8 * Math.sin(angle - Math.PI / 6));
    spCtx.lineTo(mx + nx - 8 * Math.cos(angle + Math.PI / 6), my + ny - 8 * Math.sin(angle + Math.PI / 6));
    spCtx.closePath();
    spCtx.fillStyle = '#3fb950';
    spCtx.fill();

    // Line Label Pill
    spCtx.font = 'bold 11px system-ui, sans-serif';
    const text = line.name || line.line_id;
    const tw = spCtx.measureText(text).width;
    spCtx.fillStyle = 'rgba(13, 17, 23, 0.85)';
    spCtx.fillRect(mx - tw / 2 - 6, my - 10, tw + 12, 20);
    spCtx.strokeStyle = line.color || '#e3b341';
    spCtx.lineWidth = 1;
    spCtx.strokeRect(mx - tw / 2 - 6, my - 10, tw + 12, 20);
    spCtx.fillStyle = '#fff';
    spCtx.textAlign = 'center';
    spCtx.textBaseline = 'middle';
    spCtx.fillText(text, mx, my);
  }

  // 3. Draw Active Detections & Spatial Anchors
  for (const det of spatialDetections) {
    const nb = det.bbox_normalized;
    if (!nb) continue;
    const tl = normToCanvasPoint(nb[0], nb[1]);
    const br = normToCanvasPoint(nb[2], nb[3]);
    const bw = br.x - tl.x;
    const bh = br.y - tl.y;

    // Bounding Box
    spCtx.strokeStyle = '#58a6ff';
    spCtx.lineWidth = 1.5;
    spCtx.strokeRect(tl.x, tl.y, bw, bh);

    // Bottom-Center Contact Anchor Point
    const anchorX = tl.x + bw / 2;
    const anchorY = br.y;
    spCtx.beginPath();
    spCtx.arc(anchorX, anchorY, 4, 0, Math.PI * 2);
    spCtx.fillStyle = '#3fb950';
    spCtx.fill();
    spCtx.strokeStyle = '#fff';
    spCtx.lineWidth = 1.5;
    spCtx.stroke();

    // Track ID label
    const label = `${det.label || 'obj'} #${det.track_id || '?'}`;
    spCtx.font = '10px system-ui, sans-serif';
    const tw = spCtx.measureText(label).width;
    spCtx.fillStyle = 'rgba(13, 17, 23, 0.8)';
    spCtx.fillRect(tl.x, tl.y - 14, tw + 6, 14);
    spCtx.fillStyle = '#58a6ff';
    spCtx.textAlign = 'left';
    spCtx.textBaseline = 'top';
    spCtx.fillText(label, tl.x + 3, tl.y - 12);
  }

  // 4. Draw Interactive Drawing in Progress
  if (tempDrawingPoints.length > 0) {
    const pts = tempDrawingPoints.map(p => normToCanvasPoint(p.x, p.y));
    spCtx.beginPath();
    spCtx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) {
      spCtx.lineTo(pts[i].x, pts[i].y);
    }
    if (hoverPt) {
      const hp = normToCanvasPoint(hoverPt.x, hoverPt.y);
      spCtx.lineTo(hp.x, hp.y);
    }

    spCtx.strokeStyle = currentSpatialTool === 'zone' ? '#3fb950' : '#e3b341';
    spCtx.lineWidth = 2;
    spCtx.setLineDash([4, 4]);
    spCtx.stroke();
    spCtx.setLineDash([]);

    // Draw handles on vertices
    for (const p of pts) {
      spCtx.beginPath();
      spCtx.arc(p.x, p.y, 4, 0, Math.PI * 2);
      spCtx.fillStyle = '#fff';
      spCtx.fill();
      spCtx.strokeStyle = '#3fb950';
      spCtx.lineWidth = 2;
      spCtx.stroke();
    }
  }
}

// Initialize default view
switchView('demo');
</script>
</body>
</html>
'''


def start_preview(engine: StreamCore, cache: PreviewCache, port: int) -> ThreadingHTTPServer:
    def get_camera_ids() -> frozenset[str]:
        return frozenset(c.id for c in engine.cameras)

    def render_html() -> bytes:
        current_cameras = [c.id for c in engine.cameras]
        sources: dict[tuple[str, str, str], str] = {}
        source_for: dict[str, str] = {}
        for camera in engine.cameras:
            key = (camera.uri, camera.codec, camera.decoder)
            source_for[camera.id] = (sources.setdefault(key, camera.id)
                                     if engine.share_identical_sources else camera.id)
        preview_fps = engine.config.preview.fps
        preview_interval_ms = max(1, round(1000 / preview_fps))
        webrtc_base = (engine.config.live_view.mediamtx_webrtc_base_url.rstrip("/")
                       if engine.config.live_view.enabled else "")
        live_paths = {c.id: (c.live_path or c.id.lower()) for c in engine.cameras}
        return (HTML.replace("__CAMERAS__", json.dumps(current_cameras))
                .replace("__SOURCES__", json.dumps(source_for))
                .replace("__LIVE_PATHS__", json.dumps(live_paths))
                .replace("__WEBRTC_BASE__", json.dumps(webrtc_base))
                .replace("__PREVIEW_FPS__", f"{preview_fps:g}")
                .replace("__PREVIEW_INTERVAL_MS__", str(preview_interval_ms))
                .replace("__PREVIEW_WIDTH__", str(engine.config.preview.width))
                .replace("__PREVIEW_HEIGHT__", str(engine.config.preview.height))).encode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            pass  # Avoid noisy per-frame logs.

        from pathlib import Path

        def respond(self, status: int, content_type: str, content: bytes,
                    frame_sequence: int | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.send_header("X-Content-Type-Options", "nosniff")
            if frame_sequence is not None:
                self.send_header("X-Frame-Sequence", str(frame_sequence))
            self.send_header("Content-Security-Policy", "default-src 'self' http: https: data: blob:; frame-src *; img-src * data: blob:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'")
            self.end_headers()
            if content and self.command != "HEAD":
                self.wfile.write(content)

        def respond_file(self, status: int, content_type: str, file_path: Path,
                         range_header: str | None = None) -> None:
            """Serve a file with Range request support for video streaming."""
            if not file_path.is_file():
                self.respond(404, "text/plain", b"File not found")
                return

            file_size = file_path.stat().st_size
            start = 0
            end = file_size - 1
            is_range = False

            norm_range = (range_header or "").strip()
            if norm_range.lower().startswith("bytes="):
                try:
                    range_spec = norm_range[6:].strip()
                    if "," in range_spec:
                        range_spec = range_spec.split(",", 1)[0].strip()
                    if "-" in range_spec:
                        start_str, end_str = range_spec.split("-", 1)
                        start_str = start_str.strip()
                        end_str = end_str.strip()
                        if start_str and end_str:
                            start = int(start_str)
                            end = int(end_str)
                        elif start_str:
                            start = int(start_str)
                            end = file_size - 1
                        elif end_str:
                            suffix_len = int(end_str)
                            start = max(0, file_size - suffix_len)
                            end = file_size - 1

                        if file_size == 0 or start >= file_size or start > end:
                            self.send_response(416)
                            self.send_header("Content-Range", f"bytes */{file_size}")
                            self.send_header("Content-Length", "0")
                            self.send_header("Accept-Ranges", "bytes")
                            self.end_headers()
                            return

                        end = min(end, file_size - 1)
                        is_range = True
                except (ValueError, IndexError):
                    pass

            if is_range:
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            else:
                self.send_response(status)

            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "public, max-age=3600")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Range")
            self.end_headers()

            if self.command != "HEAD":
                try:
                    with file_path.open("rb") as f:
                        f.seek(start)
                        remaining = end - start + 1
                        chunk_size = 65536
                        while remaining > 0:
                            to_read = min(chunk_size, remaining)
                            data = f.read(to_read)
                            if not data:
                                break
                            self.wfile.write(data)
                            remaining -= len(data)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    return

        def respond_json(self, status: int, data: Any) -> None:
            body = json.dumps(data).encode("utf-8")
            self.respond(status, "application/json", body)

        def read_json_body(self) -> dict[str, Any]:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0:
                return {}
            raw = self.rfile.read(content_length)
            return json.loads(raw.decode("utf-8"))

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.end_headers()

        def do_HEAD(self) -> None:
            self.do_GET()

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            c_ids = get_camera_ids()
            if path in ("/", "/demo"):
                self.respond(200, "text/html; charset=utf-8", render_html())
            elif path == "/api/capabilities":
                if getattr(engine, "onboarding_service", None) is not None:
                    caps = [c.to_dict() for c in engine.onboarding_service.registry.all()]
                    self.respond_json(200, caps)
                else:
                    self.respond_json(200, [])
            elif path == "/api/cameras":
                cams = []
                for c in engine.cameras:
                    sanitized = sanitize_rtsp_url(c.uri)
                    cams.append({
                        "camera_id": c.id,
                        "name": c.id,
                        "rtsp_url": sanitized,
                        "codec": c.codec,
                        "decoder": c.decoder,
                    })
                self.respond_json(200, cams)
            elif path.startswith("/api/cameras/") and path.endswith("/onboarding/status"):
                cam_id = path[len("/api/cameras/"):-len("/onboarding/status")].strip("/")
                service = getattr(engine, "onboarding_service", None)
                if service is None:
                    self.respond_json(500, {"error": "Onboarding service not initialized"})
                    return
                try:
                    res = service.get_status(cam_id)
                    self.respond_json(200, res)
                except ValueError as ve:
                    self.respond_json(404, {"error": str(ve)})
                except Exception as ex:
                    self.respond_json(500, {"error": str(ex)})
            elif path.startswith("/api/cameras/") and path.endswith("/recommendations"):
                cam_id = path[len("/api/cameras/"):-len("/recommendations")].strip("/")
                service = getattr(engine, "onboarding_service", None)
                if service is None:
                    self.respond_json(500, {"error": "Onboarding service not initialized"})
                    return
                try:
                    res = service.get_recommendations(cam_id)
                    self.respond_json(200, res)
                except ValueError as ve:
                    self.respond_json(404, {"error": str(ve)})
                except Exception as ex:
                    self.respond_json(500, {"error": str(ex)})
            elif path.startswith("/api/cameras/") and path.endswith("/capabilities"):
                cam_id = path[len("/api/cameras/"):-len("/capabilities")].strip("/")
                service = getattr(engine, "onboarding_service", None)
                if service is None:
                    self.respond_json(500, {"error": "Onboarding service not initialized"})
                    return
                active = service.capability_manager.get_active_capabilities(cam_id)
                cfg = service.config_store.get(cam_id)
                self.respond_json(200, {
                    "camera_id": cam_id,
                    "active_capabilities": active,
                    "config_version": cfg.version if cfg else 1,
                    "configurations": cfg.configurations if cfg else {},
                })
            elif path == "/api/status":
                status = engine.metrics.view()
                status["mode"] = engine.config.runtime.mode
                status["resources"] = engine.latest_resources()
                status["tracking"] = engine.tracking_metrics() if hasattr(engine, "tracking_metrics") else {}
                latest_res = engine.latest_results()
                status["detections"] = {
                    cam_id: [
                        {
                            "class": d.label,
                            "confidence": round(d.confidence, 2),
                            "track_id": getattr(d, "track_id", None),
                            "bbox": [
                                round(d.x1 * (getattr(res, "source_width", 0) or 1280), 1),
                                round(d.y1 * (getattr(res, "source_height", 0) or 720), 1),
                                round(d.x2 * (getattr(res, "source_width", 0) or 1280), 1),
                                round(d.y2 * (getattr(res, "source_height", 0) or 720), 1),
                            ],
                        }
                        for d in res.detections
                    ]
                    for cam_id, res in latest_res.items()
                }
                self.respond_json(200, status)
            elif path.startswith("/api/tracks/"):
                camera_id = path[len("/api/tracks/"):]
                tracks = engine.latest_tracks(camera_id) if hasattr(engine, "latest_tracks") else []
                data = {
                    "camera_id": camera_id,
                    "tracks": [
                        {
                            "track_id": t.global_track_id,
                            "class_name": t.class_name,
                            "state": str(t.state),
                            "bbox_xyxy": [round(v, 1) for v in t.bbox_xyxy],
                            "confidence": round(t.confidence, 2),
                            "duration_ms": round(t.duration_ms, 1),
                            "direction": str(t.direction),
                            "best_crop_score": round(t.best_crop_score, 2),
                            "trajectory": [[round(p[0], 1), round(p[1], 1)] for p in list(t.trajectory)[-20:]],
                        }
                        for t in tracks
                    ],
                }
                self.respond_json(200, data)
            elif path == "/api/tracks":
                all_tracks: dict[str, Any] = {}
                for cid in c_ids:
                    tracks = engine.latest_tracks(cid) if hasattr(engine, "latest_tracks") else []
                    all_tracks[cid] = [
                        {
                            "track_id": t.global_track_id,
                            "class_name": t.class_name,
                            "state": str(t.state),
                            "bbox_xyxy": [round(v, 1) for v in t.bbox_xyxy],
                            "confidence": round(t.confidence, 2),
                            "duration_ms": round(t.duration_ms, 1),
                            "direction": str(t.direction),
                            "best_crop_score": round(t.best_crop_score, 2),
                            "trajectory": [[round(p[0], 1), round(p[1], 1)] for p in list(t.trajectory)[-20:]],
                        }
                        for t in tracks
                    ]
                self.respond_json(200, all_tracks)
            elif path.startswith("/api/detections/"):
                camera_id = path[len("/api/detections/"):]
                if hasattr(cache, "touch"):
                    cache.touch(camera_id, 3.0)
                latest_res = engine.latest_results()
                res = latest_res.get(camera_id)
                status = engine.metrics.view()
                cam_m = status.get("cameras", {}).get(camera_id, {})
                w = getattr(res, "source_width", 0) or 1280
                h = getattr(res, "source_height", 0) or 720
                tracks_map = {t.global_track_id: t for t in engine.latest_tracks(camera_id)} if hasattr(engine, "latest_tracks") else {}
                if res is None:
                    data = {
                        "camera_id": camera_id,
                        "sequence": 0,
                        "timestamp": 0.0,
                        "inference_ms": 0.0,
                        "total_latency_ms": 0.0,
                        "frame_path": cam_m.get("frame_path", "GPU_NATIVE"),
                        "cpu_frame_downloads": cam_m.get("cpu_frame_downloads", 0),
                        "width": w,
                        "height": h,
                        "detections": [],
                    }
                else:
                    dets_list = []
                    for d in res.detections:
                        tid = getattr(d, "track_id", None)
                        trk = tracks_map.get(tid)
                        traj = [[round(p[0], 1), round(p[1], 1)] for p in list(trk.trajectory)[-20:]] if trk else []
                        dets_list.append({
                            "label": d.label,
                            "class_id": d.class_id,
                            "confidence": round(d.confidence, 3),
                            "track_id": tid,
                            "direction": str(trk.direction) if trk else "STATIONARY",
                            "trajectory": traj,
                            "bbox": [
                                round(d.x1 * w, 1),
                                round(d.y1 * h, 1),
                                round(d.x2 * w, 1),
                                round(d.y2 * h, 1),
                            ],
                            "bbox_normalized": [
                                round(d.x1, 4),
                                round(d.y1, 4),
                                round(d.x2, 4),
                                round(d.y2, 4),
                            ],
                        })
                    data = {
                        "camera_id": camera_id,
                        "sequence": res.frame_sequence,
                        "timestamp": res.timestamp,
                        "inference_ms": round(res.inference_ms, 2),
                        "total_latency_ms": round(res.total_latency_ms, 2),
                        "frame_path": cam_m.get("frame_path", "GPU_NATIVE"),
                        "cpu_frame_downloads": cam_m.get("cpu_frame_downloads", 0),
                        "width": w,
                        "height": h,
                        "detections": dets_list,
                    }
                self.respond_json(200, data)
            elif path == "/api/detections":
                latest_res = engine.latest_results()
                status = engine.metrics.view()
                all_dets: dict[str, Any] = {}
                for cam_id in c_ids:
                    res = latest_res.get(cam_id)
                    cam_m = status.get("cameras", {}).get(cam_id, {})
                    w = getattr(res, "source_width", 0) or 1280
                    h = getattr(res, "source_height", 0) or 720
                    tracks_map = {t.global_track_id: t for t in engine.latest_tracks(cam_id)} if hasattr(engine, "latest_tracks") else {}
                    if res is None:
                        all_dets[cam_id] = {
                            "camera_id": cam_id,
                            "sequence": 0,
                            "inference_ms": 0.0,
                            "frame_path": cam_m.get("frame_path", "GPU_NATIVE"),
                            "detections": [],
                        }
                    else:
                        dets_list = []
                        for d in res.detections:
                            tid = getattr(d, "track_id", None)
                            trk = tracks_map.get(tid)
                            traj = [[round(p[0], 1), round(p[1], 1)] for p in list(trk.trajectory)[-20:]] if trk else []
                            dets_list.append({
                                "label": d.label,
                                "class_id": d.class_id,
                                "confidence": round(d.confidence, 3),
                                "track_id": tid,
                                "direction": str(trk.direction) if trk else "STATIONARY",
                                "trajectory": traj,
                                "bbox": [
                                    round(d.x1 * w, 1),
                                    round(d.y1 * h, 1),
                                    round(d.x2 * w, 1),
                                    round(d.y2 * h, 1),
                                ],
                            })
                        all_dets[cam_id] = {
                            "camera_id": cam_id,
                            "sequence": res.frame_sequence,
                            "timestamp": res.timestamp,
                            "inference_ms": round(res.inference_ms, 2),
                            "total_latency_ms": round(res.total_latency_ms, 2),
                            "frame_path": cam_m.get("frame_path", "GPU_NATIVE"),
                            "cpu_frame_downloads": cam_m.get("cpu_frame_downloads", 0),
                            "detections": dets_list,
                        }
                self.respond_json(200, all_dets)
            elif path == "/api/frames/batch":
                if hasattr(cache, "touch"):
                    for cid in c_ids:
                        cache.touch(cid, 2.0)
                since_seqs = {}
                query = urlsplit(self.path).query
                if query:
                    import urllib.parse
                    q_params = urllib.parse.parse_qs(query)
                    if "since" in q_params:
                        try:
                            since_seqs = json.loads(q_params["since"][0])
                        except Exception:
                            pass
                all_cached = cache.all_latest()
                payload = {}
                import base64
                for cam_id in c_ids:
                    prev = all_cached.get(cam_id)
                    if prev is None:
                        payload[cam_id] = {"seq": 0, "has_frame": False}
                        continue
                    last_seen = since_seqs.get(cam_id, -1)
                    if prev.sequence > last_seen:
                        payload[cam_id] = {
                            "seq": prev.sequence,
                            "has_frame": True,
                            "jpeg": base64.b64encode(prev.jpeg).decode("ascii"),
                        }
                    else:
                        payload[cam_id] = {
                            "seq": prev.sequence,
                            "has_frame": True,
                        }
                self.respond_json(200, payload)
            elif path.startswith("/api/webrtc/"):
                camera_id = path[len("/api/webrtc/"):]
                if getattr(engine, "live_service", None) is not None:
                    try:
                        stream = engine.live_service.get(camera_id)
                        self.respond_json(200, {
                            "camera_id": stream.camera_id,
                            "protocol": stream.protocol,
                            "live_url": stream.live_url,
                            "status": stream.status,
                            "viewers": stream.active_live_viewers,
                        })
                        return
                    except Exception:
                        pass
                self.respond_json(404, {"error": "not found"})
            elif path.startswith("/api/cameras/") and path.endswith("/zones"):
                camera_id = path[len("/api/cameras/"):-len("/zones")].strip("/")
                sp = getattr(engine, "spatial_manager", None)
                if sp:
                    zones = sp.zone_mgr.get_zones(camera_id)
                    self.respond_json(200, {
                        "camera_id": camera_id,
                        "version": sp.get_config_version(camera_id),
                        "zones": [z.to_dict() for z in zones],
                    })
                else:
                    self.respond_json(200, {"camera_id": camera_id, "version": 1, "zones": []})
            elif path.startswith("/api/cameras/") and path.endswith("/lines"):
                camera_id = path[len("/api/cameras/"):-len("/lines")].strip("/")
                sp = getattr(engine, "spatial_manager", None)
                if sp:
                    lines = sp.line_mgr.get_lines(camera_id)
                    self.respond_json(200, {
                        "camera_id": camera_id,
                        "version": sp.get_config_version(camera_id),
                        "lines": [l.to_dict() for l in lines],
                    })
                else:
                    self.respond_json(200, {"camera_id": camera_id, "version": 1, "lines": []})
            elif path.startswith("/api/cameras/") and path.endswith("/rules"):
                camera_id = path[len("/api/cameras/"):-len("/rules")].strip("/")
                sp = getattr(engine, "spatial_manager", None)
                if sp:
                    rules = sp.rule_engine.get_rules(camera_id)
                    self.respond_json(200, {
                        "camera_id": camera_id,
                        "version": sp.get_config_version(camera_id),
                        "rules": [r.to_dict() for r in rules],
                    })
                else:
                    self.respond_json(200, {"camera_id": camera_id, "version": 1, "rules": []})
            elif path.startswith("/api/cameras/") and path.endswith("/occupancy"):
                camera_id = path[len("/api/cameras/"):-len("/occupancy")].strip("/")
                sp = getattr(engine, "spatial_manager", None)
                if sp:
                    occ = sp.occupancy_mgr.get_flow_occupancy(camera_id)
                    counts = sp.line_mgr.get_all_counts(camera_id)
                    self.respond_json(200, {
                        "camera_id": camera_id,
                        "visible_occupancy": occ.visible_occupancy,
                        "flow_occupancy": occ.flow_occupancy,
                        "baseline": occ.baseline,
                        "total_in": occ.total_in,
                        "total_out": occ.total_out,
                        "is_uncertain": occ.is_uncertain,
                        "line_counts": counts,
                        "last_reconciled_utc": occ.last_reconciled_utc,
                    })
                else:
                    self.respond_json(200, {"camera_id": camera_id, "visible_occupancy": 0, "flow_occupancy": 0})
            elif path.startswith("/api/cameras/") and path.endswith("/events/active"):
                camera_id = path[len("/api/cameras/"):-len("/events/active")].strip("/")
                sp = getattr(engine, "spatial_manager", None)
                if sp:
                    evts = sp.store.get_active_events(camera_id)
                    self.respond_json(200, {"camera_id": camera_id, "events": [e.to_dict() for e in evts]})
                else:
                    self.respond_json(200, {"camera_id": camera_id, "events": []})
            elif path.startswith("/api/cameras/") and path.endswith("/events"):
                camera_id = path[len("/api/cameras/"):-len("/events")].strip("/")
                sp = getattr(engine, "spatial_manager", None)
                if sp:
                    evts = sp.store.get_recent_events(camera_id, limit=50)
                    self.respond_json(200, {"camera_id": camera_id, "events": [e.to_dict() for e in evts]})
                else:
                    self.respond_json(200, {"camera_id": camera_id, "events": []})
            elif path == "/api/events" or path.startswith("/api/events?"):
                # Global events query with filters
                from datetime import datetime, timezone, timedelta
                query = urlsplit(self.path).query
                params = parse_qs(query)
                camera_id = params.get("camera_id", [None])[0] or None
                start_ist = params.get("start", [None])[0] or None
                end_ist = params.get("end", [None])[0] or None
                obj_class = params.get("class", [None])[0] or None
                clip_only = params.get("clip_only", ["0"])[0] in ("1", "true", "True")
                limit = int(params.get("limit", ["50"])[0])
                offset = int(params.get("offset", ["0"])[0])

                # Convert IST to UTC for database query
                ist_tz = timezone(timedelta(hours=5, minutes=30))
                def parse_to_utc(s: str | None) -> str | None:
                    if not s:
                        return None
                    try:
                        s = s.strip()
                        if s.endswith("Z"):
                            dt = datetime.fromisoformat(s[:-1] + "+00:00")
                        elif "+" in s or (s.rfind("-") > 10):
                            dt = datetime.fromisoformat(s)
                        else:
                            dt = datetime.fromisoformat(s).replace(tzinfo=ist_tz)
                        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    except Exception:
                        return None

                start_utc = parse_to_utc(start_ist)
                end_utc = parse_to_utc(end_ist)

                event_db = getattr(engine, "event_db", None)
                if event_db:
                    events = event_db.query_events(
                        camera_id=camera_id,
                        start_utc=start_utc,
                        end_utc=end_utc,
                        object_class=obj_class,
                        clip_only=clip_only,
                        limit=limit,
                        offset=offset,
                    )
                    self.respond_json(200, {
                        "events": [e.to_dict() for e in events],
                        "total": len(events),
                        "limit": limit,
                        "offset": offset,
                    })
                else:
                    self.respond_json(200, {"events": [], "total": 0, "limit": limit, "offset": offset})
            elif path.startswith("/api/events/"):
                # Get single event by ID
                event_id = path[len("/api/events/"):].strip("/")
                event_db = getattr(engine, "event_db", None)
                if event_db:
                    event = event_db.get_event(event_id)
                    if event:
                        self.respond_json(200, event.to_dict())
                    else:
                        self.respond_json(404, {"error": "Event not found"})
                else:
                    self.respond_json(404, {"error": "Event database not available"})
            elif path == "/api/intelligence/metrics":
                sp = getattr(engine, "spatial_manager", None)
                if sp:
                    self.respond_json(200, sp.get_telemetry_snapshot())
                else:
                    self.respond_json(200, {})
            elif path.startswith("/api/evidence/"):
                filename = path[len("/api/evidence/"):].strip("/")
                sp = getattr(engine, "spatial_manager", None)
                from pathlib import Path
                evidence_dir = Path(sp.config.evidence_storage_dir) if sp else Path("runtime/streamcore/output/evidence")
                file_path = evidence_dir / filename
                if file_path.is_file():
                    self.respond(200, "image/jpeg", file_path.read_bytes())
                    return
                self.respond(404, "text/plain", b"Evidence image not found")
            elif path.startswith("/api/snapshots/"):
                filename = path[len("/api/snapshots/"):].strip("/")
                from pathlib import Path
                vsm = getattr(engine, "visual_search_manager", None)
                base_dir = (vsm.base_dir if vsm else Path("runtime/streamcore/output")).resolve()
                snap_dir = (vsm.snapshots_dir if vsm else (base_dir / "snapshots")).resolve()

                if filename.startswith("snapshots/"):
                    filename = filename[len("snapshots/"):]

                file_path = snap_dir / filename
                if not file_path.is_file():
                    file_path = snap_dir.parent / filename
                if not file_path.is_file():
                    file_path = snap_dir / Path(filename).name
                if not file_path.is_file() and Path(filename).name:
                    matches = list(snap_dir.glob(f"**/{Path(filename).name}"))
                    if matches:
                        file_path = matches[0]
                try:
                    if file_path.is_file() and (base_dir in file_path.resolve().parents or file_path.resolve().is_relative_to(base_dir)):
                        self.respond(200, "image/jpeg", file_path.read_bytes())
                        return
                except Exception:
                    pass
                self.respond(404, "text/plain", b"Snapshot image not found")
            elif path == "/api/search-visual" or path.startswith("/api/search-visual?"):
                query_params = parse_qs(urlsplit(self.path).query)
                query = query_params.get("query", [""])[0]
                cam_id = query_params.get("camera_id", [None])[0] or None
                start_utc = query_params.get("start", [None])[0] or query_params.get("start_utc", [None])[0]
                end_utc = query_params.get("end", [None])[0] or query_params.get("end_utc", [None])[0]
                try:
                    top_k = int(query_params.get("top_k", [2])[0])
                except Exception:
                    top_k = 2
                vsm = getattr(engine, "visual_search_manager", None)
                if vsm is None:
                    from ..events.visual_search_manager import VisualSearchManager
                    ev_cfg = getattr(getattr(engine, "config", None), "events", None)
                    vsm = VisualSearchManager(
                        event_db=getattr(engine, "event_db", None),
                        settings=ev_cfg,
                    )
                    engine.visual_search_manager = vsm
                results = vsm.search(query, top_k=top_k, camera_id=cam_id, start_utc=start_utc, end_utc=end_utc)
                self.respond_json(200, {
                    "query": query,
                    "count": len(results),
                    "has_api_key": vsm.has_api_key,
                    "results": results
                })
            elif path in ("/api/settings/gemini", "/api/status/search"):
                vsm = getattr(engine, "visual_search_manager", None)
                has_vlm = False
                vlm_model = ""
                embed_model = ""
                ollama_url = ""
                if vsm and vsm.local_models:
                    has_vlm = bool(vsm.local_models.has_vlm and vsm.local_models.has_embedder)
                    vlm_model = vsm.local_models.config.vlm_model
                    embed_model = vsm.local_models.config.embed_model
                    ollama_url = vsm.local_models.config.ollama_url
                elif vsm:
                    has_vlm = vsm.has_api_key
                self.respond_json(200, {
                    "has_api_key": has_vlm,
                    "backend": "local",
                    "vlm_model": vlm_model,
                    "embed_model": embed_model,
                    "ollama_url": ollama_url,
                    "total_vectors": vsm.vector_store.total_items if vsm else 0,
                })
            elif path == "/api/events/reindex":
                vsm = getattr(engine, "visual_search_manager", None)
                if vsm is None:
                    from ..events.visual_search_manager import VisualSearchManager
                    ev_cfg = getattr(getattr(engine, "config", None), "events", None)
                    vsm = VisualSearchManager(
                        event_db=getattr(engine, "event_db", None),
                        settings=ev_cfg,
                    )
                    engine.visual_search_manager = vsm
                count = vsm.index_existing_clips_sync(max_items=500)
                self.respond_json(200, {"status": "OK", "indexed_count": count, "total_vectors": vsm.vector_store.total_items})
            elif path.startswith("/api/clips/"):
                # Serve video clips with Range support for streaming
                clip_path = path[len("/api/clips/"):].strip("/")
                from pathlib import Path
                event_db = getattr(engine, "event_db", None)
                if event_db and getattr(event_db, "config", None):
                    clips_dir = Path(event_db.config.clip_storage_dir).resolve()
                else:
                    clips_dir = Path("runtime/streamcore/output/clips").resolve()
                base_dir = clips_dir.parent

                if clip_path.startswith("clips/"):
                    clip_path = clip_path[len("clips/"):]

                file_path = clips_dir / clip_path
                if not file_path.is_file():
                    file_path = base_dir / clip_path
                if not file_path.is_file():
                    file_path = clips_dir / Path(clip_path).name
                if not file_path.is_file() and Path(clip_path).name:
                    matches = list(clips_dir.glob(f"**/{Path(clip_path).name}"))
                    if matches:
                        file_path = matches[0]
                try:
                    if file_path.is_file() and base_dir in file_path.resolve().parents:
                        range_header = self.headers.get("Range")
                        self.respond_file(200, "video/mp4", file_path, range_header)
                        return
                except Exception:
                    pass
                self.respond(404, "text/plain", b"Clip not found")
            elif path.startswith("/frame/") and path.endswith(".jpg"):
                camera_id = path[len("/frame/"):-len(".jpg")]
                if camera_id not in c_ids:
                    self.respond(404, "text/plain", b"Unknown camera")
                    return
                if hasattr(cache, "touch"):
                    cache.touch(camera_id, 3.0)
                preview = cache.latest(camera_id)
                if preview is None:
                    self.respond(200, "image/jpeg", TINY_JPEG, frame_sequence=0)
                    return
                self.respond(200, "image/jpeg", preview.jpeg, frame_sequence=preview.sequence)
            elif path.startswith("/stream/"):
                camera_id = path[len("/stream/"):]
                if camera_id.endswith(".mjpg"):
                    camera_id = camera_id[:-len(".mjpg")]
                if camera_id not in c_ids:
                    self.respond(404, "text/plain", b"Unknown camera")
                    return
                if hasattr(cache, "touch"):
                    cache.touch(camera_id, 10.0)
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                last_seq = -1
                import time
                last_touch = time.monotonic()
                try:
                    while not engine.stop_event.is_set():
                        now_m = time.monotonic()
                        if now_m - last_touch > 1.0:
                            if hasattr(cache, "touch"):
                                cache.touch(camera_id, 10.0)
                            last_touch = now_m
                        preview = cache.latest(camera_id)
                        if preview is not None and preview.sequence != last_seq:
                            last_seq = preview.sequence
                            header = (
                                b"--frame\r\n"
                                b"Content-Type: image/jpeg\r\n"
                                b"Content-Length: " + str(len(preview.jpeg)).encode() + b"\r\n\r\n"
                            )
                            self.wfile.write(header + preview.jpeg + b"\r\n")
                            self.wfile.flush()
                        time.sleep(0.01)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    return
            else:
                self.respond(404, "text/plain", b"Not found")

        def do_POST(self) -> None:
            path = urlsplit(self.path).path
            service = getattr(engine, "onboarding_service", None)
            if path == "/api/cameras":
                data = self.read_json_body()
                camera_id = (data.get("camera_id") or data.get("name") or "").strip()
                rtsp_url = (data.get("rtsp_url") or data.get("uri") or "").strip()
                codec = data.get("codec", "h264")
                decoder = data.get("decoder", "auto")
                live_path = data.get("live_path")
                if not camera_id or not rtsp_url:
                    self.respond_json(400, {"error": "Missing camera_id or rtsp_url in request payload."})
                    return
                if service is None:
                    self.respond_json(500, {"error": "Onboarding service not initialized"})
                    return
                try:
                    res = service.register_camera(
                        camera_id=camera_id,
                        rtsp_uri=rtsp_url,
                        codec=codec,
                        decoder=decoder,
                        live_path=live_path,
                    )
                    self.respond_json(201, res)
                except ValueError as ve:
                    self.respond_json(400, {"error": str(ve)})
                except RuntimeError as re_err:
                    self.respond_json(500, {"error": str(re_err)})
                except Exception as ex:
                    self.respond_json(500, {"error": str(ex)})
            elif path.startswith("/api/cameras/") and path.endswith("/onboarding/analyze"):
                camera_id = path[len("/api/cameras/"):-len("/onboarding/analyze")].strip("/")
                data = self.read_json_body()
                sample_count = int(data.get("sample_count", 20))
                sample_duration = float(data.get("sample_duration_seconds", 8.0))
                force_fresh = bool(data.get("force_fresh", False))
                if service is None:
                    self.respond_json(500, {"error": "Onboarding service not initialized"})
                    return
                try:
                    res = service.start_analysis(
                        camera_id=camera_id,
                        sample_count=sample_count,
                        sample_duration_seconds=sample_duration,
                        force_fresh=force_fresh,
                    )
                    self.respond_json(202, res)
                except ValueError as ve:
                    self.respond_json(400, {"error": str(ve)})
                except Exception as ex:
                    self.respond_json(500, {"error": str(ex)})
            elif path.startswith("/api/cameras/") and path.endswith("/onboarding/reset"):
                camera_id = path[len("/api/cameras/"):-len("/onboarding/reset")].strip("/")
                if service is not None:
                    with service._lock:
                        if camera_id in service._camera_states:
                            service._camera_states[camera_id]["status"] = "CONNECTED"
                            service._camera_states[camera_id]["error"] = None
                            service._camera_states[camera_id]["progress_percent"] = 0
                self.respond_json(200, {"camera_id": camera_id, "status": "RESET"})
            elif path == "/api/search-visual":
                data = self.read_json_body()
                query = str(data.get("query") or "").strip()
                cam_id = data.get("camera_id") or None
                start_utc = data.get("start") or data.get("start_utc") or None
                end_utc = data.get("end") or data.get("end_utc") or None
                try:
                    top_k = int(data.get("top_k", 2))
                except Exception:
                    top_k = 2

                vsm = getattr(engine, "visual_search_manager", None)
                if vsm is None:
                    from ..events.visual_search_manager import VisualSearchManager
                    ev_cfg = getattr(getattr(engine, "config", None), "events", None)
                    vsm = VisualSearchManager(
                        event_db=getattr(engine, "event_db", None),
                        settings=ev_cfg,
                    )
                    engine.visual_search_manager = vsm

                results = vsm.search(query, top_k=top_k, camera_id=cam_id, start_utc=start_utc, end_utc=end_utc)
                self.respond_json(200, {
                    "query": query,
                    "count": len(results),
                    "has_api_key": vsm.has_api_key,
                    "results": results
                })
            elif path == "/api/events/reindex":
                vsm = getattr(engine, "visual_search_manager", None)
                if vsm is None:
                    from ..events.visual_search_manager import VisualSearchManager
                    ev_cfg = getattr(getattr(engine, "config", None), "events", None)
                    vsm = VisualSearchManager(
                        event_db=getattr(engine, "event_db", None),
                        settings=ev_cfg,
                    )
                    engine.visual_search_manager = vsm
                count = vsm.index_existing_clips_sync(max_items=500)
                self.respond_json(200, {"status": "OK", "indexed_count": count, "total_vectors": vsm.vector_store.total_items})
            else:
                self.respond(404, "text/plain", b"Not found")

        def do_PUT(self) -> None:
            path = urlsplit(self.path).path
            service = getattr(engine, "onboarding_service", None)
            if path.startswith("/api/cameras/") and path.endswith("/capabilities"):
                camera_id = path[len("/api/cameras/"):-len("/capabilities")].strip("/")
                data = self.read_json_body()
                selected_caps = data.get("capabilities", [])
                expected_ver = data.get("expected_version")
                configurations = data.get("configurations")
                user_ip = self.client_address[0] if self.client_address else "127.0.0.1"
                if service is None:
                    self.respond_json(500, {"error": "Onboarding service not initialized"})
                    return
                try:
                    res = service.apply_capabilities(
                        camera_id=camera_id,
                        selected_capabilities=selected_caps,
                        expected_config_version=expected_ver,
                        configurations=configurations,
                        user_ip=user_ip,
                    )
                    self.respond_json(200, res)
                except ValueError as ve:
                    self.respond_json(400, {"error": str(ve)})
                except RuntimeError as re_err:
                    status_code = 409 if "conflict" in str(re_err).lower() else 500
                    self.respond_json(status_code, {"error": str(re_err)})
                except Exception as ex:
                    self.respond_json(500, {"error": str(ex)})
            elif path.startswith("/api/cameras/") and path.endswith("/zones"):
                camera_id = path[len("/api/cameras/"):-len("/zones")].strip("/")
                sp = getattr(engine, "spatial_manager", None)
                if sp is None:
                    self.respond_json(500, {"error": "Spatial manager not initialized"})
                    return
                data = self.read_json_body()
                zones_data = data.get("zones", [])
                expected_ver = data.get("expected_version")
                ok, msg, ver = sp.update_zones(camera_id, zones_data, expected_ver)
                if ok:
                    self.respond_json(200, {"status": "OK", "message": msg, "version": ver})
                else:
                    status_code = 409 if "conflict" in msg.lower() else 400
                    self.respond_json(status_code, {"error": msg, "version": ver})
            elif path.startswith("/api/cameras/") and path.endswith("/lines"):
                camera_id = path[len("/api/cameras/"):-len("/lines")].strip("/")
                sp = getattr(engine, "spatial_manager", None)
                if sp is None:
                    self.respond_json(500, {"error": "Spatial manager not initialized"})
                    return
                data = self.read_json_body()
                lines_data = data.get("lines", [])
                expected_ver = data.get("expected_version")
                ok, msg, ver = sp.update_lines(camera_id, lines_data, expected_ver)
                if ok:
                    self.respond_json(200, {"status": "OK", "message": msg, "version": ver})
                else:
                    status_code = 409 if "conflict" in msg.lower() else 400
                    self.respond_json(status_code, {"error": msg, "version": ver})
            elif path.startswith("/api/cameras/") and path.endswith("/rules"):
                camera_id = path[len("/api/cameras/"):-len("/rules")].strip("/")
                sp = getattr(engine, "spatial_manager", None)
                if sp is None:
                    self.respond_json(500, {"error": "Spatial manager not initialized"})
                    return
                data = self.read_json_body()
                rules_data = data.get("rules", [])
                expected_ver = data.get("expected_version")
                ok, msg, ver = sp.update_rules(camera_id, rules_data, expected_ver)
                if ok:
                    self.respond_json(200, {"status": "OK", "message": msg, "version": ver})
                else:
                    status_code = 409 if "conflict" in msg.lower() else 400
                    self.respond_json(status_code, {"error": msg, "version": ver})
            else:
                self.respond(404, "text/plain", b"Not found")

    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.daemon_threads = True
    Thread(target=server.serve_forever, name="streamcore-preview", daemon=True).start()
    return server
