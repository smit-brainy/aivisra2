/**
 * Placeholder for i-Netra screens not yet ported from the prototype.
 * Themed to the i-Netra dark sidebar/ink so it sits as a real screen while the
 * port progresses. Will be replaced screen-by-screen (see agents_folder/task.md).
 */
import React from 'react';

export default function InetraPlaceholder({ title, next = 'Ported next — see agents_folder/task.md', onOpenPrototype }) {
  return (
    <div
      style={{
        flex: 1,
        minWidth: 0,
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 12,
        background: 'var(--paper)',
        color: 'var(--ink)',
        padding: 48,
        textAlign: 'center',
      }}
    >
      <span style={{ font: '500 11px/1 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--muted)' }}>
        i-Netra · Plant 2 · INVR-01
      </span>
      <h1 style={{ margin: 0, fontSize: 40, fontWeight: 500, letterSpacing: '-0.03em', lineHeight: 1.05 }}>{title}</h1>
      <p style={{ margin: 0, fontSize: 16, color: 'var(--muted)', maxWidth: 460 }}>{next}</p>
      {onOpenPrototype && (
        <button
          onClick={onOpenPrototype}
          className="btn btn-ghost"
          style={{ marginTop: 12, height: 44, fontSize: 14.5 }}
        >
          Open verbatim prototype →
        </button>
      )}
    </div>
  );
}
