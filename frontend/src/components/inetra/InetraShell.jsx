import React from 'react';
import { TopBar, Sidebar } from './InetraChrome';

/**
 * I-Netra app shell — verbatim grid chrome from the prototype
 * (224px sidebar + 56px header). Screens render into the main cell.
 */
export default function InetraShell({ session, screen, onNav, onSignOut, camSummary, camDot, children }) {
  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        display: 'grid',
        gridTemplateColumns: '224px minmax(0,1fr)',
        gridTemplateRows: '56px minmax(0,1fr)',
        background: 'var(--paper)',
        color: 'var(--ink)',
        fontFamily: 'var(--font-sans)',
        fontSize: 15,
        lineHeight: 1.45,
        WebkitFontSmoothing: 'antialiased',
      }}
    >
      <TopBar
        session={session}
        onSignOut={onSignOut}
        onNav={onNav}
        camSummary={camSummary}
        camDot={camDot}
      />
      <Sidebar active={screen} admin={session.role === 'admin'} onNav={onNav} />
      {children}
    </div>
  );
}
