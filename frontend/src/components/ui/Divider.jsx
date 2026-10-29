import React from 'react';

/**
 * Divider — reusable UI divider line.
 * Mirrors the prototype's divider styles used between sections.
 *
 * Props:
 *   orientation — 'horizontal' | 'vertical'
 *   light — whether to use light surface styling (on dark backgrounds)
 *   dashed — whether to use dashed line
 */
export default function Divider({ orientation = 'horizontal', light = false, dashed = false }) {
  const baseStyle = {
    margin: '8px 0',
    border: 'none',
    ...(orientation === 'horizontal'
      ? { borderTop: `1px ${dashed ? 'dashed' : 'solid'} ${light ? 'var(--line-soft)' : 'var(--line)'} }
      : { borderLeft: `1px ${dashed ? 'dashed' : 'solid'} ${light ? 'var(--line-soft)' : 'var(--line)'} } ),
  };

  return <div style={baseStyle} />;
}