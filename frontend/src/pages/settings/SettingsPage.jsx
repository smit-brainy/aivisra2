/**
 * SettingsPage — i-Netra Settings screen port.
 * Powered by `window.INVR` sample data (`SCEN.day` scenario).
 * Mirrors the prototype's `out.u` context from the controller's `renderVals()`.
 *
 * Sections (tabs): storage | space | capacity | users | about
 * Each section renders from INVR merged data with `merged('day', {})`.
 *
 * Props: openSearch(opts), navTo(t, opts) — same signatures as HomePage
 */
import React, { useEffect, useRef, useState } from 'react';
import { invr, merged } from '../../prototype/api';

export default function SettingsPage({ session, openSearch, navTo }) {
  const admin = session.role === 'admin';
  const I = invr();
  const M = merged('day', {});
  const CAM = M.CAM;
  const cams = M.cams || [];
  const SCEN = M.SCEN?.day || { now: 40800, offline: {}, gaps: {}, space: { pct: '84%', kept: '38 GB', recv: '241 GB' } };
  const users = M.users || { admin: { name: 'Karan Joshi', role: 'Admin', initials: 'KJ' }, operator: { name: 'Ravi Desai', role: 'Operator', initials: 'RD' }, neha: { name: 'Neha Shah', role: 'Operator', initials: 'NS' } };

  // State per section
  const [section, setSection] = useState('storage'); // storage | space | capacity | users | about
  const [refused, setRefused] = useState(false);
  const [diskFull, setDiskFull] = useState(false);

  // --- Storage section state ---
  const [keepDays, setKeepDays] = useState(30);
  const [isDays, setIsDays] = useState(true);
  const [daysVal, setDaysVal] = useState(30);
  const [diskW, setDiskW] = useState(90);
  const [diskFill, setDiskFill] = useState('#e53935');
  const [diskUsed, setDiskUsed] = useState('7.6 TB');
  const [diskFree, setDiskFree] = useState('8 TB');
  const [diskBorder, setDiskBorder] = useState('1px solid var(--line)');
  const [diskBg, setDiskBg] = useState('var(--paper-2)');
  const [daysBorder, setDaysBorder] = useState('1px solid var(--line)');
  const [daysBg, setDaysBg] = useState('var(--paper-2)');
  const [daysDot, setDaysDot] = useState('#4caf50');
  const [diskDot, setDiskDot] = useState('#4caf50');

  // --- Space section state ---
  const [spPct, setSpPct] = useState('84%');
  const [spRecv, setSpRecv] = useState('241 GB');
  const [spKept, setSpKept] = useState('38 GB');
  const [spKeptW, setSpKeptW] = useState('0%');
  const [spScope, setSpScope] = useState('All cameras');
  const [spSentence, setSpSentence] = useState('Recording all video on lobby corridor 11:20 AM would have used 241 GB. i-Netra kept 38 GB of clips.');
  const [spCamF, setSpCamF] = useState('all');
  const [spTable, setSpTable] = useState(true);
  const [spRows, setSpRows] = useState([]);
  const [spFromNote, setSpFromNote] = useState(false);

  // --- Capacity section state ---
  const [capIdle, setCapIdle] = useState(true);
  const [capRunning, setCapRunning] = useState(false);
  const [capW, setCapW] = useState(0);
  const [capLeft, setCapLeft] = useState('15');
  const [capStart, setCapStart] = useState('now');
  const [usedPct, setUsedPct] = useState('42%');
  const [freeText, setFreeText] = useState('4.2 GB free');
  const [usedParts, setUsedParts] = useState([
    { w: 40, c: '#c62828', label: 'Low' },
    { w: 30, c: '#e65100', label: 'Standard' },
    { w: 20, c: '#f9a825', label: 'High' },
  ]);
  const [capRows, setCapRows] = useState([
    { num: 1, name: 'Main gate entry', area: 'Gates and fence', level: 'standard', checks: 10, prio: false,
      prioBg: 'var(--paper)', prioKnob: '50', prioText: 'Normal', prioImg: '' },
    { num: 2, name: 'Main gate exit', area: 'Gates and fence', level: 'standard', checks: 8, prio: false,
      prioBg: 'var(--paper)', prioKnob: '50', prioText: 'Normal', prioImg: '' },
  ]);
  const [capBulk, setCapBulk] = useState([
    { label: 'Low', bg: '#c62828', set: () => {} },
    { label: 'Standard', bg: '#e65100', set: () => {} },
    { label: 'High', bg: '#f9a825', set: () => {} },
    { label: 'Maximum', bg: '#5d8a66', set: () => {} },
  ]);

  // --- Users section state ---
  const [usersList, setUsersList] = useState([]);
  const [newName, setNewName] = useState(''); const [newUser, setNewUser] = useState(''); const [newRole, setNewRole] = useState('Operator');
  const [newTemp, setNewTemp] = useState('plant2-abc-def-55');

  // Initialize from INVR data
  useEffect(() => {
    if (!I) return;
    // Storage info from SCEN.space
    const space = SCEN.space || { pct: '84%', kept: '38 GB', recv: '241 GB' };
    setSpPct(space.pct);
    setSpRecv(space.recv);
    setSpKept(space.kept);

    // Disk info - use prototype's offline data
    const offline = SCEN.offline || {};
    const offlineCams = Object.keys(offline).map(k => +k).filter(k => offline[k]);
    const onlineCams = cams.filter(c => !offlineCams.includes(c.num));
    const total = cams.length;
    const online = onlineCams.length;
    const usedGB = Math.round((total - online) * 0.5 + 2); // simulated
    const totalGB = 8;
    setDiskUsed(`${usedGB} TB`);
    setDiskFree(`${totalGB} TB`);

    // Capacity data
    setCapIdle(true);
    setUsedPct('42%');
    setFreeText('4.2 GB free');

    // Users from INVR
    const userEntries = [];
    if (users.admin) userEntries.push({ ...users.admin, z: 3, acc: 'Full admin', accBg: '#e3f2fd', accInk: '#1565c0' });
    if (users.operator) userEntries.push({ ...users.operator, z: 2, acc: 'Standard', accBg: '#fff3e0', accInk: '#f57c00' });
    if (users.neha) userEntries.push({ ...users.neha, z: 1, acc: 'Standard', accBg: '#fff3e0', accInk: '#f57c00' });
    setUsersList(userEntries);
  }, [I, cams, SCEN, users]);

  // Helper: render a setting card
  const SettingCard = ({ title, children }) => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '22px 24px', background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: 14 }}>
      <span style={{ font: '500 11px/1.3 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--muted)' }}>{title}</span>
      {children}
    </div>
  );

  // Helper: radio button style
  const radioStyle = (checked, border, bg) => ({
    display: 'grid', gridTemplateColumns: '22px minmax(0,1fr)', gap: '14px', alignItems: 'start',
    padding: '14px', border: border, borderRadius: 8, background: bg, cursor: 'pointer'
  });

  const knobStyle = (val) => ({ width: val + 'px', height: '16px', borderRadius: '50%', background: 'var(--paper)', boxShadow: '0 1px 2px rgba(10,10,11,.3)' });

  // --- Storage Render ---
  const renderStorage = () => (
    <SettingCard title="Keep clips for">
      <div style={{ display: 'grid', gridTemplateColumns: '22px minmax(0,1fr)', gap: '14px', alignItems: 'start', padding: '14px', border: daysBorder, borderRadius: 8, background: daysBg, cursor: 'pointer' }}
        onClick={() => setIsDays(v => !v)} style={{ marginBottom: 8 }}>
        <span style={{ width: 20, height: 20, marginTop: 10, borderRadius: 50, border: '1.5px solid ' + daysDot, display: 'flex', alignItems: 'center', justifyContent: 'center', background: daysDot } } />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <span style={{ fontSize: 16, fontWeight: 500 }}>Keep clips for</span>
          <span style={{ fontSize: 14, color: 'var(--muted)' }}>Each night the box removes clips older than this, oldest day first.</span>
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '22px minmax(0,1fr)', gap: '14px', alignItems: 'start', marginTop: 8, padding: '14px', border: isDays ? diskBorder : '1px solid var(--line-soft)', borderRadius: 8, background: isDays ? diskBg : 'var(--paper-2)', cursor: 'pointer' }}
        onClick={() => setIsDays(v => !v)}>
        <span style={{ width: 20, height: 20, marginTop: 1, borderRadius: 50, border: '1.5px solid ' + diskDot, display: 'flex', alignItems: 'center', justifyContent: 'center', background: diskDot } } />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ fontSize: 16, fontWeight: 500 }}>As long as the disk has room</span>
          <span style={{ fontSize: 14, color: 'var(--muted)' }}>The box removes the oldest day first whenever the disk fills.</span>
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginTop: '12px', padding: '12px 14px', background: 'var(--paper-2)', borderRadius: 8, fontSize: 15 }}>
        <span style={{ width: 6, height: 6, flexShrink: 0, background: '#2196f3' }} />
        <span style={{ fontSize: 16, fontWeight: 500 }}>About 90 days of clips fit at today's activity.</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: 14 }}>
        <button style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)', fontSize: 14, fontWeight: 500 }} onClick={() => setKeepDays(v => Math.max(1, v - 1))}>−</button>
        <input value={daysVal} onChange={e => setDaysVal(parseInt(e.target.value))} className="fcs-input" style={{ width: '84px', height: '40px', padding: '0 10px', border: '1px solid var(--line)', borderRadius: 8, textAlign: 'center', font: '500 17px/1 var(--font-mono)', outline: 'none' }} />
        <button style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)', fontSize: 14, fontWeight: 500 }} onClick={() => setKeepDays(v => v + 1)}>+</button>
        <span style={{ fontSize: 16, fontWeight: 500 }}>days</span>
      </div>
      <div style={{ marginTop: 14, display: 'flex', alignItems: 'center', gap: '12px' }}>
        <button style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)', fontSize: 14, fontWeight: 500 }} onClick={() => { setRefused(true); }}>Save changes</button>
        <button className="hvr-ink-border" style={{ height: '48px', padding: '0 18px', border: '1px solid var(--line)', borderRadius: 999, fontSize: 15, fontWeight: 500 }} onClick={() => { setRefused(false); }}>Undo</button>
      </div>
    </div>
  );

  // --- Space Render ---
  const renderSpace = () => (
    <SettingCard title="Storage period">
      <div style={{ display: 'flex', gap: 2, padding: '3px', background: 'var(--paper-2)', border: '1px solid var(--line-soft)', borderRadius: 8 }}>
        {/* Period presets */}
      </div>
      <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '24px 32px', alignItems: 'center', padding: '26px 28px', background: 'var(--bone)', border: '1px solid var(--line)', borderRadius: 14 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <span style={{ font: '500 11px/1.3 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--muted)' }}>{{ spScope }}</span>
          <span style={{ display: 'flex', alignItems: 'baseline', gap: '12px' }}>
            <span style={{ fontFamily: 'var(--font-serif)', fontStyle: 'italic', fontSize: '96px', lineHeight: '.9', letterSpacing: '-0.02em' }}>{spPct}</span>
            <span style={{ fontSize: '18px', color: 'var(--muted)' }}>saved</span>
          </span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <p style={{ margin: '0', fontSize: '18px', lineHeight: '1.5', textWrap: 'pretty' }}>{{ spSentence }}</p>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '14px' }}>
            <span>Recording all video</span><span style={{ fontFamily: 'var(--font-mono)' }}>{spRecv}</span>
          </div>
          <div style={{ height: '10px', borderRadius: '3px', background: 'var(--paper-3)' }}>
            <div style={{ width: '65%', height: '100%', background: '#1976d2', borderRadius: '3px' }} />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '14px' }}>
            <span>Clips i-Netra kept</span><span style={{ fontFamily: 'var(--font-mono)' }}>{spKept}</span>
          </div>
          <div style={{ height: '10px', borderRadius: '3px', background: 'var(--paper-2)' }}>
            <div style={{ width: '16%', height: '100%', background: '#1976d2', borderRadius: '3px' }} />
          </div>
        </div>
      </section>
      {spTable && (
        <section style={{ display: 'flex', flexDirection: 'column', background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: '14px', overflow: 'hidden' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(170px, 1.4fr) 90px 90px 64px minmax(80px, 1fr) minmax(180px, 1.6fr)', gap: '16px', alignItems: 'center', height: '40px', padding: '0 20px', background: 'var(--bone)', borderBottom: '1px solid var(--line)', font: '500 10.5px/1 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--muted)' }}>
            <span>Camera</span><span>Received</span><span>Kept</span><span>Saved</span><span></span><span>Why it differs</span>
          </div>
          {spRows.map((r, i) => (
            <div key={i} style={{ display: 'grid', gridTemplateColumns: 'minmax(170px, 1.4fr) 90px 90px 64px minmax(80px, 1fr) minmax(180px, 1.6fr)', gap: '16px', alignItems: 'center', minHeight: '48px', padding: '6px 20px', borderBottom: '1px solid var(--line-soft)', fontSize: '14.5px' }}>
              <span><span style={{ fontFamily: 'var(--font-mono)', color: 'var(--muted)', marginRight: '8px' }}>{r.num}</span>{{ r.name }}</span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{r.recv}</span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{r.kept}</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{r.pct}</span>
              <span style={{ height: '8px', borderRadius: '2px', background: 'var(--paper-2)' }}><span style={{ display: 'block', width: r.w, height: '100%', borderRadius: '2px', background: r.fill }} /></span>
              <span style={{ fontSize: '13.5', color: 'var(--muted)', textWrap: 'pretty' }}>{r.why}</span>
            </div>
          ))}
          {(!spRows.length || spTable) && (
            <div style={{ textAlign: 'center', padding: '16px 0', color: 'var(--muted)' }}>No camera rows to display</div>
          )}
        </section>
      )}
      {spFromNote && (
        <p style={{ margin: '0', fontSize: '14.5', color: 'var(--muted)' }}>Opened from Search with the same camera and time. Pick a period above to see every camera.</p>
      )}
    </div>
  );

  // --- Capacity Render ---
  const renderCapacity = () => (
    <SettingCard title="Capacity check">
      <span style={{ font: '500 11px/1.3 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--muted)' }}>Capacity check</span>
      {capIdle && (
        <h3 style={{ margin: '0', fontSize: '22px', fontWeight: '500', letterSpacing: '-0.02em', lineHeight: '1.25' }}>This box can watch about 30 cameras at Standard detail.</h3>
        <span style={{ font: '500 12.5px/1.3 var(--font-mono)', color: 'var(--muted)' }}>{{ capWhen }}</span>
        <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '12px', marginTop: '4px' }}>
          <button className="hvr-ink-border" style={{ height: '42px', padding: '0 16px', border: '1px solid var(--line)', borderRadius: 8, background: 'var(--paper)', fontSize: '14.5', fontWeight: 500 }}>Run the check again</button>
          <span style={{ fontSize: '13.5', color: 'var(--muted)' }}>Takes up to 15 minutes.</span>
        </div>
      )}
      {capRunning && (
        <div style={{ height: '6px', borderRadius: '3px', background: 'var(--paper-3)' }}>
          <div style={{ width: capW, height: '100%', background: '#1976d2' }} />
        </div>
        <span style={{ font: '500 12.5px/1.3 var(--font-mono)', color: 'var(--muted)' }}>{{ capLeft }} · Started {{ capStart }}</span>
        <span style={{ fontSize: '14', color: 'var(--muted)' }}>Cameras keep being watched while it runs.</span>
      )}
    </div>
    <SettingCard title="AI capacity">
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '16px' }}>
        <section style={{ display: 'flex', flexDirection: 'column', gap: '12px', padding: '22px 24px', background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: 14 }}>
          <span style={{ font: '500 11px/1.3 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--muted)' }}>AI capacity</span>
          <span style={{ display: 'flex', alignItems: 'baseline', gap: '10px' }}>
            <span style={{ fontFamily: 'var(--font-serif)', fontStyle: 'italic', fontSize: '56px', lineHeight: '.95' }}>{{ usedPct }}</span>
            <span style={{ fontSize: '18px', color: 'var(--muted)' }}>in use</span>
          </span>
          <div style={{ height: '14px', display: 'flex', gap: '2px', borderRadius: '3px', background: 'var(--paper-3)' }}>
            {usedParts.map((u, i) => (
              <div key={i} style={{ width: u.w, height: '100%', background: u.c }} />
            ))}
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 14px' }}>
            {usedParts.map((u, i) => (
              <span key={i} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}>
                <span style={{ width: '10px', height: '10px', borderRadius: '2px', background: u.c, flexShrink: 0 }} />
                {{ u.label }} · {{ u.n }}
              </span>
            ))}
          </div>
          <span style={{ fontSize: '14.5' }}>{freeText}</span>
        </section>
        <section style={{ display: 'flex', flexDirection: 'column', gap: '12px', padding: '22px 24px', background: 'var(--bone)', border: '1px solid var(--line)', borderRadius: 14 }}>
          <span style={{ font: '500 11px/1.3 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--muted)' }}>Detail level for each camera</span>
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(170px, 1.3fr) minmax(100px, 1fr) minmax(300px, 2fr) 150px', gap: '16px', alignItems: 'center', height: '38px', padding: '0 20px', background: 'var(--bone)', borderBottom: '1px solid var(--line)', font: '500 10.5px/1 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--muted)' }}>
            <span>Camera</span><span>Area</span><span>How often the AI checks</span><span>Priority</span>
          </div>
          {capRows.map((r, i) => (
            <div key={i} style={{ display: 'grid', gridTemplateColumns: 'minmax(170px, 1.3fr) minmax(100px, 1fr) minmax(300px, 2fr) 150px', gap: '16px', alignItems: 'center', minHeight: '64px', padding: '8px 20px', borderBottom: '1px solid var(--line-soft)', fontSize: '14.5px' }}>
              <span><span style={{ fontFamily: 'var(--font-mono)', color: 'var(--muted)', marginRight: '8px' }}>{r.num}</span>{{ r.name }}</span>
              <span style={{ justifySelf: 'start', padding: '4px 7px', borderRadius: '4px', background: r.areaBg, color: r.areaInk, font: '500 11px/1 var(--font-mono)', letterSpacing: '.06em', textTransform: 'uppercase', whiteSpace: 'nowrap' }}>{{ r.area }}</span>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0,1fr))', gap: '2px', padding: '3px', background: 'var(--paper-2)', border: '1px solid var(--line-soft)', borderRadius: '8px' }}>
                {[{ label: 'Low', bg: '#c62828', weight: 400 }, { label: 'Standard', bg: '#e65100', weight: 500 }, { label: 'High', bg: '#f9a825', weight: 600 }, { label: 'Maximum', bg: '#5d8a66', weight: 700 }].map((l, j) => (
                  <button key={j} style={{ height: '32px', borderRadius: '6px', fontSize: '13.5', fontWeight: l.weight, background: l.bg, color: 'var(--ink)' }} onClick={() => { }}>{l.label}</button>
                ))}
              </div>
              <button onClick={() => { }} ariaPressed={r.prio} style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span style={{ position: 'relative', width: '36px', height: '22px', borderRadius: '999', background: r.prioBg, flexShrink: 0 }} />
                {{ r.prioText }}
              </button>
            </div>
          ))}
        </section>
      </div>
    </div>
  );

  // --- Users Render ---
  const renderUsers = () => (
    <SettingCard title="Users">
      <section style={{ display: 'flex', flexDirection: 'column', background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: '14px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(180px, 1.4fr) minmax(120px, 1fr) 90px minmax(150px, 1.1fr) 160px 110px', gap: '16px', alignItems: 'center', height: '40px', padding: '0 20px', background: 'var(--bone)', borderBottom: '1px solid var(--line)', borderRadius: '14px 14px 0 0', font: '500 10.5px/1 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--muted)' }}>
          <span>Name</span><span>Username</span><span>Role</span><span>Last sign-in</span><span>Access</span><span></span>
        </div>
        {usersList.map((u, i) => (
          <div key={i} style={{ position: 'relative', display: 'grid', gridTemplateColumns: 'minmax(180px, 1.4fr) minmax(120px, 1fr) 90px minmax(150px, 1.1fr) 160px 110px', gap: '16px', alignItems: 'center', minHeight: '64px', padding: '8px 20px', borderBottom: '1px solid var(--line-soft)', fontSize: '14.5px', zIndex: u.z } }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '12px', minWidth: '0' }}>
              <span style={{ width: '34px', height: '34px', flexShrink: 0, borderRadius: '50', display: 'flex', alignItems: 'center', justifyContent: 'center', background: u.avBg, color: u.avInk, font: '600 12px/1 var(--font-mono)' }}>{{ u.initials }}</span>
              <span style={{ display: 'flex', flexDirection: 'column', gap: '2', minWidth: '0' }}>
                <span style={{ fontWeight: '500' }}{{ u.name }}{{ u.you && <span style={{ fontSize: '12.5', color: 'var(--muted)' }}>You</span> }}{{ /span }}
              </span>
            </span>
            <span style={{ font: '500 13px/1 var(--font-mono)' }}{{ u.username }}{{ /span }}
            <span justifySelf="start" padding="4px 7px" borderRadius="4" background={{ u.roleBg }} color={{ u.roleInk }} font="500 11px/1 var(--font-mono)" letterSpacing=".06em" textTransform="uppercase" }}{{ u.role }}{{ /span }}
            <span style={{ color: 'var(--muted)' }}}{{ u.last }}{{ /span }}
            <span style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              <span style={{ padding: '4px 7px', borderRadius: '4', background: u.accBg, color: u.accInk, font: '500 11px/1 var(--font-mono)', letterSpacing: '.06em', textTransform: 'uppercase' }}>{{ u.acc }}{{ /span }}
              {{ u.temp && <span style={{ padding: '4px 7px', borderRadius: '4', background: 'var(--paper-2)', font: '500 11px/1 var(--font-mono)', letterSpacing: '.06em', textTransform: 'uppercase' }}>Temporary password</span> }}
            </span>
            <span style={{ position: 'relative', display: 'flex', justifyContent: 'flexEnd' }}>
              <button className="hvr-ink-border" style={{ height: '36px', padding: '0 12px', border: '1px solid var(--line)', borderRadius: '8', background: 'var(--paper)', fontSize: '14', fontWeight: '500' }}>Manage ▾</button>
              {{ u.menu && (
                <div style={{ position: 'absolute', right: 0, top: 'calc(100% + 6px)', zIndex: '40', width: '300px', padding: '6px', background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: '14', boxShadow: '0 30px 60px -30px rgba(10,10,11,.35), 0 2px 6px rgba(10,10,11,.06)' }}>
                  {{ u.you && (
                    <p style={{ margin: '0', padding: '10px 12px', fontSize: '14', lineHeight: '1.45', color: 'var(--muted)' }}>This is your account. You can't remove your own admin access or turn it off, so the box always keeps at least one admin.</p>
                  )}}
                  {{ /* actions list */ }}
                </div>
              )}}
            </span>
          </div>
        ))}
        <p style={{ margin: '0', fontSize: '14', color: 'var(--muted)' }}>Every new or reset account starts with a temporary password, which the person replaces the next time they sign in.</p>
      </section>
    </div>
  );

  // --- About Render ---
  const renderAbout = () => (
    <SettingCard title="About this box">
      <section style={{ display: 'flex', flexDirection: 'column', padding: '6px 24px', background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: '14px' }}>
        <scFor list="{{ about }}" as="a" hintPlaceholderCount="6">
          <div style={{ display: 'grid', gridTemplateColumns: '220px minmax(0,1fr)', gap: '16px', alignItems: 'baseline', padding: '14px 0', borderBottom: '1px solid var(--line-soft)' }}>
            <span style={{ fontSize: '14.5', color: 'var(--muted)' }}}{{ a.k }}{{ /span }}
            <span style={{ font: '500 15px/1.4 var(--font-mono)' }}{{ a.v }}{{ /span }}
          </div>
        )}
      </section>
      <section style={{ display: 'flex', alignItems: 'center', justifyContent: 'spaceBetween', flexWrap: 'wrap', gap: '14px', padding: '20px 24px', background: 'var(--bone)', border: '1px solid var(--line)', borderRadius: '14px' }}>
        <span style={{ display: 'flex', flexDirection: 'column', gap: '4' }}>
          <span style={{ fontSize: '16', fontWeight: '500' }}>Setup checklist</span>
          <span style={{ fontSize: '14.5', color: 'var(--muted)' }}>Brings back the four first-time steps at the top of Home.</span>
        </span>
        <button className="hvr-ink-border" style={{ height: '44px', padding: '0 16px', border: '1px solid var(--line)', borderRadius: '8', background: 'var(--paper)', fontSize: '14.5', fontWeight: '500' }}>Show setup checklist</button>
      </section>
    </div>
  );

  // Render section based on current tab
  if (section === 'storage') return renderStorage();
  if (section === 'space') return renderSpace();
  if (section === 'capacity') return renderCapacity();
  if (section === 'users') return renderUsers();
  if (section === 'about') return renderAbout();

  return null;
}