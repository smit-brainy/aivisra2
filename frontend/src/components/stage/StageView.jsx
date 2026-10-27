import React, { useEffect, useRef, useState } from 'react';
import { fetchDetections, fetchStatus, getStreamUrl, getFrameUrl } from '../../utils/api';

// Mini SVG Sparkline Component for Telemetry Trends
function Sparkline({ data = [], color = '#2563eb', height = 32, maxVal = null }) {
  if (!data || data.length < 2) {
    return (
      <div className="tele-sparkline" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
        Gathering data...
      </div>
    );
  }

  const computedMax = maxVal !== null ? maxVal : Math.max(...data, 1);
  const min = Math.min(...data, 0);
  const range = (computedMax - min) || 1;
  const width = 230;

  const points = data
    .map((val, idx) => {
      const x = (idx / (data.length - 1)) * width;
      const normalizedY = (val - min) / range;
      const y = height - normalizedY * (height - 6) - 3;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');

  return (
    <div className="tele-graph-item">
      <svg className="tele-sparkline" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
        <defs>
          <linearGradient id={`grad-${color.replace('#', '')}`} x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor={color} stopOpacity="0.25" />
            <stop offset="100%" stopColor={color} stopOpacity="0.0" />
          </linearGradient>
        </defs>
        <polygon
          points={`0,${height} ${points} ${width},${height}`}
          fill={`url(#grad-${color.replace('#', '')})`}
        />
        <polyline
          fill="none"
          stroke={color}
          strokeWidth="1.75"
          strokeLinecap="round"
          strokeLinejoin="round"
          points={points}
        />
      </svg>
    </div>
  );
}

// Chevron Icon for Collapsible Headers
function ChevronIcon({ open }) {
  return (
    <svg
      className={`tele-collapse-icon ${open ? 'open' : ''}`}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="9 18 15 12 9 6" />
    </svg>
  );
}

export default function StageView({ cameras = [], selectedCam, setSelectedCam }) {
  const [streamMode, setStreamMode] = useState('mjpeg'); // 'mjpeg' or 'webrtc'
  const [telemetry, setTelemetry] = useState(null);
  const [currentDets, setCurrentDets] = useState(null);
  const [showGraphs, setShowGraphs] = useState(false); // Single toggle state
  const canvasRef = useRef(null);
  const activeCamera = selectedCam || (cameras.length > 0 ? cameras[0].camera_id : 'CAM001');

  // Collapsible section state
  const [openSections, setOpenSections] = useState({
    performance: true,
    hardware: true,
    stream: true,
    detections: true,
  });

  const toggleSection = (key) => {
    setOpenSections((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  // Rolling history for telemetry sparklines (keeps last 30 sample points)
  const [history, setHistory] = useState({
    ingestFps: [],
    aiFps: [],
    inferMs: [],
    latencyMs: [],
    gpuUtil: [],
    nvdecUtil: [],
    vramUsed: [],
  });

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

          // Update rolling sparkline metrics
          if (statusData) {
            const camMetrics = statusData?.cameras?.[activeCamera] || {};
            const primaryGpu = (statusData?.resources?.gpus && statusData.resources.gpus.length > 0)
              ? statusData.resources.gpus[0]
              : null;

            const curIngest = Number(camMetrics.actual_fps ?? camMetrics.input_fps ?? camMetrics.decode_fps ?? 0.0);
            const curAi = Number(camMetrics.ai_fps ?? statusData.ai_target_fps ?? 0.0);
            const curInfer = Number(detsData?.inference_ms ?? 0.0);
            const curLat = Number(detsData?.total_latency_ms ?? 0.0);
            const curGpu = Number(primaryGpu?.utilization_percent ?? 0);
            const curNvdec = Number(primaryGpu?.decoder_percent ?? 0);
            const curVram = Number(((primaryGpu?.used_mib ?? 0) / 1024));

            setHistory((prev) => {
              const pushSample = (arr, val) => [...arr.slice(-29), val];
              return {
                ingestFps: pushSample(prev.ingestFps, curIngest),
                aiFps: pushSample(prev.aiFps, curAi),
                inferMs: pushSample(prev.inferMs, curInfer),
                latencyMs: pushSample(prev.latencyMs, curLat),
                gpuUtil: pushSample(prev.gpuUtil, curGpu),
                nvdecUtil: pushSample(prev.nvdecUtil, curNvdec),
                vramUsed: pushSample(prev.vramUsed, curVram),
              };
            });
          }
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
          det.class_id === 0 ? '#10b981' : [2, 3, 5, 7].includes(det.class_id) ? '#3b82f6' : '#f59e0b';

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

        ctx.fillStyle = '#ffffff';
        ctx.fillText(tag, x1 + 4, Math.max(13, y1 - 4));
      }
    }
  }, [currentDets, streamMode]);

  const camMetrics = telemetry?.cameras?.[activeCamera] || {};
  const resData = telemetry?.resources || {};
  const primaryGpu = (resData.gpus && resData.gpus.length > 0) ? resData.gpus[0] : null;

  const ingestFps = Number(camMetrics.actual_fps ?? camMetrics.input_fps ?? camMetrics.decode_fps ?? 0.0);
  const aiFps = Number(camMetrics.ai_fps ?? telemetry?.ai_target_fps ?? 0.0);
  const inferMs = Number(currentDets?.inference_ms ?? 0.0);
  const totalLatMs = Number(currentDets?.total_latency_ms ?? 0.0);
  const gpuUtil = primaryGpu?.utilization_percent ?? resData.gpu_utilization_percent ?? 0;
  const nvdecUtil = primaryGpu?.decoder_percent ?? resData.nvdec_utilization_percent ?? 0;
  const vramUsedGiB = ((primaryGpu?.used_mib ?? resData.gpu_memory_used_mb ?? 0) / 1024).toFixed(1);
  const vramTotalGiB = ((primaryGpu?.total_mib ?? resData.gpu_memory_total_mb ?? 12227) / 1024).toFixed(1);

  const activeDets = currentDets?.detections || [];

  return (
    <section id="demo-view" style={{ display: 'grid' }}>
      {/* 1. Camera Selector Sidebar */}
      <div className="demo-pane">
        <div className="demo-pane-head">
          <span>Cameras</span>
          <span style={{ fontSize: '.75rem', fontWeight: 700, color: 'var(--text-muted)' }}>{cameras.length} Total</span>
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

      {/* 2. Main Stage Video Player with Overlay (Centered exactly between equal sidebars) */}
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
            <button
              className="hud-pill green"
              style={{ pointerEvents: 'auto', cursor: 'pointer', background: 'rgba(5,150,105,0.25)' }}
              onClick={() => setStreamMode(streamMode === 'mjpeg' ? 'webrtc' : 'mjpeg')}
            >
              Feed: {streamMode.toUpperCase()}
            </button>
          </div>
        </div>
        <div className="stage-bottom">
          <div>
            Active: <strong>{activeCamera}</strong>
          </div>
          <div>
            Total Latency:{' '}
            <span style={{ color: 'var(--accent-blue)', fontWeight: 600 }}>
              {currentDets ? Math.round(totalLatMs) : '--'} ms
            </span>
          </div>
        </div>
      </div>

      {/* 3. Right Telemetry Sidebar */}
      <div className="demo-pane">
        <div className="demo-pane-head">
          <span>Telemetry</span>
          <button
            type="button"
            className={`tele-view-toggle ${showGraphs ? 'active' : ''}`}
            onClick={() => setShowGraphs((prev) => !prev)}
            title={showGraphs ? 'Switch to text values' : 'Switch to live graphs'}
            aria-label="Toggle Graph View"
          >
            {/* Feather Activity / Pulse Icon */}
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
            </svg>
          </button>
        </div>

        <div className="telemetry-body">
          {/* Performance Group */}
          <div className="tele-group">
            <div className="tele-group-header" onClick={() => toggleSection('performance')}>
              <div className="tele-label">Performance</div>
              <ChevronIcon open={openSections.performance} />
            </div>

            {openSections.performance && (
              <div className="tele-group-content">
                {!showGraphs ? (
                  <>
                    <div className="tele-row">
                      <span>Ingest FPS</span>
                      <span className="tele-val">{ingestFps.toFixed(1)}</span>
                    </div>
                    <div className="tele-row">
                      <span>AI Inference FPS</span>
                      <span className="tele-val green">{aiFps.toFixed(1)}</span>
                    </div>
                    <div className="tele-row">
                      <span>Inference Time</span>
                      <span className="tele-val">{inferMs.toFixed(1)} ms</span>
                    </div>
                    <div className="tele-row">
                      <span>Total Latency</span>
                      <span className="tele-val cyan">{totalLatMs.toFixed(1)} ms</span>
                    </div>
                  </>
                ) : (
                  <div className="tele-graph-wrap">
                    <div className="tele-graph-item">
                      <div className="tele-graph-label-row">
                        <span>Ingest FPS</span>
                        <span className="tele-val">{ingestFps.toFixed(1)}</span>
                      </div>
                      <Sparkline data={history.ingestFps} color="#059669" maxVal={30} />
                    </div>

                    <div className="tele-graph-item">
                      <div className="tele-graph-label-row">
                        <span>AI Inference FPS</span>
                        <span className="tele-val green">{aiFps.toFixed(1)}</span>
                      </div>
                      <Sparkline data={history.aiFps} color="#2563eb" maxVal={30} />
                    </div>

                    <div className="tele-graph-item">
                      <div className="tele-graph-label-row">
                        <span>Inference Time</span>
                        <span className="tele-val">{inferMs.toFixed(1)} ms</span>
                      </div>
                      <Sparkline data={history.inferMs} color="#d97706" maxVal={20} />
                    </div>

                    <div className="tele-graph-item">
                      <div className="tele-graph-label-row">
                        <span>Total Latency</span>
                        <span className="tele-val cyan">{totalLatMs.toFixed(1)} ms</span>
                      </div>
                      <Sparkline data={history.latencyMs} color="#0284c7" maxVal={60} />
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Hardware Utilization Group */}
          <div className="tele-group">
            <div className="tele-group-header" onClick={() => toggleSection('hardware')}>
              <div className="tele-label">Hardware Utilization</div>
              <ChevronIcon open={openSections.hardware} />
            </div>

            {openSections.hardware && (
              <div className="tele-group-content">
                {!showGraphs ? (
                  <>
                    <div className="tele-row">
                      <span>GPU Utilization</span>
                      <span className="tele-val">{gpuUtil}%</span>
                    </div>
                    <div className="tele-row">
                      <span>NVDEC Utilization</span>
                      <span className="tele-val green">{nvdecUtil}%</span>
                    </div>
                    <div className="tele-row">
                      <span>VRAM Memory</span>
                      <span className="tele-val">
                        {vramUsedGiB} / {vramTotalGiB} GiB
                      </span>
                    </div>
                  </>
                ) : (
                  <div className="tele-graph-wrap">
                    <div className="tele-graph-item">
                      <div className="tele-graph-label-row">
                        <span>GPU Utilization</span>
                        <span className="tele-val">{gpuUtil}%</span>
                      </div>
                      <Sparkline data={history.gpuUtil} color="#2563eb" maxVal={100} />
                    </div>

                    <div className="tele-graph-item">
                      <div className="tele-graph-label-row">
                        <span>NVDEC Utilization</span>
                        <span className="tele-val green">{nvdecUtil}%</span>
                      </div>
                      <Sparkline data={history.nvdecUtil} color="#059669" maxVal={100} />
                    </div>

                    <div className="tele-graph-item">
                      <div className="tele-graph-label-row">
                        <span>VRAM Memory</span>
                        <span className="tele-val">{vramUsedGiB} / {vramTotalGiB} GiB</span>
                      </div>
                      <Sparkline data={history.vramUsed} color="#0284c7" maxVal={parseFloat(vramTotalGiB) || 12} />
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Stream Information Group */}
          <div className="tele-group">
            <div className="tele-group-header" onClick={() => toggleSection('stream')}>
              <div className="tele-label">Stream Information</div>
              <ChevronIcon open={openSections.stream} />
            </div>

            {openSections.stream && (
              <div className="tele-group-content">
                <div className="tele-row">
                  <span>Resolution</span>
                  <span className="tele-val">
                    {currentDets?.width || 2304} x {currentDets?.height || 1296}
                  </span>
                </div>
                <div className="tele-row">
                  <span>Codec</span>
                  <span className="tele-val">
                    {camMetrics.codec || 'Unknown Codec'}
                  </span>
                </div>
                <div className="tele-row">
                  <span>Decoder</span>
                  <span className="tele-val">
                    {camMetrics.decoder_name || 'Unknown Decoder'}
                  </span>
                </div>
                <div className="tele-row">
                  <span>Frame Path</span>
                  <span className="tele-val">{camMetrics.frame_path || 'GPU_NATIVE'}</span>
                </div>
              </div>
            )}
          </div>

          {/* Active Detections & Tracks Group */}
          <div className="tele-group">
            <div className="tele-group-header" onClick={() => toggleSection('detections')}>
              <div className="tele-label">Active Detections ({activeDets.length})</div>
              <ChevronIcon open={openSections.detections} />
            </div>

            {openSections.detections && (
              <div className="tele-group-content">
                <div className="dets-box">
                  {activeDets.length === 0 ? (
                    <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '10px' }}>
                      Waiting for detections...
                    </div>
                  ) : (
                    activeDets.map((d, idx) => (
                      <div key={idx} className="det-row">
                        <span style={{ color: 'var(--accent-blue)', fontWeight: 600 }}>
                          {d.label} {d.track_id ? `[ID ${d.track_id.split(':').pop()}]` : ''}
                        </span>
                        <span style={{ color: 'var(--accent-emerald)' }}>{Math.round(d.confidence * 100)}%</span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
