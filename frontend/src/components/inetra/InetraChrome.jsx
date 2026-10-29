/**
 * Verbatim i-Netra Signals chrome: top bar + sidebar navigation,
 * ported from prototype/unpacked-tpl/app-main-template.html (header/nav/main
 * shell) with the controller `chrome()` bindings.
 *
 * Home · Live view · Search · Cameras (+ Settings for admins).
 */
import React from 'react';
import { LOGO_MARK } from '../../prototype/logos';

export const NAV_DEFS = [
  ['home', 'Home'],
  ['live', 'Live view'],
  ['search', 'Search'],
  ['cameras', 'Cameras'],
];

/**
 * TopBar — verbatim header. camDot/camSummary keep the prototype's offline
 * semantics (substituted with real camera data by the caller later).
 */
export function TopBar({ session, onSignOut, onNav, camSummary = 'No cameras yet', camDot = 'var(--paper-3)' }) {
  const admin = session.role === 'admin';
  const u = session.meta || { name: session.name || 'Karan Joshi', role: admin ? 'Admin' : 'Operator', initials: admin ? 'KJ' : 'RD' };
  const invr = (typeof window !== 'undefined' && window.INVR) || null;
  // Verbatim dlList()/tickDl(): sample DOWNLOADS list, preparing progress at +6%/tick.
  const [dls, setDls] = React.useState(null);
  const [dlOpen, setDlOpen] = React.useState(false);
  const dlListRef = React.useRef(null);
  React.useEffect(() => {
    if (!invr) return;
    dlListRef.current = (invr.DOWNLOADS || []).map(d => Object.assign({}, d));
    setDls(dlListRef.current);
    const di = setInterval(() => {
      const list = dlListRef.current || [];
      if (!list.some(d => d.status === 'preparing')) return;
      let next = list.map(d => {
        if (d.status !== 'preparing') return d;
        const pr = Math.min(1, (d.progress || 0) + 0.06);
        return pr >= 1 ? Object.assign({}, d, { status: 'ready', progress: 1, mb: d.est }) : Object.assign({}, d, { progress: pr });
      });
      dlListRef.current = next;
      setDls(next);
    }, 500);
    const onKey = e => { if (e.key === 'Escape') setDlOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => { clearInterval(di); window.removeEventListener('keydown', onKey); };
  }, []);

  const list = dls || [];
  const mine = (admin ? list : list.filter(d => d.byKey === (session.who || session.role))).slice().sort((a, b) => b.at - a.at);
  const prep = mine.filter(d => d.status === 'preparing');
  const mbText = mb => mb >= 1000 ? (mb / 1000).toFixed(1) + ' GB' : Math.round(mb) + ' MB';
  const rows = mine.map(d => {
    const st = d.status;
    return {
      name: d.name,
      meta: [d.events + ' events', st === 'ready' ? mbText(d.mb) : st === 'preparing' ? 'about ' + mbText(d.est) : '', admin ? 'by ' + d.by : '', invr ? invr.when(d.at) : ''].filter(Boolean).join(' · '),
      status: st === 'preparing' ? `Preparing · ${Math.round((d.progress || 0) * 100)}%` : st === 'ready' ? 'Ready' : 'Failed',
      chipBg: st === 'ready' ? 'var(--success-tint)' : st === 'failed' ? 'var(--danger-tint)' : 'var(--blue-tint)',
      chipInk: st === 'ready' ? 'var(--success-deep)' : st === 'failed' ? 'var(--danger-deep)' : 'var(--blue-deep)',
      preparing: st === 'preparing', ready: st === 'ready', failed: st === 'failed',
      w: Math.round((d.progress || 0) * 100) + '%',
      reason: d.reason || 'Something went wrong while preparing it.',
      save: () => {},
      retry: () => {
        const next = (dlListRef.current || []).map(x => x.id === d.id ? Object.assign({}, x, { status: 'preparing', progress: 0 }) : x);
        dlListRef.current = next; setDls(next);
      },
    };
  });

  return <header style={{ gridColumn: '1 / 3', gridRow: 1, display: 'grid', gridTemplateColumns: '224px minmax(0,1fr)', alignItems: 'center', borderBottom: '1px solid var(--line-dark)', background: 'var(--ink)', color: 'var(--paper)', position: 'relative', zIndex: 20 }}>
    <style>{`
      .hvr-dl:hover { border-color: var(--paper); }
      .hvr-blue2:hover { background: var(--blue-2); }
    `}</style>
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, height: '100%', padding: '0 20px', borderRight: '1px solid var(--line-dark)' }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 9, fontSize: 18, fontWeight: 600, letterSpacing: '-0.02em', whiteSpace: 'nowrap' }}>
        <img src={LOGO_MARK} alt="Brainy Neurals" style={{ width: 28, height: 'auto', display: 'block', flexShrink: 0 }} />
        i-Netra
      </span>
      <span style={{ width: 1, height: 22, background: 'var(--line-dark)' }} />
      <span style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        <span style={{ fontSize: 14, fontWeight: 500, lineHeight: 1.1 }}>Plant 2</span>
        <span style={{ font: '500 10.5px/1 var(--font-mono)', letterSpacing: '.06em', color: 'var(--muted-dark)' }}>INVR-01</span>
      </span>
    </div>
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 8, padding: '0 16px 0 20px', minWidth: 0 }}>
      <button onClick={() => onNav && onNav('cameras')} style={{ height: 38, display: 'flex', alignItems: 'center', gap: 8, padding: '0 12px', border: '1px solid var(--line-dark)', borderRadius: 8, background: 'var(--ink-2)', color: 'var(--paper)', fontSize: 14, whiteSpace: 'nowrap', cursor: 'pointer' }}>
        <span style={{ width: 8, height: 8, borderRadius: '50%', background: camDot }} />
        {camSummary}
      </button>
      <div style={{ position: 'relative' }}>
        <button
          onClick={() => setDlOpen(v => !v)}
          aria-expanded={dlOpen}
          style={{ height: 38, display: 'flex', alignItems: 'center', gap: 8, padding: '0 12px', border: `1px solid ${dlOpen ? 'var(--paper)' : 'var(--line-dark)'}`, borderRadius: 8, background: 'var(--ink-2)', color: 'var(--paper)', fontSize: 14, cursor: 'pointer' }}
          className="hvr-dl"
        >
          Downloads
          {prep.length > 0 && <span style={{ font: '500 11px/1 var(--font-mono)', padding: '3px 6px', borderRadius: 4, background: 'var(--blue-deep)', color: 'var(--blue-tint)' }}>{Math.round((prep[0].progress || 0) * 100) + '%'}</span>}
        </button>
        {dlOpen && (
          <div role="dialog" aria-label="Downloads" style={{ position: 'absolute', right: 0, top: 'calc(100% + 6px)', zIndex: 60, width: 470, maxHeight: 640, display: 'flex', flexDirection: 'column', background: 'var(--paper)', color: 'var(--ink)', border: '1px solid var(--line)', borderRadius: 14, boxShadow: '0 30px 60px -30px rgba(10,10,11,.35), 0 2px 6px rgba(10,10,11,.06)', overflow: 'hidden' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, padding: '16px 18px 12px', borderBottom: '1px solid var(--line-soft)' }}>
              <span style={{ fontSize: 17, fontWeight: 500 }}>Downloads</span>
              <span style={{ font: '500 10.5px/1 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--muted)' }}>{admin ? 'Everyone’s · newest first' : 'Yours · newest first'}</span>
            </div>
            <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
              {rows.map((d, i) => (
                <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: '14px 18px', borderBottom: '1px solid var(--line-soft)' }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
                    <span style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
                      <span style={{ fontSize: 15, fontWeight: 500 }}>{d.name}</span>
                      <span style={{ fontSize: 13, color: 'var(--muted)', textWrap: 'pretty' }}>{d.meta}</span>
                    </span>
                    <span style={{ flexShrink: 0, padding: '4px 7px', borderRadius: 4, background: d.chipBg, color: d.chipInk, font: '500 11px/1 var(--font-mono)', letterSpacing: '.06em', textTransform: 'uppercase', whiteSpace: 'nowrap' }}>{d.status}</span>
                  </div>
                  {d.preparing && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      <div style={{ height: 4, borderRadius: 2, background: 'var(--paper-3)', overflow: 'hidden' }}><div style={{ width: d.w, height: '100%', background: 'var(--blue)' }} /></div>
                      <span style={{ fontSize: 12.5, color: 'var(--muted)' }}>Keeps going if you leave this page.</span>
                    </div>
                  )}
                  {d.ready && (
                    <div><button onClick={d.save} className="hvr-blue2" style={{ height: 36, padding: '0 14px', borderRadius: 8, background: 'var(--blue)', color: 'var(--paper)', fontSize: 14, fontWeight: 500, border: 'none', cursor: 'pointer' }}>Download</button></div>
                  )}
                  {d.failed && (
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '8px 8px 8px 12px', background: 'var(--danger-tint)', border: '1px solid var(--line)', borderRadius: 8, color: 'var(--danger-deep)', fontSize: 13.5 }}>
                      <span>{d.reason}</span>
                      <button onClick={d.retry} className="hvr-ink-border" style={{ flexShrink: 0, height: 32, padding: '0 12px', border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', color: 'var(--ink)', fontSize: 13.5, fontWeight: 500, cursor: 'pointer' }}>Try again</button>
                    </div>
                  )}
                </div>
              ))}
              {rows.length === 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '28px 22px 30px' }}>
                  <span style={{ fontSize: 16, fontWeight: 500 }}>No downloads yet.</span>
                  <span style={{ fontSize: 14.5, color: 'var(--muted)' }}>Select events in Search to download them.</span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
      <AccountButton session={session} u={u} admin={admin} onSignOut={onSignOut} />
    </div>
  </header>;
}

