import React, { useEffect } from 'react';

export default function NotificationPopup({ notification, onClose }) {
  useEffect(() => {
    if (!notification) return undefined;
    const timer = window.setTimeout(onClose, notification.duration || 4500);
    return () => window.clearTimeout(timer);
  }, [notification, onClose]);
  if (!notification) return null;
  const colors = { error: ['var(--danger-tint)', 'var(--danger-deep)'], warning: ['var(--warning-tint)', 'var(--warning-deep)'], success: ['var(--success-tint)', 'var(--success-deep)'], info: ['var(--blue-tint)', 'var(--blue-deep)'] };
  const [background, color] = colors[notification.type] || colors.info;
  return <div role="alert" style={{ position: 'fixed', top: 22, right: 22, zIndex: 1000, maxWidth: 380, padding: '14px 16px', border: `1px solid ${color}`, borderRadius: 10, background, color, boxShadow: '0 10px 30px rgba(0,0,0,.14)', display: 'flex', gap: 14 }}><div style={{ flex: 1 }}>{notification.title && <div style={{ fontWeight: 650, marginBottom: 4 }}>{notification.title}</div>}<div style={{ lineHeight: 1.4 }}>{notification.message}</div></div><button type="button" onClick={onClose} aria-label="Close notification" style={{ border: 0, background: 'transparent', color: 'inherit', cursor: 'pointer', fontSize: 18 }}>×</button></div>;
}
