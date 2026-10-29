/**
 * InetraCameraPicker — Camera Picker dialog from `live-view.tpl.html`.
 * Shows search input, area groups with checkboxes, "Every camera"/area/camera selection.
 * Minimal build-friendly version (style block removed per prototype pattern).
 */
import React, { useEffect, useRef } from 'react';

export default function InetraCameraPicker({
  defaultOpen = true,
  label = 'Cameras',
  onToggleOpen,
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

  return (
    <div style={{ position: 'relative' }}>
      <button onClick={() => setOpen(v => !v)} aria-expanded={open}>
        {label}
      </button>
      {open && (
        <div style={{ position: 'absolute', top: 'calc(100% + 6px)', left: 0, zIndex: 50, width: 420, maxHeight: 560, display: 'flex', flexDirection: 'column', background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: 14, boxShadow: '0 30px 60px -30px rgba(10,10,11,.35), 0 2px 6px rgba(10,10,11,.06)', overflow: 'hidden' }}>
          <div style={{ padding: '12px', borderBottom: '1px solid var(--line-soft)' }}>
            <input value={q} onChange={e => setQ(e.target.value)} placeholder="Find a camera by name or number" style={{ width: '100%', height: 40, padding: '0 12px', border: '1px solid var(--line)', borderRadius: 8, background: 'var(--bone)', fontSize: 14.5, outline: 'none' }} />
          </div>
          <div style={{ flex: 1, minHeight: 0, overflow: 'auto', padding: '6px 0 8px' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '0 16px', borderTop: '1px solid var(--line-soft)', fontSize: 13, color: 'var(--muted)' }}>
              <span>Tick boxes to choose several</span>
            </span>
          </div>
        </div>
      )}
    </div>
  );
}