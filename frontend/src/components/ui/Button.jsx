import React from 'react';

/**
 * Button — reusable UI button component.
 * Mirrors the prototype's button styles (primary, ink, danger, secondary).
 * Supports size variants and full width.
 *
 * Props:
 *   children — button label
 *   variant — 'primary' | 'ink' | 'danger' | 'secondary' | 'text'
 *   size — 'sm' | 'md' | 'lg' | 'xl'
 *   fullWidth — whether to span full width
 *   onClick — click handler
 *   disabled — whether button is disabled
 *   block — block-level button (grid style)
 */
export default function Button({
  children,
  variant = 'primary',
  size = 'md',
  fullWidth = false,
  block = false,
  onClick,
  disabled = false,
  ...props
}) {
  const sizeStyles = {
    sm: { height: '32px', fontSize: '12px', padding: '0 12px' },
    md: { height: '36px', fontSize: '13.5px', padding: '0 16px' },
    lg: { height: '40px', fontSize: '14px', padding: '0 20px' },
    xl: { height: '44px', fontSize: '15px', padding: '0 22px' },
  };

  const variantStyles = {
    primary: {
      background: 'var(--blue)',
      color: 'var(--paper)',
      borderColor: 'var(--blue)',
      _hover: { background: 'var(--blue-2)' },
    },
    ink: {
      background: 'var(--ink)',
      color: 'var(--paper)',
      borderColor: 'var(--ink)',
      _hover: { background: 'var(--ink-2)' },
    },
    danger: {
      background: 'var(--danger-tint)',
      color: 'var(--danger-deep)',
      borderColor: 'var(--danger-deep)',
      _hover: { background: '#b71c1c' },
    },
    secondary: {
      background: 'var(--paper)',
      color: 'var(--ink)',
      borderColor: 'var(--line)',
      _hover: { borderColor: 'var(--ink)', background: 'var(--ink-2)' },
    },
    text: {
      background: 'transparent',
      color: 'var(--blue)',
      borderColor: 'transparent',
      _hover: { color: 'var(--blue-2)' },
    },
  };

  const baseStyle = {
    fontFamily: 'var(--font-mono)',
    fontWeight: 500,
    borderRadius: 6,
    border: '1px solid currentColor',
    cursor: disabled ? 'not-available' : 'pointer',
    transition: 'background .2s, border-color .2s, color .2s',
    ...sizeStyles[size],
    ...(fullWidth && { width: '100%' }),
    ...(block && { width: '100%' }),
  };

  const variantStyle = variantStyles[variant] || variantStyles.primary;

  const style = {
    ...baseStyle,
    background: variantStyle.background,
    color: variantStyle.color,
    borderColor: variantStyle.background.includes('var(--') ? 'var(--line)' : variantStyle.background.includes('var(--') ? variantStyle.background.replace('var(--', 'var(--') : variantStyle.background),
    ...(disabled && { opacity: 0.5, cursor: 'not-available' }),
    ...(variantStyle._hover && { '&:hover': variantStyle._hover }),
  };

  return (
    <button
      style={style}
      onClick={onClick}
      disabled={disabled}
      {...props}
    >
      {children}
    </button>
  );
}

/* eslint-enable */
// styled-component-like fallback for environments without styled-components
// This Button can be used directly or wrapped with a styling library