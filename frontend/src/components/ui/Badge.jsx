import React from 'react';

/**
 * Badge — reusable UI badge/component.
 * Mirrors the prototype's badge/token styles used throughout the UI.
 *
 * Props:
 *   text — badge label
 *   variant — 'success' | 'danger' | 'warning' | 'info' | 'primary'
 *   size — 'sm' | 'md' | 'lg'
 *   pill — whether to use pill shape (rounded corners)
 */
export default function Badge({
  text,
  variant = 'primary',
  size = 'md',
  pill = false,
}) {
  const variantColors = {
    success: { bg: 'var(--success-tint)', ink: 'var(--success-deep)' },
    danger: { bg: 'var(--danger-tint)', ink: 'var(--danger-deep)' },
    warning: { bg: 'var(--warning-tint)', ink: 'var(--warning-deep)' },
    info: { bg: 'var(--info-tint)', ink: 'var(--info-deep)' },
    primary: { bg: 'var(--blue-tint)', ink: 'var(--blue-deep)' },
  };

  const colors = variantColors[variant] || variantColors.primary;
  const fontSize = size === 'sm' ? '11px' : size === 'lg' ? '13px' : '12px';
  const padding = pill ? '6px 10px' : '4px 8px';
  const borderRadius = pill ? '999px' : 4;

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        padding: padding,
        borderRadius: borderRadius,
        background: colors.bg,
        color: colors.ink,
        fontSize: fontSize,
        fontWeight: 500,
        letterSpacing: '.04em',
        textTransform: 'uppercase',
      }}
    >
      {text}
    </span>
  );
}