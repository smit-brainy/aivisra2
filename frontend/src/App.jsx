import React, { useState, useEffect } from 'react';
import Navbar from './components/Navbar';
import LiveDemo from './pages/demo/LiveDemo';
import CameraGridPage from './pages/demo/CameraGridPage';
import OnboardingPage from './pages/setup/OnboardingPage';
import SpatialRulesPage from './pages/vision/SpatialRulesPage';
import EventsPage from './pages/vision/EventsPage';
import LivePage from './pages/live/LivePage';
import CamerasPage from './pages/cameras/CamerasPage';
import SearchPage from './pages/search/SearchPage';
import SignInPage from './pages/auth/SignInPage';
import InetraShell from './components/inetra/InetraShell';
import InetraPlaceholder from './components/inetra/InetraPlaceholder';
import HomePage from './pages/home/HomePage';
import './prototype/invr-data';
import { fetchCameras, fetchStatus } from './utils/api';

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
        if (cameras.length > 0 && !selectedCam) {
          setSelectedCam(cameras[0].camera_id);
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

  // Signed in → verbatim i-Netra shell.
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
      // Render the appropriate verbatim screen.
      if (screen === 'home') {
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
              <HomePage
                session={sess}
                openSearch={(o) => go('search', o)}
                navTo={(t, o) => go(t, o)}
              />
            </main>
          </InetraShell>
        );
      }
      if (screen === 'live') {
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
              <LivePage
                session={sess}
                openSearch={(o) => go('search', o)}
                navTo={(t, o) => go(t, o)}
              />
            </main>
          </InetraShell>
        );
      }
      if (screen === 'search') {
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
              <SearchPage
                openSearch={(o) => go('search', o)}
                navTo={(t, o) => go(t, o)}
              />
            </main>
          </InetraShell>
        );
      }
      // Fallback: placeholder for cameras/settings
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
            <InetraPlaceholder
              title={{ home: 'Home', live: 'Live view', search: 'Search', cameras: 'Cameras', settings: 'Settings' }[screen]}
              onOpenPrototype={() => handleSignedIn({ ...session, screen: 'prototype' })}
            />
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

        {activeTab === 'vision' && (
          <SpatialRulesPage
            cameras={cameras}
          />
        )}

        {activeTab === 'events' && (
          <EventsPage
            cameras={cameras}
          />
        )}
      </main>
    </div>
  );
}
