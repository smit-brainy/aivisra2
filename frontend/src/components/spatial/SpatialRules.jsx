import React, { useState, useEffect, useRef } from 'react';
import {
  fetchZones,
  updateZones,
  fetchLines,
  updateLines,
  fetchRules,
  updateRules,
  fetchOccupancy,
  fetchActiveSpatialEvents,
  getStreamUrl,
  getFrameUrl,
} from '../../utils/api';

export default function SpatialRules({ cameras = [] }) {
  const [selectedCam, setSelectedCam] = useState(cameras[0]?.camera_id || 'CAM001');
  const [zones, setZones] = useState([]);
  const [lines, setLines] = useState([]);
  const [rules, setRules] = useState([]);
  const [occupancy, setOccupancy] = useState(null);
  const [events, setEvents] = useState([]);
  const [tool, setTool] = useState('none'); // 'zone', 'line', 'none'
  const [points, setPoints] = useState([]);
  const canvasRef = useRef(null);

  useEffect(() => {
    if (!selectedCam) return;
    fetchZones(selectedCam).then((d) => setZones(d.zones || [])).catch(() => {});
    fetchLines(selectedCam).then((d) => setLines(d.lines || [])).catch(() => {});
    fetchRules(selectedCam).then((d) => setRules(d.rules || [])).catch(() => {});
    fetchOccupancy(selectedCam).then(setOccupancy).catch(() => {});
    fetchActiveSpatialEvents(selectedCam).then((d) => setEvents(d.events || [])).catch(() => {});
  }, [selectedCam]);

  // Draw zones and lines on top of canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width;
    canvas.height = rect.height;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw saved zones
    for (const z of zones) {
      if (!z.polygon || z.polygon.length < 3) continue;
      ctx.beginPath();
      for (let i = 0; i < z.polygon.length; i++) {
        const [nx, ny] = z.polygon[i];
        const x = nx * canvas.width;
        const y = ny * canvas.height;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.fillStyle = 'rgba(35, 134, 54, 0.2)';
      ctx.fill();
      ctx.lineWidth = 2;
      ctx.strokeStyle = '#3fb950';
      ctx.stroke();

      // Label
      const [lx, ly] = z.polygon[0];
      ctx.fillStyle = '#3fb950';
      ctx.font = 'bold 12px sans-serif';
      ctx.fillText(z.name || 'Zone', lx * canvas.width + 4, ly * canvas.height + 14);
    }

    // Draw saved lines
    for (const l of lines) {
      if (!l.line || l.line.length < 2) continue;
      const [p1, p2] = l.line;
      ctx.beginPath();
      ctx.moveTo(p1[0] * canvas.width, p1[1] * canvas.height);
      ctx.lineTo(p2[0] * canvas.width, p2[1] * canvas.height);
      ctx.lineWidth = 3;
      ctx.strokeStyle = '#58a6ff';
      ctx.stroke();

      ctx.fillStyle = '#58a6ff';
      ctx.font = 'bold 12px sans-serif';
      ctx.fillText(l.name || 'Tripwire', p1[0] * canvas.width + 4, p1[1] * canvas.height - 4);
    }

    // Draw active drawing points
    if (points.length > 0) {
      ctx.beginPath();
      for (let i = 0; i < points.length; i++) {
        const [nx, ny] = points[i];
        const x = nx * canvas.width;
        const y = ny * canvas.height;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.lineWidth = 2;
      ctx.strokeStyle = '#f85149';
      ctx.stroke();
    }
  }, [zones, lines, points]);

  const handleCanvasClick = (e) => {
    if (tool === 'none') return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const nx = (e.clientX - rect.left) / rect.width;
    const ny = (e.clientY - rect.top) / rect.height;

    const newPts = [...points, [nx, ny]];
    if (tool === 'line' && newPts.length === 2) {
      const newLine = {
        name: `Tripwire ${lines.length + 1}`,
        line: newPts,
        direction: 'BIDIRECTIONAL',
      };
      const updated = [...lines, newLine];
      setLines(updated);
      setPoints([]);
      setTool('none');
      updateLines(selectedCam, updated, 1).catch(() => {});
    } else if (tool === 'zone' && newPts.length >= 4) {
      const newZone = {
        name: `Zone ${zones.length + 1}`,
        polygon: newPts,
      };
      const updated = [...zones, newZone];
      setZones(updated);
      setPoints([]);
      setTool('none');
      updateZones(selectedCam, updated, 1).catch(() => {});
    } else {
      setPoints(newPts);
    }
  };

  return (
    <section id="spatial-view" style={{ display: 'grid' }}>
      {/* 1. Spatial Configuration Tools */}
      <div className="sp-card">
        <div className="sp-card-head">
          <span>📐 Spatial Elements</span>
          <select
            className="form-select"
            value={selectedCam}
            onChange={(e) => setSelectedCam(e.target.value)}
            style={{ padding: '3px 8px' }}
          >
            {cameras.map((c) => (
              <option key={c.camera_id} value={c.camera_id}>
                {c.name || c.camera_id}
              </option>
            ))}
          </select>
        </div>
        <div className="sp-body">
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              className={`sp-tool-btn ${tool === 'zone' ? 'active' : ''}`}
              style={{ flex: 1 }}
              onClick={() => {
                setTool(tool === 'zone' ? 'none' : 'zone');
                setPoints([]);
              }}
            >
              🟩 Draw Zone (4 pts)
            </button>
            <button
              className={`sp-tool-btn ${tool === 'line' ? 'active' : ''}`}
              style={{ flex: 1 }}
              onClick={() => {
                setTool(tool === 'line' ? 'none' : 'line');
                setPoints([]);
              }}
            >
              📏 Draw Line (2 pts)
            </button>
          </div>

          <div className="tele-label" style={{ marginTop: '10px' }}>Active Zones ({zones.length})</div>
          {zones.map((z, idx) => (
            <div key={idx} className="sp-list-item">
              <span style={{ color: '#3fb950', fontWeight: 600 }}>{z.name}</span>
              <span className="sp-badge info">POLYGON</span>
            </div>
          ))}

          <div className="tele-label" style={{ marginTop: '10px' }}>Tripwire Lines ({lines.length})</div>
          {lines.map((l, idx) => (
            <div key={idx} className="sp-list-item">
              <span style={{ color: '#58a6ff', fontWeight: 600 }}>{l.name}</span>
              <span className="sp-badge info">{l.direction}</span>
            </div>
          ))}
        </div>
      </div>

      {/* 2. Interactive Canvas Overlay */}
      <div className="sp-card" style={{ position: 'relative' }}>
        <div className="sp-card-head">
          <span>Interactive Spatial Stage</span>
          <span style={{ fontSize: '.78rem', color: '#8b949e' }}>
            {tool !== 'none' ? `Click stage to place ${tool} points (${points.length})` : 'Stage Ready'}
          </span>
        </div>
        <div style={{ position: 'relative', width: '100%', height: '100%', background: '#000' }}>
          <img
            src={getStreamUrl(selectedCam)}
            alt="Spatial Feed"
            style={{ width: '100%', height: '100%', objectFit: 'contain' }}
            onError={(e) => {
              e.target.src = getFrameUrl(selectedCam);
            }}
          />
          <canvas
            ref={canvasRef}
            className="sp-canvas"
            onClick={handleCanvasClick}
          ></canvas>
        </div>
      </div>

      {/* 3. Occupancy & Spatial Events */}
      <div className="sp-card">
        <div className="sp-card-head">
          <span>👥 Flow Occupancy</span>
          <span className="badge badge-gpu">{occupancy?.visible_occupancy || 0} Persons</span>
        </div>
        <div className="sp-body">
          <div className="tele-row">
            <span>Visible Occupancy:</span>
            <span className="tele-val green">{occupancy?.visible_occupancy || 0}</span>
          </div>
          <div className="tele-row">
            <span>Flow Occupancy:</span>
            <span className="tele-val cyan">{occupancy?.flow_occupancy || 0}</span>
          </div>
          <div className="tele-row">
            <span>Total In / Out:</span>
            <span className="tele-val">
              +{occupancy?.total_in || 0} / -{occupancy?.total_out || 0}
            </span>
          </div>

          <div className="tele-label" style={{ marginTop: '14px' }}>Active Events ({events.length})</div>
          {events.length === 0 ? (
            <div style={{ color: '#8b949e', textAlign: 'center', padding: '20px' }}>
              No active spatial rule breaches
            </div>
          ) : (
            events.map((e, idx) => (
              <div key={idx} className="sp-event-item">
                <div className="sp-event-top">
                  <span style={{ color: '#f85149', fontWeight: 700 }}>{e.rule_name || 'ALERT'}</span>
                  <span>{e.severity || 'CRITICAL'}</span>
                </div>
                <div className="sp-event-desc">{e.summary || 'Rule triggered'}</div>
              </div>
            ))
          )}
        </div>
      </div>
    </section>
  );
}

