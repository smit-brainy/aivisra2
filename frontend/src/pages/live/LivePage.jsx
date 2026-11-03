/**
 * LivePage — minimal live view screen.
 * Powered by window.INVR sample data; full verbatim port deferred (task list 2.2).
 * Provides Camera Picker access and basic live view scaffolding.
 */
import React from 'react';
import { fetchAreas, fetchCameras, getStreamUrl } from '../../utils/api';
import InetraCameraPicker from '../../components/inetra/InetraCameraPicker';

function LiveStream({ camera, showBoxes }) {
  const [attempt, setAttempt] = React.useState(0);
  const [failed, setFailed] = React.useState(false);
  const retryTimer = React.useRef(null);
  const streamUrl = `${getStreamUrl(camera.camera_id)}?inference=${showBoxes ? 'true' : 'false'}&retry=${attempt}`;

  React.useEffect(() => () => window.clearTimeout(retryTimer.current), []);
  const retry = () => {
    setFailed(true);
    window.clearTimeout(retryTimer.current);
    retryTimer.current = window.setTimeout(() => {
      setFailed(false);
      setAttempt(value => value + 1);
    }, 1500);
  };

  return <>{!failed && <img src={streamUrl} alt={camera.display_name || camera.camera_id} onError={retry} style={{ display: 'block', width: '100%', height: '100%', objectFit: 'contain', objectPosition: 'center', opacity: camera.online === false ? .45 : 1 }} />}<span style={{ position: 'absolute', inset: 0, display: failed ? 'grid' : 'none', placeItems: 'center', color: 'var(--muted-dark)', background: 'var(--ink)' }}>Reconnecting stream…</span></>;
}

