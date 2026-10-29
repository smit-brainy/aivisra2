import React from 'react';

/**
 * DiskFullOverlay — i-Netra disk full overlay.
 * Shown when the disk is nearly full, mirroring the prototype's settings-template.html
 * diskFull state with "The disk is 95% full, 7.6 TB of 8 TB" message.
 *
 * Props: onKeep — callback to keep current levels
 *        onChange — callback to go to settings storage section
 */
export default function DiskFullOverlay({ kept, recv, onKeep, onChange }) {
  const pct = Math.round(100 - (kept / recv * 100));
  const keptGB = Math.round(kept / 1024);
  const recvGB = Math.round(recv / 1024);

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
        maxWidth: '480px',
        width: '100%',
      }}>
        <div style={{ marginBottom: '24px' }}>
          <span style={{
            width: '32px', height: '32px', margin: '0 auto 12px',
            borderRadius: '50', background: 'var(--warning-tint)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '18', color: 'var(--warning-deep)',
          }}>!</span>
        </div>
        <h2 style={{ margin: '0 0 12', fontSize: '20', fontWeight: '500', letterSpacing: '-0.02em' }}>
          Disk Nearly Full
        </h2>
        <p style={{ margin: '0 0 24', fontSize: '15', lineHeight: '1.5', color: 'var(--muted)' }}>
          The disk is {pct}% full, {keptGB} GB kept of {recvGB} GB received.
          When it fills, the box removes the oldest day of clips first, starting with 28 Sep, so new events are always saved.
        </p>
        <div style={{ marginTop: '24', display: 'flex', gap: '12', justifyContent: 'center' }}>
          <button onClick={() => onKeep()} style={{
            padding: '8px 16px', border: '1px solid var(--line)',
            borderRadius: '6', background: 'var(--paper)',
            color: 'var(--ink)', fontSize: '13', fontWeight: '500', cursor: 'pointer',
          }}>
            Keep Current Levels
          </button>
          <button onClick={() => onChange()} style={{
            padding: '8px 16px', border: '1px solid var(--line)',
            borderRadius: '6', background: 'var(--paper-2)',
            color: 'var(--ink)', fontSize: '13', cursor: 'pointer',
          }}>
            Change Settings
          </button>
        </div>
      </div>
    </div>
  );
}