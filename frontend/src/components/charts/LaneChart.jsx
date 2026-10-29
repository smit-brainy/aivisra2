import React from 'react';

/**
 * LaneChart — AI detection lane chart component.
 * Mirrors the prototype's "Charts and meters" lane display showing
 * activity intensity per camera with color-coded lanes (Mint/Honey/Teal).
 *
 * Props:
 *   activityData — array of activity values per time bin (0-100 scale)
 *   cameraNames — array of camera labels for the side axis
 *   cellSize — size of each cell in the chart (default: 4)
 *   showGrid — whether to show grid lines (default: true)
 */
export default function LaneChart({ activityData, cameraNames, cellSize = 4, showGrid = true }) {
  const lanes = [
    { key: 'low', label: 'Mint', color: '#a7ffef', bg: '#a7ffef1a' },
    { key: 'medium', label: 'Honey', color: '#ffd6a5', bg: '#ffd6a51a' },
    { key: 'high', label: 'Teal', color: '#81a1c1', bg: '#81a1c11a' },
  ];

  const maxActivity = activityData ? Math.max(...activityData) : 1;
  const normalized = activityData ? activityData.map(v => Math.min(v / (maxActivity || 1), 100)) : [0];

  // Determine lane level for each bin
  const laneLevels = normalized.map(v => {
    if (v < 30) return 'low';
    if (v < 70) return 'medium';
    return 'high';
  });

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: `repeat(auto-fill, minmax(${cellSize}px, ${cellSize}px))`,
      gridTemplateRows: `repeat(${cameraNames?.length || 5}, minmax(${cellSize}px, ${cellSize}px))`,
      gap: 2,
      background: 'var(--paper-2)',
      ...(showGrid && {
        border: '1px solid var(--line)',
        borderRadius: 4,
      }),
    }})
  );
}

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
      color: 'var(--muted)',
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
  };

  const style = {
    ...variantStyles[variant],
    ...(isNow && { marginRight: '12px', color: 'var(--ink)' }),
    ...(className && { className }),
  };

  return <span style={style}>{text}</span>;
}

/**
 * HourMeter — hourly activity meter component.
 * Mirrors the prototype's hourly meter that fills Blue and turns Honey when nearly full.
 *
 * Props:
 *   percentage — fill percentage (0-100)
 *   showText — whether to show the percentage text (default: true)
 */
export function HourMeter({ percentage, showText = true }) {
  const fillPercent = Math.max(0, Math.min(100, percentage));
  const isNearlyFull = fillPercent >= 80;
  const meterColor = isNearlyFull ? '#f9a825' : '#1976d2'; // Honey or Blue

  const meterStyle = {
    width: `${fillPercent}%`,
    height: '100%',
    background: meterColor,
    transition: 'width .3s, background .3s',
  };

  const textStyle = {
    display: showText ? 'block' : 'none',
    marginTop: '4px',
    textAlign: 'center',
    fontSize: '10px',
    fontWeight: 500,
    color: 'var(--paper)',
  };

  return (
    <div style={{
      height: '10px',
      borderRadius: '3px',
      background: 'var(--paper-3)',
      overflow: 'hidden',
      position: 'relative',
    }}>
      <div style={meterStyle} />
      {showText && (
        <span style={textStyle}>{Math.round(fillPercent)}%</span>
      )}
    </div>
  );
}