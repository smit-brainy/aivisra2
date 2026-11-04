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
import React, { useEffect, useRef } from 'react';
import { invr, merged } from '../../prototype/api';
import { fetchAreas, fetchCameras, fetchEvent, fetchEvents, getEventClipUrl, getSnapshotUrl } from '../../utils/api';
import { areaColor } from '../../utils/areaColors';

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
  const [dbCameras, setDbCameras] = React.useState([]);
  const [dbAreas, setDbAreas] = React.useState([]);
  const [dbEvents, setDbEvents] = React.useState([]);
  const [selectedEvent, setSelectedEvent] = React.useState(null);
  const evidenceRequestRef = useRef(0);
  const vehicleClasses = React.useMemo(() => new Set(['bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 'boat']), []);
  const matchesTypeFilter = event => {
    const objectClass = String(event?.object_class || event?.kind || '').toLowerCase();
    if (objectClass === 'person') return sTypes.person;
    if (vehicleClasses.has(objectClass)) return sTypes.vehicle;
    return sTypes.other;
  };
  const openEvidence = async event => {
    if (!event) return;
    const requestId = evidenceRequestRef.current + 1;
    evidenceRequestRef.current = requestId;
    setSelectedEvent(event);
    try {
      let latest = await fetchEvent(event.event_id);
      // Clip recording is asynchronous. Refresh briefly so a card clicked just
      // after detection can receive its clip path without requiring a reload.
      for (let attempt = 0; attempt < 5 && !latest.clip_path; attempt += 1) {
        await new Promise(resolve => window.setTimeout(resolve, 1000));
        if (evidenceRequestRef.current !== requestId) return;
        latest = await fetchEvent(event.event_id);
      }
      if (evidenceRequestRef.current === requestId) setSelectedEvent(latest);
    } catch (_) { /* Keep the event summary visible if refresh fails. */ }
  };
  const closeEvidence = () => {
    evidenceRequestRef.current += 1;
    setSelectedEvent(null);
  };
  const [dbFilters, setDbFilters] = React.useState({ start: '', end: '', area_id: '', camera_id: '', object_class: '' });
  const detectingObjects = React.useMemo(
    () => [...new Set(dbEvents.map(event => event.object_class).filter(Boolean))].sort((a, b) => a.localeCompare(b)),
    [dbEvents]
  );
  const formatIst = value => {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat('en-IN', {
      timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'medium', hour12: true,
    }).format(date);
  };

  useEffect(() => {
    fetchCameras().then(setDbCameras).catch(() => {});
    fetchAreas().then(setDbAreas).catch(() => {});
  }, []);
  useEffect(() => {
    const params = { limit: '100', offset: '0' };
    if (dbFilters.start) params.start = dbFilters.start;
    if (dbFilters.end) params.end = dbFilters.end;
    if (dbFilters.camera_id) params.camera_id = dbFilters.camera_id;
    if (dbFilters.object_class) params.class = dbFilters.object_class;
    setSLoading(true);
    fetchEvents(params).then(body => setDbEvents(body.events || [])).catch(() => setDbEvents([])).finally(() => setSLoading(false));
  }, [dbFilters]);
  const areaCameras = dbFilters.area_id ? dbCameras.filter(camera => camera.area_id === dbFilters.area_id) : dbCameras;
  const selectedArea = dbAreas.find(area => area.area_id === dbFilters.area_id);
  // Helper: format a seconds value into HH:MM or clock string
  const fmtTime = (s) => {
    const m = Math.floor(s / 60), r = s % 60;
    return r ? `${m} min ${r} s` : `${m} min`;
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

  // Use persisted track events whenever the backend is available. The prototype
  // data remains only as a visual fallback while the API is unavailable.
  if (dbEvents.length || dbCameras.length) {
    const cameraNames = new Map(dbCameras.map(c => [String(c.camera_id), c.display_name || c.name || c.camera_id]));
    R.list = dbEvents.filter(matchesTypeFilter).filter(event => !dbFilters.area_id || dbCameras.find(camera => String(camera.camera_id) === String(event.camera_id))?.area_id === dbFilters.area_id).map(event => ({
      id: event.event_id,
      camNum: event.camera_id,
      camLabel: `${cameraNames.get(String(event.camera_id)) || event.camera_id} (${event.camera_id})`,
      kind: event.object_class || 'Unknown',
      when: formatIst(event.started_at_utc),
      time: Date.parse(event.started_at_utc || '') || 0,
      dot: 'var(--sky)',
      confidence: event.max_confidence,
      evidence: event,
    })).sort((a, b) => sSort === 'new' ? b.time - a.time : a.time - b.time);
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
  const typeButton = active => ({ padding: '8px 12px', border: '1px solid var(--line)', borderRadius: 7, background: active ? 'var(--blue-tint)' : 'var(--paper)', color: active ? 'var(--blue-deep)' : 'var(--ink)', fontSize: 13, fontWeight: active ? 600 : 400, cursor: 'pointer' });

  return (
    <div className="search-page" style={{ flex: 1, minHeight: 0, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 16, padding: '28px 42px 42px' }}>
      <h1 style={{ margin: 0, fontSize: 30, fontWeight: 500 }}>Search</h1>
      <div style={{ display: 'flex', gap: 12, marginBottom: 2, alignItems: 'center', flexWrap: 'wrap', fontSize: 14 }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, color: 'var(--muted)', fontSize: 12 }}>Start time<input type={dbFilters.start ? 'datetime-local' : 'text'} placeholder="Start date and time" value={dbFilters.start} onFocus={e => { e.currentTarget.type = 'datetime-local'; }} onBlur={e => { if (!e.currentTarget.value) e.currentTarget.type = 'text'; }} onChange={e => setDbFilters(v => ({ ...v, start: e.target.value }))} style={{ padding: '8px 10px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)' }} /></label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, color: 'var(--muted)', fontSize: 12 }}>End time<input type={dbFilters.end ? 'datetime-local' : 'text'} placeholder="End date and time" value={dbFilters.end} onFocus={e => { e.currentTarget.type = 'datetime-local'; }} onBlur={e => { if (!e.currentTarget.value) e.currentTarget.type = 'text'; }} onChange={e => setDbFilters(v => ({ ...v, end: e.target.value }))} style={{ padding: '8px 10px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)' }} /></label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, color: 'var(--muted)', fontSize: 12 }}>Area<select value={dbFilters.area_id} onChange={e => setDbFilters(v => ({ ...v, area_id: e.target.value, camera_id: '' }))} style={{ padding: '8px 10px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)' }}><option value="">All areas</option>{dbAreas.map(area => <option key={area.area_id} value={area.area_id}>{area.name}</option>)}</select>{selectedArea && <span style={{ alignSelf: 'flex-start', padding: '3px 7px', borderRadius: 4, fontSize: 11, fontWeight: 600, ...areaColor(selectedArea) }}>{selectedArea.name}</span>}</label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, color: 'var(--muted)', fontSize: 12 }}>Camera<select value={dbFilters.camera_id} onChange={e => setDbFilters(v => ({ ...v, camera_id: e.target.value }))} style={{ padding: '8px 10px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)' }}><option value="">All cameras</option>{areaCameras.map(c => <option key={c.camera_id} value={c.camera_id}>{c.display_name || c.name || c.camera_id}</option>)}</select></label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, color: 'var(--muted)', fontSize: 12 }}>Object<select value={dbFilters.object_class} onChange={e => setDbFilters(v => ({ ...v, object_class: e.target.value }))} style={{ padding: '8px 10px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)' }}><option value="">Currently detected objects</option>{detectingObjects.map(objectClass => <option key={objectClass} value={objectClass}>{objectClass}</option>)}</select></label>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>Type</span>
          <span style={{ display: 'flex', gap: 3 }}>
            <button type="button" onClick={() => setSTypes(v => ({ person: !v.person, vehicle: v.vehicle, other: v.other }))} className="hvr-ink-border" style={typeButton(sTypes.person)}>Person</button>
            <button type="button" onClick={() => setSTypes(v => ({ person: v.person, vehicle: !v.vehicle, other: v.other }))} className="hvr-ink-border" style={typeButton(sTypes.vehicle)}>Vehicle</button>
            <button type="button" onClick={() => setSTypes(v => ({ person: v.person, vehicle: v.vehicle, other: !v.other }))} className="hvr-ink-border" style={typeButton(sTypes.other)}>Other objects</button>
          </span>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>Sort</span>
          <button type="button" onClick={() => setSSort(v => v === 'new' ? 'old' : 'new')} className="hvr-ink-border" style={{ padding: '12px 14px', border: '1px solid var(--line)', borderRadius: 8, background: 'var(--paper)', color: 'var(--ink)' }}>{sSort === 'new' ? 'Newest first' : 'Oldest first'}</button>
        </div>
      </div>

      <div style={{ background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: 8, padding: 16, color: 'var(--ink)' }}>
        <h2 style={{ marginTop: 0 }}>Search Results <small style={{ color: 'var(--muted)', fontWeight: 400 }}>({R.list.length})</small></h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(240px,1fr))', gap: 12 }}>{R.list.slice(0, sShow).map(event => <button type="button" key={event.id} onClick={() => openEvidence(event.evidence)} className="hvr-stat" style={{ display: 'flex', flexDirection: 'column', gap: 8, textAlign: 'left', border: '1px solid var(--line)', borderRadius: 10, padding: 10, background: 'var(--paper)', overflow: 'hidden' }}>{event.evidence?.snapshot_path ? <img src={getSnapshotUrl(event.evidence.snapshot_path)} alt={`${event.kind} detection`} style={{ width: '100%', height: 140, objectFit: 'cover', borderRadius: 6, background: 'var(--bone)' }} /> : <div style={{ width: '100%', height: 140, display: 'grid', placeItems: 'center', borderRadius: 6, background: 'var(--bone)', color: 'var(--muted)', fontSize: 12 }}>No event image</div>}<strong style={{ color: 'var(--ink)' }}>{event.kind}</strong><div style={{ color: 'var(--muted)', fontSize: 13 }}>{event.camLabel} · {event.when}</div></button>)}</div>
        {!R.list.length && <p style={{ color: 'var(--muted)' }}>No events match the current filters.</p>}
      </div>

      <div style={{ marginTop: 8 }}>
        <button onClick={() => setShowPlayer(!showPlayer)} style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 6, background: showPlayer ? 'var(--ink-2)' : 'var(--paper)', color: showPlayer ? 'var(--ink)' : 'var(--ink)', cursor: 'pointer' }}>
          {showPlayer ? 'Hide player' : 'Show player strip'}
        </button>
      </div>
      {showPlayer && playerStrip()}
      {selectedEvent && <div role="dialog" aria-modal="true" style={{ position: 'fixed', inset: 0, zIndex: 2000, background: 'rgba(0,0,0,.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }} onClick={closeEvidence}>
        <div style={{ width: 'min(820px, 95vw)', maxHeight: '90vh', overflow: 'auto', background: 'var(--paper)', color: 'var(--ink)', borderRadius: 10, padding: 20 }} onClick={e => e.stopPropagation()}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}><h2 style={{ margin: 0 }}>{selectedEvent.object_class || 'Event'} · {selectedEvent.camera_name || selectedEvent.camera_id}</h2><button type="button" onClick={closeEvidence} style={{ padding: '5px 10px' }}>Close</button></div>
          {selectedEvent.snapshot_path ? <img src={getSnapshotUrl(selectedEvent.snapshot_path)} alt={`${selectedEvent.object_class || 'Event'} evidence`} style={{ display: 'block', width: '100%', maxHeight: 420, objectFit: 'contain', background: '#111', borderRadius: 6 }} /> : <p style={{ color: 'var(--muted)' }}>No event image is available.</p>}
          {selectedEvent.clip_path ? <video controls preload="metadata" src={getEventClipUrl(selectedEvent.event_id)} style={{ display: 'block', width: '100%', marginTop: 14, borderRadius: 6 }} /> : <p style={{ color: 'var(--muted)' }}>The event video is still being recorded or is unavailable.</p>}
        </div>
      </div>}
    </div>
  );
}