export function AccountButton({ session, u, admin, onSignOut }) {
  const [menu, setMenu] = React.useState(false);
  const avatarBg = ({ admin: 'var(--iris)', operator: 'var(--teal)', neha: 'var(--sky)' })[session.who || session.role] || 'var(--iris)';
  const avatarInk = (session.who || session.role) === 'admin' ? 'var(--paper)' : 'var(--ink)';
  return (
    <div style={{ position: 'relative' }}>
      <button
        onClick={() => setMenu((v) => !v)}
        aria-expanded={menu}
        style={{ height: 38, display: 'flex', alignItems: 'center', gap: 10, padding: '0 10px 0 5px', border: `1px solid ${menu ? 'var(--paper)' : 'var(--line-dark)'}`, borderRadius: 8, background: 'var(--ink-2)', color: 'var(--paper)', cursor: 'pointer' }}
      >
        <span style={{ width: 28, height: 28, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: avatarBg, color: avatarInk, font: '600 11px/1 var(--font-mono)' }}>{u.initials}</span>
        <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 3, lineHeight: 1 }}>
          <span style={{ fontSize: 13.5, fontWeight: 500 }}>{u.name}</span>
          <span style={{ font: '500 10px/1 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--muted-dark)' }}>{u.role}</span>
        </span>
        <span style={{ fontSize: 11, color: 'var(--muted-dark)' }}>▾</span>
      </button>
      {menu && (
        <div
          style={{ position: 'absolute', right: 0, top: 'calc(100% + 6px)', width: 260, padding: 8, background: 'var(--paper)', color: 'var(--ink)', border: '1px solid var(--line)', borderRadius: 14, boxShadow: '0 30px 60px -30px rgba(10,10,11,.35), 0 2px 6px rgba(10,10,11,.06)', zIndex: 60 }}
          onMouseLeave={() => setMenu(false)}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3, padding: '10px 10px 12px', borderBottom: '1px solid var(--line-soft)' }}>
            <span style={{ fontSize: 15, fontWeight: 500 }}>{u.name}</span>
            <span style={{ fontSize: 13.5, color: 'var(--muted)' }}>
              {admin ? 'Admin · cameras, settings and accounts' : 'Operator · watch, search and download'}
            </span>
          </div>
          {(admin ? [['cameras', 'Cameras'], ['settings', 'Settings']] : [['cameras', 'Cameras']]).map(([k, label]) => (
            <button
              key={k}
              onClick={() => { setMenu(false); onNav && onNav(k); }}
              style={{ width: '100%', height: 40, padding: '0 10px', borderRadius: 8, textAlign: 'left', fontSize: 14.5, border: 'none', background: 'transparent', color: 'var(--ink)', cursor: 'pointer' }}
            >
              {label}
            </button>
          ))}
          <button
            onClick={() => { setMenu(false); onSignOut && onSignOut(); }}
            style={{ width: '100%', height: 40, marginTop: 6, padding: '0 10px', borderRadius: 8, textAlign: 'left', fontSize: 14.5, border: 'none', background: 'transparent', color: 'var(--ink)', cursor: 'pointer' }}
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * Sidebar — verbatim i-Netra navigation rail.
 */
export function Sidebar({ active, admin, onNav }) {
  const defs = NAV_DEFS.concat(admin ? [['settings', 'Settings']] : []);
  return (
    <nav aria-label="Main" style={{ gridColumn: 1, gridRow: 2, display: 'flex', flexDirection: 'column', gap: 2, padding: '16px 12px', borderRight: '1px solid var(--line-dark)', background: 'var(--ink)' }}>
      {defs.map(([k, label]) => {
        const on = active === k;
        return (
          <button
            key={k}
            onClick={() => onNav && onNav(k)}
            style={{ height: 44, display: 'flex', alignItems: 'center', gap: 12, padding: '0 12px', borderRadius: 8, textAlign: 'left', fontSize: 15, fontWeight: on ? 500 : 400, background: on ? 'var(--ink-2)' : 'transparent', color: on ? 'var(--paper)' : 'var(--muted-dark)', boxShadow: on ? '0 0 0 1px var(--line-dark)' : 'none', border: 'none', cursor: 'pointer' }}
          >
            <span style={{ width: 6, height: 6, flexShrink: 0, background: on ? 'var(--blue)' : 'transparent' }} />
            {label}
          </button>
        );
      })}
    </nav>
  );
}
