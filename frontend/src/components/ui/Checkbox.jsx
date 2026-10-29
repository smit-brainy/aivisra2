import React, { useState } from 'react';

/**
 * Checkbox — reusable UI checkbox component.
 * Mirrors the prototype's checkbox styles used in capability selection and settings.
 *
 * Props:
 *   checked — controlled checked state
 *   onChange — onChange handler
 *   disabled — whether checkbox is disabled
 *   text — optional text label alongside the checkbox
 *   size — 'sm' | 'md' | 'lg'
 */
export default function Checkbox({ checked, onChange, disabled = false, text, size = 'md' }) {
  const sizeStyles = {
    sm: { width: '18px', height: '18px' },
    md: { width: '20px', height: '20px' },
    lg: { width: '24px', height: '24px' },
  };

  const [isChecked, setIsChecked] = useState(checked);

  const inputStyle = {
    width: sizeStyles[size].width,
    height: sizeStyles[size].height,
    flexShrink: 0,
    cursor: disabled ? 'not-available' : 'pointer',
  };

  const labelStyle = {
    fontSize: size === 'sm' ? '12px' : size === 'lg' ? '14px' : '13px',
    lineHeight: 1.5,
    cursor: disabled ? 'not-available' : 'pointer',
  };

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <input
        type="checkbox"
        checked={isChecked}
        onChange={e => setIsChecked(e.target.checked)}
        onChange={onChange}
        style={inputStyle}
        disabled={disabled}
      />
      {text && (
        <span style={labelStyle}>{text}</span>
      )}
    </div>
  );
}