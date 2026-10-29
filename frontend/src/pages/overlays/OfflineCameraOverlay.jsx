import React from 'react';

/**
 * OfflineCameraOverlay — i-Netra offline camera overlay.
 * Shown when a camera is offline, mirroring the prototype's misc-b.tpl.html
 * offline state with coral dot and "Offline since {date}" text.
 *
 * Props: cam — camera object with num, name, since, status properties
 *        onRetry — callback when user clicks retry
 */
export default function OfflineCameraOverlay({ cam, onRetry }) {
  const sinceDate = cam.since ? new Date(1970, 0, 1).setSeconds(cam.since / 60 / 60 / 24 * -1) : null;
  const sinceDisplay = sinceDate
    ? `${Math.abs(sinceDate / 86400)} days ago`
    : 'unknown';

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
        padding: '32px 24px',
        maxWidth: '400px',
        textAlign: 'center',
        width: '100%',
      }}>
        <div style={{ marginBottom: '24px' }}>
          <span style={{
            width: '32px', height: '32px', margin: '0 auto 12px',
            borderRadius: '50', background: 'var(--coral)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '18', color: 'var(--ink)',
          }}>●</span>
        </div>
        <h2 style={{ margin: '0 0 12', fontSize: '20', fontWeight: '500', letterSpacing: '-0.02em' }}>
          Camera Offline
        </h2>
        <p style={{ margin: '0 0 24', fontSize: '15', lineHeight: '1.5', color: 'var(--muted)' }}>
          This camera has been offline since {sinceDisplay}.
        </p>
        <div style={{ marginTop: '24', display: 'flex', gap: '12', justifyContent: 'center' }}>
          <button onClick={() => onRetry()} style={{
            padding: '8px 16px', border: '1px solid var(--line)',
            borderRadius: '6', background: 'var(--paper)',
            color: 'var(--ink)', fontSize: '13', cursor: 'pointer',
          }}>
            Retry
          </button>
          <button onClick={() => {} } style={{
            padding: '8px 16px', border: '1px solid var(--line)',
            borderRadius: '6', background: 'var(--paper-2)',
            color: 'var(--muted)', fontSize: '13', cursor: 'pointer',
          }}>
            Ignore
          </button>
        </div>
      </div>
    </div>
  );
}