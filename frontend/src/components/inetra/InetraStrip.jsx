/**
 * ActivityStrip — verbatim port of prototype `home.tpl.html`
 * (markup + renderVals). props: times (number[]), start, end, now,
 * bin, offline [[from,to|null]], height, axis, onPick(t).
 */
import React from 'react';
import { invr, ready } from '../../prototype/api';

export default function InetraStrip({ times, start = 0, end, now = null, bin = 300, offline = [], height = 20, axis = true, onPick }) {
  const [readyOk, setReadyOk] = React.useState(!!invr());
  const [hover, setHover] = React.useState(null);
  React.useEffect(() => ready(() => setReadyOk(true)), []);

  if (!readyOk || !invr()) return <div style={{ position: 'relative', width: '100%', height, background: 'var(--paper-2)', borderRadius: 3 }} />;
  const I = invr();
  const demo = times == null;
  const T = demo ? I.camTimes(0)[3] : times;
  const st = start ?? 0, en = end ?? I.DAY, span = Math.max(1, en - st);
  const bn = bin ?? 300, nb = Math.max(1, Math.ceil(span / bn));
  const nw = demo ? 40800 : (now ?? null);
  const counts = new Array(nb).fill(0), first = new Array(nb).fill(null);
  T.forEach(t => {
    if (t < st || t >= en || (nw != null && t > nw)) return;
    const i = Math.floor((t - st) / bn);
    counts[i]++; if (first[i] == null || t < first[i]) first[i] = t;
  });
  const lvl = c => c === 0 ? 0 : c === 1 ? 1 : c <= 3 ? 2 : 3;
  const col = { 1: 'color-mix(in oklch, var(--blue) 38%, var(--paper-2))', 2: 'var(--blue)', 3: 'var(--blue-deep)' };
  const stops = []; let i = 0;
  while (i < nb) {
    const L = lvl(counts[i]); let j = i;
    while (j < nb && lvl(counts[j]) === L) j++;
    if (L) { const a = (i / nb * 100).toFixed(3), b = (j / nb * 100).toFixed(3); stops.push(`transparent ${a}%`, `${col[L]} ${a}%`, `${col[L]} ${b}%`, `transparent ${b}%`); }
    i = j;
  }
  const pct = t => ((t - st) / span * 100) + '%';
  const offSpans = (offline || []).map(o => {
    const a = Math.max(o[0], st), b = Math.min(o[1] ?? nw ?? en, en);
    return b > a ? { a, b, open: o[1] == null, from: o[0], to: o[1], left: pct(a), width: ((b - a) / span * 100) + '%' } : null;
  }).filter(Boolean);
  const futFrac = nw == null ? 0 : Math.min(1, Math.max(0, (en - nw) / span));
  const hb = hover;
  let tip = null;
  if (hb != null && hb >= 0 && hb < nb && (nw == null || st + hb * bn <= nw)) {
    const b0 = st + hb * bn, b1 = b0 + bn, c = counts[hb], mid = b0 + bn / 2;
    const off = offSpans.find(o => mid >= o.a && mid <= o.b);
    const tt = bn >= 120 ? I.span(b0, b1) : I.clock(b0);
    const text = off ? (off.open ? 'Offline since ' + I.clock(off.from) : 'Offline ' + I.span(off.from, off.to)) : `${tt} · ${c ? c + (c === 1 ? ' event' : ' events') : 'No events'}`;
    const f = (mid - st) / span;
    tip = { text, left: pct(b0), w: (bn / span * 100) + '%', center: pct(mid), tx: f < 0.12 ? '-12%' : f > 0.88 ? '-88%' : '-50%', clickable: c > 0 && !!onPick };
  }
  const step = span >= 12 * I.H ? 3 * I.H : span >= 5 * I.H ? I.H : span >= 2 * I.H ? 1800 : span > 1800 ? 900 : 300;
  const ticks = [];
  for (let t = Math.ceil(st / step) * step; t <= en; t += step) {
    const f = (t - st) / span;
    ticks.push({ left: (f * 100) + '%', tx: f < 0.01 ? '0' : f > 0.99 ? '-100%' : '-50%', label: t % I.H === 0 ? I.hourLabel(t) : I.clock(t).replace(/ (AM|PM)$/, '') });
  }
  const binAt = e => { const r = e.currentTarget.getBoundingClientRect(); return Math.min(nb - 1, Math.max(0, Math.floor((e.clientX - r.left) / r.width * nb))); };

  return (
    <div style={{ position: 'relative', width: '100%', fontFamily: 'var(--font-sans)', userSelect: 'none' }}>
      <div
        onMouseMove={e => { const b = binAt(e); if (b !== hover) setHover(b); }}
        onMouseLeave={() => setHover(null)}
        onClick={e => { const b = binAt(e); if (counts[b] && onPick) onPick(first[b]); }}
        title={tip ? tip.text : ''}
        style={{ position: 'relative', height: height, background: 'var(--paper-2)', borderRadius: 3, cursor: tip && tip.clickable ? 'pointer' : 'default' }}
      >
        <div style={{ position: 'absolute', inset: 0, borderRadius: 3, backgroundImage: stops.length ? `linear-gradient(90deg, ${stops.join(', ')})` : 'none' }} />
        {offSpans.map((o, k) => (
          <div key={k} style={{ position: 'absolute', top: 0, bottom: 0, left: o.left, width: o.width, background: 'repeating-linear-gradient(135deg, var(--coral) 0 1.5px, var(--coral-tint) 1.5px 5px)' }} />
        ))}
        {futFrac > 0 && (
          <div style={{ position: 'absolute', top: 0, bottom: 0, right: 0, width: (futFrac * 100) + '%', borderRadius: '0 3px 3px 0', background: 'repeating-linear-gradient(135deg, var(--line-soft) 0 1px, transparent 1px 6px), var(--bone)', boxShadow: 'inset 0 0 0 1px var(--line-soft)' }} />
        )}
        {nw != null && nw > st && nw < en && (
          <div style={{ position: 'absolute', top: -3, bottom: -3, left: nw != null ? pct(nw) : '0%', width: 2, marginLeft: -1, background: 'var(--ink)', pointerEvents: 'none' }} />
        )}
        {tip && (
          <React.Fragment>
            <div style={{ position: 'absolute', top: -2, bottom: -2, left: tip.left, width: tip.w, minWidth: 3, boxShadow: '0 0 0 1.5px var(--ink)', borderRadius: 2, pointerEvents: 'none' }} />
            <div style={{ position: 'absolute', bottom: 'calc(100% + 8px)', left: tip.center, transform: `translateX(${tip.tx})`, background: 'var(--ink)', color: 'var(--paper)', font: '500 12px/1.2 var(--font-mono)', padding: '6px 9px', borderRadius: 4, whiteSpace: 'nowrap', pointerEvents: 'none', zIndex: 5 }}>{tip.text}</div>
          </React.Fragment>
        )}
      </div>
      {axis && (
        <div style={{ position: 'relative', height: 16, marginTop: 7 }}>
          {ticks.map((k, t) => (
            <span key={t} style={{ position: 'absolute', top: 0, left: k.left, transform: `translateX(${k.tx})`, font: '500 11px/1 var(--font-mono)', color: 'var(--muted)', whiteSpace: 'nowrap' }}>{k.label}</span>
          ))}
        </div>
      )}
    </div>
  );
}
