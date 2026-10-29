import React from 'react';

/**
 * Thin accessors over the verbatim prototype sample data (`window.INVR`).
 * Every component renders only after `ready()` resolves, mirroring the
 * prototype controllers' boot loop.
 */
export function invr() {
  return (typeof window !== 'undefined' && window.INVR) || null;
}

/** Resolves once window.INVR exists (prototype boot loop). */
export function ready(cb, tries = 0) {
  if (invr()) { cb(); return () => {}; }
  if (tries > 100) return () => {};
  const t = setTimeout(() => ready(cb, tries + 1), 30);
  return () => clearTimeout(t);
}

/** React hook: true once window.INVR is available. */
export function useInvrReady() {
  const [ok, setOk] = React.useState(!!invr());
  React.useEffect(() => ready(() => setOk(true)), []);
  return ok;
}

/** Verbatim controller merged() data (edits empty, scenario). */
export function merged(scen = 'day', edits = {}) {
  const I = invr();
  return I.merge(edits, scen);
}
