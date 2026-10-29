import React from 'react';
import { useHoverProps } from '../../hooks/useHoverProps';

/**
 * Button — reusable UI button component.
 * Mirrors the prototype's button styles (primary, ink, danger, secondary).
 * Supports size variants and full width.
 *
 * Hover is applied at runtime via useHoverProps() — plain React ignores the
 * `&:hover` CSS-in-JS syntax that the original port used, so those hovers
 * never rendered. The hook merges the variant's hover style on mouse enter.
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
      hover: { background: 'var(--blue-2)', borderColor: 'var(--blue-2)' },
    },
    ink: {
      background: 'var(--ink)',
      color: 'var(--paper)',
      borderColor: 'var(--ink)',
      hover: { background: 'var(--ink-2)', borderColor: 'var(--ink-2)' },
    },
    danger: {
      background: 'var(--danger-tint)',
      color: 'var(--danger-deep)',
      borderColor: 'var(--danger-deep)',
      hover: { background: 'var(--danger-tint)', borderColor: 'var(--danger)' },
    },
    secondary: {
      background: 'var(--paper)',
      color: 'var(--ink)',
      borderColor: 'var(--line)',
      hover: { borderColor: 'var(--ink)' },
    },
    text: {
      background: 'transparent',
      color: 'var(--blue)',
      borderColor: 'transparent',
      hover: { color: 'var(--blue-2)' },
    },
  };

  const baseStyle = {
    fontFamily: 'var(--font-mono)',
    fontWeight: 500,
    borderRadius: 6,
    border: '1px solid currentColor',
    cursor: disabled ? 'not-allowed' : 'pointer',
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
    borderColor: variantStyle.borderColor,
    ...(disabled && { opacity: 0.5, cursor: 'not-allowed' }),
  };

  const hover = useHoverProps(style, disabled ? null : variantStyle.hover);

  return (
    <button
      {...hover}
      onClick={onClick}
      disabled={disabled}
      {...props}
    >
      {children}
    </button>
  );
}
