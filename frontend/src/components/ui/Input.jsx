import React from 'react';

/**
 * Input — reusable UI input component.
 * Mirrors the prototype's input styles with design tokens.
 *
 * Props:
 *   type — input type (text, password, email, number)
 *   placeholder — placeholder text
 *   value — controlled value
 *   onChange — onChange handler
 *   label — optional label text
 *   labelProps — optional label style overrides
 *   inputProps — additional input props
 *   disabled — whether input is disabled
 *   fullWidth — whether input spans full width
 */
export default function Input({
  type = 'text',
  placeholder = '',
  value,
  onChange,
  label,
  labelProps,
  inputProps = {},
  disabled = false,
  fullWidth = false,
  className = '',
}) {
  const inputStyle = {
    width: fullWidth ? '100%' : '100%',
    height: '40px',
    padding: '0 14px',
    border: '1px solid var(--line)',
    borderRadius: 8,
    background: 'var(--paper)',
    color: 'var(--ink)',
    fontSize: '14.5px',
    fontFamily: 'inherit',
    outline: 'none',
    transition: 'border-color .15s, box-shadow .15s',
    ...(disabled && {
      opacity: 0.5,
      cursor: 'not-allowed',
    }),
  };

  // `.fcs-input` carries the prototype's `style-focus` ring
  // (border-color: var(--blue); box-shadow: 0 0 0 3px var(--blue-tint)).
  const inputClassName = ['fcs-input', inputProps.className, className]
    .filter(Boolean)
    .join(' ');

  const labelStyle = {
    fontFamily: 'var(--font-mono)',
    fontSize: '10.5px',
    letterSpacing: '.08em',
    textTransform: 'uppercase',
    color: 'var(--muted)',
    display: 'block',
    marginBottom: '4px',
  };

  return (
    <div style={{ width: fullWidth ? '100%' : 'auto' }}>
      {label && (
        <span style={labelStyle}>{label}</span>
      )}
      <input
        type={type}
        placeholder={placeholder}
        value={value}
        onChange={onChange}
        style={inputStyle}
        disabled={disabled}
        {...inputProps}
        className={inputClassName}
      />
    </div>
  );
}