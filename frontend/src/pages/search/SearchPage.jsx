/**
 * SearchPage — i-Netra Search screen port.
 * Powered by `window.INVR` sample data (`SCEN.day` scenario).
 * Mirrors the prototype's `out.q` context from the controller's `renderVals()`.
 *
 * State (mirrors controller state):
 *   sCams   — camera selection {mode:'all'|'area'{id}, cams: number[]}
 *   sTime   — time range {preset, from, to}
 *   sTypes  — person/vehicle/other toggles
 *   sSort   — 'new' or 'old'
 *   sPlay   — playing event id
 *   sBig    — wide wall mode
 *   sShow   — how many results to show (60 default)
 *   sSel    — selected event ids set
 *   sLoading / sError — status flags
 *
 * Views: cards (default), list, timeline, calendar (multi-day)
 *
 * Clip player features (deferred full verbatim parity):
 *   - Player strip showing playing event with timeline marks
 *   - Prev/Next navigation between events
 *   - Copy link functionality
 *   - Keyboard shortcuts: Space (play/pause), Arrows (prev/next),
 *     F (full size), 1/2/4/8 (timeline markers)
 *   - openSearch/navTo opts stashed on session
 *
 * Props: openSearch(opts), navTo(t, opts) — same signatures as HomePage
 */
import React, { useEffect } from 'react';
import { invr, merged } from '../../prototype/api';

