/**
 * SignInPage — verbatim port of the i-Netra prototype sign-in screen
 * (template: prototype/unpacked-tpl/app-main-template.html lines 794–905;
 *  logic: prototype controller `signIn` / auth message map).
 *
 * UI only: authentication is local against the fictional sample users from
 * `prototype/invr-data.js`. Any non-empty password works (prototype rule).
 */
import React, { useState } from 'react';
import { LOGO_MARK, LOGO_FULL } from '../../prototype/logos';

export const SAMPLE_ACCOUNTS = [
  ['karan.joshi', 'Admin'],
  ['ravi.desai', 'Operator'],
  ['neha.shah', 'Sets her own password'],
  ['first.admin', 'Brand-new box, first admin'],
  ['arjun.mehta', 'Access turned off'],
];

const KNOWN = {
  'karan.joshi': ['admin', null, false, false],
  'ravi.desai': ['operator', null, false, false],
  'neha.shah': ['operator', 'neha', true, false],
  'first.admin': ['admin', null, false, true],
};

const COMMON = ['password12345678', 'passwordpassword', '123456789012345', '1234567890123456',
  'qwertyuiopasdfgh', 'iloveyouiloveyou', 'welcome123456789', 'admin12345678901'];

function msgBox(tone) {
  return { bg: `var(--${tone}-tint)`, ink: `var(--${tone}-deep)` };
}

/** 
 * Props:
 *  onSignedIn({ role, who, first }) — called after sign-in (for the shell to gate pages)
 */
