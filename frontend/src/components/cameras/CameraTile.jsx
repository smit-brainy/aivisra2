import React from 'react';
import { useHoverProps } from '../../hooks/useHoverProps';

/**
 * CameraTile — reusable camera display tile.
 * Mirrors the prototype's camera tile style used in live view and clip player.
 * Shows camera number, name, area badge, and live indicator dot.
 *
 * Hover is applied at runtime via useHoverProps() — the previous `&:hover`
 * key inside the inline style object was ignored by React, so the tile never
 * lifted on hover.
 *
 * Props:
 *   cam — camera object with num, name, area, status, kind properties
 *   small — whether to render in small size (default: false)
 *   onClick — optional click handler
 */
export function CameraTile({ cam, small = false, onClick }) {
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
    transition: 'transform .15s',
  };

  const hover = useHoverProps(tileStyle, onClick ? { transform: 'translateY(-2px)' } : null);

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
    borderRadius: '50%',
    background: dotColor,
    flexShrink: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontWeight: 'bold',
    fontSize: small ? '10px' : '12px',
    color: 'var(--paper)',
  };

  const content = (
    <div style={{ display: 'flex', alignItems: 'center', gap: small ? '6px' : '10px' }}>
      <span style={dotStyle}>{num}</span>
      <span style={nameStyle}>{name}</span>
      <span style={areaStyle}>{area}</span>
    </div>
  );

  if (onClick) {
    return (
      <div {...hover} onClick={() => onClick(cam)}>
        {content}
      </div>
    );
  }

  return <div {...hover}>{content}</div>;
}

export default CameraTile;
