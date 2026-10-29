/**
 * CamerasPage — i-Netra Cameras screen.
 * Displays the 16 prototype cameras in a grid with status dots,
 * area grouping, and quick actions (Live, Search, Remove).
 * Powered by `window.INVR` sample data (`SCEN.day`).
 *
 * Props: openSearch(opts), navTo(t, opts) — same signatures as HomePage.
 */
import React, { useEffect } from 'react';
import { invr, merged } from '../../prototype/api';

export default function CamerasPage({ openSearch, navTo }) {
  const I = invr();
  const M = merged('day', {});
  const CAM = M.CAM;
  const cams = M.cams || [];

  // State
  const [view, setView] = React.useState('grid'); // 'grid' | 'list'
  const [q, setQ] = React.useState('');
  const [areaF, setAreaF] = React.useState('all');
  const [statusF, setStatusF] = React.useState('all');
  const [layout, setLayout] = React.useState('list'); // 'list' | 'grid'
  const [shown, setShown] = React.useState(40);
  const [loadingMore, setLoadingMore] = React.useState(false);
  const [sellF, setSellF] = React.useState('all'); // status filter

  useEffect(() => {
    const onStorage = () => { try { setView(localStorage.getItem('aivisra_cams_view') || 'grid'); } catch (e) {} };
    window.addEventListener('storage', onStorage);
    onStorage();
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  useEffect(() => {
    try { localStorage.setItem('aivisra_cams_view', view); } catch (e) {}
  }, [view]);

  if (!I) {
    return (
      <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', gap: 12, padding: 24, background: 'var(--paper)', color: 'var(--ink)' }}>
        <h1>Cameras</h1>
        <p>Load sample data to view cameras.</p>
        <button onClick={() => window.location.reload()}>Reload with sample data</button>
      </div>
    );
  }

  // Filter cameras
  const offN = cams.filter(c => c.status === 'offline').length;
  const total = cams.length;
  const pool = cams.filter(c =>
    (!q || String(c.num).startsWith(q) || c.name.toLowerCase().includes(q)) &&
    (areaF === 'all' || c.area === areaF) &&
    (statusF === 'all' || c.status === statusF)
  );
  const inPool = new Set(pool.map(c => c.num));

  // Row component for list view
  const row = (c) => {
    const off = c.status === 'offline';
    return {
      num: c.num, name: c.name, scene: c.scene,
      statusText: off ? 'Offline since ' + c.since : 'Online',
      statusInk: off ? 'var(--danger-deep)' : 'var(--ink)', dot: off ? 'var(--danger)' : 'var(--success)',
      events: (times[c.num] || []).filter(t => t <= (I.SCEN.day?.now ?? 40800)).length,
      level: I.LV[c.level].label, via: c.via === 'recorder' ? 'From the recorder' : 'Direct to camera',
      open: () => navTo('search', { cams: [c.num], preset: 'today' }),
      live: () => navTo('live', { cam: c.num }),
      search: () => navTo('search', { cams: [c.num], preset: 'today' }),
    };
  };

  // Groups by area
  const groups = I.AREAS?.map(a => {
    const rs = a.cams.map(n => CAM[n]).filter(c => c && inPool.has(c.num));
    if (!rs.length) return null;
    return {
      id: a.id, name: a.name, toneBg: I.areaTone(a.id).bg, toneInk: I.areaTone(a.id).ink,
      countText: a.cams.length + (a.cams.length === 1 ? ' camera' : ' cameras'),
      rows: rs.map(row), ink: 'var(--muted)', mark: 'transparent',
    };
  }).filter(g => g && g.rows.length);

  // Pagination
  const start = shown - 40;
  const shownPool = pool.slice(start, shown);
  const budget = layout === 'grid' ? Infinity : 40;
  let shownN = 0;
  const filteredGroups = groups.map(g => {
    const rows = g.rows.slice(0, Math.max(0, budget - shownN));
    shownN += rows.length;
    return Object.assign({}, g, { rows });
  }).filter(g => g.rows.length);

  // Layout options
  const layouts = [
    { label: 'List', set: () => setLayout('list') },
    { label: 'Grid', set: () => setLayout('grid') },
  ];

  return (
    <div style={{ flex: 1, minHeight: 0, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 12, padding: '24px 32px 32px' }}>


      {/* Toolbar */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, alignItems: 'center', fontSize: 14 }}>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>Search</span>
          <input value={q} onChange={e => { setQ(e.target.value); } }
            placeholder="Find a camera by name or number"
            style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)', fontSize: 14, minWidth: 200 }} />
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>Area</span>
          <select value={areaF} onChange={e => { setAreaF(e.target.value); } }
            style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)', fontSize: 14 }}>
            <option value="all">All areas</option>
            {I.AREAS?.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>Status</span>
          <select value={statusF} onChange={e => { setStatusF(e.target.value); } }
            style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)', fontSize: 14 }}>
            <option value="all">All</option>
            <option value="online">Online {total - offN}</option>
            <option value="offline">Offline {offN}</option>
          </select>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>View</span>
          <select value={layout} onChange={e => { setLayout(e.target.value); setShown(40); } }
            style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)', fontSize: 14 }}>
            <option value="list">List</option>
            <option value="grid">Grid</option>
          </select>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>Show</span>
          <select value={shown} onChange={e => { setShown(parseInt(e.target.value)); } }
            style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)', fontSize: 14 }}>
            <option value={40}>40</option>
            <option value={all}>All</option>
          </select>
        </div>
      </div>

      {/* Content area */}
      {view === 'grid' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(236px, 1fr))', gap: 14, padding: '4px 0 14px' }}>
          {filteredGroups.map(g => (
            <div key={g.id} style={{ marginBottom: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 7px', borderRadius: 4, background: g.toneBg, color: g.toneInk, font: '500 11px/1 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase' }}>
                <span>{g.name}</span> {g.countText}
              </div>
              {g.rows.map(r => (
                <div key={r.num} style={{ border: '1px solid var(--line)', borderRadius: 14, background: 'var(--bone)', padding: '12px 14px', cursor: 'pointer', marginBottom: '4px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: '4px' }}>
                    <span style={{ width: 28, height: 28, borderRadius: '50%', background: r.dot, flexShrink: 0 }} />
                    <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                      <span style={{ fontSize: 15.5, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.name}</span>
                      <span style={{ fontSize: 13.5, color: r.statusInk }}>{r.statusText}</span>
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, color: 'var(--muted)' }}>
                    <span>{r.events} today</span>
                    <span onClick={r.search}>Search</span>
                    <span onClick={r.live}>Live</span>
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      {view === 'list' && (
        <div style={{ maxHeight: '600px', overflow: 'auto' }}>
          {filteredGroups.map(g => (
            <div key={g.id} style={{ marginBottom: 12, paddingBottom: '8px', borderBottom: '1px solid var(--line-soft)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 7px', borderRadius: 4, background: g.toneBg, color: g.toneInk, font: '500 11px/1 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase' }}>
                <span>{g.name}</span> {g.countText}
              </div>
              {g.rows.map(r => (
                <div key={r.num} style={{ border: '1px solid var(--line)', borderRadius: '6px', background: 'var(--paper)', padding: '12px 14px', marginBottom: '4px', display: 'grid', gridTemplateColumns: '28px 1fr auto 80px', gap: '10px', alignItems: 'center' }}>
                  <span style={{ fontSize: 13, color: r.statusInk }}>{r.dot}</span>
                  <span style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                    <span style={{ fontSize: 15.5, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.name}</span>
                    <span style={{ fontSize: 13.5, color: r.statusInk }}>{r.statusText}</span>
                  </span>
                  <span>{r.events} today</span>
                  <span style={{ textAlign: 'right', fontSize: 13 }}>
                    <span onClick={r.search}>Search</span>
                    <span onClick={r.live}>Live</span>
                  </span>
                </div>
              ))}
            </div>
          ))}
          {/* Load more */}
          {loadingMore && (
            <div style={{ textAlign: 'center', padding: '16px 0', color: 'var(--muted)' }}>Loading the next 40 cameras…</div>
          )}
          {shownN < pool.length && (
            <div style={{ textAlign: 'center', padding: '16px 0', color: 'var(--muted)' }}>
              Show more {pool.length - shownN} more
            </div>
          )}
        </div>
      )}

      {/* Summary bar */}
      <div style={{ background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: 8, padding: '12px 16px', marginTop: '12px', fontSize: 14, color: 'var(--muted)' }}>
        <span>{total - offN} of {total} online</span>
        <span style={{ marginLeft: 'auto' }}>{shownN} of {pool.length} shown</span>
      </div>
    </div>
  );
}