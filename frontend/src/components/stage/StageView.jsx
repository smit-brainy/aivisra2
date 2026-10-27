import React, { useEffect, useRef, useState } from 'react';
import { fetchDetections, fetchStatus, getStreamUrl, getFrameUrl } from '../../utils/api';

export default function StageView({ cameras = [], selectedCam, setSelectedCam }) {
  const [streamMode, setStreamMode] = useState('mjpeg'); // 'mjpeg' or 'webrtc'
  const [telemetry, setTelemetry] = useState(null);
  const [currentDets, setCurrentDets] = useState(null);
  const canvasRef = useRef(null);
  const activeCamera = selectedCam || (cameras.length > 0 ? cameras[0].camera_id : 'CAM001');

  // Poll telemetry and detections for active camera
  useEffect(() => {
    let isMounted = true;
    const interval = setInterval(async () => {
      try {
        const [statusData, detsData] = await Promise.all([
          fetchStatus().catch(() => null),
          fetchDetections(activeCamera).catch(() => null),
        ]);
        if (isMounted) {
          if (statusData) setTelemetry(statusData);
          if (detsData) setCurrentDets(detsData);
        }
      } catch (err) {
        // quiet polling error
      }
    }, 500);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [activeCamera]);

  // Canvas drawing for WebRTC mode / raw bounding boxes
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    // Resize canvas to match display size
    const rect = canvas.getBoundingClientRect();
    if (canvas.width !== rect.width || canvas.height !== rect.height) {
      canvas.width = rect.width;
      canvas.height = rect.height;
    }

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (streamMode === 'webrtc' && currentDets) {
      const dets = currentDets.detections || [];
      const srcW = currentDets.width || 1280;
      const srcH = currentDets.height || 720;
      const scale = Math.min(canvas.width / srcW, canvas.height / srcH);
      const renderW = srcW * scale;
      const renderH = srcH * scale;
      const offsetX = (canvas.width - renderW) / 2;
      const offsetY = (canvas.height - renderH) / 2;

      for (const det of dets) {
        const x1 = offsetX + det.bbox[0] * scale;
        const y1 = offsetY + det.bbox[1] * scale;
        const x2 = offsetX + det.bbox[2] * scale;
        const y2 = offsetY + det.bbox[3] * scale;
        const w = x2 - x1;
        const h = y2 - y1;

        const color =
          det.class_id === 0 ? '#3fb950' : [2, 3, 5, 7].includes(det.class_id) ? '#79c0ff' : '#d29922';

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

        ctx.lineWidth = 2.5;
        ctx.strokeStyle = color;
        ctx.strokeRect(x1, y1, w, h);

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
  }, [currentDets, streamMode]);

  const camMetrics = telemetry?.cameras?.[activeCamera] || {};
  const resData = telemetry?.resources || {};
  const activeDets = currentDets?.detections || [];

  return (
    <section id="demo-view" style={{ display: 'grid' }}>
      {/* 1. Camera Selector Sidebar */}
      <div className="demo-pane">
        <div className="demo-pane-head">
          <span>Cameras</span>
          <span id="demo-cam-count">{cameras.length}</span>
        </div>
        <div className="cam-list">
          {cameras.map((c) => (
            <div
              key={c.camera_id}
              className={`cam-item ${c.camera_id === activeCamera ? 'selected' : ''}`}
              onClick={() => setSelectedCam(c.camera_id)}
            >
              <span>{c.name || c.camera_id}</span>
              <span className="cam-dot online"></span>
            </div>
          ))}
        </div>
      </div>

      {/* 2. Main Stage Video Player with Overlay */}
      <div className="demo-pane stage-center">
        <div className="stage-video-box">
          <img
            id="stage-mjpeg"
            src={getStreamUrl(activeCamera)}
            alt="Live Stream"
            style={{ width: '100%', height: '100%', objectFit: 'contain' }}
            onError={(e) => {
              e.target.src = getFrameUrl(activeCamera);
            }}
          />
          <canvas ref={canvasRef} id="demo-canvas"></canvas>
          <div className="stage-hud">
            <span className="hud-pill green">{activeCamera}</span>
            <span className="hud-pill">
              {currentDets?.width || 1280}x{currentDets?.height || 720}
            </span>
            <button
              className="hud-pill green"
              style={{ pointerEvents: 'auto', cursor: 'pointer', background: 'rgba(35,134,54,0.25)' }}
              onClick={() => setStreamMode(streamMode === 'mjpeg' ? 'webrtc' : 'mjpeg')}
            >
              🎥 Feed: {streamMode.toUpperCase()}
            </button>
          </div>
        </div>
        <div className="stage-bottom">
          <div>
            Active: <strong>{activeCamera}</strong> · <span>nvh264dec (GPU HW)</span>
          </div>
          <div>
            Source Latency:{' '}
            <span style={{ color: '#79c0ff', fontWeight: 600 }}>
              {currentDets ? Math.round(currentDets.total_latency_ms) : '--'} ms
            </span>
          </div>
        </div>
      </div>

      {/* 3. Right Telemetry Sidebar */}
      <div className="demo-pane">
        <div className="demo-pane-head">
          <span>GPU AI Telemetry</span>
          <span className="tele-val cyan">RTX 5070</span>
        </div>
        <div className="telemetry-body">
          <div className="tele-group">
            <div className="tele-label">Zero-Copy Pipeline</div>
            <div className="tele-row">
              <span>Frame Path</span>
              <span className="badge badge-gpu">{currentDets?.frame_path || 'GPU_NATIVE'}</span>
            </div>
            <div className="tele-row">
              <span>CPU Downloads</span>
              <span className="badge badge-zero">{currentDets?.cpu_frame_downloads || 0} frames</span>
            </div>
          </div>

          <div className="tele-group">
            <div className="tele-label">Stream & Inference Performance</div>
            <div className="tele-row">
              <span>Ingest FPS</span>
              <span className="tele-val">{(camMetrics.ingest_fps || 24.0).toFixed(1)}</span>
            </div>
            <div className="tele-row">
              <span>AI Inference FPS</span>
              <span className="tele-val green">{(telemetry?.inference_fps || 24.0).toFixed(1)}</span>
            </div>
            <div className="tele-row">
              <span>Inference Time</span>
              <span className="tele-val">{(currentDets?.inference_ms || 1.8).toFixed(1)} ms</span>
            </div>
            <div className="tele-row">
              <span>Total Latency</span>
              <span className="tele-val cyan">{(currentDets?.total_latency_ms || 2.4).toFixed(1)} ms</span>
            </div>
          </div>

          <div className="tele-group">
            <div className="tele-label">Hardware Utilization</div>
            <div className="tele-row">
              <span>GPU Utilization</span>
              <span className="tele-val">{resData.gpu_utilization_percent || 0}%</span>
            </div>
            <div className="tele-row">
              <span>NVDEC Utilization</span>
              <span className="tele-val green">{resData.nvdec_utilization_percent || 0}%</span>
            </div>
            <div className="tele-row">
              <span>VRAM Memory</span>
              <span className="tele-val">
                {(resData.gpu_memory_used_mb / 1024 || 0).toFixed(1)} /{' '}
                {(resData.gpu_memory_total_mb / 1024 || 12).toFixed(1)} GiB
              </span>
            </div>
          </div>

          <div className="tele-group">
            <div className="tele-label">
              Active Detections & Tracks ({activeDets.length})
            </div>
            <div className="dets-box">
              {activeDets.length === 0 ? (
                <div style={{ color: '#8b949e', textAlign: 'center', padding: '10px' }}>
                  Waiting for detections...
                </div>
              ) : (
                activeDets.map((d, idx) => (
                  <div key={idx} className="det-row">
                    <span style={{ color: '#58a6ff', fontWeight: 600 }}>
                      {d.label} {d.track_id ? `[ID ${d.track_id.split(':').pop()}]` : ''}
                    </span>
                    <span style={{ color: '#3fb950' }}>{Math.round(d.confidence * 100)}%</span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

