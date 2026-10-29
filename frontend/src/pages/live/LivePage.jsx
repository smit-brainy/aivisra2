/**
 * LivePage — minimal live view screen.
 * Powered by window.INVR sample data; full verbatim port deferred (task list 2.2).
 * Provides Camera Picker access and basic live view scaffolding.
 */
import React from 'react';
import { invr } from '../../prototype/api';
import InetraCameraPicker from '../../components/inetra/InetraCameraPicker';

export default function LivePage({ session, openSearch, navTo }) {
  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', gap: 12, padding: 24, background: 'var(--paper)', color: 'var(--ink)' }}>
      <h1>Live view</h1>
      <p>Camera wall — follow-on from task 2.1 Home.</p>
      <button onClick={() => openSearch && openSearch({ preset: 'today' })}>Choose cameras</button>
      <InetraCameraPicker
        defaultOpen={false}
        label="Cameras"
        cameras={invr()?.CAMS?.map(c => Object.assign({}, c, { status: 'online' })) || []}
        areas={invr()?.AREAS || []}
        value={{ mode: 'all' }}
        onChange={() => {}}
        onToggleOpen={() => {}}
      />
    </div>
  );
}