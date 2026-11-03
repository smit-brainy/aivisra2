import React, { useEffect, useState } from 'react';
import { Minus, Plus, RefreshCw, Trash2, UserRoundPen } from 'lucide-react';
import { deleteUser, fetchCameras, fetchStorageInfo, fetchSystemInfo, fetchUsers, updateCameraMetadata, updateStorage, updateUser } from '../../utils/api';
import NotificationPopup from '../../components/NotificationPopup';

export default function SettingsSimple({ session }) {
  const [section, setSection] = useState('storage');
  const [days, setDays] = useState(30);
  const [unlimited, setUnlimited] = useState(false);
  const [storageInfo, setStorageInfo] = useState(null);
  const [spaceCameras, setSpaceCameras] = useState([]);
  const [users, setUsers] = useState([]);
  const [userError, setUserError] = useState('');
  const [editingUser, setEditingUser] = useState(null);
  const [editUsername, setEditUsername] = useState('');
  const [editRole, setEditRole] = useState('operator');
  const [notification, setNotification] = useState(null);
  const [systemInfo, setSystemInfo] = useState(null);
  const [capacityCameras, setCapacityCameras] = useState([]);
  const loadUsers = () => fetchUsers().then(body => setUsers(body.users || [])).catch(error => setUserError(error.message));
  useEffect(() => {
    if (section !== 'users' || session?.role !== 'admin') return;
    loadUsers();
    const timer = window.setInterval(loadUsers, 10000);
    return () => window.clearInterval(timer);
  }, [section, session?.role]);
  useEffect(() => {
    if (section !== 'about') return;
    fetchSystemInfo().then(setSystemInfo).catch(() => setSystemInfo(null));
    const timer = window.setInterval(() => fetchSystemInfo().then(setSystemInfo).catch(() => {}), 1000);
    return () => window.clearInterval(timer);
  }, [section]);
  useEffect(() => {
    if (section !== 'space') return;
    let disposed = false;
    fetchCameras().then(value => { if (!disposed) setSpaceCameras(value || []); }).catch(error => console.warn('[Settings] space estimate camera refresh failed', error));
    return () => { disposed = true; };
  }, [section]);
  useEffect(() => {
    if (section !== 'capacity') return;
    let disposed = false;
    const load = () => fetchCameras().then(value => { if (!disposed) setCapacityCameras(value || []); }).catch(error => console.warn('[Settings] capacity refresh failed', error));
    load();
    const timer = window.setInterval(load, 10000);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [section]);
  const changeCameraDetail = async (cameraId, level) => {
    const previous = capacityCameras;
    setCapacityCameras(current => current.map(camera => camera.camera_id === cameraId ? { ...camera, level } : camera));
    try {
      const updated = await updateCameraMetadata(cameraId, { level });
      setCapacityCameras(current => current.map(camera => camera.camera_id === cameraId ? { ...camera, ...updated, level } : camera));
      setNotification({ type: 'success', title: 'Detail updated', message: 'Inference frequency updated for this camera.' });
    } catch (error) {
      setCapacityCameras(previous);
      setNotification({ type: 'error', title: 'Detail update failed', message: error.message || 'The inference frequency could not be updated.' });
    }
  };
  const detailOptions = [['low', 'Low', '1 FPS'], ['standard', 'Standard', '5 FPS'], ['high', 'High', '15 FPS'], ['maximum', 'Maximum', '25 FPS']];
  const estimate = (() => {
    const bitrateMbps = spaceCameras.reduce((total, camera) => {
      const codec = String(camera.codec || 'h264').toLowerCase();
      const base = codec.includes('265') || codec.includes('hevc') ? 1.2 : codec.includes('264') ? 2.0 : 2.5;
      const fps = Number(camera.decoding_fps) || 25;
      return total + base * Math.min(1.5, Math.max(0.5, fps / 25));
    }, 0);
    const fullBytes = bitrateMbps * 1000 * 1000 / 8 * 86400 * (unlimited ? 30 : days) * spaceCameras.length / Math.max(1, spaceCameras.length);
    // Temporary evidence model: one 10-second clip at the camera bitrate plus
    // a 250 KB snapshot per stored event. This is explicitly an estimate until
    // the recorder exposes exact bytes per event.
    const eventBytes = (storageInfo?.event_count || 0) * (bitrateMbps * 1000 * 1000 / 8 * 10 + 250 * 1024);
    const savedBytes = Math.max(0, fullBytes - eventBytes);
    const savedPercent = fullBytes > 0 ? Math.min(100, Math.max(0, savedBytes / fullBytes * 100)) : 0;
    return { bitrateMbps, fullBytes, eventBytes, savedBytes, savedPercent };
  })();
  const formatBytes = bytes => {
    if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
    const index = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
    return `${(bytes / (1024 ** index)).toFixed(index > 2 ? 1 : 0)} ${units[index]}`;
  };
  useEffect(() => {
    if (section !== 'storage') return;
    fetchStorageInfo().then(info => { setStorageInfo(info); setDays(info.retention_days); }).catch(() => {});
  }, [section]);
  const saveRetention = async value => {
    const daysValue = Math.max(1, Math.min(3650, Number(value) || 1));
    try { const info = await updateStorage({ retention_days: daysValue }); setStorageInfo(info); setDays(daysValue); setNotification({ type: 'success', title: 'Storage updated', message: `Clips and evidence older than ${daysValue} day${daysValue === 1 ? '' : 's'} are removed automatically.` }); }
    catch (error) { setNotification({ type: 'error', title: 'Storage update failed', message: 'The retention setting could not be updated. Please try again.' }); }
  };
  const saveUser = async userId => {
    const requestedUsername = editUsername.trim();
    const requestedRole = editRole;
    try {
      await updateUser(userId, { username: requestedUsername, role: requestedRole });
    } catch (error) { setNotification({ type: 'error', title: 'User update failed', message: error.message.includes('500') ? 'The account could not be updated right now. Please try again.' : error.message }); return; }
    setUsers(current => current.map(user => user.user_id === userId ? { ...user, username: requestedUsername, role: requestedRole } : user));
    setEditingUser(null); setUserError('');
    setNotification({ type: 'success', title: 'User updated', message: 'The user account was updated successfully.' });
  };
  const removeUser = async user => {
    if (!window.confirm(`Delete ${user.display_name || user.username}?`)) return;
    try { await deleteUser(user.user_id); setUsers(current => current.filter(item => item.user_id !== user.user_id)); setUserError(''); }
    catch (error) { setNotification({ type: 'error', title: 'User deletion failed', message: error.message.includes('500') ? 'The account could not be deleted right now. Please try again.' : error.message }); }
  };
  const sections = [['recording', 'RECORDING'], ['storage', 'Storage'], ['space', 'Space saved'], ['capacity', 'Capacity and detail'], ['people', 'PEOPLE'], ['users', 'Users'], ['box', 'THIS BOX'], ['about', 'About this box']];
  return <><NotificationPopup notification={notification} onClose={() => setNotification(null)} /><div className="settings-page" style={{ display: 'grid', gridTemplateColumns: '330px minmax(0,1fr)', minHeight: '100%', background: 'var(--paper)', color: 'var(--ink)' }}>
    <aside style={{ padding: '34px 18px', borderRight: '1px solid var(--line)' }}><h1 style={{ margin: '0 20px 46px', fontSize: 30, fontWeight: 500 }}>Settings</h1>{sections.map(([key, label]) => key === 'recording' || key === 'people' || key === 'box' ? <div key={key} style={{ margin: '18px 20px 8px', font: '500 11px var(--font-mono)', letterSpacing: '.08em', color: 'var(--muted)' }}>{label}</div> : <button type="button" key={key} onClick={() => setSection(key)} className="hvr-bone" style={{ display: 'block', width: '100%', padding: '14px 20px', textAlign: 'left', border: section === key ? '2px solid var(--blue)' : '1px solid transparent', borderRadius: 12, background: section === key ? 'var(--blue-tint)' : 'transparent', color: section === key ? 'var(--blue-deep)' : 'var(--ink)', fontSize: 16 }}>{section === key ? '■ ' : ''}{label}</button>)}</aside>
    <main style={{ padding: '40px 58px', maxWidth: 1400 }}><div style={{ font: '500 11px var(--font-mono)', letterSpacing: '.08em', color: 'var(--muted)' }}>SETTINGS · {section.toUpperCase()}</div><h2 style={{ margin: '12px 0', fontSize: 40, fontWeight: 500 }}>{section === 'storage' ? 'Storage' : section === 'space' ? 'Space saved' : section === 'capacity' ? 'Capacity and detail' : section === 'users' ? 'Users' : 'About this box'}</h2><p style={{ margin: '0 0 28px', fontSize: 22, color: 'var(--muted)' }}>{section === 'storage' ? 'How long clips stay on the box before the oldest are removed.' : 'Manage this part of your i-Netra box.'}</p>
      {section === 'storage' && <div style={{ display: 'grid', gridTemplateColumns: '1.1fr .9fr', gap: 24 }}><section style={{ padding: 34, border: '1px solid var(--line)', borderRadius: 16 }}><h3 style={{ marginTop: 0, fontSize: 25 }}>Keep clips for</h3><button type="button" onClick={() => setUnlimited(false)} style={{ width: '100%', padding: 20, textAlign: 'left', border: !unlimited ? '2px solid var(--blue)' : '1px solid var(--line)', borderRadius: 12, background: !unlimited ? 'var(--blue-tint)' : 'var(--paper)', color: 'var(--ink)' }}><strong style={{ display: 'flex', alignItems: 'center', gap: 8 }}><span style={{ color: 'var(--blue)' }}>●</span>{days} days</strong><div style={{ margin: '12px 0 0 38px', color: 'var(--muted)' }}>Each night the box removes clips older than this, oldest day first.</div><div style={{ display: 'flex', gap: 8, margin: '14px 0 0 38px' }}><button type="button" onClick={e => { e.stopPropagation(); saveRetention(days - 1); }} style={{ display: 'grid', placeItems: 'center', width: 32, height: 32, color: 'var(--ink)', background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: 6 }}><Minus size={15} /></button><button type="button" onClick={e => { e.stopPropagation(); saveRetention(days + 1); }} style={{ display: 'grid', placeItems: 'center', width: 32, height: 32, color: 'var(--ink)', background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: 6 }}><Plus size={15} /></button></div></button><button type="button" onClick={() => { setUnlimited(true); }} style={{ width: '100%', marginTop: 14, padding: 20, textAlign: 'left', border: unlimited ? '2px solid var(--blue)' : '1px solid var(--line)', borderRadius: 12, background: unlimited ? 'var(--blue-tint)' : 'var(--paper)', color: 'var(--ink)' }}><strong style={{ display: 'flex', alignItems: 'center', gap: 8 }}><span style={{ color: 'var(--muted)' }}>○</span>As long as the disk has room</strong><div style={{ margin: '12px 0 0 38px', color: 'var(--muted)' }}>Retention is controlled by available disk space.</div></button><div style={{ marginTop: 22, padding: 16, background: 'var(--bone)', borderRadius: 10, color: 'var(--muted)' }}>{storageInfo ? `${storageInfo.event_count} events currently stored` : 'Loading storage data…'}</div></section><section style={{ padding: 34, border: '1px solid var(--line)', borderRadius: 16 }}><h3 style={{ marginTop: 0, fontSize: 25 }}>Disk</h3><div style={{ font: 'italic 72px var(--font-serif)' }}>{storageInfo ? `${(storageInfo.used_bytes / 1099511627776).toFixed(1)} TB` : '—'} <small style={{ font: 'normal 18px var(--font-sans)', color: 'var(--muted)' }}>of {storageInfo ? `${(storageInfo.total_bytes / 1099511627776).toFixed(1)} TB` : '—'} in use</small></div><div style={{ height: 16, margin: '20px 0', background: 'var(--paper-3)', borderRadius: 4 }}><div style={{ width: storageInfo ? `${Math.min(100, (storageInfo.used_bytes / storageInfo.total_bytes) * 100)}%` : '0%', height: '100%', background: 'var(--blue)', borderRadius: 4 }} /></div><p>Events retained <strong style={{ float: 'right' }}>{storageInfo?.event_count ?? '—'}</strong></p><p>Free <strong style={{ float: 'right' }}>{storageInfo ? `${(storageInfo.free_bytes / 1099511627776).toFixed(1)} TB` : '—'}</strong></p><p>Retention <strong style={{ float: 'right' }}>{storageInfo?.retention_days ?? '—'} days</strong></p></section></div>}
      {section === 'space' && <section style={{ padding: 24, border: '1px solid var(--line)', borderRadius: 16 }}>
        <h3 style={{ marginTop: 0, fontSize: 25 }}>Estimated space saved</h3>
        <p style={{ color: 'var(--muted)' }}>A theoretical comparison of continuous recording versus event-only evidence for the current cameras and retention period.</p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: 14 }}>
          {[['Continuous recording', formatBytes(estimate.fullBytes)], ['Event-only evidence', formatBytes(estimate.eventBytes)], ['Estimated saved', formatBytes(estimate.savedBytes)], ['Space saved', `${estimate.savedPercent.toFixed(1)}%`]].map(([label, value]) => <div key={label} style={{ padding: 18, background: 'var(--bone)', border: '1px solid var(--line)', borderRadius: 10 }}><div style={{ color: 'var(--muted)', fontSize: 13, marginBottom: 8 }}>{label}</div><strong style={{ fontSize: 26, color: 'var(--ink)' }}>{value}</strong></div>)}
        </div>
        <div style={{ marginTop: 18, color: 'var(--muted)', fontSize: 14 }}>Based on {spaceCameras.length} stream{spaceCameras.length === 1 ? '' : 's'}, approximately {estimate.bitrateMbps.toFixed(1)} Mbps combined, {unlimited ? '30' : days} days, {storageInfo?.event_count || 0} stored events, one 10-second clip per event, and a 250 KB snapshot. Actual values vary with camera bitrate and event duration.</div>
      </section>}
      {section === 'users' && <section style={{ padding: 24, border: '1px solid var(--line)', borderRadius: 16 }}>
        {userError && <p role="alert" style={{ color: 'var(--danger-deep)' }}>{userError}</p>}
        {session?.role !== 'admin' ? <p style={{ color: 'var(--muted)' }}>Only administrators can manage users.</p> : <><div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}><button type="button" onClick={loadUsers} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '7px 10px', border: '1px solid var(--line)', borderRadius: 7, background: 'var(--paper)', color: 'var(--ink)' }}><RefreshCw size={14} />Refresh</button></div>{users.map(user => <div key={user.user_id} style={{ display: 'grid', gridTemplateColumns: 'minmax(180px,1fr) minmax(150px,1fr) 140px 180px', gap: 14, alignItems: 'center', padding: '14px 0', borderBottom: '1px solid var(--line-soft)' }}>
          <div><strong>{user.display_name || user.username}</strong><div style={{ color: 'var(--muted)', fontSize: 13 }}>{user.username}</div></div>
          <span style={{ color: 'var(--muted)', fontSize: 13 }}>{user.last_login_at ? new Date(user.last_login_at * 1000).toLocaleString('en-IN') : 'Never signed in'}</span>
          <span style={{ textTransform: 'capitalize' }}>{user.role === 'viewer' ? 'User' : user.role}</span>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>{user.user_id !== session?.user_id && <><button type="button" onClick={() => { setEditingUser(user.user_id); setEditUsername(user.username); setEditRole(user.role); }} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '7px 9px', border: '1px solid var(--line)', borderRadius: 7, background: 'var(--paper)', color: 'var(--ink)' }}><UserRoundPen size={14} />Manage</button><button type="button" onClick={() => removeUser(user)} aria-label={`Delete ${user.username}`} style={{ display: 'inline-flex', alignItems: 'center', padding: '7px 9px', border: '1px solid var(--danger)', borderRadius: 7, background: 'var(--paper)', color: 'var(--danger-deep)' }}><Trash2 size={14} /></button></>}</div>
          {editingUser === user.user_id && <div style={{ gridColumn: '1 / -1', display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', paddingTop: 8 }}><input value={editUsername} onChange={event => setEditUsername(event.target.value)} placeholder="Username" style={{ padding: 8, border: '1px solid var(--line)', borderRadius: 6, background: '#fff', color: '#111', caretColor: '#111' }} /><select value={editRole} onChange={event => setEditRole(event.target.value)} style={{ width: 140, padding: '8px 30px 8px 8px', border: '1px solid var(--line)', borderRadius: 6, background: '#fff', color: '#111', appearance: 'auto' }}><option value="admin">Admin</option><option value="operator">Operator</option><option value="viewer">User</option></select><button type="button" onClick={() => saveUser(user.user_id)} style={{ padding: '8px 12px', border: 0, borderRadius: 6, background: 'var(--blue)', color: 'var(--paper)' }}>Save</button><button type="button" onClick={() => setEditingUser(null)} style={{ padding: '8px 12px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)' }}>Cancel</button></div>}
        </div>)}</>}
      </section>}
      {section === 'about' && <section style={{ padding: 24, border: '1px solid var(--line)', borderRadius: 16 }}><div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16 }}>{[['System OS', systemInfo?.os], ['System RAM', systemInfo?.ram?.total_bytes ? `${(systemInfo.ram.total_bytes / 1073741824).toFixed(1)} GB` : 'Unavailable'], ['System CPU', systemInfo?.cpu], ['System GPU', systemInfo?.gpu], ['Storage', systemInfo?.storage?.total_bytes ? `${(systemInfo.storage.free_bytes / 1099511627776).toFixed(1)} TB free of ${(systemInfo.storage.total_bytes / 1099511627776).toFixed(1)} TB` : 'Unavailable'], ['Time zone', systemInfo?.time_zone], ['Current time', systemInfo?.current_time ? new Date(systemInfo.current_time).toLocaleString('en-IN') : 'Loading…'], ['Cameras', systemInfo ? String(systemInfo.camera_count) : 'Loading…'], ['Software version', systemInfo?.software_version || 'Loading…']].map(([label, value]) => <div key={label} style={{ padding: '16px 18px', background: 'var(--bone)', border: '1px solid var(--line)', borderRadius: 10 }}><div style={{ color: 'var(--muted)', fontSize: 13, marginBottom: 7 }}>{label}</div><strong style={{ overflowWrap: 'anywhere' }}>{value || 'Loading…'}</strong></div>)}</div></section>}
      {section === 'capacity' && <section style={{ padding: 24, border: '1px solid var(--line)', borderRadius: 16 }}>
        <p style={{ marginTop: 0, color: 'var(--muted)' }}>Choose how often AI inference runs for each camera. Changes apply immediately without restarting the camera stream.</p>
        {capacityCameras.length === 0 ? <p style={{ color: 'var(--muted)' }}>No cameras are currently available.</p> : capacityCameras.map(camera => <div key={camera.camera_id} style={{ display: 'grid', gridTemplateColumns: 'minmax(180px, 1fr) minmax(280px, 2fr)', gap: 20, alignItems: 'center', padding: '18px 0', borderBottom: '1px solid var(--line-soft)' }}>
          <div><strong>{camera.display_name || camera.name || camera.camera_id}</strong><div style={{ color: 'var(--muted)', font: '13px var(--font-mono)' }}>{camera.camera_id}</div></div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 8 }}>{detailOptions.map(([value, label, fps]) => <button type="button" key={value} onClick={() => camera.level !== value && changeCameraDetail(camera.camera_id, value)} style={{ padding: '10px 8px', border: camera.level === value ? '2px solid var(--blue)' : '1px solid var(--line)', borderRadius: 8, background: camera.level === value ? 'var(--blue-tint)' : 'var(--paper)', color: 'var(--ink)', cursor: 'pointer' }}><span style={{ display: 'block', fontWeight: 600 }}>{label}</span><small style={{ color: 'var(--muted)' }}>{fps}</small></button>)}</div>
        </div>)}
      </section>}
    </main>
  </div></>;
}
