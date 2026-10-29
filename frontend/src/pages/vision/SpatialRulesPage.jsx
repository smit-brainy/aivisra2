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
    const loadSpatialData = () => {
      fetchZones(selectedCam).then((d) => setZones(d.zones || [])).catch(() => {});
      fetchLines(selectedCam).then((d) => setLines(d.lines || [])).catch(() => {});
      fetchRules(selectedCam).then((d) => setRules(d.rules || [])).catch(() => {});
      fetchOccupancy(selectedCam).then(setOccupancy).catch(() => {});
      fetchActiveSpatialEvents(selectedCam).then((d) => setEvents(d.events || [])).catch(() => {});
    };

    loadSpatialData();
    const interval = setInterval(loadSpatialData, 2000);
    return () => clearInterval(interval);
  }, [selectedCam]);

  // Draw zones and lines on top of canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const rect = canvas.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) {
      canvas.width = rect.width;
      canvas.height = rect.height;
    }

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const parsePoint = (pt) => {
      if (!pt) return [0, 0];
      if (Array.isArray(pt)) return [Number(pt[0]) || 0, Number(pt[1]) || 0];
      if (typeof pt === 'object') return [Number(pt.x) || 0, Number(pt.y) || 0];
      return [0, 0];
    };

    // Draw saved zones
    for (const z of zones) {
      if (!z.polygon || z.polygon.length < 3) continue;
      ctx.beginPath();
      for (let i = 0; i < z.polygon.length; i++) {
        const [nx, ny] = parsePoint(z.polygon[i]);
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
      const [lx, ly] = parsePoint(z.polygon[0]);
      ctx.fillStyle = '#3fb950';
      ctx.font = 'bold 12px sans-serif';
      ctx.fillText(z.name || 'Zone', lx * canvas.width + 4, ly * canvas.height + 14);
    }

    // Draw saved lines
    for (const l of lines) {
      if (!l.line || l.line.length < 2) continue;
      const p1 = parsePoint(l.line[0]);
      const p2 = parsePoint(l.line[1]);
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
        const [nx, ny] = parsePoint(points[i]);
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
      const newLineId = `line_${Date.now()}`;
      const newLine = {
        line_id: newLineId,
        name: `Tripwire ${lines.length + 1}`,
        point_a: { x: newPts[0][0], y: newPts[0][1] },
        point_b: { x: newPts[1][0], y: newPts[1][1] },
        direction: 'BIDIRECTIONAL',
        applicable_classes: ['person'],
        enabled: true,
      };
      const updated = [...lines, newLine];
      setLines(updated);
      setPoints([]);
      setTool('none');
      updateLines(selectedCam, updated).catch(() => {});
    } else if (tool === 'zone' && newPts.length >= 4) {
      const newZoneId = `zone_${Date.now()}`;
      const newZone = {
        zone_id: newZoneId,
        name: `Zone ${zones.length + 1}`,
        polygon: newPts.map((p) => ({ x: p[0], y: p[1] })),
        applicable_classes: ['person'],
        enabled: true,
      };
      const updated = [...zones, newZone];
      setZones(updated);
      setPoints([]);
      setTool('none');
      updateZones(selectedCam, updated).then(() => {
        // Automatically ensure an active alert rule exists for this zone
        const autoRule = {
          rule_id: `rule_enter_${newZoneId}`,
          name: `${newZone.name} Intrusion Alert`,
          rule_type: 'ZONE_ENTER',
          target_geometry_id: newZoneId,
          object_classes: ['person'],
          severity: 'CRITICAL',
          enabled: true,
          cooldown_seconds: 5,
        };
        const updatedRules = [...rules.filter((r) => r.rule_id !== autoRule.rule_id), autoRule];
        setRules(updatedRules);
        updateRules(selectedCam, updatedRules).catch(() => {});
      }).catch(() => {});
    } else {
      setPoints(newPts);
    }
  };

  return (
    <section id="spatial-view" style={{ display: 'grid' }}>
      {/* 1. Spatial Configuration Tools */}
      <div className="sp-card">
        <div className="sp-card-head">
          <span>Spatial Elements</span>
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
              Draw Zone (4 pts)
            </button>
            <button
              className={`sp-tool-btn ${tool === 'line' ? 'active' : ''}`}
              style={{ flex: 1 }}
              onClick={() => {
                setTool(tool === 'line' ? 'none' : 'line');
                setPoints([]);
              }}
            >
              Draw Line (2 pts)
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
      <div className="sp-card" style={{ display: 'flex', flexDirection: 'column' }}>
        <div className="sp-card-head">
          <span>Interactive Spatial Stage</span>
          <span style={{ fontSize: '.78rem', color: '#8b949e' }}>
            {tool !== 'none' ? `Click stage to place ${tool} points (${points.length})` : 'Stage Ready'}
          </span>
        </div>
        <div className="stage-video-box" style={{ position: 'relative', width: '100%', aspectRatio: '16 / 9', background: '#020617' }}>
          <img
            src={getStreamUrl(selectedCam)}
            alt="Spatial Feed"
            style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
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
          <span>Flow Occupancy</span>
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

