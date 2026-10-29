import React from 'react';

/**
 * SessionExpiredOverlay — i-Netra session expired overlay.
 * Shown when the user's session has expired and they need to sign in again.
 * Mirrors the prototype's sign-out / session expiration flow.
 *
 * Props: onSignIn — callback to sign in again
 *        onCancel — callback to go to home (optional)
 */
export default function SessionExpiredOverlay({ onSignIn, onCancel }) {
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
            borderRadius: '50', background: 'var(--ink-tint)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '24', color: 'var(--ink-deep)',
          }}>🔒</span>
        </div>
        <h2 style={{ margin: '0 0 12', fontSize: '22', fontWeight: '500', letterSpacing: '-0.02em' }}>
          Session Expired
        </h2>
        <p style={{ margin: '0 0 24', fontSize: '15', lineHeight: '1.5', color: 'var(--muted)' }}>
          Your session has expired. Please sign in again to continue.
        </p>
        <div style={{ marginTop: '24', display: 'flex', gap: '12', justifyContent: 'center' }}>
          <button onClick={() => onSignIn()} style={{
            padding: '10px 24px', border: '1px solid var(--line)',
            borderRadius: '8', background: 'var(--ink)',
            color: 'var(--paper)', fontSize: '14', fontWeight: '500', cursor: 'pointer',
          }}>
            Sign In
          </button>
          {onCancel && (
            <button onClick={() => onCancel()} style={{
              padding: '10px 24px', border: '1px solid var(--line)',
              borderRadius: '8', background: 'var(--paper)',
              color: 'var(--ink)', fontSize: '14', cursor: 'pointer',
            }}>
              Go Home
            </button>
          )}
        </div>
      </div>
    </div>
  );
}