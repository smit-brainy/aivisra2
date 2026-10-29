import React from 'react';

/**
 * CameraTile — reusable camera display tile.
 * Mirrors the prototype's camera tile style used in live view and clip player.
 * Shows camera number, name, area badge, and live indicator dot.
 *
 * Props:
 *   cam — camera object with num, name, area, status, kind properties
 *   small — whether to render in small size (default: false)
 *   onClick — optional click handler
 */
export default function CameraTile({ cam, small = false, onClick }) {
  const isCam = cam && cam.num !== undefined;
  const num = isCam ? cam.num : 1;
  const name = isCam ? cam.name : 'Camera';
  const area = isCam ? cam.area : 'Unassigned';
  const status = isCam ? cam.status : 'online';
  const kind = isCam ? (cam.kind || 'person') : 'person';

  const dotColor = status === 'online' ? '#4caf50' : '#f44336';
  const bgGradient = kind === 'person'
    ? 'radial-gradient(80% 55% at 30% 6%, rgba(59,69,82,.20), transparent 62%), linear-gradient(180deg, #3b4552 0%, #2d343d ' + (30 + num * 3) + '%, #22272d ' + (30 + num * 3 + 0.6) + '%, #181b1f 100%)'
    : kind === 'vehicle'
    ? 'radial-gradient(80% 55% at 30% 6%, rgba(220,230,241,.20), transparent 62%), linear-gradient(180deg, #e0e6f1 0%, #c5d0e6 ' + (30 + num * 3) + '%, #a9bfe3 ' + (30 + num * 3 + 0.6) + '%, #8c9ecc 100%)'
    : 'radial-gradient(80% 55% at 30% 6%, rgba(180,140,130,.20), transparent 62%), linear-gradient(180deg, #b48c84 0%, #a87d78 ' + (30 + num * 3) + '%, #9c706b ' + (30 + num * 3 + 0.6) + '%, #8f635e 100%)';

  const tileStyle = {
    border: '1px solid var(--line)',
    borderRadius: small ? 4 : 8,
    background: small ? 'var(--paper-2)' : bgGradient,
    color: 'var(--ink)',
    cursor: onClick ? 'pointer' : 'default',
    overflow: 'hidden',
    ...(onClick && { transition: 'transform .15s' }),
    ...(onClick && { '&:hover': { transform: 'translateY(-2px)' } }),
  };

  const nameStyle = {
    fontSize: small ? '11px' : '14px',
    fontWeight: 500,
    letterSpacing: '-0.01em',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    margin: small ? '4px 0 0' : '8px 0 0',
  };

  const areaStyle = {
    fontSize: small ? '10px' : '12px',
    fontWeight: 500,
    letterSpacing: '.04em',
    textTransform: 'uppercase',
    color: 'var(--muted)',
    margin: small ? '2px 0 0' : '6px 0 0',
  };

  const dotStyle = {
    width: small ? '12px' : '16px',
    height: small ? '12px' : '16px',
    borderRadius: '50',
    background: dotColor,
    flexShrink: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontWeight: 'bold',
    fontSize: small ? '10px' : '12px',
    color: 'var(--paper)',
  };

  const contentStyle = {
    padding: small ? '8px' : '12px',
  };

  if (onClick) {
    return (
      <div style={tileStyle} onClick={() => onClick(cam)}>      
        <div style={{ display: 'flex', alignItems: 'center', gap: small ? '6px' : '10px' }}>
          <span style={dotStyle}>{num}</span>
          <span style={nameStyle}>{name}</span>
          <span style={areaStyle}>{area}</span>
        </div>
      </div>
    );
  }

  return (
    <div style={tileStyle}>
      <div style={{ display: 'flex', alignItems: 'center', gap: small ? '6px' : '10px' }}>
        <span style={dotStyle}>{num}</span>
        <span style={nameStyle}>{name}</span>
        <span style={areaStyle}>{area}</span>
      </div>
    </div>
  );
}

/**
 * PersonChip — reusable person/vehicle/other filter chip.
 * Mirrors the prototype's type chip style used in Search and Live view filters.
 * Shows type label with color-coded background.
 *
 * Props:
 *   text — chip label (e.g., 'Person', 'Vehicle', 'Other')
 *   variant — 'person' | 'vehicle' | 'other' | 'all'
 *   selected — whether the chip is selected
 *   onClick — optional click handler
 *   size — 'sm' | 'md' | 'lg'
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
    ...(onClick && { '&:hover': { background: styles.bg.replace('tint', 'deep') } }),
  };

  const labelStyle = {
    display: 'flex',
    alignItems: 'center',
    gap: '2px',
  };

  if (onClick) {
    return (
      <div style={chipStyle} onClick={() => onClick(variant)}>      
        <span style={labelStyle}>
          {text}
        </span>
      </div>
    );
  }

  return (
    <div style={chipStyle}>
      <span style={labelStyle}>{text}</span>
    </div>
  );
}