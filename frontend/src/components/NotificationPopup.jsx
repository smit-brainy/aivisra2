import React, { useEffect } from 'react';
import { X } from 'lucide-react';

export default function NotificationPopup({ notification, onClose }) {
  useEffect(() => {
    if (!notification) return undefined;
    if (notification.actions?.length || notification.persistent) return undefined;
    const timer = window.setTimeout(onClose, notification.duration || 4500);
    return () => window.clearTimeout(timer);
  }, [notification, onClose]);
  if (!notification) return null;
  const colors = { error: ['var(--danger-tint)', 'var(--danger-deep)'], warning: ['var(--warning-tint)', 'var(--warning-deep)'], success: ['var(--success-tint)', 'var(--success-deep)'], info: ['var(--blue-tint)', 'var(--blue-deep)'] };
  const [background, color] = colors[notification.type] || colors.info;
  return <div role="alertdialog" style={{ position: 'fixed', top: 22, right: 22, zIndex: 1000, maxWidth: 380, padding: '14px 16px', border: `1px solid ${color}`, borderRadius: 10, background, color, boxShadow: '0 10px 30px rgba(0,0,0,.14)', display: 'flex', gap: 14 }}><div style={{ flex: 1 }}>{notification.title && <div style={{ fontWeight: 650, marginBottom: 4 }}>{notification.title}</div>}<div style={{ lineHeight: 1.4 }}>{notification.message}</div>{notification.actions?.length > 0 && <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>{notification.actions.map(action => <button type="button" key={action.label} onClick={action.onClick} style={{ padding: '6px 10px', border: action.primary ? 0 : '1px solid currentColor', borderRadius: 6, background: action.primary ? 'currentColor' : 'transparent', color: action.primary ? background : 'inherit', cursor: 'pointer', fontWeight: 600 }}>{action.label}</button>)}</div>}</div><button type="button" onClick={onClose} aria-label="Close notification" style={{ alignSelf: 'flex-start', border: 0, background: 'transparent', color: 'inherit', cursor: 'pointer', display: 'grid', placeItems: 'center', padding: 2 }}><X size={17} strokeWidth={2} aria-hidden="true" /></button></div>;
}
