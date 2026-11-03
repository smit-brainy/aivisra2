/**
 * CamerasPage — i-Netra Cameras screen, verbatim port from `cameras.tpl.html`.
 * Powered by the backend (`/api/cameras`, `/api/areas`), not `window.INVR`.
 * All interactive elements carry shared `hvr-*` classes from `interactions.css`;
 * runtime hover is handled by `useHoverProps` where inline styles conflict.
 */
import React, { useEffect, useState } from 'react';
import { ArrowRight, Pencil, Radio, Search, Trash2, X } from 'lucide-react';
import { deleteCamera, fetchCamera, fetchCameras, fetchAreas, createArea, updateCameraMetadata, updateArea, deleteArea, registerCamera } from '../../utils/api';
import NotificationPopup from '../../components/NotificationPopup';

class CameraViewErrorBoundary extends React.Component {
  state = { error: null };
  static getDerivedStateFromError(error) { return { error }; }
  componentDidCatch(error, info) { console.error('[CamerasPage] list view render failed', error, info); }
  render() {
    if (!this.state.error) return this.props.children;
    return <div role="alert" style={{ padding: 20, border: '1px solid var(--danger)', borderRadius: 10, background: 'var(--danger-tint)', color: 'var(--danger-deep)' }}>Unable to render the camera list. Refresh the page or check the browser console for details.</div>;
  }
}

