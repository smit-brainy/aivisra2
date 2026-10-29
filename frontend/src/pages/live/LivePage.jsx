/**
 * LivePage — minimal live view screen.
 * Powered by window.INVR sample data; full verbatim port deferred (task list 2.2).
 * Provides Camera Picker access and basic live view scaffolding.
 */
import React from 'react';
import { fetchAreas, fetchCameras, getFrameUrl } from '../../utils/api';
import { invr } from '../../prototype/api';
import InetraCameraPicker from '../../components/inetra/InetraCameraPicker';

export default function LivePage({ session, openSearch, navTo }) {
  const fallback = React.useMemo(() => Array.from({ length: 16 }, (_, i) => ({ camera_id: String(i + 1), display_name: ['Main gate entry', 'Main gate exit', 'Lobby corridor', 'Reception', 'Visitor parking', 'Staff parking', 'Dock 1', 'Dock 2', 'Stores', 'Line A', 'Line B', 'Packing', 'Back gate', 'Stairwell 2', 'Server room door', 'North fence'][i], area_id: ['gates', 'office', 'office', 'office', 'parking', 'parking', 'warehouse', 'warehouse', 'warehouse', 'production', 'production', 'production', 'gates', 'office', 'office', 'gates'][i], online: i !== 15, status: i === 15 ? 'offline' : 'online' })), []);
  const [cameras, setCameras] = React.useState([]);
  const [areas, setAreas] = React.useState([]);
  const [selection, setSelection] = React.useState({ mode: 'all' });
  const [layout, setLayout] = React.useState(16);
  const [showBoxes, setShowBoxes] = React.useState(true);
  const [showEvents, setShowEvents] = React.useState(false);
  const [fullScreen, setFullScreen] = React.useState(false);
  React.useEffect(() => {
    Promise.all([fetchCameras(), fetchAreas()]).then(([loaded, loadedAreas]) => {
      if (loaded.length) { setCameras(loaded); setAreas(loadedAreas); return; }
      const sample = invr();
      if (sample && sample.CAMS?.length) {
        setCameras((sample.CAMS || []).map(c => ({ camera_id: String(c.num), display_name: c.name, area_id: c.area, online: c.status !== 'offline', status: c.status, frame_url: null })));
        setAreas((sample.AREAS || []).map(a => ({ area_id: a.id, name: a.name })));
      } else { setCameras(fallback); setAreas([...new Map(fallback.map(c => [c.area_id, { area_id: c.area_id, name: c.area_id[0].toUpperCase() + c.area_id.slice(1) }])).values()]); }
    }).catch(() => { setCameras(fallback); });
  }, [fallback]);
  const chosen = selection.mode === 'all' ? cameras : selection.mode === 'area' ? cameras.filter(c => c.area_id === selection.area) : cameras.filter(c => (selection.cams || []).includes(c.camera_id));
  return (
    <div className="live-view-page" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', gap: 12, padding: fullScreen ? 16 : 24, background: 'var(--paper)', color: 'var(--ink)', ...(fullScreen ? { position: 'fixed', inset: 0, zIndex: 200, overflow: 'auto' } : {}) }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}><h1 style={{ margin: 0, fontSize: 28, fontWeight: 500 }}>Live view</h1><span style={{ padding: '8px 14px', borderRadius: 999, background: 'var(--ink)', color: 'var(--paper)', font: '500 12px var(--font-mono)', letterSpacing: '.08em' }}>● LIVE</span><div style={{ display: 'flex', gap: 6, marginLeft: 8, padding: 4, background: 'var(--bone)', borderRadius: 10 }}>{[1, 4, 9, 16].map(size => <button type="button" key={size} className="hvr-ink-border" onClick={() => setLayout(size)} style={{ minWidth: 42, padding: '9px 11px', border: size === layout ? '2px solid var(--blue)' : '1px solid transparent', borderRadius: 8, background: size === layout ? 'var(--blue-tint)' : 'transparent' }}>{size}</button>)}</div><button type="button" className="hvr-ink-border" onClick={() => setShowBoxes(v => !v)} style={{ padding: '10px 16px', border: '1px solid var(--line)', borderRadius: 8, background: showBoxes ? 'var(--blue-tint)' : 'var(--paper)' }}>◉ {showBoxes ? 'Show boxes' : 'Hide boxes'}</button><button type="button" className="hvr-ink-border" onClick={() => setShowEvents(v => !v)} style={{ marginLeft: 'auto', padding: '10px 16px', border: '1px solid var(--line)', borderRadius: 8, background: showEvents ? 'var(--blue-tint)' : 'var(--paper)' }}>Latest events</button><button type="button" className="hvr-ink-border" onClick={() => setFullScreen(v => !v)} style={{ padding: '10px 16px', border: '1px solid var(--line)', borderRadius: 8, background: 'var(--paper)' }}>{fullScreen ? 'Exit full screen' : 'Full screen'}</button><InetraCameraPicker
        defaultOpen={false}
        label="Cameras"
        cameras={cameras}
        areas={areas}
        value={selection}
        onChange={setSelection}
        onToggleOpen={() => {}}
      /></div>
      <div style={{ color: 'var(--muted)', fontSize: 14 }}>{chosen.length} camera{chosen.length === 1 ? '' : 's'} selected.</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 20, padding: '2px 0 8px', borderBottom: '1px solid var(--line-soft)', overflow: 'auto' }}><button type="button" className="hvr-ink-border" onClick={() => setSelection({ mode: 'all' })} style={{ padding: '12px 18px', border: '2px solid var(--blue)', borderRadius: 10, background: 'var(--blue-tint)', color: 'var(--blue-deep)', fontWeight: 600, whiteSpace: 'nowrap' }}>■ Every camera&nbsp; {cameras.length}</button>{areas.map(area => <button type="button" key={area.area_id} className="hvr-underline" onClick={() => setSelection({ mode: 'area', area: area.area_id })} style={{ border: 0, background: 'transparent', color: 'var(--muted)', fontSize: 15, whiteSpace: 'nowrap' }}>■ {area.name} <small>{cameras.filter(c => c.area_id === area.area_id).length}</small></button>)}</div>
      <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.sqrt(layout)}, minmax(0, 1fr))`, gap: 8, flex: 1 }}>{chosen.slice(0, layout).map((camera, index) => <div key={camera.camera_id} style={{ minHeight: 180, background: `linear-gradient(160deg, hsl(${210 + index * 19} 18% 28%), hsl(${210 + index * 19} 12% 8%))`, borderRadius: 6, overflow: 'hidden', position: 'relative', border: '1px solid var(--line-dark)' }}>{camera.frame_url && <img src={camera.frame_url || getFrameUrl(camera.camera_id)} alt={camera.display_name || camera.camera_id} style={{ width: '100%', height: 180, objectFit: 'cover', opacity: camera.online === false ? .45 : 1 }} />}{showBoxes && camera.online !== false && <><span style={{ position: 'absolute', left: '28%', top: '24%', width: '18%', height: '40%', border: '2px solid var(--sky)', borderRadius: 2 }} /><span style={{ position: 'absolute', left: '28%', top: '18%', background: 'var(--sky)', color: 'var(--ink)', padding: '2px 5px', font: '500 11px var(--font-mono)' }}>Person</span></>}<div style={{ position: 'absolute', inset: 'auto 0 0', padding: '26px 12px 10px', color: 'var(--paper)', background: 'linear-gradient(transparent, rgba(0,0,0,.85))' }}><strong style={{ fontSize: 15 }}>{camera.camera_id} &nbsp;{camera.display_name || camera.camera_id}</strong><span style={{ marginLeft: 8, fontSize: 12, color: camera.online === false ? 'var(--danger)' : 'var(--success)' }}>● {camera.status || 'online'}</span></div></div>)}{showEvents && <aside style={{ gridColumn: '1 / -1', border: '1px solid var(--line)', borderRadius: 10, padding: 14, background: 'var(--paper)' }}><strong>Latest events</strong><div style={{ display: 'flex', gap: 18, marginTop: 10, color: 'var(--muted)', fontSize: 13 }}>No recent events on the selected cameras.</div></aside>}</div>
    </div>
  );
}
