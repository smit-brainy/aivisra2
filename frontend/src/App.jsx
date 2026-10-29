import React, { useState, useEffect } from 'react';
import Navbar from './components/Navbar';
import LiveDemo from './pages/demo/LiveDemo';
import CameraGridPage from './pages/demo/CameraGridPage';
import OnboardingPage from './pages/setup/OnboardingPage';
import SpatialRulesPage from './pages/vision/SpatialRulesPage';
import EventsPage from './pages/vision/EventsPage';
import IIntraPrototype from './pages/inetra/IIntraPrototype';
import SignInPage from './pages/auth/SignInPage';
import InetraShell from './components/inetra/InetraShell';
import InetraPlaceholder from './components/inetra/InetraPlaceholder';
import HomePage from './pages/home/HomePage';
import './prototype/invr-data';
import { fetchCameras, fetchStatus } from './utils/api';
import './styles/fonts.css';
import './styles/foundations.css';
import './styles/buttons.css';
import './styles/theme.css';

export default function App() {
  const [activeTab, setActiveTab] = useState('inetra');
  const [cameras, setCameras] = useState([]);
  const [selectedCam, setSelectedCam] = useState('CAM001');
  const [status, setStatus] = useState(null);
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('aivisra_theme') || 'light';
  });
  // Ported i-Netra auth (prototype sample users; any non-empty password works)
  const [session, setSession] = useState(() => {
    try { return JSON.parse(localStorage.getItem('aivisra_session')); } catch (e) { return null; }
  });

  const handleSignedIn = (user) => {
    setSession(user);
    localStorage.setItem('aivisra_session', JSON.stringify(user));
  };

  const handleSignOut = () => {
    setSession(null);
    localStorage.removeItem('aivisra_session');
  };

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

  // Auth gate (i-Netra flow: sign in → set own password → app)
  if (!session) {
    return (
      <div style={{ position: 'fixed', inset: 0 }}>
        <SignInPage onSignedIn={handleSignedIn} />
      </div>
    );
  }

  // Signed in → verbatim i-Netra shell. The legacy AIVISRA shell (Navbar +
  // tabs) stays for `screen === 'legacy'` until all screens are ported.
  if (session && session.screen !== 'legacy') {
    const INVR = (typeof window !== 'undefined' && window.INVR) || null;
    const meta = (INVR && INVR.users && INVR.users[session.who || session.role]) || null;
    const sess = { ...session, meta };
    const screen = session.screen || 'home';
    const iNetraScreens = ['home', 'live', 'search', 'cameras', 'settings'];
    if (iNetraScreens.includes(screen)) {
      // Verbatim controller semantics: openSearch(opts)/navTo(t, opts) set the
      // session screen and stash pending options for the target screen.
      const go = (t, opts) => {
        const next = { ...session, screen: t === 'addcams' ? 'cameras' : t === 'denied' ? 'settings' : t };
        if (t === 'search') next.searchOpts = opts || {};
        try { sessionStorage.setItem('aivisra_inetra_opts', JSON.stringify({ opts: opts || {}, to: next.screen })); } catch (x) {}
        handleSignedIn(next);
      };
      const camSummary = !INVR ? 'No cameras yet' : (() => {
        const M = INVR.merge({}, 'day');
        const off = M.cams.filter(c => c.status === 'offline');
        return `${M.cams.length - off.length} of ${M.cams.length} cameras online`;
      })();
      return (
        <InetraShell
          session={sess}
          screen={screen}
          onSignOut={handleSignOut}
          onNav={(k, opts) => go(k, opts)}
          camSummary={camSummary}
          camDot={INVR ? (INVR.SCEN.day.offline[16] != null ? 'var(--danger)' : 'var(--success)') : 'var(--paper-3)'}
        >
          <main style={{ gridColumn: 2, gridRow: 2, position: 'relative', minWidth: 0, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            {screen === 'home' ? (
              <HomePage
                session={sess}
                openSearch={(o) => go('search', o)}
                navTo={(t, o) => go(t, o)}
              />
            ) : (
              <InetraPlaceholder
                title={{ home: 'Home', live: 'Live view', search: 'Search', cameras: 'Cameras', settings: 'Settings' }[screen]}
                onOpenPrototype={() => handleSignedIn({ ...session, screen: 'prototype' })}
              />
            )}
          </main>
        </InetraShell>
      );
    }
  }

  return (
    <div className="app-container">
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        theme={theme}
        onToggleTheme={toggleTheme}
        session={session}
        onSignOut={handleSignOut}
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
