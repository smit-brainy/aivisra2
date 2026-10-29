import React, { useState, useEffect } from 'react';
import Navbar from './components/Navbar';
import LiveDemo from './pages/demo/LiveDemo';
import CameraGridPage from './pages/demo/CameraGridPage';
import OnboardingPage from './pages/setup/OnboardingPage';
import SpatialRulesPage from './pages/vision/SpatialRulesPage';
import EventsPage from './pages/vision/EventsPage';
import IIntraPrototype from './pages/inetra/IIntraPrototype';
import { fetchCameras, fetchStatus } from './utils/api';
import './styles/fonts.css';
import './styles/foundations.css';
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
          <LiveDemo
            cameras={cameras}
            selectedCam={selectedCam}
            setSelectedCam={setSelectedCam}
          />
        )}

        {activeTab === 'grid' && (
          <CameraGridPage
            cameras={cameras}
            onSelectCamera={handleSelectCameraFromGrid}
          />
        )}

        {activeTab === 'onboarding' && (
          <OnboardingPage
            cameras={cameras}
            onRefreshCameras={loadCameras}
          />
        )}

        {activeTab === 'spatial' && (
          <SpatialRulesPage
            cameras={cameras}
          />
        )}

        {activeTab === 'events' && (
          <EventsPage
            cameras={cameras}
          />
        )}

        {activeTab === 'inetra' && (
          <IIntraPrototype />
        )}
      </main>

      <footer>
        <span>AIVISRA</span>
        <span>Brainy Neurals - AI Software Company</span>
      </footer>
    </div>
  );
}
