/**
 * MonthCalendar — verbatim port of prototype `clip-a.tpl.html`
 * (markup + renderVals). props: cams (number[]|null), types, selA, selB,
 * month, nav, size ('compact'|'large'), keepDays, onPick(off).
 */
import React from 'react';
import { invr, ready } from '../../prototype/api';

export default function InetraMonthCalendar({ cams = null, types = null, selA = -1, selB, month = null, nav = true, size = 'compact', keepDays = 30, onPick }) {
  const [readyOk, setReadyOk] = React.useState(!!invr());
  const [mo, setMo] = React.useState(null);
  React.useEffect(() => ready(() => setReadyOk(true)), []);
  if (!readyOk || !invr()) return null;
  const I = invr();

  const large = size === 'large', keep = keepDays, useNav = nav && large !== true ? nav : nav;
  const base = month != null ? month : I.monthOf(selA != null ? selA : 0);
  const cur = nav ? (mo ?? base) : base;
  const flat = [].concat(...I.monthWeeks(cur));
  const cs = cams && cams.length ? cams : null, tp = types || null;
  const kept = c => c && c.off <= 0 && c.off >= -keep;
  const counts = {}; let mx = 0, mn = Infinity, anyOff = false, anyRem = false;
  flat.forEach(c => { if (kept(c)) { const n = I.dayCount(c.off, cs, tp); counts[c.off] = n; if (n > mx) mx = n; if (n > 0 && n < mn) mn = n; } });
  if (mn === Infinity) mn = 0;
  const lv0 = n => !mx ? 0 : !n ? 0 : (n - mn) / Math.max(1, mx - mn) < 0.3 ? 1 : (n - mn) / Math.max(1, mx - mn) < 0.75 ? 2 : 3;
  const a = selA, b = selB ?? selA;
  const lo = a == null ? null : Math.min(a, b), hi = a == null ? null : Math.max(a, b);
  const cells = flat.map((c, ci) => {
    if (!c) return { key: 'x' + ci, vis: 'hidden', d: '', bg: 'transparent', ink: 'var(--ink)', ring: 'none', cursor: 'default', pe: 'none', deco: 'none', pick: () => {}, aria: '', title: '', sel: false, tag: false, offMark: false, hasSub: false, sub: '', numFont: '', pad: '', align: '', justify: '', cellH: '' };
    const fut = c.off > 0, rem = c.off < -keep, n = counts[c.off] || 0;
    const lv = !kept(c) ? -1 : lv0(n);
    const off = kept(c) && I.offlineOn(c.off, cs);
    if (off) anyOff = true; if (rem) anyRem = true;
    const sel = lo != null && c.off >= lo && c.off <= hi;
    const ok = kept(c);
    return {
      key: c.off, vis: 'visible', d: c.d, sel, tag: large && c.off === 0, offMark: off,
      bg: rem ? 'repeating-linear-gradient(135deg, var(--paper-2) 0 5px, var(--paper-3) 5px 6px)' : fut ? 'transparent' : ['var(--paper)', 'var(--blue-tint)', 'var(--blue)', 'var(--blue-deep)'][lv],
      ink: rem || fut ? 'var(--muted)' : lv >= 2 ? 'var(--paper)' : lv === 1 ? 'var(--blue-deep)' : 'var(--ink)',
      ring: sel ? 'inset 0 0 0 2px var(--ink), inset 0 0 0 4px var(--paper)' : (ok && lv === 0) ? 'inset 0 0 0 1px var(--line)' : 'none',
      deco: !large && c.off === 0 ? 'underline' : 'none',
      hasSub: large && !fut, sub: rem ? 'Clips removed' : `${n.toLocaleString('en-IN')} ${n === 1 ? 'event' : 'events'}`,
      cursor: ok ? 'pointer' : 'default', pe: ok ? 'auto' : 'none',
      title: rem ? 'Clips removed' : fut ? '' : `${I.dayLong(c.off)} · ${n} events${off ? ' · a camera was offline' : ''}`,
      aria: `${I.dayLong(c.off)}, ${rem ? 'clips removed' : fut ? 'not yet' : n + ' events'}${off ? ', a camera was offline' : ''}`,
      pick: () => { if (ok && onPick) onPick(c.off); }
    };
  });
  const gap = large ? '6px' : '4px', cellH = large ? '84px' : '38px', pad = large ? '9px 10px' : '0';
  const align = large ? 'flex-start' : 'center', justify = large ? 'space-between' : 'center';
  const numFont = large ? '600 15px/1 var(--font-sans)' : '500 14px/1 var(--font-sans)';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, fontFamily: 'var(--font-sans)', color: 'var(--ink)' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <button onClick={() => setMo(cur - 1)} aria-label="Previous month" className="hvr-ink-border" style={{ width: 34, height: 34, border: '1px solid var(--line)', borderRadius: 8, background: 'var(--paper)', fontSize: 14, visibility: nav && cur > -2 ? 'visible' : 'hidden', cursor: 'pointer' }}>←</button>
        <span style={{ fontSize: large ? '17px' : '15px', fontWeight: 500, letterSpacing: '-0.01em' }}>{I.monthTitle(cur)}</span>
        <button onClick={() => setMo(cur + 1)} aria-label="Next month" className="hvr-ink-border" style={{ width: 34, height: 34, border: '1px solid var(--line)', borderRadius: 8, background: 'var(--paper)', fontSize: 14, visibility: nav && cur < 0 ? 'visible' : 'hidden', cursor: 'pointer' }}>→</button>
      </div>
      <div role="grid" aria-label={I.monthTitle(cur)} style={{ display: 'grid', gridTemplateColumns: 'repeat(7, minmax(0, 1fr))', gap }}>
        {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((l, i) => (
          <span key={'w' + i} style={{ paddingBottom: 2, textAlign: 'center', font: '500 10.5px/1 var(--font-mono)', letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--muted)' }}>{l}</span>
        ))}
        {cells.map(c => (
          <button
            key={c.key}
            onClick={c.pick}
            aria-label={c.aria}
            aria-pressed={c.sel}
            title={c.title}
            style={{ position: 'relative', height: cellH, minWidth: 0, display: 'flex', flexDirection: 'column', alignItems: align, justifyContent: justify, gap: 4, padding: pad, borderRadius: 6, background: c.bg, color: c.ink, boxShadow: c.ring, cursor: c.cursor, pointerEvents: c.pe, visibility: c.vis, textAlign: 'left', overflow: 'hidden', border: 'none' }}
            className="hvr-cal-cell"
          >
            <span style={{ display: 'flex', alignItems: 'baseline', gap: 6, font: numFont, textDecoration: c.deco, textUnderlineOffset: 3, textDecorationThickness: 2 }}>
              {c.d}
              {c.tag && <span style={{ font: '500 10px/1 var(--font-mono)', letterSpacing: '.06em', textTransform: 'uppercase' }}>Today</span>}
            </span>
            {c.hasSub && <span style={{ maxWidth: '100%', font: '500 11px/1.2 var(--font-mono)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.sub}</span>}
            {c.offMark && <span aria-hidden="true" style={{ position: 'absolute', top: 4, right: 4, width: 7, height: 7, background: 'var(--danger)', boxShadow: '0 0 0 1.5px var(--paper)' }} />}
          </button>
        ))}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '6px 14px', fontSize: 12.5, color: 'var(--muted)' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>Quieter<span style={{ width: 12, height: 12, borderRadius: 3, background: 'var(--blue-tint)' }} /><span style={{ width: 12, height: 12, borderRadius: 3, background: 'var(--blue)' }} /><span style={{ width: 12, height: 12, borderRadius: 3, background: 'var(--blue-deep)' }} />Busier</span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span style={{ width: 12, height: 12, borderRadius: 3, background: 'repeating-linear-gradient(135deg, var(--paper-2) 0 4px, var(--paper-3) 4px 5px)' }} />Clips removed</span>
        {anyOff && <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span style={{ width: 8, height: 8, background: 'var(--danger)' }} />A camera was offline</span>}
      </div>
      {anyRem && <span style={{ fontSize: 12.5, color: 'var(--muted)', textWrap: 'pretty' }}>{`Clips before ${I.dateLong(-keep)} were removed, so those days can’t be opened.`}</span>}
    </div>
  );
}