export default function CamerasPage({ openSearch, navTo }) {
  const [cameras, setCameras] = useState([]);
  const [areas, setAreas] = useState([]);
  const [view, setView] = useState('grid');
  const [searchQuery, setSearchQuery] = useState('');
  const [areaFilter, setAreaFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [shown, setShown] = useState(40);
  const [loading, setLoading] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [addForm, setAddForm] = useState({ camera_id: '', name: '', uri: '', codec: 'h264', decoder: 'auto', decoding_fps: '', status: 'active' });
  const [addError, setAddError] = useState('');
  const [addingCamera, setAddingCamera] = useState(false);
  const [editForm, setEditForm] = useState({ camera_id: '', name: '', uri: '', codec: 'h264', decoder: 'auto', decoding_fps: '' });
  const [editError, setEditError] = useState('');
  const [editSelectedId, setEditSelectedId] = useState('');
  const [notification, setNotification] = useState(null);

  // Load data on mount
  useEffect(() => {
    setLoading(true);
    fetchCameras().then((data) => {
      // The API is the single source of truth; do not fall back to prototype data.
      setCameras(data);
      setLoading(false);
    }).catch(() => setLoading(false));
    fetchAreas().then((data) => setAreas(data)).catch(() => {});
    const telemetryTimer = window.setInterval(() => {
      fetchCameras().then(setCameras).catch(() => {});
    }, 5000);
    return () => window.clearInterval(telemetryTimer);
  }, []);


  const refreshCameras = () => fetchCameras().then(setCameras).catch(() => {});

  const handleAddCamera = async (event) => {
    event.preventDefault();
    setAddError('');
    setAddingCamera(true);
    try {
      await registerCamera({ ...addForm, decoding_fps: addForm.decoding_fps === '' ? null : Number(addForm.decoding_fps), rtsp_url: addForm.uri });
      setAddOpen(false);
      setAddForm({ camera_id: '', name: '', uri: '', codec: 'h264', decoder: 'auto', decoding_fps: '', status: 'active' });
      // Do not keep the form blocked while the heavier health/list request runs.
      refreshCameras();
    } catch (error) { setAddError(error.message || 'Could not add camera.'); }
    finally { setAddingCamera(false); }
  };

  // Sync browser back/forward with view preference
  useEffect(() => {
    try { localStorage.setItem('aivisra_cams_view', view); } catch (_) {}
  }, [view]);

  // ---- helpers ----
  const filtered = cameras.filter(c => {
    const displayName = c.display_name || c.name || c.camera_id || '';
    const matchesSearch = !searchQuery || displayName.toLowerCase().includes(searchQuery.toLowerCase()) || String(c.camera_id || '').startsWith(searchQuery);
    const isOnline = c.status === 'online' || statusFilter === 'all';
    const matchesStatus = statusFilter === 'all' || c.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const visible = filtered.slice(0, shown);
  const isEnd = shown >= filtered.length && filtered.length > 0;
  const statusPresentation = status => {
    if (status === 'online') return { label: 'Online', dot: 'var(--success)', color: 'var(--success-deep)' };
    if (status === 'degraded') return { label: 'Degraded', dot: 'var(--honey)', color: 'var(--honey-deep)' };
    if (status === 'reconnecting') return { label: 'Reconnecting', dot: 'var(--honey)', color: 'var(--honey-deep)' };
    if (status === 'unknown') return { label: 'Starting…', dot: 'var(--muted)', color: 'var(--muted)' };
    return { label: 'Offline', dot: 'var(--danger)', color: 'var(--danger-deep)' };
  };

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
      <button type="button" className="hvr-ink-border" onClick={() => { setSearchQuery(''); setAreaFilter('all'); setStatusFilter('all'); setShown(40); }} style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)', fontSize: 14 }}>Show every camera</button>
      <button type="button" className="hvr-ink-border" onClick={() => { setEditSelectedId(cameras[0]?.camera_id || ''); setEditError(''); setModalMode('edit-picker'); }} style={{ padding: '6px 12px', minHeight: 34, borderRadius: 6, fontSize: 14, lineHeight: 1.2, display: 'inline-flex', alignItems: 'center', gap: 6, border: '1px solid var(--line)', background: 'var(--paper)', color: 'var(--ink)' }}><Pencil size={15} aria-hidden="true" />Edit camera</button>
      <button type="button" className="btn btn-primary" onClick={() => setAddOpen(true)} style={{ padding: '6px 12px', minHeight: 34, borderRadius: 6, fontSize: 14, lineHeight: 1.2, display: 'inline-flex', alignItems: 'center', gap: 6 }}>Add camera <ArrowRight size={16} aria-hidden="true" /></button>
      <button type="button" onClick={() => { setModalCameraId(cameras[0]?.camera_id || ''); setModalMode('remove-picker'); }} disabled={!cameras.length} style={{ padding: '6px 12px', minHeight: 34, borderRadius: 6, fontSize: 14, lineHeight: 1.2, display: 'inline-flex', alignItems: 'center', gap: 6, border: '1px solid var(--danger)', background: 'var(--paper)', color: 'var(--danger-deep)', opacity: cameras.length ? 1 : .55 }}><Trash2 size={15} aria-hidden="true" />Delete camera</button>
    </div>
  );

  // ---- list view ----
  const listView = () => (
    <div style={{ maxHeight: '600px', overflow: 'auto' }}>
      {visible.filter(Boolean).map(c => {
        // Per-camera metadata from the enriched /api/cameras response
        const meta = c || {};
        const cameraId = String(meta.camera_id || meta.id || 'unknown');
        const displayName = String(meta.display_name || meta.name || cameraId);
        const status = String(meta.status || meta.state || 'unknown');
        const statusInk = status === 'online' ? 'var(--ink)' : 'var(--danger-deep)';

        // useHoverProps returns: style (merged), onMouseEnter, onMouseLeave
        // We apply it to the row div so the .hvr-bone / .hvr-ink-border rules
        // take effect even with inline styles.
        return (
          <div key={cameraId} className="hvr-bone" style={{ border: '1px solid var(--line)', borderRadius: '6px', background: 'var(--paper)', padding: '12px 14px', marginBottom: '4px', display: 'grid', gridTemplateColumns: '28px 1fr auto 80px', gap: '10px', alignItems: 'center' }}>
            <span style={{ fontSize: 13, color: status === 'online' ? 'var(--success)' : 'var(--danger)' }}>●</span>
            <span style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
              <span style={{ fontSize: 15.5, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{displayName}</span>
              <span style={{ fontSize: 13.5, color: statusInk }}>{status}</span>
            </span>
            <span>{meta.events_count || 0} events today</span>
            <span style={{ textAlign: 'right', fontSize: 13 }}>
              <span onClick={() => navTo && navTo('search', { cams: [cameraId], preset: 'today' })} className="hvr-ink-border" style={{ padding: '2px 6px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 12, fontWeight: 500 }}>Search</span>
              <span onClick={() => navTo && navTo('live', { cam: cameraId })} className="hvr-ink-border" style={{ padding: '2px 6px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 12, fontWeight: 500 }}>Live</span>
              <span onClick={() => openModal('rename', cameraId)} className="hvr-ink-border" style={{ padding: '2px 6px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 12, fontWeight: 500 }}>Rename</span>
              <span onClick={() => { setModalMode('remove'); setModalCameraId(cameraId); }} className="hvr-ink-border" style={{ padding: '2px 6px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 12, fontWeight: 500, color: 'var(--danger)' }}>Remove</span>
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
        const status = statusPresentation(c.status);
        // useHoverProps for the .hvr-bone background hover
        return (
          <div key={c.camera_id} className="hvr-bone" style={{ border: '1px solid var(--line)', borderRadius: 14, background: 'var(--paper)', padding: '12px 14px', cursor: 'pointer', marginBottom: '4px' }}>
            <div onClick={() => navTo && navTo('live', { cam: c.camera_id })} style={{ cursor: 'pointer' }}>
            <div style={{ height: 112, margin: '-12px -14px 10px', overflow: 'hidden', background: 'var(--bone)', display: 'grid', placeItems: 'center' }}><img src={`/stream/${encodeURIComponent(c.camera_id)}`} alt={`${c.display_name || c.name || c.camera_id} live preview`} onError={(event) => { event.currentTarget.style.display = 'none'; console.warn('[CamerasPage] live preview unavailable', c.camera_id); }} style={{ width: '100%', height: '100%', objectFit: 'cover' }} /><span style={{ color: 'var(--muted)', fontSize: 12 }}>Waiting for live preview…</span></div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: '4px' }}>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <span style={{ fontSize: 15.5, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.display_name || c.camera_id}</span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 13.5, color: status.color }}><span aria-hidden="true" style={{ width: 6, height: 6, borderRadius: '50%', flexShrink: 0, background: status.dot }} />{status.label}</span>
              </span>
            </div></div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'var(--muted)' }}>
              <span style={{ width: 88, flexShrink: 0 }}>FPS: {Number.isFinite(Number(c.ai_fps)) ? Number(c.ai_fps).toFixed(1) : '—'}</span>
              <span role="button" tabIndex={0} onClick={() => navTo && navTo('search', { cams: [c.camera_id], preset: 'today' })} className="hvr-ink-border" style={{ flex: 1, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 4, padding: '6px 4px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 12, fontWeight: 500 }}><Search size={13} strokeWidth={2} aria-hidden="true" />Search</span>
              <span role="button" tabIndex={0} onClick={() => navTo && navTo('live', { cam: c.camera_id })} className="hvr-ink-border" style={{ flex: 1, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 4, padding: '6px 4px', border: '1px solid var(--line)', borderRadius: 6, fontSize: 12, fontWeight: 500 }}><Radio size={13} strokeWidth={2} aria-hidden="true" />Live</span>
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
    if (mode === 'edit') {
      const camera = cameras.find(item => item.camera_id === cameraId) || {};
      setEditError('');
      setEditForm({ camera_id: camera.camera_id || cameraId, name: camera.display_name || camera.name || '', uri: camera.rtsp_url || camera.uri || '', codec: camera.codec || 'h264', decoder: camera.decoder || 'auto', decoding_fps: camera.decoding_fps ?? '' });
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
  const handleEdit = async event => {
    event.preventDefault();
    setEditError('');
    const nextId = editForm.camera_id.trim();
    if (!nextId || !editForm.name.trim() || !editForm.uri.trim()) { setEditError('Camera ID, name, and RTSP URL are required.'); return; }
    try {
      await updateCameraMetadata(modalCameraId, { camera_id: nextId, name: editForm.name.trim(), uri: editForm.uri.trim(), codec: editForm.codec.trim(), decoder: editForm.decoder.trim(), decoding_fps: editForm.decoding_fps === '' ? null : Number(editForm.decoding_fps), display_name: editForm.name.trim() });
      setModalMode(null);
      refreshCameras();
    } catch (error) { setEditError(error.message || 'Could not update camera.'); }
  };
  const handleRemove = async () => {
    if (!modalCameraId) return;
    if (window.confirm('Remove camera ' + modalCameraId + '?')) {
      try {
        await deleteCamera(modalCameraId);
        setCameras(current => current.filter(camera => camera.camera_id !== modalCameraId));
      } catch (e) { setNotification({ type: 'error', title: 'Camera deletion failed', message: e.message || 'The camera could not be deleted.' }); }
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
      <NotificationPopup notification={notification} onClose={() => setNotification(null)} />
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', borderBottom: '1px solid var(--line)', paddingBottom: 12 }}>
        <h1 style={{ margin: 0, fontSize: 26, fontWeight: 500 }}>Cameras</h1>
        <span style={{ color: 'var(--muted)', fontSize: 14 }}>{cameras.length} cameras · {areas.length} areas</span>
      </div>

      {toolbar}

      {/* Content area */}
      {view === 'grid' && gridView()}
      {view === 'list' && <CameraViewErrorBoundary>{listView()}</CameraViewErrorBoundary>}

      {/* Camera detail modal */}
      {addOpen && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <form onSubmit={handleAddCamera} style={{ background: 'var(--paper)', color: 'var(--ink)', border: '1px solid var(--line)', borderRadius: 12, padding: 24, width: 460, maxWidth: '92vw', display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div><h2 style={{ margin: 0 }}>Add camera</h2><p style={{ margin: '6px 0 0', color: 'var(--muted)' }}>Camera details are stored in the database.</p></div>
            {addError && <div role="alert" style={{ padding: 10, borderRadius: 6, background: 'var(--danger-tint)', color: 'var(--danger-deep)' }}>{addError}</div>}
            {[['camera_id', 'Camera number / ID', 'CAM001'], ['name', 'Camera name', 'Main gate'], ['uri', 'RTSP URL', 'rtsp://user:password@host/stream']].map(([key, label, placeholder]) => <label key={key} style={{ display: 'flex', flexDirection: 'column', gap: 5 }}><span>{label}</span><input required value={addForm[key]} placeholder={placeholder} onChange={e => setAddForm({ ...addForm, [key]: e.target.value })} style={{ padding: 10, border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)' }} /></label>)}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}><label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}><span>Codec</span><input value={addForm.codec} onChange={e => setAddForm({ ...addForm, codec: e.target.value })} style={{ padding: 10, border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)' }} /></label><label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}><span>Decoder</span><input value={addForm.decoder} onChange={e => setAddForm({ ...addForm, decoder: e.target.value })} style={{ padding: 10, border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)' }} /></label></div>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}><span>Decoding FPS</span><input type="number" min="1" step="1" value={addForm.decoding_fps} onChange={e => setAddForm({ ...addForm, decoding_fps: e.target.value })} style={{ padding: 10, border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)' }} /></label>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, marginTop: 6 }}><button type="button" disabled={addingCamera} onClick={() => setAddOpen(false)} style={{ border: 0, background: 'transparent', color: 'var(--ink)', cursor: addingCamera ? 'wait' : 'pointer' }}>Cancel</button><div style={{ display: 'flex', gap: 8 }}><button type="button" disabled={addingCamera} onClick={() => alert('CSV camera import is planned as an upcoming feature.')} style={{ padding: '8px 12px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)' }}>Upload CSV (coming soon)</button><button type="submit" disabled={addingCamera} className="btn btn-primary">{addingCamera ? 'Adding camera…' : 'Add camera'}</button></div></div>
          </form>
        </div>
      )}

      {modalMode && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div style={{ background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: 8, padding: '24px', width: 400, maxWidth: '90vw', maxHeight: '80vh', overflow: 'auto' }}>
            <button type="button" onClick={closeModal} aria-label="Close modal" style={{ position: 'absolute', top: 8, right: 8, width: 24, height: 24, display: 'grid', placeItems: 'center', border: 0, background: 'transparent', cursor: 'pointer' }}><X size={17} aria-hidden="true" /></button>
            {modalMode === 'edit-picker' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <h3 style={{ margin: 0 }}>Edit camera</h3>
                <p style={{ margin: 0, color: 'var(--muted)', fontSize: 13 }}>Choose a camera to edit.</p>
                <select value={editSelectedId} onChange={e => setEditSelectedId(e.target.value)} style={{ padding: 10, border: '1px solid var(--line)', borderRadius: 6, background: '#fff', color: '#111' }}>
                  {cameras.map(camera => <option key={camera.camera_id} value={camera.camera_id}>{camera.display_name || camera.name || camera.camera_id} ({camera.camera_id})</option>)}
                </select>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}><button type="button" onClick={closeModal} style={{ padding: '7px 12px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)' }}>Cancel</button><button type="button" className="btn btn-primary" onClick={() => openModal('edit', editSelectedId)} disabled={!editSelectedId}>Continue</button></div>
              </div>
            )}
            {modalMode === 'remove-picker' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <h3 style={{ margin: 0 }}>Delete camera</h3>
                <p style={{ margin: 0, color: 'var(--muted)', fontSize: 13 }}>Choose the camera to permanently remove from the database and runtime.</p>
                <select value={modalCameraId} onChange={e => setModalCameraId(e.target.value)} style={{ padding: 10, border: '1px solid var(--line)', borderRadius: 6, background: '#fff', color: '#111' }}>
                  {cameras.map(camera => <option key={camera.camera_id} value={camera.camera_id}>{camera.display_name || camera.name || camera.camera_id} ({camera.camera_id})</option>)}
                </select>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}><button type="button" onClick={closeModal} style={{ padding: '7px 12px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)' }}>Cancel</button><button type="button" onClick={() => setModalMode('remove')} disabled={!modalCameraId} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '7px 12px', border: 0, borderRadius: 6, background: 'var(--danger)', color: 'var(--paper)' }}><Trash2 size={14} />Continue</button></div>
              </div>
            )}
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
            {modalMode === 'edit' && (
              <form onSubmit={handleEdit} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <h3 style={{ margin: 0 }}>Edit camera</h3>
                <p style={{ margin: 0, color: 'var(--muted)', fontSize: 13 }}>Update the camera configuration stored in the database.</p>
                {editError && <div role="alert" style={{ padding: 9, borderRadius: 6, background: 'var(--danger-tint)', color: 'var(--danger-deep)', fontSize: 13 }}>{editError}</div>}
                {[['camera_id', 'Camera number / ID'], ['name', 'Camera name'], ['uri', 'RTSP URL'], ['codec', 'Codec'], ['decoder', 'Decoder']].map(([key, label]) => <label key={key} style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 13 }}><span>{label}</span><input required value={editForm[key]} onChange={e => setEditForm({ ...editForm, [key]: e.target.value })} style={{ padding: 9, border: '1px solid var(--line)', borderRadius: 6, background: '#fff', color: '#111' }} /></label>)}
                <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 13 }}><span>Decoding FPS</span><input type="number" min="1" step="1" value={editForm.decoding_fps} onChange={e => setEditForm({ ...editForm, decoding_fps: e.target.value })} style={{ padding: 9, border: '1px solid var(--line)', borderRadius: 6, background: '#fff', color: '#111' }} /></label>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 6 }}><button type="button" onClick={closeModal} style={{ padding: '7px 12px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)' }}>Cancel</button><button type="submit" className="btn btn-primary" style={{ padding: '7px 12px' }}>Save changes</button></div>
              </form>
            )}
            {modalMode === 'remove' && (
              <div>
                <h3>Remove camera</h3>
                <p>Remove camera <strong>{modalCameraId}</strong>?</p>
                <div style={{ margin: '16px 0', display: 'flex', justifyContent: 'flex-end' }}>
                  <button onClick={closeModal} style={{ padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 4, background: 'var(--paper)', color: 'var(--ink)' }}>Cancel</button>
                  <button onClick={handleRemove} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 12px', border: '1px solid var(--line)', borderRadius: 4, background: 'var(--danger)', color: 'var(--paper)' }}><Trash2 size={14} />Remove</button>
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
        <span>{filtered.length} of {cameras.length} cameras</span>
      </div>
    </div>
  );
}
