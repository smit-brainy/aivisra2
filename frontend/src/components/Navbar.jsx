import React, { useState } from 'react';
import { LOGO_MARK } from '../prototype/logos';

export const NAV_ITEMS = [['home', 'Home'], ['live', 'Live view'], ['search', 'Search'], ['cameras', 'Cameras']];

export function Sidebar({ active = 'home', admin = false, onNav }) {
  const items = admin ? [...NAV_ITEMS, ['settings', 'Settings']] : NAV_ITEMS;
  return <nav aria-label="Main navigation" style={{ gridColumn: 1, gridRow: 2, display: 'flex', flexDirection: 'column', gap: 2, padding: '16px 12px', borderRight: '1px solid var(--line-dark)', background: 'var(--ink)' }}>
    {items.map(([id, label]) => <button key={id} type="button" onClick={() => onNav?.(id)} style={{ height: 44, display: 'flex', alignItems: 'center', gap: 12, padding: '0 12px', border: 0, borderRadius: 8, textAlign: 'left', fontSize: 15, fontWeight: active === id ? 500 : 400, background: active === id ? 'var(--ink-2)' : 'transparent', color: active === id ? 'var(--paper)' : 'var(--muted-dark)', cursor: 'pointer' }}><span style={{ width: 6, height: 6, background: active === id ? 'var(--blue)' : 'transparent' }} />{label}</button>)}
  </nav>;
}

export default function Navbar({ session, active = 'home', onNav, onSignOut, camSummary = '0 of 0 cameras online', camDot = 'var(--paper-3)', legacy = false, activeTab, setActiveTab, theme, onToggleTheme }) {
  const [profileOpen, setProfileOpen] = useState(false);
  const name = session?.display_name || session?.username || session?.name || session?.who || 'User';
  const role = session?.role || 'operator';
  const initials = name.split(/\s+/).map(part => part[0]).join('').slice(0, 2).toUpperCase();
  const legacyTabs = [{ id: 'demo', label: 'Camera View' }, { id: 'grid', label: 'Multi-Grid Camera' }, { id: 'onboarding', label: 'Camera Setup' }, { id: 'spatial', label: 'Spatial Rules & Zones' }, { id: 'events', label: 'Events & Clips' }];
  return <header style={{ gridColumn: legacy ? 'auto' : '1 / 3', gridRow: legacy ? 'auto' : 1, display: 'flex', alignItems: 'center', justifyContent: 'space-between', minHeight: 56, padding: '0 16px 0 20px', borderBottom: '1px solid var(--line-dark)', background: 'var(--ink)', color: 'var(--paper)', position: 'relative', zIndex: 20 }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}><img src={LOGO_MARK} alt="Brainy Neurals" style={{ width: 28 }} /><strong>i-Netra</strong><span style={{ color: 'var(--muted-dark)' }}>Plant 2</span></div>
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      {legacy ? <nav className="nav-tab-bar">{legacyTabs.map(tab => <button key={tab.id} className={`nav-tab-btn ${activeTab === tab.id ? 'active' : ''}`} onClick={() => setActiveTab(tab.id)}>{tab.label}</button>)}</nav> : <button type="button" onClick={() => onNav?.('cameras')} style={{ height: 38, padding: '0 12px', border: '1px solid var(--line-dark)', borderRadius: 8, background: 'var(--ink-2)', color: 'var(--paper)', cursor: 'pointer' }}><span style={{ color: camDot }}>● </span>{camSummary}</button>}
      {legacy && <button type="button" className="theme-toggle-btn" onClick={onToggleTheme} aria-label="Toggle theme">{theme === 'dark' ? '☀' : '☾'}</button>}
      <div style={{ position: 'relative' }}><button type="button" onClick={() => setProfileOpen(v => !v)} aria-expanded={profileOpen} style={{ height: 38, display: 'flex', alignItems: 'center', gap: 9, padding: '0 10px 0 5px', border: '1px solid var(--line-dark)', borderRadius: 8, background: 'var(--ink-2)', color: 'var(--paper)', cursor: 'pointer' }}><span style={{ width: 28, height: 28, display: 'grid', placeItems: 'center', borderRadius: '50%', background: 'var(--teal)', color: 'var(--ink)', fontSize: 11, fontWeight: 700 }}>{initials}</span><span style={{ textAlign: 'left' }}><span style={{ display: 'block', fontSize: 13.5 }}>{name}</span><span style={{ display: 'block', fontSize: 10, color: 'var(--muted-dark)', textTransform: 'uppercase' }}>{role}</span></span>▾</button>{profileOpen && <div style={{ position: 'absolute', right: 0, top: 'calc(100% + 6px)', width: 230, padding: 8, background: 'var(--paper)', color: 'var(--ink)', border: '1px solid var(--line)', borderRadius: 12, boxShadow: '0 20px 40px rgba(0,0,0,.2)' }}><div style={{ padding: 10, borderBottom: '1px solid var(--line-soft)' }}><strong>{name}</strong><div style={{ color: 'var(--muted)', fontSize: 13 }}>{role}</div></div><button type="button" onClick={() => { setProfileOpen(false); onSignOut?.(); }} style={{ width: '100%', marginTop: 6, padding: 10, border: 0, background: 'transparent', color: 'var(--ink)', textAlign: 'left', cursor: 'pointer' }}>Log out</button></div>}</div>
    </div>
  </header>;
}
