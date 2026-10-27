import React, { useState, useEffect } from 'react';
import Navbar from './components/Navbar';
import StageView from './components/stage/StageView';
import GridView from './components/grid/GridView';
import Onboarding from './components/onboarding/Onboarding';
import SpatialRules from './components/spatial/SpatialRules';
import EventsView from './components/events/EventsView';
import { fetchCameras, fetchStatus } from './utils/api';
import './styles/theme.css';

export default function App() {
  const [activeTab, setActiveTab] = useState('demo');
  const [cameras, setCameras] = useState([]);
  const [selectedCam, setSelectedCam] = useState('CAM001');
  const [status, setStatus] = useState(null);
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('aivisra_theme') || 'light';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('aivisra_theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  };

  const loadCameras = () => {
    fetchCameras()
      .then((cams) => {
        setCameras(cams);
        if (cams.length > 0 && !selectedCam) {
          setSelectedCam(cams[0].camera_id);
        }
      })
      .catch(() => {});
  };

  useEffect(() => {
    loadCameras();
    fetchStatus().then(setStatus).catch(() => {});
  }, []);

  const handleSelectCameraFromGrid = (camId) => {
    setSelectedCam(camId);
    setActiveTab('demo');
  };

  return (
    <div className="app-container">
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        theme={theme}
        onToggleTheme={toggleTheme}
      />

      <main className="main-content">
        {activeTab === 'demo' && (
          <StageView
            cameras={cameras}
            selectedCam={selectedCam}
            setSelectedCam={setSelectedCam}
          />
        )}

        {activeTab === 'grid' && (
          <GridView
            cameras={cameras}
            onSelectCamera={handleSelectCameraFromGrid}
          />
        )}

        {activeTab === 'onboarding' && (
          <Onboarding
            cameras={cameras}
            onRefreshCameras={loadCameras}
          />
        )}

        {activeTab === 'spatial' && (
          <SpatialRules
            cameras={cameras}
          />
        )}

        {activeTab === 'events' && (
          <EventsView
            cameras={cameras}
          />
        )}
      </main>

      <footer>
        <span>AIVISRA</span>
        <span>Brainy Neurals - AI Software Company</span>
      </footer>
    </div>
  );
}
