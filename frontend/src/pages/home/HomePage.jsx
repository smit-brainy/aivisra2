/**
 * Home — verbatim port of the prototype's `isHome` screen block
 * (app-main-template.html lines 121–312) with its controller bindings
 * (`out.h`, `chrome()` context, `steps`). Sample data from window.INVR,
 * scenario 'day' (Busy day · 11:20 AM).
 *
 * callback props:
 *   openSearch(opts) — same signature as the controller's openSearch()
 *   navTo(t, opts)   — same signature as the controller's navTo()
 */
import React from 'react';
import { invr, merged } from '../../prototype/api';
import InetraStrip from '../../components/inetra/InetraStrip';
import InetraEventCard from '../../components/inetra/InetraEventCard';
import InetraMonthCalendar from '../../components/inetra/InetraMonthCalendar';
import { fetchCameras, fetchEvent, fetchEvents, getEventClipUrl, getSnapshotUrl } from '../../utils/api';
import { areaColor } from '../../utils/areaColors';

const STEPS = [
  ['Add your cameras', 'Opens Add cameras. Find them on this network, add them from the recorder, enter an address or upload a list.', 'Add cameras'],
  ['Check detail levels', 'Opens Capacity and detail in Settings, where each camera is set to Low, Standard, High or Maximum.', 'Check detail levels'],
  ['Choose how long to keep clips', 'Opens Storage in Settings. Clips are kept for 30 days until you choose otherwise.', 'Choose how long'],
  ['Add the people who will use i-Netra', 'Opens Users in Settings, where you create accounts and give each one a role.', 'Add people'],
];
const NAV_SECTIONS = { 2: 'capacity', 3: 'storage', 4: 'users' };

// Lucide-style ArrowUpRight icon for the card navigation affordance.
function OpenSearchIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M7 17 17 7" /><path d="M7 7h10v10" /></svg>;
}

