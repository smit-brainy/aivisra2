import React from 'react';
import { useHoverProps } from '../../hooks/useHoverProps';

/**
 * PersonChip — reusable person/vehicle/other filter chip.
 * Mirrors the prototype's type chip style used in Search and Live view filters.
 * Shows type label with color-coded background matching the design token system.
 *
 * Hover is applied at runtime via useHoverProps() — the previous `&:hover`
 * key inside the inline style object was silently ignored by React, so the
 * chip never changed appearance on hover.
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
      ink: 'var(--sky-deep)',
      hoverBg: selected ? 'var(--sky)' : 'var(--sky-tint)',
    },
    vehicle: {
      bg: selected ? 'var(--honey-tint)' : 'var(--honey)',
      ink: 'var(--honey-deep)',
      hoverBg: selected ? 'var(--honey)' : 'var(--honey-tint)',
    },
    other: {
      bg: selected ? 'var(--teal-tint)' : 'var(--teal)',
      ink: 'var(--teal-deep)',
      hoverBg: selected ? 'var(--teal)' : 'var(--teal-tint)',
    },
    all: {
      bg: selected ? 'var(--paper-2)' : 'var(--paper)',
      ink: 'var(--ink)',
      hoverBg: selected ? 'var(--paper)' : 'var(--paper-2)',
    },
  };

  const styles = variantStyles[variant] || variantStyles.person;
  const fontSize = size === 'sm' ? '11px' : size === 'lg' ? '13px' : '12px';
  const padding = size === 'sm' ? '4px 8px' : size === 'lg' ? '8px 16px' : '6px 12px';

  const chipStyle = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    padding: padding,
    borderRadius: 4,
    background: styles.bg,
    color: styles.ink,
    fontSize: fontSize,
    fontWeight: 500,
    letterSpacing: '.04em',
    textTransform: 'uppercase',
    cursor: onClick ? 'pointer' : 'default',
    transition: 'background .15s',
  };

  const hover = useHoverProps(chipStyle, onClick ? { background: styles.hoverBg } : null);

  return (
    <div {...hover} onClick={() => onClick && onClick(variant)}>
      {text}
    </div>
  );
}

export default PersonChip;
