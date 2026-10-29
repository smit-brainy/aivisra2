/**
 * InetraCameraPicker — Camera Picker dialog from `live-view.tpl.html`.
 * Shows search input, area groups with checkboxes, "Every camera"/area/camera selection.
 * Minimal build-friendly version (style block removed per prototype pattern).
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';

export default function InetraCameraPicker({
  defaultOpen = true,
  label = 'Cameras',
  onToggleOpen,
  cameras = [],
  areas = [],
  value = { mode: 'all' },
  onChange,
}) {
  const [open, setOpen] = React.useState(defaultOpen);
  const [q, setQ] = React.useState('');
  const rootRef = useRef(null);

  useEffect(() => {
    const onDoc = e => {
      if (open && !rootRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  const selected = useMemo(() => {
    if (value.mode === 'all') return new Set(cameras.map(c => c.camera_id || c.id));
    if (value.mode === 'area') return new Set(cameras.filter(c => c.area_id === value.area).map(c => c.camera_id || c.id));
    return new Set(value.cams || []);
  }, [cameras, value]);
  const visible = cameras.filter(c => !q || String(c.camera_id || c.id).toLowerCase().includes(q.toLowerCase()) || String(c.display_name || c.name || '').toLowerCase().includes(q.toLowerCase()));
  const choose = next => onChange && onChange(next);
  const toggle = id => { const next = new Set(selected); next.has(id) ? next.delete(id) : next.add(id); choose(next.size === cameras.length ? { mode: 'all' } : { mode: 'cams', cams: [...next] }); };

  return (
    <div style={{ position: 'relative' }}>
      <button onClick={() => setOpen(v => !v)} aria-expanded={open} style={{ color: 'var(--ink)' }}>
        {label}
      </button>
      {open && (
        <div style={{ position: 'absolute', top: 'calc(100% + 6px)', left: 0, zIndex: 50, width: 420, maxHeight: 560, display: 'flex', flexDirection: 'column', background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: 14, boxShadow: '0 30px 60px -30px rgba(10,10,11,.35), 0 2px 6px rgba(10,10,11,.06)', overflow: 'hidden' }}>
          <div style={{ padding: '12px', borderBottom: '1px solid var(--line-soft)' }}>
            <input value={q} onChange={e => setQ(e.target.value)} className="fcs-input" placeholder="Find a camera by name or number" style={{ width: '100%', height: 40, padding: '0 12px', border: '1px solid var(--line)', borderRadius: 8, background: 'var(--bone)', fontSize: 14.5, outline: 'none' }} />
          </div>
          <div style={{ flex: 1, minHeight: 0, overflow: 'auto', padding: '6px 0 8px' }}>
            <button type="button" className="hvr-blue2" onClick={() => choose({ mode: 'all' })} style={{ width: '100%', height: 46, padding: '0 16px', background: value.mode === 'all' ? 'var(--blue-tint)' : 'transparent', textAlign: 'left' }}>Every camera <small style={{ float: 'right', color: 'var(--muted)' }}>{cameras.filter(c => c.online !== false).length} of {cameras.length} online</small></button>
            {areas.map(area => { const rows = visible.filter(c => c.area_id === area.area_id); if (!rows.length) return null; return <div key={area.area_id}><div style={{ padding: '10px 16px 6px', borderTop: '1px solid var(--line-soft)', font: '500 11px/1 var(--font-mono)', textTransform: 'uppercase', color: 'var(--muted)' }}>{area.name}</div>{rows.map(camera => { const id = camera.camera_id || camera.id; return <button type="button" key={id} onClick={() => toggle(id)} className="hvr-blue2" style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 10, height: 42, padding: '0 16px', background: selected.has(id) ? 'var(--blue-tint)' : 'transparent', textAlign: 'left' }}><span style={{ width: 18, height: 18, border: '1.5px solid var(--line)', borderRadius: 4, color: 'var(--blue)', textAlign: 'center' }}>{selected.has(id) ? '✓' : ''}</span><span style={{ width: 68, color: 'var(--muted)', fontFamily: 'var(--font-mono)' }}>{id}</span><span style={{ flex: 1 }}>{camera.display_name || camera.name || id}</span><span style={{ color: camera.online === false ? 'var(--danger-deep)' : 'var(--muted)', fontSize: 12 }}>{camera.status || 'unknown'}</span></button>; })}</div>; })}
          </div>
        </div>
      )}
    </div>
  );
}