export default function HomePage({ session, openSearch, navTo }) {
  const admin = session.role === 'admin';
  const [hDay, setHDay] = React.useState('today');       // 'today' | 'yesterday' | 'date'
  const [hDayOff, setHDayOff] = React.useState(-2);
  const [hCal, setHCal] = React.useState(false);
  const [steps, setSteps] = React.useState(null);        // admin checklist states {1..4}
  const [forceChecklist, setForceChecklist] = React.useState(false);
  const [checkHidden, setCheckHidden] = React.useState(false);
  const [dbCameras, setDbCameras] = React.useState([]);
  const [dbEvents, setDbEvents] = React.useState([]);
  const [dbLoaded, setDbLoaded] = React.useState(true);
  const [playingEvent, setPlayingEvent] = React.useState(null);

  React.useEffect(() => {
    let disposed = false;
    const loadCameras = () => fetchCameras().then(value => { if (!disposed) setDbCameras(value || []); }).catch(error => { console.warn('[HomePage] camera list refresh failed', error); });
    const loadEvents = () => fetchEvents({ limit: '10000', offset: '0' }).then(value => { if (!disposed) setDbEvents(value.events || []); }).catch(error => { console.warn('[HomePage] event refresh failed', error); });
    loadCameras(); loadEvents();
    const cameraTimer = window.setInterval(loadCameras, 60000);
    const eventTimer = window.setInterval(loadEvents, 120000);
    return () => { disposed = true; window.clearInterval(cameraTimer); window.clearInterval(eventTimer); };
  }, []);

  React.useEffect(() => {
    const onKey = e => { if (e.key === 'Escape') { setHCal(false); setForceChecklist(false); } };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  if (!invr()) return <div style={{ flex: 1, padding: 32, color: 'var(--ink)' }}><h1>Home</h1><p style={{ color: 'var(--muted)' }}>The application is offline. Connect to the backend to view cameras and events.</p></div>;
  const I = invr();
  const scen = I.SCEN.day;
  let now = scen.now;
  if (dbLoaded) {
    const istNow = Date.now() + (5.5 * 60 * 60 * 1000);
    now = (istNow / 1000) % 86400;
  }
  const M = merged('day', {});
  const DAY = I.DAY, H = I.H;
  const CAM = M.CAM;
  const cams = dbCameras.map(c => ({ num: c.camera_id, name: c.display_name || c.name || c.camera_id, label: c.display_name || c.name || c.camera_id, status: c.status === 'offline' ? 'offline' : 'online' }));
  const offCams = cams.filter(c => c.status === 'offline');

  const dOff = hDay === 'today' ? 0 : hDay === 'yesterday' ? -1 : hDayOff;
  let times = I.camTimes(dOff), dStart = dOff * DAY;
  const areas = M.areas.filter(a => a.cams.length);
  const since = scen.since || 0;
  const staticGroups = areas.map(a => ({
    name: a.name, toneBg: I.areaTone(a.id).bg, toneInk: I.areaTone(a.id).ink, count: a.cams.length + (a.cams.length === 1 ? ' camera' : ' cameras'),
    rows: a.cams.map(n => {
      const c = CAM[n], t0 = times[n] || [], tt = scen.since == null ? t0 : dOff === 0 ? t0.filter(t => t >= since) : [];
      return {
        num: n, name: c.name, times: tt, cnt: dOff === 0 ? tt.filter(t => t <= now).length : tt.length,
        offline: dOff === 0 ? (scen.gaps[n] || []) : [], isOff: dOff === 0 && c.status === 'offline',
        open: () => openSearch({ cams: [n], preset: dOff === 0 ? 'today' : dOff === -1 ? 'yesterday' : null, day: dOff }),
        pick: t => openSearch({ cams: [n], focusT: t }),
      };
    }),
  }));
  const realGroups = dbCameras.length ? Object.values(dbCameras.reduce((groups, camera) => {
    const area = camera.area;
    const groupKey = area?.area_id || 'unassigned';
    const tone = area ? areaColor(area) : { background: 'var(--paper-2)', color: 'var(--muted)' };
    const group = groups[groupKey] || { name: area?.name || 'Unassigned', toneBg: tone.background, toneInk: tone.color, rows: [] };
    group.rows.push(camera);
    groups[groupKey] = group;
    return groups;
  }, {})).map(group => ({
    ...group,
    count: `${group.rows.length} ${group.rows.length === 1 ? 'camera' : 'cameras'}`,
    rows: group.rows.map(camera => {
      const cameraEvents = dbEvents.filter(event => String(event.camera_id) === String(camera.camera_id));
      const eventTimes = cameraEvents.map(event => {
        const stamp = Date.parse(event.started_at_utc || '');
        if (Number.isNaN(stamp)) return null;
        const istStamp = stamp + (5.5 * 60 * 60 * 1000);
        const istNow = Date.now() + (5.5 * 60 * 60 * 1000);
        const dayStart = Math.floor(istNow / 86400000) * 86400000;
        return Math.max(0, Math.min(DAY, (istStamp - dayStart) / 1000));
      }).filter(value => value !== null);
      const name = camera.display_name || camera.name || camera.camera_id;
      return { num: camera.camera_id, name, times: eventTimes, cnt: eventTimes.length, offline: [], isOff: camera.status === 'offline', open: () => openSearch({ cams: [camera.camera_id], preset: 'today' }), pick: time => openSearch({ cams: [camera.camera_id], focusT: time }) };
    }),
  })) : [];
  const groups = realGroups;
  const realTodayEvents = dbEvents.map((event, index) => {
    const stamp = Date.parse(event.started_at_utc || '');
    if (Number.isNaN(stamp)) return null;
    const istStamp = stamp + (5.5 * 60 * 60 * 1000);
    const istNow = Date.now() + (5.5 * 60 * 60 * 1000);
    const dayStart = Math.floor(istNow / 86400000) * 86400000;
    const seconds = Math.max(0, Math.min(DAY, (istStamp - dayStart) / 1000));
    const camera = dbCameras.find(item => String(item.camera_id) === String(event.camera_id));
    return { id: event.event_id || `${event.camera_id}-${event.started_at_utc}-${index}`, cam: event.camera_id, kind: event.object_class || 'Unknown', type: event.object_class === 'person' ? 'person' : event.object_class === 'car' || event.object_class === 'truck' || event.object_class === 'bus' || event.object_class === 'motorcycle' ? 'vehicle' : 'other', t: seconds, dur: event.duration_seconds || 0, cameraName: camera?.display_name || camera?.name || event.camera_name || event.camera_id, snapshot_path: event.snapshot_path, event_id: event.event_id, clip_path: event.clip_path };
  }).filter(Boolean).filter(event => event.t <= DAY);
  let todayEv = scen.noCams ? [] : I.day(0).filter(e => e.t <= now && e.t >= since);
  todayEv = realTodayEvents;
  {
    times = {};
    todayEv.forEach(event => { (times[event.cam] ||= []).push(event.t); });
  }
  const people = todayEv.filter(e => e.type === 'person').length;
  const last = todayEv[todayEv.length - 1];
  const nf = now / DAY;

  const stp = steps || {};
  const nextK = [1, 2, 3, 4].find(k => stp[k] === 'todo');
  const doneN = [1, 2, 3, 4].filter(k => stp[k] === 'done').length;
  const canShowChecklist = admin && !!steps && !checkHidden && (doneN < 4 || forceChecklist);
  const checkSteps = STEPS.map(([title, sub, action], i) => {
    const k = i + 1, stt = stp[k], done = stt === 'done';
    return {
      idx: '0' + k, title, sub, action, status: done ? 'Done' : stt === 'skipped' ? 'Skipped' : 'To do',
      chipBg: done ? 'var(--success-tint)' : 'var(--paper-2)', chipInk: done ? 'var(--success-deep)' : 'var(--ink)',
      bar: done ? 'var(--success)' : 'var(--paper-3)',
      isNext: k === nextK, isLater: !done && k !== nextK, canSkip: stt === 'todo',
      go: () => { if (k === 1) navTo('addcams', {}); else navTo('settings', { section: NAV_SECTIONS[k], setup: k }); },
      skip: () => setSteps(st => Object.assign({}, st, { [k]: 'skipped' })),
    };
  });

  const yEv = scen.noCams ? [] : I.day(-1).filter(e => e.t <= now - DAY && e.t >= since - DAY);
  const yP = yEv.filter(e => e.type === 'person').length, yV = yEv.length - yP;
  const cmpY = (x, y) => x === y ? 'Same as this time yesterday' : `${Math.abs(x - y)} ${x > y ? 'more' : 'fewer'} than this time yesterday`;
  const seg = on => ({ bg: on ? 'var(--blue-tint)' : 'transparent', ink: on ? 'var(--blue-deep)' : 'var(--muted)', ring: on ? '0 0 0 1px var(--blue)' : 'none', weight: on ? 600 : 400 });
  const days = [['today', 'Today'], ['yesterday', 'Yesterday'], ['date', 'Pick a date']].map(([k, l]) =>
    Object.assign({ label: l, key: k, set: () => { setHDay(k); setHCal(k === 'date'); } }, seg(hDay === k)));
  const card = e => {
    const c = M.CAM[e.cam] || I.CAM[e.cam] || { label: e.cameraName || e.cam, scene: '' };
    return { id: e.id, kind: e.kind, type: e.type, camLabel: e.cameraName || c.label, when: I.when(e.t), dur: I.dur(e.dur), durS: e.dur, scene: c.scene, x: e.x, t: e.t, cam: e.cam, snapshotPath: e.snapshot_path, eventId: e.id };
  };

  return (
    <div style={{ flex: 1, minHeight: 0, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 20, padding: '24px 32px 32px' }}>


      {canShowChecklist && (
        <section aria-label="Setup checklist" style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 4fr) minmax(0, 8fr)', gap: 40, padding: '24px 28px', background: 'var(--bone)', border: '1px solid var(--line)', borderRadius: 14 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <span style={{ font: '500 11px/1.3 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--muted)' }}>Set up i-Netra · {doneN} of 4 done</span>
            <h2 style={{ margin: 0, fontSize: 26, fontWeight: 500, letterSpacing: '-0.025em', lineHeight: 1.15 }}>{doneN === 4 ? 'Plant 2 is set up.' : 'Finish setting up Plant 2.'}</h2>
            <div><button onClick={() => { setForceChecklist(false); setCheckHidden(true); }} className="hvr-ink-border" style={{ height: 36, padding: '0 12px', border: '1px solid var(--line)', borderRadius: 8, background: 'var(--paper)', fontSize: 14, fontWeight: 500, cursor: 'pointer' }}>Hide checklist</button></div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0,1fr))', gap: 4 }}>
              {checkSteps.map((st, i) => <span key={i} style={{ height: 6, borderRadius: 2, background: st.bar }} />)}
            </div>
            <div style={{ display: 'flex', gap: 12, padding: '12px 14px', background: 'var(--info-tint)', border: '1px solid var(--line)', borderRadius: 8, color: 'var(--info-deep)', fontSize: 14.5, lineHeight: 1.45 }}>
              <span style={{ width: 7, height: 7, marginTop: 7, flexShrink: 0, background: 'var(--info-deep)' }} />
              <span><strong style={{ fontWeight: 600 }}>Capacity check at install:</strong> This box can watch about 30 cameras at Standard detail.</span>
            </div>
            <span style={{ fontSize: 13.5, lineHeight: 1.5, color: 'var(--muted)', textWrap: 'pretty' }}>Any step can be skipped and done later. The checklist hides once every step is done, and About this box in Settings can bring it back.</span>
          </div>
          <ol style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', borderTop: '1px solid var(--line)' }}>
            {checkSteps.map(st => (
              <li key={st.idx} style={{ display: 'grid', gridTemplateColumns: '40px minmax(0,1fr) auto', alignItems: 'center', gap: 16, minHeight: 72, padding: '12px 0', borderBottom: '1px solid var(--line)' }}>
                <span style={{ font: '500 13px/1 var(--font-mono)', color: 'var(--muted)' }}>{st.idx}</span>
                <span style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
                  <span style={{ fontSize: 16.5, fontWeight: 500, letterSpacing: '-0.01em' }}>{st.title}</span>
                  <span style={{ fontSize: 14, color: 'var(--muted)', textWrap: 'pretty' }}>{st.sub}</span>
                </span>
                <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 14 }}>
                  <span style={{ padding: '4px 7px', borderRadius: 4, background: st.chipBg, color: st.chipInk, font: '500 11px/1 var(--font-mono)', letterSpacing: '.06em', textTransform: 'uppercase', whiteSpace: 'nowrap' }}>{st.status}</span>
                  {st.isNext && <a className="btn btn-primary" href="#" onClick={e => { e.preventDefault(); st.go(); }} style={{ height: 48 }}>{st.action}</a>}
                  {st.isLater && <button onClick={st.go} className="hvr-ink-border" style={{ height: 40, padding: '0 14px', border: '1px solid var(--line)', borderRadius: 8, background: 'var(--paper)', fontSize: 14, fontWeight: 500, whiteSpace: 'nowrap', cursor: 'pointer' }}>{st.action} →</button>}
                  {st.canSkip && <button onClick={st.skip} className="hvr-skip" style={{ fontSize: 14, paddingBottom: 1, border: 'none', borderBottom: '1px solid var(--line)', borderRadius: 0, cursor: 'pointer' }}>Skip</button>}
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}

      {offCams.length > 0 && (
        <div role="status" style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '10px 12px 10px 16px', background: 'var(--danger-tint)', border: '1px solid var(--line)', borderRadius: 8, color: 'var(--danger-deep)' }}>
          <span style={{ width: 8, height: 8, flexShrink: 0, background: 'var(--danger-deep)' }} />
          <span style={{ flex: 1, fontSize: 15 }}><strong style={{ fontWeight: 600 }}>{offCams.map(c => c.label).join(', ')}</strong> has been offline since {offCams[0] ? offCams[0].since : ''}. {admin ? "Check the camera's power and network cable." : "Nothing is saved from it until it's back, and your admin can check it."}</span>
          {admin && <button onClick={() => navTo('cameras', { view: 'page', cam: offCams[0] ? offCams[0].num : 16 })} className="hvr-ink-border" style={{ height: 36, padding: '0 14px', border: '1px solid var(--line)', borderRadius: 8, background: 'var(--paper)', color: 'var(--ink)', fontSize: 14, fontWeight: 500, whiteSpace: 'nowrap', cursor: 'pointer' }}>Open camera →</button>}
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span style={{ font: '500 11px/1.3 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--muted)' }}>{`Wed ${I.dateShort(0)} · ${I.clock(now)} site time`}</span>
        <h1 style={{ margin: 0, fontSize: 30, fontWeight: 500, letterSpacing: '-0.025em', lineHeight: 1.1 }}>Today so far</h1>
      </div>

      {!scen.noCams && (
        <React.Fragment>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0,1fr))', gap: 16 }}>
            <button onClick={() => openSearch({ preset: 'today', types: { person: true, vehicle: false, other: false } })} className="hvr-stat" style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 10, padding: '20px 22px', textAlign: 'left', background: 'var(--bone)', border: '1px solid var(--line)', borderRadius: 14, cursor: 'pointer' }}>
              <span style={{ alignSelf: 'flex-start', padding: '5px 8px', borderRadius: 4, background: 'var(--sky-tint)', font: '500 11px/1 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--sky-deep)' }}>People seen</span>
              <span style={{ color: 'var(--ink)', fontFamily: 'var(--font-serif)', fontStyle: 'italic', fontWeight: 400, fontSize: 60, lineHeight: 0.95, letterSpacing: '-0.02em' }}>{people}</span>
              <div aria-hidden="true" style={{ display: 'flex', alignItems: 'flex-end', gap: 2, width: '100%', height: 34 }}>
                {I.hourBars(todayEv, 'person', 'var(--sky)', now).map((b, i) => <span key={i} style={{ flex: 1, height: b.h, borderRadius: 1, background: b.c }} />)}
              </div>
              <span style={{ fontSize: 13.5, color: 'var(--muted)', textWrap: 'pretty' }}>{cmpY(people, yP)}</span>
              <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, width: '100%', fontSize: 14, color: 'var(--muted)' }}><span>{`Since ${I.clock(since)}`}</span><span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, color: 'var(--blue-deep)', fontWeight: 600, whiteSpace: 'nowrap' }}>Open in Search <OpenSearchIcon /></span></span>
            </button>
            <button onClick={() => openSearch({ preset: 'today', types: { person: false, vehicle: true, other: false } })} className="hvr-stat" style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 10, padding: '20px 22px', textAlign: 'left', background: 'var(--bone)', border: '1px solid var(--line)', borderRadius: 14, cursor: 'pointer' }}>
              <span style={{ alignSelf: 'flex-start', padding: '5px 8px', borderRadius: 4, background: 'var(--honey-tint)', font: '500 11px/1 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--honey-deep)' }}>Vehicles seen</span>
              <span style={{ color: 'var(--ink)', fontFamily: 'var(--font-serif)', fontStyle: 'italic', fontWeight: 400, fontSize: 60, lineHeight: 0.95, letterSpacing: '-0.02em' }}>0</span>
              <div aria-hidden="true" style={{ display: 'flex', alignItems: 'flex-end', gap: 2, width: '100%', height: 34 }}>
                {I.hourBars([], 'vehicle', 'var(--honey)', now).map((b, i) => <span key={i} style={{ flex: 1, height: b.h, borderRadius: 1, background: b.c }} />)}
              </div>
              <span style={{ fontSize: 13.5, color: 'var(--muted)', textWrap: 'pretty' }}>No vehicle events recorded</span>
              <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, width: '100%', fontSize: 14, color: 'var(--muted)' }}><span>{`Since ${I.clock(since)}`}</span><span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, color: 'var(--blue-deep)', fontWeight: 600, whiteSpace: 'nowrap' }}>Open in Search <OpenSearchIcon /></span></span>
            </button>
            <button onClick={() => navTo('cameras', { offlineFirst: offCams.length > 0 })} className="hvr-stat" style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 10, padding: '20px 22px', textAlign: 'left', background: 'var(--bone)', color: 'var(--ink)', border: '1px solid var(--line)', borderRadius: 14, cursor: 'pointer' }}>
              <span style={{ alignSelf: 'flex-start', padding: '5px 8px', borderRadius: 4, background: offCams.length ? 'var(--danger-tint)' : 'var(--success-tint)', font: '500 11px/1 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', color: offCams.length ? 'var(--danger-deep)' : 'var(--success-deep)' }}>Cameras online</span>
              <span style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                <span style={{ color: 'var(--ink)', fontFamily: 'var(--font-serif)', fontStyle: 'italic', fontWeight: 400, fontSize: 60, lineHeight: 0.95, letterSpacing: '-0.02em' }}>{cams.length - offCams.length}</span>
                <span style={{ fontSize: 22, color: 'var(--muted)', whiteSpace: 'nowrap' }}>of {cams.length}</span>
              </span>
              <div aria-hidden="true" style={{ display: 'flex', gap: 3, width: '100%', height: 34, alignItems: 'flex-end' }}>
                {cams.map(c => <span key={c.num} style={{ flex: 1, height: 14, borderRadius: 2, background: c.status === 'offline' ? 'var(--danger)' : 'var(--success)' }} />)}
              </div>
              <span style={{ fontSize: 14, color: 'var(--muted)' }}>{offCams.length ? `${offCams[0].label} offline since ${offCams[0].since}` : 'Every camera is online'} · Open Cameras →</span>
            </button>
            {admin ? (
              <button onClick={() => navTo('settings', { section: 'storage' })} className="hvr-stat" style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 10, padding: '20px 22px', textAlign: 'left', background: 'var(--bone)', border: '1px solid var(--line)', borderRadius: 14, cursor: 'pointer' }}>
                <span style={{ alignSelf: 'flex-start', padding: '5px 8px', borderRadius: 4, background: 'var(--blue-tint)', font: '500 11px/1 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--blue-deep)' }}>Space saved</span>
                <span style={{ color: 'var(--ink)', fontFamily: 'var(--font-serif)', fontStyle: 'italic', fontWeight: 400, fontSize: 60, lineHeight: 0.95, letterSpacing: '-0.02em' }}>0</span>
                <div aria-hidden="true" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', gap: 4, width: '100%', height: 34 }}>
                  <div style={{ height: 9, borderRadius: 2, background: 'var(--paper-3)' }} />
                  <div style={{ height: 9, borderRadius: 2, background: 'var(--paper-2)' }}><div style={{ width: '100%', height: '100%', borderRadius: 2, background: 'var(--blue)' }} /></div>
                </div>
                <span style={{ fontSize: 14, color: 'var(--muted)' }}>0 saved · Open Storage →</span>
              </button>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 10, padding: '20px 22px', background: 'var(--bone)', border: '1px solid var(--line)', borderRadius: 14 }}>
                <span style={{ alignSelf: 'flex-start', padding: '5px 8px', borderRadius: 4, background: 'var(--blue-tint)', font: '500 11px/1 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--blue-deep)' }}>Space saved</span>
                <span style={{ color: 'var(--ink)', fontFamily: 'var(--font-serif)', fontStyle: 'italic', fontWeight: 400, fontSize: 60, lineHeight: 0.95, letterSpacing: '-0.02em' }}>0</span>
                <div aria-hidden="true" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', gap: 4, width: '100%', height: 34 }}>
                  <div style={{ height: 9, borderRadius: 2, background: 'var(--paper-3)' }} />
                  <div style={{ height: 9, borderRadius: 2, background: 'var(--paper-2)' }}><div style={{ width: '100%', height: '100%', borderRadius: 2, background: 'var(--blue)' }} /></div>
                </div>
                <span style={{ fontSize: 14, color: 'var(--muted)' }}>0 saved. The box keeps only the moments people or vehicles appear.</span>
              </div>
            )}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(320px, 30%)', gap: 16, alignItems: 'start' }}>
            <section aria-label="Activity by camera" style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 12, padding: '18px 20px 16px', background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: 14 }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px 16px' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 260, flex: 1 }}>
                  <h2 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 12, fontSize: 17, fontWeight: 500, letterSpacing: '-0.01em' }}>
                    Activity by camera <span style={{ padding: '4px 7px', borderRadius: 4, background: 'var(--blue-tint)', color: 'var(--blue-deep)', font: '500 10px/1 var(--font-mono)', letterSpacing: '.05em' }}>Total activity: {todayEv.length}</span>
                    {scen.since != null && dOff === 0 && <span style={{ padding: '4px 7px', borderRadius: 4, background: 'var(--paper-2)', font: '500 11px/1 var(--font-mono)', letterSpacing: '.04em', color: 'var(--ink)' }}>{'Watching since ' + I.clock(scen.since)}</span>}
                  </h2>
                  <span style={{ fontSize: 13.5, color: 'var(--muted)', textWrap: 'pretty' }}>Each mark is a moment people or vehicles appeared, and darker marks are busier. Click one to open it in Search.</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div role="group" aria-label="Day" style={{ display: 'flex', gap: 2, padding: 3, background: 'var(--paper-2)', border: '1px solid var(--line-soft)', borderRadius: 8 }}>
                    {days.map(d => (
                      <button key={d.key} onClick={d.set} style={{ height: 34, padding: '0 12px', borderRadius: 6, fontSize: 14, fontWeight: d.weight, background: d.bg, color: d.ink, boxShadow: d.ring, border: 'none', cursor: 'pointer' }}>{d.label}</button>
                    ))}
                  </div>
                  {hDay === 'date' && (
                    <div style={{ position: 'relative' }}>
                      <button onClick={() => setHCal(v => !v)} aria-expanded={hCal} className="hvr-ink-border" style={{ height: 40, display: 'flex', alignItems: 'center', gap: 10, padding: '0 12px', border: `1px solid ${hCal ? 'var(--blue)' : 'var(--line)'}`, borderRadius: 8, background: 'var(--paper)', fontSize: 14, whiteSpace: 'nowrap', cursor: 'pointer' }}>{I.dayLong(dOff)}<span style={{ fontSize: 11, color: 'var(--muted)' }}>▾</span></button>
                      {hCal && (
                        <div style={{ position: 'absolute', top: 'calc(100% + 6px)', right: 0, zIndex: 40, width: 380, padding: 16, background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: 14, boxShadow: '0 30px 60px -30px rgba(10,10,11,.35), 0 2px 6px rgba(10,10,11,.06)' }}>
                          <InetraMonthCalendar size="compact" cams={null} selA={dOff} selB={dOff} onPick={off => { setHDayOff(off); setHDay(off === 0 ? 'today' : off === -1 ? 'yesterday' : 'date'); setHCal(false); }} />
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
              {/* midnightNote only for scen midnight (not wired yet in 'day') */}
              <div style={{ display: 'grid', gridTemplateColumns: '184px minmax(0,1fr) 44px', gap: 12, alignItems: 'end', marginTop: 4 }}>
                <span />
                <div style={{ position: 'relative', height: 12 }}>
                  {[0, 3, 6, 9, 12, 15, 18, 21, 24].map((hh, i) => (
                    <span key={i} style={{ position: 'absolute', top: 0, left: (hh / 24 * 100) + '%', transform: `translateX(${i === 0 ? '0' : i === 8 ? '-100%' : '-50%'})`, font: '500 11px/1 var(--font-mono)', color: 'var(--muted)', whiteSpace: 'nowrap' }}>{I.hourLabel(hh * H)}</span>
                  ))}
                </div>
                <span style={{ textAlign: 'right', font: '500 10px/1 var(--font-mono)', letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--muted)' }}>Events</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                {groups.map(g => (
                  <React.Fragment key={g.name}>
                    <div style={{ height: 32, display: 'flex', alignItems: 'flex-end', gap: 8, paddingBottom: 6, marginTop: 8, font: '500 10.5px/1 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--muted)' }}>
                      <span style={{ padding: '4px 7px', borderRadius: 4, background: g.toneBg, color: g.toneInk }}>{g.name}</span>
                      <span style={{ paddingBottom: 4 }}>{g.count}</span>
                    </div>
                    {g.rows.map(r => (
                      <div key={r.num} style={{ display: 'grid', gridTemplateColumns: '184px minmax(0,1fr) 44px', gap: 12, alignItems: 'center', height: 27 }}>
                        <button onClick={r.open} title={`Search ${r.num} ${r.name}`} className="hvr-underline" style={{ height: '100%', minWidth: 0, display: 'flex', alignItems: 'center', gap: 8, textAlign: 'left', fontSize: 14, background: 'transparent', border: 'none', cursor: 'pointer' }}>
                          <span style={{ width: 20, flexShrink: 0, font: '500 12.5px/1 var(--font-mono)', color: 'var(--muted)' }}>{r.num}</span>
                          <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.name}</span>
                          {r.isOff && <span style={{ flexShrink: 0, padding: '3px 5px', borderRadius: 4, background: 'var(--danger-tint)', color: 'var(--danger-deep)', font: '500 10px/1 var(--font-mono)', letterSpacing: '.06em', textTransform: 'uppercase' }}>Offline</span>}
                        </button>
                        <InetraStrip times={r.times} start={dStart} end={dStart + DAY} now={dOff === 0 ? now : null} bin={300} offline={r.offline} height={18} axis={false} onPick={r.pick} />
                        <span style={{ textAlign: 'right', font: '500 13px/1 var(--font-mono)' }}>{r.cnt}</span>
                      </div>
                    ))}
                  </React.Fragment>
                ))}
              </div>
              {dOff === 0 && (
                <div style={{ display: 'grid', gridTemplateColumns: '184px minmax(0,1fr) 44px', gap: 12 }}>
                  <span />
                  <div style={{ position: 'relative', height: 22 }}>
                    <span style={{ position: 'absolute', top: 2, left: (nf * 100) + '%', transform: `translateX(${nf < 0.05 ? '0' : nf > 0.95 ? '-100%' : '-50%'})`, padding: '4px 7px', borderRadius: 4, background: 'var(--ink)', color: 'var(--paper)', font: '500 11px/1 var(--font-mono)', whiteSpace: 'nowrap' }}>{`Now · ${I.clock(now)}`}</span>
                  </div>
                  <span />
                </div>
              )}
            </section>
            <section aria-label="Latest events" style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 6, padding: '18px 12px 12px', background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: 14 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '0 8px 6px' }}>
                <h2 style={{ margin: 0, fontSize: 17, fontWeight: 500, letterSpacing: '-0.01em' }}>Latest events</h2>
                <span style={{ display: 'flex', alignItems: 'center', gap: 7, font: '500 10.5px/1 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--muted)' }}>
                  <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--signal)', boxShadow: '0 0 0 1px var(--ink)' }} />Updates as they arrive
                </span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                {todayEv.slice(0, 5).map(e => {
                  const ev = card(e);
                  return <InetraEventCard key={ev.id} ev={ev} variant="row" selectable={false} onPlay={async () => { try { setPlayingEvent(await fetchEvent(ev.eventId)); } catch (_) { setPlayingEvent(ev); } }} />;
                })}
              </div>
      {playingEvent && <div role="dialog" aria-modal="true" onClick={() => setPlayingEvent(null)} style={{ position: 'fixed', inset: 0, zIndex: 2000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20, background: 'rgba(0,0,0,.65)' }}><div onClick={e => e.stopPropagation()} style={{ width: 'min(900px, 95vw)', padding: 18, borderRadius: 12, background: 'var(--paper)' }}><div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}><strong>{playingEvent.object_class || 'Event'} · {playingEvent.camera_name || playingEvent.camera_id}</strong><button type="button" onClick={() => setPlayingEvent(null)}>Close</button></div>{playingEvent.clip_path ? <video controls autoPlay src={getEventClipUrl(playingEvent.event_id)} style={{ width: '100%', maxHeight: '70vh', background: '#111' }} /> : <p style={{ color: 'var(--muted)' }}>The clip is not available for this event.</p>}</div></div>}
              <div style={{ marginTop: 4, padding: '12px 8px 4px', borderTop: '1px solid var(--line-soft)' }}>
                <a href="#" onClick={e => { e.preventDefault(); openSearch({ preset: 'today' }); }} style={{ height: 26, minHeight: 26, display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 14.5, fontWeight: 500, color: 'var(--ink)', textDecoration: 'none', borderBottom: '1px solid var(--line)' }} onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--ink)'; }} onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--line)'; }}>See all of today's events in Search</a>
              </div>
            </section>
          </div>
        </React.Fragment>
      )}
    </div>
  );
}