export default function SignInPage({ onSignedIn }) {
  const [aUser, setUser] = useState('');
  const [aPass, setPass] = useState('');
  const [aShow, setShow] = useState(false);
  const [aMsg, setMsg] = useState(null);      // wrong | locked | off | expired
  const [aLocked, setLocked] = useState(null);
  const [aTries, setTries] = useState(0);
  const [aForgot, setForgot] = useState(false);

  // setpw state
  const [pA, setPA] = useState('');
  const [pB, setPB] = useState('');
  const [pShow, setPShow] = useState(false);
  const [pMsg, setPMsg] = useState(null);     // short | weak | match

  const [who, setWho] = useState(null);       // pending setpw user

  // I.clock(sec) — verbatim from prototype/invr-data.js
  const clock = (sec, daySecs = 86400) => {
    const s = ((sec % daySecs) + daySecs) % daySecs;
    const m = Math.floor(s / 60), h = Math.floor(m / 60), mi = m % 60;
    return (h % 12 === 0 ? 12 : h % 12) + ':' + (mi < 10 ? '0' : '') + mi + ' ' + (h < 12 ? 'AM' : 'PM');
  };

  const signIn = (e) => {
    if (e && e.preventDefault) e.preventDefault();
    const u = aUser.trim().toLowerCase();
    if (aLocked && aLocked === u) { setMsg('locked'); return; }
    if (u === 'arjun.mehta') { setMsg('off'); return; }
    const k = KNOWN[u];
    if (k && aPass.length > 0) {
      const [role, whoKey, setpw, first] = k;
      if (setpw) {
        setWho({ name: u, role });
        setPA(''); setPB(''); setPMsg(null);
        return;
      }
      onSignedIn({ role, who: whoKey, first });
      return;
    }
    const tries = aTries + 1;
    if (tries >= 5) { setTries(tries); setMsg('locked'); setLocked(u); }
    else { setTries(tries); setMsg('wrong'); }
  };

  const savePw = (e) => {
    if (e && e.preventDefault) e.preventDefault();
    if (pA.length < 15) { setPMsg('short'); return; }
    if (COMMON.includes(pA.toLowerCase())) { setPMsg('weak'); return; }
    if (pA !== pB) { setPMsg('match'); return; }
    onSignedIn({ role: who.role, who: who.name, first: false }, { passwordSet: true });
  };

  const onEnter = (fn) => (e) => { if (e.key === 'Enter') { e.preventDefault(); fn(); } };

  /* ---------- shared transcribed pieces ---------- */

  let m = null, mbg = null, mink = 'var(--ink)', msub = '';
  if (!who && aMsg) {
    const MSG = {
      wrong: ['That username or password is not right. Try again, or ask your admin to reset it.', '', 'danger'],
      locked: ['Too many wrong tries for this username. Wait 5 minutes and try again, or ask your admin to reset your password.', `You can try again at ${clock(7 * 3600 + 12 * 60 + 300)}.`, 'danger'],
      off: ['Your access to i-Netra is turned off, so ask your admin if you need it back.', '', 'warning'],
      expired: ['You were signed out, so sign in again to carry on where you left off.', 'You’ll go back to Search with the same cameras, time and page.', 'info'],
    }[aMsg];
    if (MSG) {
      m = MSG[0];
      msub = MSG[1];
      ({ bg: mbg, ink: mink } = msgBox(MSG[2]));
    }
  }

  const len = pA.length;
  const PM = {
    short: 'Use at least 15 characters. A short sentence is the easiest to remember.',
    weak: 'That password is too easy to guess. Try a short sentence instead.',
    match: 'The two passwords are not the same yet. Type the new one again.',
  };

  const authAside = (
    <aside
      style={{
        position: 'relative', overflow: 'hidden', display: 'flex', flexDirection: 'column',
        justifyContent: 'space-between', padding: '44px 56px',
        background: 'linear-gradient(115deg, #0858FF 0%, #0A48E0 55%, #0334B8 100%)',
        color: 'var(--paper)',
      }}
    >
      <div
        aria-hidden="true"
        style={{
          position: 'absolute', inset: 0,
          backgroundImage: 'linear-gradient(rgba(255,255,255,.10) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.10) 1px, transparent 1px)',
          backgroundSize: '60px 60px',
          WebkitMaskImage: 'radial-gradient(ellipse 80% 70% at 60% 45%, #000 0%, transparent 78%)',
          maskImage: 'radial-gradient(ellipse 80% 70% at 60% 45%, #000 0%, transparent 78%)',
        }}
      />
      <span aria-hidden="true" style={{ position: 'absolute', top: '22%', right: '18%', width: 6, height: 6, background: 'var(--paper)' }} />
      <span aria-hidden="true" style={{ position: 'absolute', top: '46%', right: '14%', width: 6, height: 6, background: 'var(--signal)' }} />
      <div style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 14 }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 14, fontSize: 26, fontWeight: 600, letterSpacing: '-0.02em' }}>
          <span style={{ width: 52, height: 52, display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 8, background: 'var(--paper)' }}>
            <img src={LOGO_MARK} alt="Brainy Neurals" style={{ width: 34, height: 'auto', display: 'block', flexShrink: 0 }} />
          </span>
          i-Netra
        </span>
      </div>
      <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', gap: 18 }}>
        <span style={{ font: '500 12px/1.3 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', color: 'rgba(255,255,255,.82)' }}>
          You are signing in to
        </span>
        <span style={{ fontSize: 'clamp(56px, 5vw, 96px)', fontWeight: 500, letterSpacing: '-0.035em', lineHeight: 0.95 }}>
          Plant 2
        </span>
        <span style={{ font: '500 17px/1.3 var(--font-mono)', color: 'rgba(255,255,255,.82)' }}>
          Box INVR-01
        </span>
      </div>
      <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', gap: 10, maxWidth: 440, fontSize: 15, lineHeight: 1.5, color: 'rgba(255,255,255,.82)' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--paper)' }}>
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--signal)' }} />
          The box is on and answering
        </span>
        <span>i-Netra runs on this box at the site, with no internet connection.</span>
        <span style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 14 }}>
          <span style={{ font: '500 11px/1 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', color: 'rgba(255,255,255,.82)' }}>Built by</span>
          <span style={{ alignSelf: 'flex-start', display: 'flex', padding: '10px 14px', borderRadius: 8, background: 'var(--paper)' }}>
            <img src={LOGO_FULL} alt="Brainy Neurals" style={{ height: 32, width: 'auto', display: 'block' }} />
          </span>
        </span>
      </div>
    </aside>
  );

  return (
    <div style={{ position: 'absolute', inset: 0, display: 'grid', gridTemplateColumns: 'minmax(0,5fr) minmax(0,7fr)', background: 'var(--paper)' }}>
      {authAside}

      <div style={{ minWidth: 0, minHeight: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', padding: 48, overflow: 'auto' }}>
        {!who ? (
          /* ---- SIGN IN verbatim ---- */
          <div style={{ width: '100%', maxWidth: 460, marginBlock: 'auto', display: 'flex', flexDirection: 'column', gap: 20 }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <h1 style={{ margin: 0, fontSize: 40, fontWeight: 500, letterSpacing: '-0.03em', lineHeight: 1.05 }}>Sign in</h1>
              <p style={{ margin: 0, fontSize: 16, color: 'var(--muted)' }}>Use the username and password your admin gave you.</p>
            </div>

            {m && (
              <div role="alert" style={{ display: 'flex', gap: 12, padding: '12px 14px', background: mbg, color: mink, border: '1px solid var(--line)', borderRadius: 8, fontSize: 15, lineHeight: 1.45 }}>
                <span style={{ width: 8, height: 8, marginTop: 7, flexShrink: 0, background: mink }} />
                <span style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <span>{m}</span>
                  {msub ? <span style={{ font: '500 12.5px/1.4 var(--font-mono)' }}>{msub}</span> : null}
                </span>
              </div>
            )}

            <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span style={{ fontSize: 14, fontWeight: 500 }}>Username</span>
              <input
                value={aUser}
                onChange={(e) => setUser(e.target.value)}
                onKeyDown={onEnter(signIn)}
                autoComplete="username"
                spellCheck="false"
                style={{ height: 52, padding: '0 14px', border: `1px solid ${aMsg === 'wrong' ? 'var(--danger-deep)' : 'var(--line)'}`, borderRadius: 8, background: 'var(--paper)', fontSize: 16, outline: 'none' }}
                onFocus={(e) => { e.target.style.borderColor = 'var(--blue)'; }}
                onBlur={(e) => { e.target.style.borderColor = aMsg === 'wrong' ? 'var(--danger-deep)' : 'var(--line)'; }}
              />
            </label>

            <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span style={{ fontSize: 14, fontWeight: 500 }}>Password</span>
              <span style={{ position: 'relative', display: 'block' }}>
                <input
                  type={aShow ? 'text' : 'password'}
                  value={aPass}
                  onChange={(e) => setPass(e.target.value)}
                  onKeyDown={onEnter(signIn)}
                  autoComplete="current-password"
                  style={{ width: '100%', height: 52, padding: '0 76px 0 14px', border: `1px solid ${aMsg === 'wrong' ? 'var(--danger-deep)' : 'var(--line)'}`, borderRadius: 8, background: 'var(--paper)', fontSize: 16, outline: 'none' }}
                />
                <button
                  type="button"
                  onClick={() => setShow((v) => !v)}
                  style={{ position: 'absolute', right: 6, top: 6, height: 40, padding: '0 12px', borderRadius: 6, fontSize: 14, fontWeight: 500, border: 'none', background: 'transparent', cursor: 'pointer', color: 'var(--ink)' }}
                  onMouseEnter={(e) => { e.target.style.background = 'var(--blue-tint)'; e.target.style.color = 'var(--blue-deep)'; }}
                  onMouseLeave={(e) => { e.target.style.background = 'transparent'; e.target.style.color = 'var(--ink)'; }}
                >
                  {aShow ? 'Hide' : 'Show'}
                </button>
              </span>
            </label>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16, marginTop: 4 }}>
              <button
                type="button"
                onClick={signIn}
                className="btn btn-primary"
                style={{ height: 48, padding: '0 20px', fontSize: 15.5, fontWeight: 500 }}
              >
                Sign in
              </button>
              <button
                type="button"
                onClick={() => setForgot((v) => !v)}
                style={{ fontSize: 14.5, fontWeight: 500, paddingBottom: 1, border: 'none', borderBottom: '1px solid var(--line)', background: 'transparent', cursor: 'pointer' }}
              >
                Forgot your password?
              </button>
            </div>

            {aForgot && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '16px 18px', background: 'var(--bone)', border: '1px solid var(--line)', borderRadius: 8, fontSize: 15, lineHeight: 1.5 }}>
                <span style={{ fontWeight: 500 }}>Your admin resets passwords.</span>
                <span style={{ color: 'var(--muted)', textWrap: 'pretty' }}>
                  i-Netra runs without the internet, so it can’t send a reset email. Ask an admin for Plant 2 to reset yours, then sign in with the temporary password they give you.
                </span>
                <span style={{ color: 'var(--muted)', textWrap: 'pretty' }}>
                  If the only admin forgets their password, the installer can reset it from the box itself.
                </span>
              </div>
            )}

            {/* Prototype-only account filler */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginTop: 8, padding: 12, background: 'var(--ink)', color: 'var(--paper)', borderRadius: 14 }}>
              <span style={{ padding: '2px 6px 8px', font: '500 10.5px/1.4 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--muted-dark)' }}>
                Prototype only · any password · click to fill
              </span>
              {SAMPLE_ACCOUNTS.map(([user, what]) => (
                <button
                  key={user}
                  onClick={() => { setUser(user); setPass('demo-password'); }}
                  style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, height: 38, padding: '0 8px', borderRadius: 8, textAlign: 'left', border: 'none', background: 'transparent', color: 'inherit', cursor: 'pointer' }}
                  onMouseEnter={(e) => { e.target.style.background = 'var(--ink-2)'; }}
                  onMouseLeave={(e) => { e.target.style.background = 'transparent'; }}
                >
                  <span style={{ font: '500 13.5px/1 var(--font-mono)' }}>{user}</span>
                  <span style={{ fontSize: 13, color: 'var(--muted-dark)' }}>{what}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          /* ---- SET YOUR OWN PASSWORD verbatim ---- */
          <div style={{ width: '100%', maxWidth: 480, marginBlock: 'auto', display: 'flex', flexDirection: 'column', gap: 20 }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <span style={{ font: '500 11px/1.3 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--muted)' }}>
                Signed in as {who.name}
              </span>
              <h1 style={{ margin: 0, fontSize: 40, fontWeight: 500, letterSpacing: '-0.03em', lineHeight: 1.05 }}>Set your own password</h1>
              <p style={{ margin: 0, fontSize: 16, color: 'var(--muted)', textWrap: 'pretty' }}>
                You signed in with a temporary password. Choose your own before anything else opens.
              </p>
            </div>

            {pMsg && (
              <div role="alert" style={{ display: 'flex', gap: 12, padding: '12px 14px', background: 'var(--danger-tint)', color: 'var(--danger-deep)', border: '1px solid var(--line)', borderRadius: 8, fontSize: 15, lineHeight: 1.45 }}>
                <span style={{ width: 8, height: 8, marginTop: 7, flexShrink: 0, background: 'var(--danger-deep)' }} />
                <span>{PM[pMsg]}</span>
              </div>
            )}

            <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span style={{ fontSize: 14, fontWeight: 500 }}>New password</span>
              <span style={{ position: 'relative', display: 'block' }}>
                <input
                  type={pShow ? 'text' : 'password'}
                  value={pA}
                  onChange={(e) => { setPA(e.target.value); setPMsg(null); }}
                  onKeyDown={onEnter(savePw)}
                  autoComplete="new-password"
                  style={{ width: '100%', height: 52, padding: '0 76px 0 14px', border: '1px solid var(--line)', borderRadius: 8, background: 'var(--paper)', fontSize: 16, outline: 'none' }}
                />
                <button
                  type="button"
                  onClick={() => setPShow((v) => !v)}
                  style={{ position: 'absolute', right: 6, top: 6, height: 40, padding: '0 12px', borderRadius: 6, fontSize: 14, fontWeight: 500, border: 'none', background: 'transparent', cursor: 'pointer', color: 'var(--ink)' }}
                >
                  {pShow ? 'Hide' : 'Show'}
                </button>
              </span>
            </label>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: -6 }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(15, minmax(0,1fr))', gap: 3 }}>
                {Array.from({ length: 15 }, (_, i) => (
                  <span key={i} style={{ height: 6, borderRadius: 1, background: i < len ? (len >= 15 ? 'var(--blue)' : 'var(--ink)') : 'var(--paper-3)' }} />
                ))}
              </div>
              <span style={{ font: '500 12.5px/1.3 var(--font-mono)', color: len >= 15 ? 'var(--success-deep)' : 'var(--muted)' }}>
                {len >= 15 ? `${len} characters · long enough` : `${len} of 15 characters`}
              </span>
              <span style={{ fontSize: 14.5, lineHeight: 1.5, color: 'var(--muted)', textWrap: 'pretty' }}>
                Use at least 15 characters of any kind. A short sentence you can remember works well, and spaces are allowed.
              </span>
            </div>

            <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span style={{ fontSize: 14, fontWeight: 500 }}>Type it again</span>
              <input
                type={pShow ? 'text' : 'password'}
                value={pB}
                onChange={(e) => { setPB(e.target.value); setPMsg(null); }}
                onKeyDown={onEnter(savePw)}
                autoComplete="new-password"
                style={{ height: 52, padding: '0 14px', border: '1px solid var(--line)', borderRadius: 8, background: 'var(--paper)', fontSize: 16, outline: 'none' }}
              />
            </label>

            {pB.length > 0 && (
              <span style={{ marginTop: -10, font: '500 12.5px/1.3 var(--font-mono)', color: pA === pB ? 'var(--success-deep)' : 'var(--muted)' }}>
                {pA === pB ? 'Both match' : 'Not the same yet'}
              </span>
            )}

            <div style={{ marginTop: 4 }}>
              <button
                type="button"
                onClick={savePw}
                className="btn btn-primary"
                style={{ height: 48, padding: '0 20px', fontSize: 15.5, fontWeight: 500 }}
              >
                Save and continue
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
