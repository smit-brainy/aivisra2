import React, { useState } from 'react';
import { LOGO_MARK, LOGO_FULL } from '../../prototype/logos';
import { login, signup } from '../../utils/api';
import NotificationPopup from '../../components/NotificationPopup';

const inputStyle = { height: 52, padding: '0 14px', border: '1px solid var(--line)', borderRadius: 8, background: 'var(--paper)', color: 'var(--ink)', fontSize: 16, outline: 'none' };

export default function SignInPage({ onSignedIn }) {
  const [mode, setMode] = useState('signin');
  const [username, setUsername] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [role, setRole] = useState('operator');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const notify = (type, message, title) => setNotice({ type, message, title });

  async function submit(event) {
    event.preventDefault();
    if (!username.trim() || !password) return notify('warning', 'Enter your username and password.');
    if (mode === 'signup' && password !== confirm) return notify('warning', 'The passwords do not match.');
    setBusy(true);
    try {
      if (mode === 'signup') {
        await signup({ username: username.trim(), display_name: displayName.trim() || undefined, password, role });
        notify('success', 'Your request was sent to an administrator. You can sign in after it is approved.', 'Request submitted');
        setMode('signin'); setPassword(''); setConfirm('');
      } else {
        const result = await login({ username: username.trim(), password });
        onSignedIn({ ...result.user, session: result.session, screen: 'home' });
      }
    } catch (error) { notify('error', error.message || 'Unable to contact the backend.', 'Authentication error'); }
    finally { setBusy(false); }
  }

  return <div style={{ position: 'absolute', inset: 0, display: 'grid', gridTemplateColumns: 'minmax(0,5fr) minmax(0,7fr)', background: 'var(--paper)', color: 'var(--ink)' }}>
    <NotificationPopup notification={notice} onClose={() => setNotice(null)} />
    <aside style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', padding: '44px 56px', background: 'linear-gradient(115deg, #0858FF, #0334B8)', color: 'var(--paper)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, fontSize: 26, fontWeight: 600 }}><span style={{ width: 52, height: 52, display: 'grid', placeItems: 'center', borderRadius: 8, background: 'var(--paper)' }}><img src={LOGO_MARK} alt="Brainy Neurals" style={{ width: 34 }} /></span>i-Netra</div>
      <div><span style={{ display: 'block', font: '500 12px var(--font-mono)', opacity: .82 }}>SECURE CAMERA OPERATIONS</span><span style={{ display: 'block', marginTop: 16, fontSize: 'clamp(56px, 5vw, 96px)', fontWeight: 500, lineHeight: .95 }}>Plant 2</span></div>
      <div style={{ maxWidth: 440, lineHeight: 1.5, opacity: .84 }}>Local box authentication.<span style={{ display: 'flex', marginTop: 18, padding: '10px 14px', width: 'fit-content', borderRadius: 8, background: 'var(--paper)' }}><img src={LOGO_FULL} alt="Brainy Neurals" style={{ height: 32 }} /></span></div>
    </aside>
    <main style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 48, overflow: 'auto' }}><form onSubmit={submit} style={{ width: '100%', maxWidth: 460, display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div><h1 style={{ margin: 0, color: 'var(--ink)', fontSize: 40, fontWeight: 500 }}>{mode === 'signin' ? 'Sign in' : 'Create account'}</h1><p style={{ color: 'var(--muted)', fontSize: 16 }}>{mode === 'signin' ? 'Use your account to continue.' : 'Create a local user account.'}</p></div>
      {mode === 'signup' && <label><span style={{ color: 'var(--ink)', display: 'block', marginBottom: 6 }}>Display name</span><input value={displayName} onChange={e => setDisplayName(e.target.value)} autoComplete="name" style={{ ...inputStyle, width: '100%' }} /></label>}
      {mode === 'signup' && <label><span style={{ color: 'var(--ink)', display: 'block', marginBottom: 6 }}>Requested access</span><select value={role} onChange={e => setRole(e.target.value)} style={{ ...inputStyle, width: '100%' }}><option value="operator">Operator</option><option value="viewer">User</option></select><small style={{ display: 'block', marginTop: 6, color: 'var(--muted)' }}>An administrator will review and approve your request.</small></label>}
      <label><span style={{ color: 'var(--ink)', display: 'block', marginBottom: 6 }}>Username</span><input value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" style={{ ...inputStyle, width: '100%' }} /></label>
      <label><span style={{ color: 'var(--ink)', display: 'block', marginBottom: 6 }}>Password</span><span style={{ position: 'relative', display: 'block' }}><input type={show ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)} autoComplete={mode === 'signin' ? 'current-password' : 'new-password'} style={{ ...inputStyle, width: '100%', paddingRight: 72 }} /><button type="button" onClick={() => setShow(!show)} style={{ position: 'absolute', right: 6, top: 6, height: 40, border: 0, background: 'transparent', color: 'var(--ink)' }}>{show ? 'Hide' : 'Show'}</button></span></label>
      {mode === 'signup' && <label><span style={{ color: 'var(--ink)', display: 'block', marginBottom: 6 }}>Confirm password</span><input type="password" value={confirm} onChange={e => setConfirm(e.target.value)} autoComplete="new-password" style={{ ...inputStyle, width: '100%' }} /></label>}
      <button type="submit" disabled={busy} className="btn btn-primary" style={{ height: 48 }}>{busy ? 'Please wait…' : mode === 'signin' ? 'Sign in' : 'Create account'}</button>
      {mode === 'signin' && <button type="button" onClick={() => notify('info', 'Contact your administrator to reset your password.', 'Forgot password')} style={{ border: 0, background: 'transparent', color: 'var(--blue-deep)', cursor: 'pointer' }}>Forgot password?</button>}
      <button type="button" onClick={() => { setMode(mode === 'signin' ? 'signup' : 'signin'); setPassword(''); setConfirm(''); }} style={{ border: 0, background: 'transparent', color: 'var(--blue-deep)', cursor: 'pointer' }}>{mode === 'signin' ? 'Need an account? Sign up' : 'Already have an account? Sign in'}</button>
      <p style={{ margin: 0, textAlign: 'center', color: 'var(--muted)', fontSize: 13 }}>Forgot password is currently unavailable. Contact an administrator.</p>
    </form></main>
  </div>;
}
