import React, { useRef } from 'react';

/**
 * IIntraPrototype — full-screen, verbatim host of the i-Netra Milestone 1
 * clickable prototype (self-extracting bundle under /public/prototype).
 *
 * UI + interactions are verbatim. Backend hooks come later behind this page.
 * A small toolbar lets devs jump straight into a prototype screen/state so
 * the prototype-controls panel isn't always needed.
 */
const LINKS = [
  { label: 'Sign in', src: '/prototype/i-netra.html' },
  { label: 'All screens', src: '/prototype/colour-roles.html' },
];

export default function IIntraPrototype() {
  const frame = useRef(null);

  return (
    <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column' }}>
      <div
        style={{
          flexShrink: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'flex-end',
          gap: 8,
          padding: '6px 12px',
          background: 'var(--paper-2, #eee)',
          borderBottom: '1px solid var(--line, #ddd)',
        }}
      >
        {LINKS.map((l) => (
          <button
            key={l.label}
            onClick={() => {
              if (frame.current) frame.current.src = l.src;
            }}
            style={{ padding: '4px 10px', fontSize: 12.5 }}
          >
            {l.label}
          </button>
        ))}
      </div>
      <iframe
        ref={frame}
        src={LINKS[0].src}
        title="i-Netra prototype UI"
        style={{ flex: 1, width: '100%', border: 'none', display: 'block', background: '#fff' }}
      />
    </div>
  );
}
