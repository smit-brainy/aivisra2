import React from 'react';

/**
 * AccessDenied — i-Netra access denied overlay.
 * Shown when a non-admin user tries to navigate to Settings or Add cameras.
 * Mirrors the prototype's `isSettings: scr === 'settings' && admin` check.
 *
 * Props: onBack — callback to go back to previous screen (typically Home)
 */
export default function AccessDenied({ onBack }) {
  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      background: 'rgba(10,10,11,.85)',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 100,
      color: 'var(--ink)',
      fontFamily: 'var(--font-sans)',
    }}>
      <div style={{
        background: 'var(--paper)',
        border: '1px solid var(--line)',
        borderRadius: '14px',
        padding: '40px 32px',
        maxWidth: '400px',
        textAlign: 'center',
        width: '100%',
      }}>
        <div style={{ marginBottom: '24px' }}>
          <span style={{
            width: '40px', height: '40px', margin: '0 auto 16px',
            borderRadius: '50', background: 'var(--danger-tint)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '24', color: 'var(--danger-deep)',
          }}><svg style={{ width: '24', height: '24' }} viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round'>
            <line x1='18' y1='6' x2='6' y2='18' />
            <line x1='6' y1='6' x2='18' y2='18' />
          </svg></span>
        </div>
        <h2 style={{ margin: '0 0 12', fontSize: '22', fontWeight: '500', letterSpacing: '-0.02em' }}>
          Access Denied
        </h2>
        <p style={{ margin: '0 0 24', fontSize: '15', lineHeight: '1.5', color: 'var(--muted)' }}>
          You don't have permission to view this page.
        </p>
        <button onClick={() => onBack()} style={{
          padding: '10px 24px', border: '1px solid var(--line)',
          borderRadius: '8', background: 'var(--paper)',
          color: 'var(--ink)', fontSize: '14', fontWeight: '500',
          cursor: 'pointer',
        }}>
          Go Home
        </button>
      </div>
    </div>
  );
}