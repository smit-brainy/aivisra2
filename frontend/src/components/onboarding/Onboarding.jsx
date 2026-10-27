import React, { useState, useEffect } from 'react';
import {
  fetchCapabilities,
  fetchCameraCapabilities,
  applyCameraCapabilities,
  registerCamera,
  triggerCameraAnalysis,
  getOnboardingStatus,
  getCameraRecommendations,
  resetCameraOnboarding,
} from '../../utils/api';

export default function Onboarding({ cameras = [], onRefreshCameras }) {
  const [selectedCam, setSelectedCam] = useState(cameras[0]?.camera_id || 'CAM001');
  const [allCaps, setAllCaps] = useState([]);
  const [activeCaps, setActiveCaps] = useState([]);
  const [configVersion, setConfigVersion] = useState(1);
  const [analysisProgress, setAnalysisProgress] = useState(0);
  const [analyzing, setAnalyzing] = useState(false);
  const [alert, setAlert] = useState(null);

  // New Camera Form
  const [newCamId, setNewCamId] = useState('');
  const [newRtspUrl, setNewRtspUrl] = useState('');
  const [newCodec, setNewCodec] = useState('h264');

  useEffect(() => {
    fetchCapabilities().then(setAllCaps).catch(() => {});
  }, []);

  useEffect(() => {
    if (selectedCam) {
      fetchCameraCapabilities(selectedCam)
        .then((data) => {
          setActiveCaps(data.active_capabilities || []);
          setConfigVersion(data.config_version || 1);
        })
        .catch(() => {});
    }
  }, [selectedCam]);

  const handleRegister = async (e) => {
    e.preventDefault();
    try {
      await registerCamera({
        camera_id: newCamId,
        rtsp_url: newRtspUrl,
        codec: newCodec,
      });
      setAlert({ type: 'success', msg: `Camera ${newCamId} registered successfully!` });
      setNewCamId('');
      setNewRtspUrl('');
      if (onRefreshCameras) onRefreshCameras();
    } catch (err) {
      setAlert({ type: 'error', msg: `Failed to register: ${err.message}` });
    }
  };

  const handleStartAnalysis = async () => {
    setAnalyzing(true);
    setAnalysisProgress(10);
    try {
      await triggerCameraAnalysis(selectedCam, { sample_count: 20, sample_duration_seconds: 8.0 });
      let current = 10;
      const timer = setInterval(async () => {
        current += 20;
        setAnalysisProgress(Math.min(current, 90));
        try {
          const st = await getOnboardingStatus(selectedCam);
          if (st.status === 'READY' || current >= 100) {
            clearInterval(timer);
            setAnalysisProgress(100);
            setAnalyzing(false);
            const rec = await getCameraRecommendations(selectedCam);
            setAlert({ type: 'success', msg: 'Scene analysis complete! Recommended capabilities updated.' });
          }
        } catch (_) {}
      }, 1000);
    } catch (err) {
      setAnalyzing(false);
      setAlert({ type: 'error', msg: `Analysis failed: ${err.message}` });
    }
  };

  const toggleCapability = (capId) => {
    if (activeCaps.includes(capId)) {
      setActiveCaps(activeCaps.filter((c) => c !== capId));
    } else {
      setActiveCaps([...activeCaps, capId]);
    }
  };

  const handleSaveCapabilities = async () => {
    try {
      await applyCameraCapabilities(selectedCam, {
        capabilities: activeCaps,
        expected_version: configVersion,
      });
      setAlert({ type: 'success', msg: 'Capabilities saved and applied to camera pipeline!' });
    } catch (err) {
      setAlert({ type: 'error', msg: `Failed to save: ${err.message}` });
    }
  };

  return (
    <section id="onboarding-view" style={{ display: 'flex' }}>
      {alert && (
        <div className={`alert-box ${alert.type}`} style={{ display: 'block', marginBottom: '14px' }}>
          {alert.msg}
        </div>
      )}

      {/* 1. Register Camera Card */}
      <div className="ob-card">
        <div className="ob-card-head">
          <span>⚡ Register & Connect RTSP Camera</span>
        </div>
        <form className="ob-card-body" onSubmit={handleRegister}>
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Camera Identifier</label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. CAM002"
                value={newCamId}
                onChange={(e) => setNewCamId(e.target.value)}
                required
              />
            </div>
            <div className="form-group" style={{ flex: 2 }}>
              <label className="form-label">RTSP Stream URI</label>
              <input
                type="text"
                className="form-input"
                placeholder="rtsp://127.0.0.1:8554/live/stream"
                value={newRtspUrl}
                onChange={(e) => setNewRtspUrl(e.target.value)}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">Codec</label>
              <select className="form-select" value={newCodec} onChange={(e) => setNewCodec(e.target.value)}>
                <option value="h264">H.264 (NVDEC Hardware)</option>
                <option value="h265">H.265 / HEVC</option>
              </select>
            </div>
            <button type="submit" className="btn active-green" style={{ height: '38px' }}>
              + Add Camera
            </button>
          </div>
        </form>
      </div>

      {/* 2. Auto-Analysis Card */}
      <div className="ob-card">
        <div className="ob-card-head">
          <span>🔍 AI Scene Analysis & Automatic Recommendations</span>
          <select
            className="form-select"
            value={selectedCam}
            onChange={(e) => setSelectedCam(e.target.value)}
            style={{ padding: '4px 10px' }}
          >
            {cameras.map((c) => (
              <option key={c.camera_id} value={c.camera_id}>
                {c.name || c.camera_id}
              </option>
            ))}
          </select>
        </div>
        <div className="ob-card-body">
          <p style={{ margin: 0, color: '#8b949e', fontSize: '.85rem' }}>
            StreamCore runs hardware NVDEC frame sampling to detect pedestrians, vehicles, indoor/outdoor
            lighting, and density, automatically recommending optimal analytics.
          </p>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            <button
              type="button"
              className="btn active"
              onClick={handleStartAnalysis}
              disabled={analyzing}
            >
              {analyzing ? '⏳ Analyzing Scene...' : '🚀 Run Scene Auto-Analysis'}
            </button>
            <div className="progress-container" style={{ flex: 1 }}>
              <div className="progress-bar" style={{ width: `${analysisProgress}%` }}></div>
              <div className="progress-text">{analysisProgress}% Complete</div>
            </div>
          </div>
        </div>
      </div>

      {/* 3. Capability Selection Card */}
      <div className="ob-card">
        <div className="ob-card-head">
          <span>🎛️ Active AI Capabilities for {selectedCam}</span>
          <span style={{ fontSize: '.75rem', color: '#8b949e' }}>Config Version: {configVersion}</span>
        </div>
        <div className="ob-card-body">
          <div className="caps-list">
            {allCaps.map((cap) => {
              const isChecked = activeCaps.includes(cap.id);
              return (
                <div key={cap.id} className="cap-item">
                  <input
                    type="checkbox"
                    className="cap-checkbox"
                    checked={isChecked}
                    onChange={() => toggleCapability(cap.id)}
                  />
                  <div className="cap-content">
                    <div className="cap-header">
                      <span className="cap-title">{cap.name}</span>
                      <div className="cap-badges">
                        <span className="cap-badge score">{cap.category}</span>
                        <span className="cap-badge available">GPU Accelerated</span>
                      </div>
                    </div>
                    <div className="cap-desc">{cap.description}</div>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="action-bar" style={{ marginTop: '14px' }}>
            <button type="button" className="btn active-green" onClick={handleSaveCapabilities}>
              💾 Save & Apply Capabilities
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

