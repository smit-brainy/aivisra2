import React, { useState } from 'react';
import {
  fetchEvents,
  getClipUrl,
  getSnapshotUrl,
} from '../../utils/api';

// Feather SVG Icons (Stroke-based, zero emojis)
function SearchIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}

function PlayIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="5 3 19 12 5 21 5 3" />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  );
}

function ExternalLinkIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
      <polyline points="15 3 21 3 21 9" />
      <line x1="10" y1="14" x2="21" y2="3" />
    </svg>
  );
}

export default function EventsView({ cameras = [] }) {
  const [camFilter, setCamFilter] = useState('');
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');
  const [objClass, setObjClass] = useState('');
  const [loading, setLoading] = useState(false);
  const [events, setEvents] = useState(null);
  const [alert, setAlert] = useState(null);

  const handleQuery = async (e) => {
    e?.preventDefault();
    setLoading(true);
    setEvents(null);
    try {
      const res = await fetchEvents({
        camera_id: camFilter || undefined,
        start: startTime || undefined,
        end: endTime || undefined,
        class: objClass || undefined,
        clip_only: true,
      });
      setEvents(res.events || []);
    } catch (err) {
      setAlert({ type: 'error', msg: `Query failed: ${err.message}` });
    } finally {
      setLoading(false);
    }
  };

  return (
    <section id="events-view">
      {alert && (
        <div className={`alert-box ${alert.type}`} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>{alert.msg}</span>
          <button
            type="button"
            onClick={() => setAlert(null)}
            style={{ background: 'transparent', border: 'none', color: 'inherit', cursor: 'pointer', padding: '2px', display: 'flex', alignItems: 'center' }}
            title="Dismiss"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      )}

      <div className="ev-main">
        <div className="ev-main-head">
          <div>
            <div className="ev-main-title">Events &amp; Clips</div>
            <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
              Filter recorded track events by camera, time range and object class.
            </div>
          </div>
        </div>

        <div className="ev-main-body">
          <form onSubmit={handleQuery}>
            <div className="ev-form-row" style={{ marginBottom: '16px' }}>
              <div className="form-group">
                <label className="form-label">Camera</label>
                <select
                  className="form-select"
                  value={camFilter}
                  onChange={(e) => setCamFilter(e.target.value)}
                >
                  <option value="">All Cameras</option>
                  {cameras.map((c) => (
                    <option key={c.camera_id} value={c.camera_id}>
                      {c.name || c.camera_id}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Start Time</label>
                <input
                  type="datetime-local"
                  className="form-input"
                  value={startTime}
                  onChange={(e) => setStartTime(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label className="form-label">End Time</label>
                <input
                  type="datetime-local"
                  className="form-input"
                  value={endTime}
                  onChange={(e) => setEndTime(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Class</label>
                <select
                  className="form-select"
                  value={objClass}
                  onChange={(e) => setObjClass(e.target.value)}
                >
                  <option value="">All Classes</option>
                  <option value="person">person</option>
                  <option value="car">car</option>
                  <option value="truck">truck</option>
                  <option value="bus">bus</option>
                  <option value="motorcycle">motorcycle</option>
                </select>
              </div>
            </div>

            <div style={{ display: 'flex', gap: '10px' }}>
              <button type="submit" className="btn active-green" disabled={loading}>
                <SearchIcon />
                <span>{loading ? 'Searching...' : 'Find Clips'}</span>
              </button>
            </div>
          </form>

          {events !== null && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '10px' }}>
              <hr className="ev-divider" />
              <div className="ev-results-header">
                {events.length === 0
                  ? 'No recorded events found for this time range.'
                  : `Found ${events.length} recorded events with video clips`}
              </div>

              {events.map((ev) => {
                const clipUrl = ev.clip_path ? getClipUrl(ev.clip_path) : null;
                const snapUrl = ev.snapshot_path ? getSnapshotUrl(ev.snapshot_path) : null;
                return (
                  <div key={ev.event_id} className="ev-event-row">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', minWidth: 0 }}>
                      {snapUrl && (
                        <a href={snapUrl} target="_blank" rel="noreferrer">
                          <img
                            src={snapUrl}
                            alt="Event snapshot"
                            className="ev-snap-img"
                            style={{ width: '96px', height: '54px', objectFit: 'cover' }}
                          />
                        </a>
                      )}
                      <div className="ev-event-info">
                        <span className="ev-event-cam">{ev.camera_id}</span>
                        <span className="ev-event-sep">·</span>
                        <span className="ev-event-class">{ev.object_class}</span>
                        <span className="ev-event-sep">·</span>
                        <span className="ev-event-ts">{ev.started_at_utc}</span>
                      </div>
                    </div>

                    {clipUrl && (
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <a
                          href={clipUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="btn"
                          style={{ padding: '4px 10px', fontSize: '0.78rem', textDecoration: 'none' }}
                        >
                          <PlayIcon />
                          <span>Watch Clip</span>
                        </a>
                        <a
                          href={clipUrl}
                          download
                          className="btn"
                          style={{ padding: '4px 10px', fontSize: '0.78rem', textDecoration: 'none' }}
                        >
                          <DownloadIcon />
                          <span>Download</span>
                        </a>
                        <a
                          href={clipUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="btn"
                          style={{ padding: '4px 10px', fontSize: '0.78rem', textDecoration: 'none' }}
                        >
                          <ExternalLinkIcon />
                          <span>Open</span>
                        </a>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
