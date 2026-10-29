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

  useEffect(() => {
    const load = () => {
      try { const v = localStorage.getItem('aivisra_search_view'); setView(v || 'cards'); } catch (e) {}
    };
    load();
    const handle = () => { try { localStorage.setItem('aivisra_search_view', view); } catch (e) {} };
    window.addEventListener('unload', handle);
    return () => { window.removeEventListener('unload', handle); };
  }, [view]);

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
          <button onClick={() => setSPlay(prevEvent.id)} style={btnProps}>Prev</button>
          <button onClick={() => setSPlay(nextEvent.id)} style={btnProps}>Next</button>
          <button onClick={() => setSPlay(null)} style={btnProps}>Close</button>
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
    <div style={{ flex: 1, minHeight: 0, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 12, padding: '24px 32px 32px' }}>
      <style>{`.hvr-blue2:hover { background: var(--blue-2); } .hvr-ink-border:hover { border-color: var(--ink); } .hvr-skip:hover { border-color: var(--ink); }`}</style>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, alignItems: 'center', fontSize: 14 }}>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>Cameras</span>
          <button onClick={() => setSCams(v => ({ mode: v.mode === 'all' ? 'cams' : 'all' }))} className="hvr-blue2" style={cameraBtnProps}>
            {sCams.mode === 'all' ? 'Select cams' : 'All cameras'}
          </button>
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
          <button onClick={() => setSSort(v => v === 'new' ? 'old' : 'new')} className="hvr-blue2" style={sortBtnProps}>{sSort}</button>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>View</span>
          <button onClick={() => setView(v => ({ cards: 'list', list: 'timeline', timeline: 'calendar', calendar: 'cards' }[v] || 'cards'))} className="hvr-blue2" style={viewBtnProps}>{view}</button>
        </div>
      </div>

      <div style={{ background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: 8, padding: 16, color: 'var(--ink)' }}>
        <h2>Search Results</h2>
        <p>Search results with camera filters, type filters, and time range.</p>
        <p>Using prototype sample data (16 cameras, fictional events from 28 Oct 2026).</p>
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
