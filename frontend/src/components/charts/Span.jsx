import React from 'react';

/**
 * Span — standardized timestamp span component.
 * Mirrors the prototype's span display style for timestamps like
 * "Now ·", date labels, and hour indicators.
 *
 * Props:
 *   text — the span text content
 *   variant — 'now' | 'date' | 'hour' | 'custom'
 *   isNow — whether this represents the current time (adds "Now" indicator)
 *   className — optional additional CSS classes
 */
export function Span({ text, variant = 'custom', isNow = false, className }) {
  const variantStyles = {
    now: {
      marginRight: '8px',
      color: isNow ? 'var(--ink)' : 'var(--muted)',
      fontSize: '11px',
      fontWeight: 500,
      letterSpacing: '.08em',
      textTransform: 'uppercase',
    },
    date: {
      marginRight: '6px',
      color: 'var(--muted)',
      fontSize: '10px',
      fontWeight: 500,
      letterSpacing: '.06em',
      textTransform: 'uppercase',
    },
    hour: {
      color: 'var(--muted)',
      fontSize: '10px',
      fontWeight: 500,
      letterSpacing: '.04em',
      textTransform: 'uppercase',
    },
    custom: {
      color: 'var(--muted)',
      fontSize: '11px',
      fontWeight: 500,
      letterSpacing: '.08em',
      textTransform: 'uppercase',
    },
  };

  const style = {
    ...variantStyles[variant],
    ...(isNow && { marginRight: '12px', color: 'var(--ink)' }),
    ...(className && { className }),
  };

  return <span style={style}>{text}</span>;
}