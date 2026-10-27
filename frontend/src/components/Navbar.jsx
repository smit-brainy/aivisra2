import React from 'react';

export default function Navbar({ activeTab, setActiveTab, mode = 'Production AI' }) {
  return (
    <>
      <header>
        <div>
          <h1>
            AIVISRA StreamCore <span className="badge-tag">Stage 4: GPU-Native AI</span>
          </h1>
          <p className="subtitle">
            End-to-End GPU Decode (NVDEC) → CUDA Preprocess (FP16) → Batched YOLO11 Inference · Zero CPU Copy
          </p>
        </div>
        <div id="runtime-mode-badge" style={{ fontSize: '.85rem', color: '#79c0ff', fontWeight: 600 }}>
          Mode: {mode}
        </div>
      </header>

      <div className="toggle-bar">
        <span className="toggle-title">System Console:</span>
        <button
          className={`btn ${activeTab === 'demo' ? 'active-green' : ''}`}
          onClick={() => setActiveTab('demo')}
        >
          🎯 Single-Camera Focus (Full Stage)
        </button>
        <button
          className={`btn ${activeTab === 'grid' ? 'active-green' : ''}`}
          onClick={() => setActiveTab('grid')}
        >
          🤖 Multi-Grid Overview (All Cameras)
        </button>
        <button
          className={`btn ${activeTab === 'onboarding' ? 'active-green' : ''}`}
          onClick={() => setActiveTab('onboarding')}
        >
          ⚡ Smart Camera Onboarding & AI
        </button>
        <button
          className={`btn ${activeTab === 'spatial' ? 'active-green' : ''}`}
          onClick={() => setActiveTab('spatial')}
        >
          📐 Spatial Intelligence & Rules
        </button>
        <button
          className={`btn ${activeTab === 'events' ? 'active-green' : ''}`}
          onClick={() => setActiveTab('events')}
        >
          🧠 AI Visual Search & Clips
        </button>
      </div>
    </>
  );
}