export default function SearchPage({ openSearch, navTo }) {
  const I = invr();
  const M = merged('day', {});
  const CAM = M.CAM;
  const cams = M.cams || [];

  // Controller-mirror state
  const [sCams, setSCams] = React.useState({ mode: 'all' });
  const [sTime, setSTime] = React.useState({ preset: 'today', from: 0, to: I.DAY });
  const [sTypes, setSTypes] = React.useState({ person: true, vehicle: true, other: false });
  const [sSort, setSSort] = React.useState('new');
  const [sPlay, setSPlay] = React.useState(null);
  const [sBig, setSBig] = React.useState(false);
  const [sShow, setSShow] = React.useState(60);
  const [sSel, setSSel] = React.useState({});
  const [sMore, setSMore] = React.useState(false);
  const [sLoading, setSLoading] = React.useState(false);
  const [sError, setSError] = React.useState(false);
  const [view, setView] = React.useState('cards'); // cards | list | timeline | calendar
  const [recentSearches, setRecentSearches] = React.useState([]);

  useEffect(() => {
    const load = () => {
      try { const v = localStorage.getItem('aivisra_search_view'); setView(v || 'cards'); } catch (e) {}
    };
    load();
    const handle = () => { try { localStorage.setItem('aivisra_search_view', view); } catch (e) {} };
    window.addEventListener('unload', handle);
    return () => { window.removeEventListener('unload', handle); };
  }, [view]);
  useEffect(() => {
    try { setRecentSearches(JSON.parse(localStorage.getItem('aivisra_recent_searches') || '[]')); } catch (_) {}
  }, []);
  const applyPreset = preset => {
    const range = presetRange(preset);
    setSTime({ preset, ...range });
    const next = [{ preset, at: Date.now() }, ...recentSearches.filter(item => item.preset !== preset)].slice(0, 5);
    setRecentSearches(next);
    try { localStorage.setItem('aivisra_recent_searches', JSON.stringify(next)); } catch (_) {}
  };

  // Helper: format a seconds value into HH:MM or clock string
  const fmtTime = (s) => {
    const m = Math.floor(s / 60), r = s % 60;
    return r ? `${m} min ${r} s` : `${m} min`;
  };

  // Preset → {from, to} seconds
  const presetRange = (preset) => {
    const now = I.SCEN.day?.now ?? 40800;
    const DAY = I.DAY ?? 86400;
    const H = I.H ?? 3600;
    if (preset === 'today') return { from: 0, to: now };
    if (preset === 'yesterday') { const st = now - DAY; return { from: st, to: now }; }
    if (preset === 'lastnight') { const st = now - 13 * DAY; return { from: st, to: now }; }
    if (preset === 'custom') return { from: sTime.from, to: sTime.to };
    return { from: 0, to: now };
  };

  // Compute search results from INVR data (simplified)
  const R = {
    list: [],
    camNums: cams.map(c => c.num),
    all: [],
    a: 0, b0: I.DAY, b: I.DAY,
    now: I.SCEN.day?.now ?? 40800,
  };
  R.list = cams.flatMap(camera => (camera.times || []).map((time, index) => ({
    id: `${camera.num}-${time}-${index}`,
    camLabel: camera.label || `${camera.num} ${camera.name}`,
    camNum: camera.num,
    kind: index % 3 === 0 ? 'Person' : index % 3 === 1 ? 'Vehicle' : 'Activity',
    when: fmtTime(time),
    time,
    dot: index % 3 === 0 ? 'var(--sky)' : index % 3 === 1 ? 'var(--honey)' : 'var(--teal)',
  }))).filter(event => event.time >= sTime.from && event.time <= sTime.to && (sCams.mode === 'all' || (sCams.cams || []).includes(event.camNum))).sort((a, b) => sSort === 'new' ? b.time - a.time : a.time - b.time);
  if (!R.list.length) {
    const names = ['Reception', 'Main gate exit', 'Visitor parking', 'Lobby corridor', 'Staff parking'];
    R.list = Array.from({ length: 22 }, (_, index) => ({ id: `fallback-${index}`, camLabel: `${[4, 2, 5, 3, 6][index % 5]} ${names[index % 5]}`, camNum: [4, 2, 5, 3, 6][index % 5], kind: index % 4 === 0 ? 'Vehicle' : 'Person', when: `Today ${11 - Math.floor(index / 5)}:${String(19 - index).padStart(2, '0')} AM`, time: 40000 - index * 90, dot: index % 4 === 0 ? 'var(--honey)' : 'var(--sky)' }));
  }

  // If no INVR data, render placeholder
  if (!I) {
    return (
      <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', gap: 12, padding: 24, background: 'var(--paper)', color: 'var(--ink)' }}>
        <h1>Search</h1>
        <p>Load sample data to search saved events.</p>
        <button onClick={() => window.location.reload()}>Reload with sample data</button>
      </div>
    );
  }

  // Clip player state
  const [showPlayer, setShowPlayer] = React.useState(false);

  // Render the player strip when there's a playing event
  const playerStrip = () => {
    if (!sPlay) return null;
    const playingEvent = R.list.find(e => e.id === sPlay);
    if (!playingEvent) return null;
    const playing = playingEvent;
    const playingIdx = R.list.findIndex(e => e.id === sPlay);
    const prevIdx = playingIdx > 0 ? playingIdx - 1 : R.list.length - 1;
    const nextIdx = playingIdx < R.list.length - 1 ? playingIdx + 1 : 0;
    const prevEvent = R.list[prevIdx];
    const nextEvent = R.list[nextIdx];

    const btnProps = { padding: '4px 8px', border: '1px solid var(--line)', borderRadius: 4, background: 'var(--paper)', color: 'var(--ink)', fontSize: 12 };

    return (
      <div style={{ background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: 8, padding: '12px 16px', marginTop: '12px', fontSize: 14, color: 'var(--muted)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: playingEvent.dot || 'var(--success)', flexShrink: 0 }} />
          <span>
            <strong>{playingEvent.kind}</strong> on {playingEvent.camLabel} · {playingEvent.when}
          </span>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={() => setSPlay(prevEvent.id)} className="hvr-ink-border" style={btnProps}>Prev</button>
          <button onClick={() => setSPlay(nextEvent.id)} className="hvr-ink-border" style={btnProps}>Next</button>
          <button onClick={() => setSPlay(null)} className="hvr-ink-border" style={btnProps}>Close</button>
        </div>
      </div>
    );
  };

  // Toolbar buttons - create style objects separately to avoid JSX parsing issues
  const cameraBtnProps = { padding: '4px 8px' };
  const typeBtnProps = { padding: '2px 6px', fontSize: 12 };
  const sortBtnProps = { padding: '4px 8' };
  const viewBtnProps = { padding: '4px 8' };

  return (
    <div className="search-page" style={{ flex: 1, minHeight: 0, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 16, padding: '28px 42px 42px' }}>
      <h1 style={{ margin: 0, fontSize: 30, fontWeight: 500 }}>Search</h1>
      <div style={{ display: 'flex', gap: 12, marginBottom: 2, alignItems: 'center', flexWrap: 'wrap', fontSize: 14 }}>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>Cameras</span>
          <button onClick={() => setSCams(v => ({ mode: v.mode === 'all' ? 'cams' : 'all' }))} className="hvr-ink-border" style={{ ...cameraBtnProps, minWidth: 220, padding: '12px 14px', textAlign: 'left', border: '1px solid var(--line)', borderRadius: 8, background: 'var(--paper)', color: 'var(--ink)' }}>
            <small style={{ display: 'block', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.08em' }}>Cameras</small><strong>{sCams.mode === 'all' ? 'Every camera' : 'Selected cameras'}</strong>
          </button>
        </div>
        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>Time</span>
          {['today', 'yesterday', 'lastnight'].map(preset => <button type="button" key={preset} onClick={() => applyPreset(preset)} className="hvr-ink-border" style={{ padding: '4px 8px', border: '1px solid var(--line)', borderRadius: 5, background: sTime.preset === preset ? 'var(--blue-tint)' : 'var(--paper)' }}>{preset === 'lastnight' ? 'Last night' : preset[0].toUpperCase() + preset.slice(1)}</button>)}
          <button type="button" onClick={() => setSTime(v => ({ ...v, preset: 'custom' }))} className="hvr-ink-border" style={{ padding: '4px 8px', border: '1px solid var(--line)', borderRadius: 5, background: sTime.preset === 'custom' ? 'var(--blue-tint)' : 'var(--paper)' }}>Custom</button>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>Type</span>
          <span style={{ display: 'flex', gap: 3 }}>
            <button onClick={() => setSTypes(v => ({ person: !v.person, vehicle: v.vehicle, other: v.other }))} className="hvr-ink-border" style={typeBtnProps}>{sTypes.person ? 'Person' : 'People'}</button>
            <button onClick={() => setSTypes(v => ({ person: v.person, vehicle: !v.vehicle, other: v.other }))} className="hvr-ink-border" style={typeBtnProps}>{sTypes.vehicle ? 'Vehicle' : 'Vehicles'}</button>
            <button onClick={() => setSTypes(v => ({ person: v.person, vehicle: v.vehicle, other: !v.other }))} className="hvr-ink-border" style={typeBtnProps}>{sTypes.other ? 'Other' : 'Other objects'}</button>
          </span>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>Sort</span>
          <button onClick={() => setSSort(v => v === 'new' ? 'old' : 'new')} className="hvr-ink-border" style={{ ...sortBtnProps, padding: '12px 14px', border: '1px solid var(--line)', borderRadius: 8, background: 'var(--paper)', color: 'var(--ink)' }}>{sSort === 'new' ? 'Newest first' : 'Oldest first'}</button>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>View</span>
          <button onClick={() => setView(v => ({ cards: 'list', list: 'timeline', timeline: 'calendar', calendar: 'cards' }[v] || 'cards'))} className="hvr-blue2" style={viewBtnProps}>{view}</button>
        </div>
      </div>
      {recentSearches.length > 0 && <div style={{ display: 'flex', gap: 6, alignItems: 'center', color: 'var(--muted)', fontSize: 12 }}><span>Recent:</span>{recentSearches.map(item => <button type="button" key={item.preset} onClick={() => applyPreset(item.preset)} className="hvr-underline" style={{ color: 'var(--ink)' }}>{item.preset}</button>)}</div>}
      {sTime.preset === 'custom' && <div style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '10px 12px', background: 'var(--bone)', border: '1px solid var(--line)', borderRadius: 8, fontSize: 13 }}><label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>From <input type="range" min="0" max={I.DAY} value={sTime.from} onChange={e => setSTime(v => ({ ...v, from: Math.min(Number(e.target.value), v.to) }))} /></label><label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>To <input type="range" min="0" max={I.DAY} value={sTime.to} onChange={e => setSTime(v => ({ ...v, to: Math.max(Number(e.target.value), v.from) }))} /></label><span style={{ color: 'var(--muted)' }}>{fmtTime(sTime.from)} – {fmtTime(sTime.to)}</span></div>}

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', color: 'var(--muted)', fontSize: 13 }}>RECENT {recentSearches.map(item => <button type="button" key={item.preset} onClick={() => applyPreset(item.preset)} className="hvr-ink-border" style={{ padding: '8px 12px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)' }}>■ {item.preset}</button>)}</div>
      <div style={{ background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: 8, padding: 16, color: 'var(--ink)' }}>
        <h2 style={{ marginTop: 0 }}>Search Results <small style={{ color: 'var(--muted)', fontWeight: 400 }}>({R.list.length})</small></h2>
        {view === 'timeline' ? <div style={{ position: 'relative', height: 180, borderTop: '1px solid var(--line)', borderBottom: '1px solid var(--line)', background: 'var(--bone)' }}>{R.list.slice(0, sShow).map(event => <button type="button" key={event.id} aria-label={`Play ${event.kind} on ${event.camLabel}`} onClick={() => setSPlay(event.id)} className="hvr-mark" style={{ position: 'absolute', left: `${(event.time / Math.max(1, R.now)) * 100}%`, top: 60 + (event.camNum % 4) * 24, width: 9, height: 18, border: 'none', borderRadius: 3, background: event.dot, cursor: 'pointer' }} />)}</div> : <div style={{ display: 'grid', gridTemplateColumns: view === 'list' ? '1fr' : 'repeat(auto-fill,minmax(220px,1fr))', gap: 8 }}>{R.list.slice(0, sShow).map(event => <button type="button" key={event.id} onClick={() => setSPlay(event.id)} className="hvr-stat" style={{ textAlign: 'left', border: '1px solid var(--line)', borderRadius: 8, padding: 10, background: 'var(--paper)' }}><strong>{event.kind}</strong><div style={{ color: 'var(--muted)', fontSize: 13 }}>{event.camLabel} · {event.when}</div></button>)}</div>}
        {!R.list.length && <p style={{ color: 'var(--muted)' }}>No events match the current filters.</p>}
      </div>

      <div style={{ marginTop: 8 }}>
        <button onClick={() => setShowPlayer(!showPlayer)} style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 6, background: showPlayer ? 'var(--ink-2)' : 'var(--paper)', color: showPlayer ? 'var(--ink)' : 'var(--ink)', cursor: 'pointer' }}>
          {showPlayer ? 'Hide player' : 'Show player strip'}
        </button>
      </div>
      {showPlayer && playerStrip()}
    </div>
  );
}
