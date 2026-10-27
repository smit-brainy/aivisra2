import React from 'react';
import { getStreamUrl, getFrameUrl } from '../../utils/api';

export default function GridView({ cameras = [], onSelectCamera }) {
  return (
    <section className="grid">
      {cameras.map((c) => (
        <article
          key={c.camera_id}
          className="card"
          style={{ cursor: 'pointer' }}
          onClick={() => onSelectCamera(c.camera_id)}
        >
          <div className="card-head">
            <span>{c.name || c.camera_id}</span>
            <span className="state connected">ONLINE</span>
          </div>
          <div className="frame">
            <img
              src={getStreamUrl(c.camera_id)}
              alt={c.camera_id}
              onError={(e) => {
                e.target.src = getFrameUrl(c.camera_id);
              }}
            />
          </div>
          <div className="stats">
            <div>Decoder: {c.decoder || 'nvh264dec (GPU HW)'}</div>
            <div>Codec: {c.codec || 'H.264'}</div>
          </div>
        </article>
      ))}
      {cameras.length === 0 && (
        <div style={{ color: '#8b949e', gridColumn: '1 / -1', padding: '30px', textAlign: 'center' }}>
          No cameras detected. Add a camera from the Onboarding tab.
        </div>
      )}
    </section>
  );
}

