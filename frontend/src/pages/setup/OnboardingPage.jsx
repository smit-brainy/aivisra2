import React, { useState, useEffect } from 'react';
import {
  fetchCapabilities,
  fetchCameraCapabilities,
  applyCameraCapabilities,
  registerCamera,
  triggerCameraAnalysis,
  getOnboardingStatus,
  getCameraRecommendations,
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

  // Group capabilities by category
  const categories = Array.from(new Set(allCaps.map((c) => c.category || 'General')));

  return (
    <section id="onboarding-view">
      {alert && (
        <div className={`alert-box ${alert.type}`}>
          {alert.msg}
        </div>
      )}

      {/* 1. Register Camera Card */}
      <div className="ob-card">
        <div className="ob-card-head">
          <span className="ob-card-title">Register New Camera</span>
        </div>
        <form className="ob-card-body" onSubmit={handleRegister}>
          <div className="form-grid">
            <div className="form-group">
              <label className="form-label">Camera ID</label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. CAM002"
                value={newCamId}
                onChange={(e) => setNewCamId(e.target.value)}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">RTSP Stream URI</label>
              <input
                type="text"
                className="form-input"
                placeholder="rtsp://192.168.1.55/stream1"
                value={newRtspUrl}
                onChange={(e) => setNewRtspUrl(e.target.value)}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">Video Codec</label>
              <select className="form-select" value={newCodec} onChange={(e) => setNewCodec(e.target.value)}>
                <option value="h264">H.264 (Hardware NVDEC)</option>
                <option value="h265">H.265 / HEVC</option>
              </select>
            </div>
            <button type="submit" className="btn active-green" style={{ height: '38px', minWidth: '120px' }}>
              Add Camera
            </button>
          </div>
        </form>
      </div>

      {/* 2. Scene Auto-Analysis Card */}
      <div className="ob-card">
        <div className="ob-card-head">
          <span className="ob-card-title">AI Scene Analysis</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span className="form-label" style={{ margin: 0 }}>Target Camera:</span>
            <select
              className="form-select"
              value={selectedCam}
              onChange={(e) => setSelectedCam(e.target.value)}
              style={{ padding: '5px 10px', fontSize: '0.82rem' }}
            >
              {cameras.map((c) => (
                <option key={c.camera_id} value={c.camera_id}>
                  {c.name || c.camera_id}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="ob-card-body">
          <p className="ob-section-desc">
            Hardware NVDEC automatically samples video frames to detect density, pedestrians, vehicles, and
            lighting conditions, generating tailored analytics recommendations.
          </p>

          <div className="analysis-action-box">
            <button
              type="button"
              className="btn btn-blue"
              onClick={handleStartAnalysis}
              disabled={analyzing}
              style={{ minWidth: '180px' }}
            >
              {analyzing ? 'Analyzing Stream...' : 'Run Scene Auto-Analysis'}
            </button>

            <div className="progress-container">
              <div className="progress-bar" style={{ width: `${analysisProgress}%` }}></div>
              <div className="progress-text">{analysisProgress}% Complete</div>
            </div>
          </div>
        </div>
      </div>

      {/* 3. Capability Selection Card */}
      <div className="ob-card">
        <div className="ob-card-head">
          <span className="ob-card-title">Camera AI Capabilities</span>
          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            Selected: <strong style={{ color: 'var(--text-primary)' }}>{selectedCam}</strong> · Config v{configVersion}
          </span>
        </div>

        <div className="ob-card-body">
          {categories.map((category) => {
            const categoryCaps = allCaps.filter((c) => (c.category || 'General') === category);
            if (categoryCaps.length === 0) return null;

            return (
              <div key={category} className="caps-category-group">
                <div className="caps-category-title">{category}</div>
                <div className="caps-grid">
                  {categoryCaps.map((cap) => {
                    const isChecked = activeCaps.includes(cap.id);
                    const isImplemented = cap.implementation_status !== 'NOT_IMPLEMENTED';

                    return (
                      <div
                        key={cap.id}
                        className={`cap-card ${isChecked ? 'active' : ''} ${!isImplemented ? 'disabled' : ''}`}
                        onClick={() => isImplemented && toggleCapability(cap.id)}
                      >
                        <input
                          type="checkbox"
                          className="cap-checkbox"
                          checked={isChecked}
                          disabled={!isImplemented}
                          onChange={() => {}}
                        />
                        <div className="cap-content">
                          <div className="cap-header">
                            <span className="cap-title">{cap.display_name || cap.name || cap.id}</span>
                            <div className="cap-badges">
                              <span
                                className={`cap-badge ${
                                  isImplemented ? 'available' : 'not-implemented'
                                }`}
                              >
                                {isImplemented ? 'Available' : 'Coming Soon'}
                              </span>
                            </div>
                          </div>
                          <div className="cap-desc">{cap.description}</div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}

          <div className="ob-footer-bar">
            <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
              {activeCaps.length} active capabilities enabled for {selectedCam}
            </span>
            <button
              type="button"
              className="btn active-green"
              onClick={handleSaveCapabilities}
              style={{ minWidth: '160px' }}
            >
              Save Capabilities
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
