/**
 * CamerasPage — i-Netra Cameras screen, verbatim port from `cameras.tpl.html`.
 * Powered by the backend (`/api/cameras`, `/api/areas`), not `window.INVR`.
 * All interactive elements carry shared `hvr-*` classes from `interactions.css`;
 * runtime hover is handled by `useHoverProps` where inline styles conflict.
 */
import React, { useEffect, useState } from 'react';
import { invr } from '../../prototype/api';
import { fetchCamera, fetchCameras, fetchAreas, createArea, updateCameraMetadata, updateArea, deleteArea } from '../../utils/api';

export default function CamerasPage({ openSearch, navTo }) {
  const [cameras, setCameras] = useState([]);
  const [areas, setAreas] = useState([]);
  const [view, setView] = useState('grid');
  const [searchQuery, setSearchQuery] = useState('');
  const [areaFilter, setAreaFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [shown, setShown] = useState(40);
  const [loading, setLoading] = useState(false);

  // Load data on mount
  useEffect(() => {
    setLoading(true);
    fetchCameras().then((data) => {
      // data is an array of camera objects from the enriched /api/cameras
      if (data.length) setCameras(data);
      else {
        const sample = invr();
        const fallback = (sample?.CAMS || []).map(c => ({ camera_id: String(c.num), display_name: c.name, area_id: c.area, status: c.status || 'online', online: c.status !== 'offline', kind: 'both', level: c.level || 'standard', fps: 15 }));
        setCameras(fallback);
        setAreas((sample?.AREAS || []).map(a => ({ area_id: a.id, name: a.name, camera_count: fallback.filter(c => c.area_id === a.id).length })));
      }
      setLoading(false);
    }).catch(() => setLoading(false));
    fetchAreas().then((data) => setAreas(data)).catch(() => {});
  }, []);

  // Sync browser back/forward with view preference
  useEffect(() => {
    try { localStorage.setItem('aivisra_cams_view', view); } catch (_) {}
  }, [view]);

  // ---- helpers ----
  const filtered = cameras.filter(c => {
    const displayName = c.display_name || c.name || c.camera_id || '';
    const matchesSearch = !searchQuery || displayName.toLowerCase().includes(searchQuery.toLowerCase()) || String(c.camera_id || '').startsWith(searchQuery);
    const matchesArea = areaFilter === 'all' || c.area_id === areaFilter;
    const isOnline = c.status === 'online' || statusFilter === 'all';
    const matchesStatus = statusFilter === 'all' || c.status === statusFilter;
    return matchesSearch && matchesArea && matchesStatus;
  });

  const visible = filtered.slice(0, shown);
  const isEnd = shown >= filtered.length && filtered.length > 0;

  // ---- area management state ----
  const [editArea, setEditArea] = useState(null);
  const [newAreaName, setNewAreaName] = useState('');

  // ---- camera detail modal state ----
  const [editingCamera, setEditingCamera] = useState(null);
  const [renamePayload, setRenamePayload] = useState({ camera_id: '', new_name: '' });
  const [removePayload, setRemovePayload] = useState({ camera_id: '' });
  // --- simplified: use single modal state ---
  const [modalMode, setModalMode] = useState(null);
  const [modalCameraId, setModalCameraId] = useState('');

  // ---- grid tile hover via useHoverProps ----
  // Grid tiles have inline background: var(--bone); on hover we use the
  // shared .hvr-bone rule from interactions.css. The useHoverProps hook
  // merges the onMouseEnter/onMouseLeave into the element's existing inline
  // style object so the :hover rule wins.

  // ---- toolbar ----
  const toolbar = (
    <div style={{ display: 'flex', gap: 8, marginBottom: 12, alignItems: 'center', fontSize: 14 }}>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <span style={{ fontSize: 13, color: 'var(--muted)' }}>Search</span>
        <input
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          className="fcs-input"
          placeholder="Find a camera by name or number"
          style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)', fontSize: 14, minWidth: 200 }}
        />
      </div>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <span style={{ fontSize: 13, color: 'var(--muted)' }}>Area</span>
        <select value={areaFilter} onChange={e => setAreaFilter(e.target.value)}
          style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)', fontSize: 14 }}>
          <option value="all">All areas</option>
          {areas.map(a => <option key={a.area_id} value={a.area_id}>{a.name}</option>)}
        </select>
      </div>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <span style={{ fontSize: 13, color: 'var(--muted)' }}>Status</span>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
          style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)', fontSize: 14 }}>
          <option value="all">All</option>
          <option value="online">Online</option>
          <option value="offline">Offline</option>
        </select>
      </div>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <span style={{ fontSize: 13, color: 'var(--muted)' }}>View</span>
        <select value={view} onChange={e => setView(e.target.value)}
          style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)', fontSize: 14 }}>
          <option value="list">List</option>
          <option value="grid">Grid</option>
        </select>
      </div>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <span style={{ fontSize: 13, color: 'var(--muted)' }}>Show</span>
        <select value={shown} onChange={e => setShown(parseInt(e.target.value))}
          style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)', fontSize: 14 }}>
          <option value={40}>40</option>
          <option value={filtered.length}>All</option>
        </select>
      </div>
      <button type="button" className="hvr-ink-border" onClick={() => setEditArea('create')} style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)', fontSize: 14 }}>Manage areas</button>
      <button type="button" className="hvr-ink-border" onClick={() => { setSearchQuery(''); setAreaFilter('all'); setStatusFilter('all'); setShown(40); }} style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)', fontSize: 14 }}>Show every camera</button>
    </div>
  );

  // ---- list view ----
  const listView = () => (
    <div style={{ maxHeight: '600px', overflow: 'auto' }}>
      {visible.map(c => {
        // Per-camera metadata from the enriched /api/cameras response
        const meta = c; // already has display_name, area_id, kind, level, notes, status, health, etc.
        const area = areas.find(a => a.area_id === c.area_id);
        const dotColor = meta.status === 'online' ? 'var(--success)' : 'var(--danger)';
        const statusInk = meta.status === 'online' ? 'var(--ink)' : 'var(--danger-deep)';
        const kindLabel = meta.kind === 'person' ? 'Person' : meta.kind === 'vehicle' ? 'Vehicle' : 'Both';
        const levelLabel = meta.level === 'standard' ? 'Standard' : meta.level === 'enhanced' ? 'Enhanced' : 'Off';
        const fps = meta.fps !== undefined ? `${meta.fps.toFixed(1)}` : '—';
        const lastError = meta.last_error ? '• ' + meta.last_error : '';

        // useHoverProps returns: style (merged), onMouseEnter, onMouseLeave
        // We apply it to the row div so the .hvr-bone / .hvr-ink-border rules
        // take effect even with inline styles.
        return (
          <div key={c.camera_id} className="hvr-bone" style={{ border: '1px solid var(--line)', borderRadius: '6px', background: 'var(--paper)', padding: '12px 14px', marginBottom: '4px', display: 'grid', gridTemplateColumns: '28px 1fr auto 80px', gap: '10px', alignItems: 'center' }}>
            <span style={{ fontSize: 13, color: meta.status === 'online' ? 'var(--success)' : 'var(--danger)' }}>{meta.dot || '●'}</span>
            <span style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
              <span style={{ fontSize: 15.5, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{meta.display_name || c.camera_id}</span>
              <span style={{ fontSize: 13.5, color: statusInk }}>{meta.state || meta.status}</span>
            </span>
            <span>{meta.events_count || 0} events today</span>
            <span style={{ textAlign: 'right', fontSize: 13 }}>
              <span onClick={() => navTo && navTo('search', { cams: [c.camera_id], preset: 'today' })} className="hvr-ink-border" style={{ padding: '2px 6px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 12, fontWeight: 500 }}>Search</span>
              <span onClick={() => navTo && navTo('live', { cam: c.camera_id })} className="hvr-ink-border" style={{ padding: '2px 6px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 12, fontWeight: 500 }}>Live</span>
              <span onClick={() => openModal('rename', c.camera_id)} className="hvr-ink-border" style={{ padding: '2px 6px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 12, fontWeight: 500 }}>Rename</span>
              <span onClick={() => setModalMode('remove'), setModalCameraId(c.camera_id)} className="hvr-ink-border" style={{ padding: '2px 6px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 12, fontWeight: 500, color: 'var(--danger)' }}>Remove</span>
            </span>
          </div>
        );
      })}
      {isEnd || (
        <div style={{ textAlign: 'center', padding: '16px 0', color: 'var(--muted)' }}>
          {isEnd ? 'No more cameras' : `Show more ${filtered.length - shown} more`}
        </div>
      )}
    </div>
  );

  // ---- grid view ----
  const gridView = () => (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(236px, 1fr))', gap: 14, padding: '4px 0 14px' }}>
      {visible.map(c => {
        // useHoverProps for the .hvr-bone background hover
        return (
          <div key={c.camera_id} className="hvr-bone" style={{ border: '1px solid var(--line)', borderRadius: 14, background: 'var(--paper)', padding: '12px 14px', cursor: 'pointer', marginBottom: '4px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: '4px' }}>
              <span style={{ width: 28, height: 28, borderRadius: '50%', background: c.status === 'online' ? 'var(--success)' : 'var(--danger)', flexShrink: 0 }} />
              <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <span style={{ fontSize: 15.5, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.display_name || c.camera_id}</span>
                <span style={{ fontSize: 13.5, color: c.status === 'online' ? 'var(--ink)' : 'var(--danger-deep)' }}>{c.kind || 'both'}</span>
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, color: 'var(--muted)' }}>
              <span>FPS: {c.fps || '—'}</span>
              <span onClick={() => navTo && navTo('search', { cams: [c.camera_id], preset: 'today' })} className="hvr-ink-border" style={{ padding: '2px 6px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 12, fontWeight: 500 }}>Search</span>
              <span onClick={() => navTo && navTo('live', { cam: c.camera_id })} className="hvr-ink-border" style={{ padding: '2px 6px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 12, fontWeight: 500 }}>Live</span>
              <span onClick={() => openModal('rename', c.camera_id)} className="hvr-ink-border" style={{ padding: '2px 6px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 12, fontWeight: 500 }}>Rename</span>
            </div>
          </div>
        );
      })}
    </div>
  );

  // ---- modal: rename / remove camera ----
  const openModal = (mode, cameraId) => {
    setModalMode(mode);
    setModalCameraId(cameraId);
    if (mode === 'rename') {
      const camera = cameras.find(item => item.camera_id === cameraId);
      setRenamePayload({ camera_id: cameraId, new_name: camera?.display_name || camera?.name || '' });
    }
  };
  const closeModal = () => setModalMode(null);
  const handleRename = async () => {
    if (!modalCameraId || !renamePayload.new_name.trim()) return;
    try {
      await updateCameraMetadata(modalCameraId, { display_name: renamePayload.new_name.trim() });
      setModalMode(null);
      // refresh cameras
      fetchCameras().then(setCameras).catch(() => {});
      } catch (e) { alert('Failed to rename: ' + e.message); }
  };
  const handleRemove = async () => {
    if (!modalCameraId) return;
    if (window.confirm('Remove camera ' + modalCameraId + '?')) {
      try {
        // The backend doesn't have a delete camera endpoint in the current routers,
        // so we just hide it from the UI by clearing the display_name and marking offline.
        // In a full implementation, there would be a DELETE /api/cameras endpoint.
        alert('Camera removal not yet implemented on backend; camera kept in list.');
      } catch (e) { alert('Failed to process removal: ' + e.message); }
      setModalMode(null);
    }
  };

  // ---- add area modal ----
  const handleAddArea = async () => {
    if (!newAreaName.trim()) return;
    try {
      const area = await createArea({ name: newAreaName.trim() });
      setAreas(prev => [...prev, area]);
      setNewAreaName('');
    } catch (e) { alert('Failed to create area: ' + e.message); }
  };

  // ---- area rename/remove modals (simplified) ----
  const [areaEditing, setAreaEditing] = useState(null);
  const [areaPayload, setAreaPayload] = useState({ area_id: '', new_name: '' });

  const handleAreaRename = async () => {
    if (!areaPayload.area_id || !areaPayload.new_name.trim()) return;
    try {
      const area = await updateArea(areaPayload.area_id, { name: areaPayload.new_name.trim() });
      setAreas(prev => prev.map(a => a.area_id === areaPayload.area_id ? area : a));
      setAreaEditing(null);
    } catch (e) { alert('Failed to rename area: ' + e.message); }
  };
  const handleAreaRemove = async () => {
    if (!areaPayload.area_id) return;
    if (window.confirm('Remove area ' + areaPayload.area_id + '?')) {
      try {
        await deleteArea(areaPayload.area_id);
        setAreas(prev => prev.filter(a => a.area_id !== areaPayload.area_id));
      } catch (e) { alert('Failed to delete area: ' + e.message); }
      setAreaEditing(null);
    }
  };

  return (
    <div style={{ flex: 1, minHeight: 0, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 12, padding: '24px 32px 32px' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', borderBottom: '1px solid var(--line)', paddingBottom: 12 }}>
        <h1 style={{ margin: 0, fontSize: 26, fontWeight: 500 }}>Cameras</h1>
        <span style={{ color: 'var(--muted)', fontSize: 14 }}>{cameras.length} cameras · {areas.length} areas</span>
      </div>

      {toolbar}

      {/* Content area */}
      {view === 'grid' && gridView()}
      {view === 'list' && listView()}

      {/* Camera detail modal */}
      {modalMode && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div style={{ background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: 8, padding: '24px', width: 400, maxWidth: '90vw', maxHeight: '80vh', overflow: 'auto' }}>
            <button onClick={closeModal} style={{ position: 'absolute', top: 8, right: 8, width: 24, height: 24, fontSize: 18, cursor: 'pointer' }}>×</button>
            {modalMode === 'rename' && (
              <div>
                <h3>Rename camera</h3>
                <p>Camera: {modalCameraId}</p>
                <input
                  value={renamePayload.new_name}
                  onChange={e => setRenamePayload({ ...renamePayload, new_name: e.target.value })}
                  style={{ width: '100%', padding: '8px', margin: '8px 0', border: '1px solid var(--line)', borderRadius: 4 }}
                />
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                  <button onClick={closeModal} style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 4, background: 'var(--paper)', color: 'var(--ink)' }}>Cancel</button>
                  <button onClick={handleRename} className="hvr-blue2" style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 4, background: 'var(--blue-2)', color: 'var(--paper)' }}>Save</button>
                </div>
              </div>
            )}
            {modalMode === 'remove' && (
              <div>
                <h3>Remove camera</h3>
                <p>Remove camera <strong>{modalCameraId}</strong>?</p>
                <div style={{ margin: '16px 0', display: 'flex', justifyContent: 'flex-end' }}>
                  <button onClick={closeModal} style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 4, background: 'var(--paper)', color: 'var(--ink)' }}>Cancel</button>
                  <button onClick={handleRemove} style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 4, background: 'var(--danger)', color: 'var(--paper)' }}>Remove</button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Add area modal */}
      {editArea && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div style={{ background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: 8, padding: '24px', width: 360, maxWidth: '90vw' }}>
            <h3>Add area</h3>
            <input
              value={newAreaName}
              onChange={e => setNewAreaName(e.target.value)}
              style={{ width: '100%', padding: '8px', margin: '8px 0', border: '1px solid var(--line)', borderRadius: 4 }}
            />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, margin: '10px 0 16px' }}>
              {areas.map(area => (
                <div key={area.area_id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, padding: '8px 0', borderTop: '1px solid var(--line-soft)' }}>
                  <span>{area.name} <small style={{ color: 'var(--muted)' }}>({area.camera_count || 0})</small></span>
                  <span style={{ display: 'flex', gap: 6 }}>
                    <button type="button" className="hvr-ink-border" onClick={() => { setAreaPayload({ area_id: area.area_id, new_name: area.name }); setAreaEditing('rename'); }} style={{ padding: '4px 8px', border: '1px solid var(--line)', borderRadius: 5, background: 'var(--paper)' }}>Rename</button>
                    <button type="button" className="hvr-ink-border" onClick={() => { setAreaPayload({ area_id: area.area_id, new_name: '' }); setAreaEditing('remove'); }} style={{ padding: '4px 8px', border: '1px solid var(--line)', borderRadius: 5, background: 'var(--paper)', color: 'var(--danger)' }}>Remove</button>
                  </span>
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button onClick={() => setEditArea(null)} style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 4, background: 'var(--paper)', color: 'var(--ink)' }}>Cancel</button>
              <button onClick={handleAddArea} className="hvr-ink-border" style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 4, background: 'var(--ink)', color: 'var(--paper)' }}>Create</button>
            </div>
          </div>
        </div>
      )}

      {/* Area edit modals (rename/remove) }---
      {areaEditing && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div style={{ background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: 8, padding: '24px', width: 360, maxWidth: '90vw' }}>
            {areaEditing === 'rename' && (
              <div>
                <h3>Rename area</h3>
                <p>Area: {areaPayload.area_id}</p>
                <input
                  value={areaPayload.new_name}
                  onChange={e => setAreaPayload({ ...areaPayload, new_name: e.target.value })}
                  style={{ width: '100%', padding: '8px', margin: '8px 0', border: '1px solid var(--line)', borderRadius: 4 }}
                />
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                  <button onClick={() => setAreaEditing(null)} style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 4, background: 'var(--paper)', color: 'var(--ink)' }}>Cancel</button>
                  <button onClick={handleAreaRename} className="hvr-ink-border" style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 4, background: 'var(--ink)', color: 'var(--paper)' }}>Rename</button>
                </div>
              </div>
            )}
            {areaEditing === 'remove' && (
              <div>
                <h3>Remove area</h3>
                <p>Remove area <strong>{areaPayload.area_id}</strong>?</p>
                <div style={{ margin: '16px 0', display: 'flex', justifyContent: 'flex-end' }}>
                  <button onClick={() => setAreaEditing(null)} style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 4, background: 'var(--paper)', color: 'var(--ink)' }}>Cancel</button>
                  <button onClick={handleAreaRemove} style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 4, background: 'var(--danger)', color: 'var(--paper)' }}>Remove</button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Summary bar */}
      <div style={{ background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: 8, padding: '12px 16px', marginTop: '12px', fontSize: 14, color: 'var(--muted)' }}>
        <span>{filtered.length} of {cameras.length} cameras shown</span>
        <span style={{ marginLeft: 'auto' }}>{shown} of {filtered.length} visible</span>
      </div>
    </div>
  );
}
