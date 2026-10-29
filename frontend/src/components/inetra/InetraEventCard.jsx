/**
 * EventCard — verbatim port of prototype `misc-a.tpl.html`
 * (card + row variants, tone per event type).
 * props: ev {kind,type,camLabel,when,dur,scene,x,...}, variant
 * ('card'|'row'), selected, playing, selectable, onPlay, onToggle.
 */
import React from 'react';
import { invr, ready } from '../../prototype/api';

export default function InetraEventCard({ ev, variant = 'card', selected = false, playing = false, selectable = true, onPlay, onToggle }) {
  const [readyOk, setReadyOk] = React.useState(!!invr());
  React.useEffect(() => ready(() => setReadyOk(true)), []);
  if (!readyOk || !invr()) return null;
  const I = invr();
  const e = ev || { id: 'demo', kind: 'Person', type: 'person', camLabel: '3 Lobby corridor', when: 'Today 9:14 AM', dur: '38 s', scene: I.CAM[3].scene, x: 0.42 };
  const isP = e.type !== 'vehicle', isO = e.type === 'other';
  const TONE = isO ? ['var(--teal)', 'var(--teal-tint)', 'var(--teal-deep)'] : isP ? ['var(--sky)', 'var(--sky-tint)', 'var(--sky-deep)'] : ['var(--honey)', 'var(--honey-tint)', 'var(--honey-deep)'];
  const w = isP ? 0.18 : 0.38;
  const sel = !!selected;
  const box = { left: (Math.min(e.x ?? 0.4, 1 - w - 0.04) * 100) + '%', top: isP ? '16%' : '34%', w: (w * 100) + '%', h: isP ? '70%' : '46%', color: TONE[0] };

  const play = anyEv => { onPlay && onPlay(e); };

  if (variant === 'row') {
    return (
      <div
        onClick={play}
        role="button"
        aria-label={`Play ${e.kind} on ${e.camLabel}, ${e.when}`}
        style={{ display: 'grid', gridTemplateColumns: '96px minmax(0,1fr) 34px', alignItems: 'center', gap: 12, padding: 8, borderRadius: 8, cursor: 'pointer', fontFamily: 'var(--font-sans)', color: 'var(--ink)' }}
        className="hvr-row"
      >
        <div style={{ position: 'relative', aspectRatio: '16 / 9', borderRadius: 4, overflow: 'hidden', background: e.scene }}>
          <div style={{ position: 'absolute', left: box.left, top: box.top, width: box.w, height: box.h, border: `1.5px solid ${box.color}`, borderRadius: 2 }} />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
          <span style={{ fontSize: 14.5, fontWeight: 500, lineHeight: 1.3, textWrap: 'pretty' }}>
            <span style={{ display: 'inline-block', width: 8, height: 8, marginRight: 8, verticalAlign: 1, background: box.color, boxShadow: `inset 0 0 0 1px ${TONE[2]}` }} />
            {e.kind} · {e.camLabel}
          </span>
          <span style={{ font: '500 12px/1.3 var(--font-mono)', color: 'var(--muted)' }}>{e.when} · {e.dur}</span>
        </div>
        <span style={{ width: 34, height: 34, display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid var(--line)', borderRadius: '50%', background: 'var(--paper)' }}>
          <span style={{ width: 0, height: 0, marginLeft: 2, borderLeft: '9px solid var(--ink)', borderTop: '6px solid transparent', borderBottom: '6px solid transparent' }} />
        </span>
      </div>
    );
  }

  return (
    <div
      style={{ display: 'flex', flexDirection: 'column', background: sel ? 'var(--paper)' : 'var(--bone)', border: `1px solid ${playing ? 'var(--ink)' : sel ? 'var(--blue)' : 'var(--line)'}`, boxShadow: sel ? '0 0 0 1px var(--blue)' : playing ? '0 0 0 1px var(--ink)' : 'none', borderRadius: 8, overflow: 'hidden', fontFamily: 'var(--font-sans)', color: 'var(--ink)' }}
      className="hvr-ink-border"
    >
      <div onClick={play} style={{ position: 'relative', aspectRatio: '16 / 9', background: e.scene, cursor: 'pointer' }}>
        <div style={{ position: 'absolute', left: box.left, top: box.top, width: box.w, height: box.h, border: `2px solid ${box.color}`, borderRadius: 2, background: 'radial-gradient(ellipse at 50% 42%, rgba(225,230,236,.30), transparent 72%)' }} />
        {playing && (
          <span style={{ position: 'absolute', top: 8, left: 8, background: 'var(--blue)', color: 'var(--paper)', font: '500 10.5px/1 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', padding: '5px 7px', borderRadius: 4 }}>Playing</span>
        )}
        <span style={{ position: 'absolute', right: 8, bottom: 8, background: 'rgba(10,10,11,.78)', color: 'var(--paper)', font: '500 11.5px/1 var(--font-mono)', padding: '5px 6px', borderRadius: 4 }}>{e.dur}</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: '10px 12px 12px' }}>
        <span style={{ alignSelf: 'flex-start', marginBottom: 6, padding: '4px 7px', borderRadius: 4, background: TONE[1], color: TONE[2], font: '500 11px/1 var(--font-mono)', letterSpacing: '.06em', textTransform: 'uppercase' }}>{e.kind}</span>
        <span style={{ fontSize: 15, fontWeight: 500, letterSpacing: '-0.01em', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{e.camLabel}</span>
        <span style={{ font: '500 12px/1.4 var(--font-mono)', color: 'var(--muted)' }}>{e.when}</span>
        {selectable !== false ? (
          <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
            <button onClick={play} className="hvr-ink-border" style={{ flex: 1, height: 34, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', fontSize: 13.5, fontWeight: 500, cursor: 'pointer' }}>
              <span style={{ width: 0, height: 0, borderLeft: '8px solid currentColor', borderTop: '5px solid transparent', borderBottom: '5px solid transparent' }} />Play
            </button>
            <button
              onClick={() => { onToggle && onToggle(e); }}
              aria-pressed={sel}
              className="hvr-ink-border"
              style={{ flex: 1, height: 34, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7, border: `1px solid ${sel ? 'var(--blue-deep)' : 'var(--line)'}`, borderRadius: 6, background: sel ? 'var(--blue-tint)' : 'var(--paper)', color: sel ? 'var(--blue-deep)' : 'var(--ink)', fontSize: 13.5, fontWeight: 500, cursor: 'pointer' }}
            >
              <span style={{ width: 14, height: 14, borderRadius: 3, border: `1.5px solid ${sel ? 'var(--blue-deep)' : 'var(--ink)'}`, background: sel ? 'var(--blue-deep)' : 'transparent', color: 'var(--paper)', font: '700 10px/11px var(--font-sans)', textAlign: 'center' }}>{sel ? '✓' : ''}</span>
              {sel ? 'Selected' : 'Select'}
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
            <button onClick={play} className="hvr-ink-border" style={{ width: '100%', height: 34, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, border: '1px solid var(--line)', borderRadius: 6, background: 'var(--paper)', fontSize: 13.5, fontWeight: 500, cursor: 'pointer' }}>
              <span style={{ width: 0, height: 0, borderLeft: '8px solid currentColor', borderTop: '5px solid transparent', borderBottom: '5px solid transparent' }} />Play
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