export default function LivePage({ session, openSearch, navTo }) {
  const [cameras, setCameras] = React.useState([]);
  const [areas, setAreas] = React.useState([]);
  const [selection, setSelection] = React.useState({ mode: 'all' });
  const [layout, setLayout] = React.useState(16);
  const [showBoxes, setShowBoxes] = React.useState(true);
  const [fullScreen, setFullScreen] = React.useState(false);
  React.useEffect(() => {
    let disposed = false;
    Promise.all([fetchCameras(), fetchAreas()]).then(([loaded, loadedAreas]) => {
      if (disposed) return;
      setCameras(loaded);
      setAreas(loadedAreas);
    }).catch((error) => {
      // A temporary API failure must not erase the currently rendered camera
      // set. The next navigation/reload can retry without showing 0 cameras.
      console.warn('[LivePage] camera list refresh failed', error);
    });
    return () => { disposed = true; };
  }, []);
  const chosen = selection.mode === 'all' ? cameras : selection.mode === 'area' ? cameras.filter(c => c.area_id === selection.area) : cameras.filter(c => (selection.cams || []).includes(c.camera_id));
  const changeLayout = size => {
    setLayout(size);
    // The single-camera selector intentionally narrows the shared selection to
    // one camera. When moving back to a multi-camera layout, restore the full
    // camera set instead of rendering a one-tile grid.
    if (size > 1 && selection.mode === 'cams' && (selection.cams || []).length <= 1) {
      setSelection({ mode: 'all' });
    }
  };
  return (
    <div className="live-view-page" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', gap: 12, padding: fullScreen ? 16 : 24, background: 'var(--paper)', color: 'var(--ink)', ...(fullScreen ? { position: 'fixed', inset: 0, zIndex: 200, overflow: 'auto' } : {}) }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}><h1 style={{ margin: 0, fontSize: 28, fontWeight: 500 }}>Live view</h1><span style={{ padding: '8px 14px', borderRadius: 999, background: 'var(--ink)', color: 'var(--paper)', font: '500 12px var(--font-mono)', letterSpacing: '.08em' }}>● LIVE</span><div style={{ display: 'flex', gap: 6, marginLeft: 8, padding: 4, background: 'var(--bone)', borderRadius: 10 }}>{[1, 4, 9, 16].map(size => <button type="button" key={size} className="hvr-ink-border" onClick={() => changeLayout(size)} style={{ minWidth: 42, padding: '9px 11px', border: size === layout ? '2px solid var(--blue)' : '1px solid transparent', borderRadius: 8, background: size === layout ? 'var(--blue-tint)' : 'transparent' }}>{size}</button>)}</div><button type="button" className="hvr-ink-border" onClick={() => setShowBoxes(v => !v)} style={{ padding: '10px 16px', border: '1px solid var(--line)', borderRadius: 8, background: showBoxes ? 'var(--blue-tint)' : 'var(--paper)' }}>◉ {showBoxes ? 'Show boxes' : 'Hide boxes'}</button><button type="button" className="hvr-ink-border" onClick={() => setFullScreen(v => !v)} style={{ marginLeft: 'auto', padding: '10px 16px', border: '1px solid var(--line)', borderRadius: 8, background: 'var(--paper)' }}>{fullScreen ? 'Exit full screen' : 'Full screen'}</button><InetraCameraPicker
        defaultOpen={false}
        label="Cameras"
        cameras={cameras}
        areas={areas}
        value={selection}
        onChange={setSelection}
        onToggleOpen={() => {}}
      /></div>
      <div style={{ color: 'var(--muted)', fontSize: 14 }}>{chosen.length} camera{chosen.length === 1 ? '' : 's'} selected.</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 20, padding: '2px 0 8px', borderBottom: '1px solid var(--line-soft)', overflow: 'auto' }}><button type="button" className="hvr-ink-border" onClick={() => setSelection({ mode: 'all' })} style={{ padding: '12px 18px', border: '2px solid var(--blue)', borderRadius: 10, background: 'var(--blue-tint)', color: 'var(--blue-deep)', fontWeight: 600, whiteSpace: 'nowrap' }}>Every camera&nbsp; {cameras.length}</button>{areas.map(area => <button type="button" key={area.area_id} className="hvr-underline" onClick={() => setSelection({ mode: 'area', area: area.area_id })} style={{ border: 0, background: 'transparent', color: 'var(--muted)', fontSize: 15, whiteSpace: 'nowrap' }}>■ {area.name} <small>{cameras.filter(c => c.area_id === area.area_id).length}</small></button>)}</div>
      {layout === 1 && chosen[0] && <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', border: '1px solid var(--line)', borderRadius: 8, background: 'var(--bone)' }}><select aria-label="Select camera" value={chosen[0].camera_id} onChange={e => setSelection({ mode: 'cams', cams: [e.target.value] })} style={{ minWidth: 180, padding: '7px 10px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)', fontWeight: 600 }}>{cameras.map(camera => <option key={camera.camera_id} value={camera.camera_id}>{camera.display_name || camera.name || camera.camera_id} ({camera.camera_id})</option>)}</select><span style={{ color: 'var(--muted)', fontFamily: 'var(--font-mono)' }}>ID: {chosen[0].camera_id}</span></div>}
      <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.sqrt(layout)}, minmax(0, 1fr))`, gridTemplateRows: `repeat(${Math.sqrt(layout)}, minmax(0, 1fr))`, gap: 8, flex: 1, minHeight: 0, overflow: 'hidden' }}>{chosen.slice(0, layout).map((camera, index) => <div key={camera.camera_id} style={{ minWidth: 0, minHeight: 0, background: `linear-gradient(160deg, hsl(${210 + index * 19} 18% 28%), hsl(${210 + index * 19} 12% 8%))`, borderRadius: 6, overflow: 'hidden', position: 'relative', border: '1px solid var(--line-dark)' }}><LiveStream camera={camera} showBoxes={showBoxes} /><div style={{ position: 'absolute', inset: 'auto 0 0', padding: '26px 12px 10px', color: 'var(--paper)', background: 'linear-gradient(transparent, rgba(0,0,0,.85))' }}><strong style={{ fontSize: 15 }}>{camera.camera_id} &nbsp;{camera.display_name || camera.camera_id}</strong><span style={{ marginLeft: 8, fontSize: 12, color: camera.online === false ? 'var(--danger)' : 'var(--success)' }}>● {camera.status || 'online'}</span></div></div>)}</div>
    </div>
  );
}
