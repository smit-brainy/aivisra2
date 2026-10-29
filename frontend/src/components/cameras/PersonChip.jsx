import React from 'react';

/**
 * PersonChip — reusable person/vehicle/other filter chip.
 * Mirrors the prototype's type chip style used in Search and Live view filters.
 * Shows type label with color-coded background matching the design token system.
 *
 * Props:
 *   text — chip label (e.g., 'Person', 'Vehicle', 'Other', 'All')
 *   variant — 'person' | 'vehicle' | 'other' | 'all'
 *   selected — whether the chip is selected
 *   onClick — optional click handler
 *   size — 'sm' | 'md' | 'lg' (default: 'md')
 */
export function PersonChip({ text, variant = 'person', selected = false, onClick, size = 'md' }) {
  const variantStyles = {
    person: {
      bg: selected ? 'var(--sky-tint)' : 'var(--sky)',
      ink: selected ? 'var(--sky-deep)' : 'var(--sky-deep)',
    },
    vehicle: {
      bg: selected ? 'var(--honey-tint)' : 'var(--honey)',
      ink: selected ? 'var(--honey-deep)' : 'var(--honey-deep)',
    },
    other: {
      bg: selected ? 'var(--teal-tint)' : 'var(--teal)',
      ink: selected ? 'var(--teal-deep)' : 'var(--teal-deep)',
    },
    all: {
      bg: selected ? 'var(--paper-tint)' : 'var(--paper)',
      ink: selected ? 'var(--paper-deep)' : 'var(--paper-deep)',
    },
  };

  const styles = variantStyles[variant] || variantStyles.person;
  const fontSize = size === 'sm' ? '11px' : size === 'lg' ? '13px' : '12px';
  const padding = size === 'sm' ? '4px 8px' : size === 'lg' ? '8px 16px' : '6px 12px';
  const borderRadius = 4;

  const chipStyle = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    padding: padding,
    borderRadius: borderRadius,
    background: styles.bg,
    color: styles.ink,
    fontSize: fontSize,
    fontWeight: 500,
    letterSpacing: '.04em',
    textTransform: 'uppercase',
    cursor: onClick ? 'pointer' : 'default',
    transition: 'background .15s',
    ...(onClick && { '&:hover': { background: styles.bg.includes('tint') ? styles.bg.replace('tint', 'deep') : styles.bg } }),
  };

  return (
    <div style={chipStyle} onClick={() => onClick && onClick(variant)}>
      {text}
    </div>
  );
}