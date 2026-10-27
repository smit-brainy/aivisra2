import React, { useState, useEffect } from 'react';
import {
  searchVisual,
  fetchEvents,
  fetchSearchStatus,
  reindexEvents,
  getClipUrl,
  getSnapshotUrl,
} from '../../utils/api';

export default function EventsView({ cameras = [] }) {
  // Visual Search State
  const [queryText, setQueryText] = useState('');
  const [camFilter, setCamFilter] = useState('');
  const [topK, setTopK] = useState(2);
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState(null);
  const [searchStatus, setSearchStatus] = useState(null);
  const [reindexing, setReindexing] = useState(false);
  const [alert, setAlert] = useState(null);

  // Time-based Clip Query State
  const [timeCam, setTimeCam] = useState('');
  const [timeStart, setTimeStart] = useState('');
  const [timeEnd, setTimeEnd] = useState('');
  const [timeClass, setTimeClass] = useState('person');
  const [timeEvents, setTimeEvents] = useState(null);

  useEffect(() => {
    fetchSearchStatus().then(setSearchStatus).catch(() => {});
  }, []);

  const handleVisualSearch = async (e) => {
    e?.preventDefault();
    if (!queryText.trim()) return;
    setSearching(true);
    setSearchResults(null);
    try {
      const res = await searchVisual({
        query: queryText,
        camera_id: camFilter || null,
        start: startTime || null,
        end: endTime || null,
        top_k: Number(topK),
      });
      setSearchResults(res.results || []);
    } catch (err) {
      setAlert({ type: 'error', msg: `Search failed: ${err.message}` });
    } finally {
      setSearching(false);
    }
  };

  const handleReindex = async () => {
    setReindexing(true);
    try {
      const res = await reindexEvents();
      setAlert({
        type: 'success',
        msg: `Re-indexing complete: ${res.indexed_count} clips indexed into FAISS (Total: ${res.total_vectors})`,
      });
      fetchSearchStatus().then(setSearchStatus).catch(() => {});
    } catch (err) {
      setAlert({ type: 'error', msg: `Reindex failed: ${err.message}` });
    } finally {
      setReindexing(false);
    }
  };

  const handleTimeQuery = async (e) => {
    e.preventDefault();
    try {
      const res = await fetchEvents({
        camera_id: timeCam || undefined,
        start: timeStart || undefined,
        end: timeEnd || undefined,
        class: timeClass || undefined,
        clip_only: true,
      });
      setTimeEvents(res.events || []);
    } catch (err) {
      setAlert({ type: 'error', msg: `Time query failed: ${err.message}` });
    }
  };

  const quickPrompts = [
    'person with white clothes',
    'person wearing dark jacket',
    'someone in blue jeans',
    'person carrying backpack',
    'red color car',
  ];

  return (
    <section id="events-view" style={{ display: 'flex', flexDirection: 'column', gap: '20px', maxWidth: '1000px', margin: '0 auto', width: '100%' }}>
      {alert && (
        <div className={`alert-box ${alert.type}`} style={{ display: 'block' }}>
          {alert.msg}
        </div>
      )}

      {/* 1. AI NATURAL LANGUAGE VISUAL SEARCH (FAISS + LOCAL VLM) */}
      <div style={{ background: '#161b22', border: '1px solid #388bfd', borderRadius: '8px', overflow: 'hidden', boxShadow: '0 4px 20px rgba(56,139,253,0.12)' }}>
        <div style={{ padding: '16px 20px', background: '#1c2128', borderBottom: '1px solid #30363d', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontSize: '1.4rem' }}>🧠</span>
            <div>
              <div style={{ fontWeight: 700, fontSize: '1.05rem', color: '#e6edf3' }}>
                AI Natural Language Video Search
              </div>
              <div style={{ fontSize: '.78rem', color: '#8b949e' }}>
                Local VLM (Qwen 3.5 9B) & FAISS vector search across COCO detections & video clips
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <span
              className="badge"
              style={{ background: '#23863622', border: '1px solid #238636', color: '#3fb950', fontSize: '.78rem' }}
            >
              100% Local VLM ({searchStatus?.total_vectors || 0} vectors)
            </span>
            <button
              type="button"
              className="btn"
              style={{ padding: '4px 10px', fontSize: '.78rem' }}
              onClick={handleReindex}
              disabled={reindexing}
            >
              {reindexing ? '⏳ Indexing...' : '↻ Index Past Clips'}
            </button>
          </div>
        </div>

        <div style={{ padding: '22px 24px' }}>
          <form onSubmit={handleVisualSearch}>
            <div style={{ display: 'flex', gap: '12px', marginBottom: '14px', flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: '280px' }}>
                <label className="form-label" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>Describe the person / clothing / vehicle <span style={{ color: '#f85149' }}>*</span></span>
                  <span
                    style={{ fontSize: '.75rem', color: '#58a6ff', cursor: 'pointer' }}
                    onClick={() => setQueryText('person with white clothes')}
                  >
                    Example: "person with white clothes"
                  </span>
                </label>
                <div style={{ position: 'relative' }}>
                  <input
                    type="text"
                    className="form-input"
                    style={{ paddingLeft: '36px', fontSize: '1rem', height: '42px', width: '100%', boxSizing: 'border-box' }}
                    placeholder="e.g. person with white clothes, someone wearing blue jeans, dark jacket..."
                    value={queryText}
                    onChange={(e) => setQueryText(e.target.value)}
                    required
                  />
                  <span style={{ position: 'absolute', left: '12px', top: '11px', color: '#8b949e', fontSize: '1.05rem' }}>🔍</span>
                </div>
              </div>

              <div style={{ width: '170px' }}>
                <label className="form-label">Camera Filter</label>
                <select
                  className="form-select"
                  style={{ height: '42px', width: '100%' }}
                  value={camFilter}
                  onChange={(e) => setCamFilter(e.target.value)}
                >
                  <option value="">-- All Cameras --</option>
                  {cameras.map((c) => (
                    <option key={c.camera_id} value={c.camera_id}>
                      {c.name || c.camera_id}
                    </option>
                  ))}
                </select>
              </div>

              <div style={{ width: '140px' }}>
                <label className="form-label">Matches</label>
                <select
                  className="form-select"
                  style={{ height: '42px', width: '100%' }}
                  value={topK}
                  onChange={(e) => setTopK(e.target.value)}
                >
                  <option value="2">Top 2 (Recommended)</option>
                  <option value="5">Top 5</option>
                  <option value="10">Top 10</option>
                </select>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px', marginBottom: '14px' }}>
              <div>
                <label className="form-label">Start Time (IST, Optional)</label>
                <input
                  type="datetime-local"
                  className="form-input"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                  value={startTime}
                  onChange={(e) => setStartTime(e.target.value)}
                />
              </div>
              <div>
                <label className="form-label">End Time (IST, Optional)</label>
                <input
                  type="datetime-local"
                  className="form-input"
                  style={{ width: '100%', boxSizing: 'border-box' }}
                  value={endTime}
                  onChange={(e) => setEndTime(e.target.value)}
                />
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
              <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                <button
                  type="submit"
                  className="btn active-green"
                  style={{ padding: '9px 24px', fontSize: '.92rem', fontWeight: 700 }}
                  disabled={searching}
                >
                  {searching ? '⚡ Searching...' : '⚡ Search Clips'}
                </button>
                <button
                  type="button"
                  className="btn"
                  style={{ padding: '9px 18px', fontSize: '.92rem' }}
                  onClick={() => {
                    setQueryText('');
                    setSearchResults(null);
                    setStartTime('');
                    setEndTime('');
                  }}
                >
                  🔄 Reset
                </button>
              </div>

              <div style={{ display: 'flex', gap: '6px', alignItems: 'center', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '.75rem', color: '#8b949e' }}>Quick prompts:</span>
                {quickPrompts.map((p, idx) => (
                  <button
                    key={idx}
                    type="button"
                    className="btn"
                    style={{ padding: '3px 8px', fontSize: '.75rem' }}
                    onClick={() => {
                      setQueryText(p);
                    }}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          </form>

          {/* Search Results Display */}
          {searchResults && (
            <div style={{ marginTop: '20px', paddingTop: '16px', borderTop: '1px solid #21262d' }}>
              <div style={{ fontWeight: 700, fontSize: '1rem', color: '#e6edf3', marginBottom: '14px' }}>
                🎯 Top {searchResults.length} Visual Matches for "{queryText}"
              </div>
              {searchResults.length === 0 ? (
                <div style={{ color: '#8b949e', textAlign: 'center', padding: '20px' }}>
                  No visual matches found matching query and time constraints.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  {searchResults.map((item, idx) => {
                    const started = item.started_at_utc
                      ? new Date(item.started_at_utc.replace('Z', '+00:00'))
                      : new Date();
                    const matchPercent =
                      item.similarity_percent || Math.round((item.similarity || 0) * 100);
                    const scoreColor =
                      matchPercent >= 75 ? '#3fb950' : matchPercent >= 60 ? '#58a6ff' : '#d29922';
                    const clipUrl = item.clip_url ? item.clip_url : getClipUrl(item.clip_path || '');
                    const snapUrl = item.snapshot_url
                      ? item.snapshot_url
                      : item.snapshot_path
                      ? getSnapshotUrl(item.snapshot_path)
                      : null;

                    return (
                      <div
                        key={idx}
                        style={{
                          background: '#0d1117',
                          border: '1px solid #30363d',
                          borderRadius: '8px',
                          overflow: 'hidden',
                        }}
                      >
                        <div
                          style={{
                            padding: '12px 16px',
                            background: '#1c2128',
                            borderBottom: '1px solid #30363d',
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            flexWrap: 'wrap',
                            gap: '8px',
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span
                              className="badge"
                              style={{
                                background: `${scoreColor}22`,
                                border: `1px solid ${scoreColor}`,
                                color: scoreColor,
                                fontWeight: 700,
                                fontSize: '.85rem',
                              }}
                            >
                              🎯 Match #{idx + 1} · {matchPercent}% Similarity
                            </span>
                            <span style={{ fontWeight: 600, color: '#58a6ff', fontSize: '1.05rem' }}>
                              {item.camera_id}
                            </span>
                            <span style={{ fontSize: '.8rem', color: '#8b949e' }}>
                              Event {item.event_id}
                            </span>
                          </div>
                          <div style={{ fontSize: '.8rem', color: '#8b949e' }}>
                            ⏰ Started: {started.toLocaleString()}
                          </div>
                        </div>

                        <div
                          style={{
                            padding: '16px',
                            display: 'grid',
                            gridTemplateColumns: 'minmax(180px, 220px) 1fr',
                            gap: '18px',
                          }}
                        >
                          {/* Left: Snapshot */}
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            <div
                              style={{
                                fontSize: '.75rem',
                                color: '#8b949e',
                                fontWeight: 700,
                                textTransform: 'uppercase',
                              }}
                            >
                              {(item.object_class || 'Object').toUpperCase()} Snapshot
                            </div>
                            {snapUrl ? (
                              <a href={snapUrl} target="_blank" rel="noreferrer">
                                <img
                                  src={snapUrl}
                                  alt="Detection Crop"
                                  style={{
                                    width: '100%',
                                    maxHeight: '260px',
                                    objectFit: 'contain',
                                    background: '#010409',
                                    borderRadius: '6px',
                                    border: '1px solid #30363d',
                                  }}
                                />
                              </a>
                            ) : (
                              <div
                                style={{
                                  background: '#161b22',
                                  padding: '30px',
                                  textAlign: 'center',
                                  color: '#8b949e',
                                  borderRadius: '6px',
                                }}
                              >
                                No snapshot image
                              </div>
                            )}
                            <div style={{ fontSize: '.78rem', color: '#8b949e', textAlign: 'center' }}>
                              Crop from detection event
                            </div>
                          </div>

                          {/* Right: Video Clip and AI Description */}
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                            <div
                              style={{
                                background: '#161b22',
                                borderLeft: '3px solid #58a6ff',
                                padding: '10px 14px',
                                borderRadius: '0 6px 6px 0',
                                fontSize: '.85rem',
                                color: '#e6edf3',
                              }}
                            >
                              <div
                                style={{
                                  fontSize: '.75rem',
                                  color: '#79c0ff',
                                  fontWeight: 700,
                                  marginBottom: '4px',
                                  textTransform: 'uppercase',
                                }}
                              >
                                AI Visual Description
                              </div>
                              <div>
                                {item.description || 'Person detection indexed in FAISS vector store.'}
                              </div>
                            </div>

                            <video
                              controls
                              style={{
                                width: '100%',
                                maxHeight: '380px',
                                background: '#000',
                                borderRadius: '6px',
                                border: '1px solid #30363d',
                              }}
                              preload="metadata"
                            >
                              <source src={clipUrl} type="video/mp4" />
                              Your browser does not support the video tag.
                            </video>

                            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                              <a
                                href={clipUrl}
                                target="_blank"
                                rel="noreferrer"
                                className="btn"
                                style={{ textDecoration: 'none', padding: '6px 14px', fontSize: '.82rem' }}
                              >
                                🔗 Open in New Tab
                              </a>
                              <a
                                href={clipUrl}
                                download
                                className="btn"
                                style={{ textDecoration: 'none', padding: '6px 14px', fontSize: '.82rem' }}
                              >
                                ⬇ Download Clip
                              </a>
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 2. FIND VIDEO CLIP BY TIME RANGE */}
      <div style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: '8px', overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', fontWeight: 700, fontSize: '1rem', background: '#1c2128', borderBottom: '1px solid #30363d' }}>
          📋 Find Video Clip by Time Range
        </div>
        <div style={{ padding: '24px' }}>
          <form onSubmit={handleTimeQuery}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: '16px' }}>
              <div className="form-group">
                <label className="form-label">Camera ID (Optional)</label>
                <select
                  className="form-select"
                  value={timeCam}
                  onChange={(e) => setTimeCam(e.target.value)}
                >
                  <option value="">-- All Cameras --</option>
                  {cameras.map((c) => (
                    <option key={c.camera_id} value={c.camera_id}>
                      {c.name || c.camera_id}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Start Time (IST) <span style={{ color: '#f85149' }}>*</span></label>
                <input
                  type="datetime-local"
                  className="form-input"
                  value={timeStart}
                  onChange={(e) => setTimeStart(e.target.value)}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">End Time (IST) <span style={{ color: '#f85149' }}>*</span></label>
                <input
                  type="datetime-local"
                  className="form-input"
                  value={timeEnd}
                  onChange={(e) => setTimeEnd(e.target.value)}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">Class</label>
                <select
                  className="form-select"
                  value={timeClass}
                  onChange={(e) => setTimeClass(e.target.value)}
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
            <div style={{ display: 'flex', gap: '12px' }}>
              <button type="submit" className="btn active-green" style={{ padding: '10px 24px' }}>
                🔍 Find Clip
              </button>
            </div>
          </form>

          {/* Time Query Results */}
          {timeEvents && (
            <div style={{ marginTop: '20px', paddingTop: '16px', borderTop: '1px solid #21262d' }}>
              <div style={{ fontWeight: 600, color: '#e6edf3', marginBottom: '10px' }}>
                Found {timeEvents.length} recorded events with video clips:
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {timeEvents.map((ev, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: '12px',
                      background: '#0d1117',
                      borderRadius: '6px',
                      border: '1px solid #30363d',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                    }}
                  >
                    <div>
                      <span style={{ color: '#58a6ff', fontWeight: 600 }}>{ev.camera_id}</span>
                      <span style={{ margin: '0 8px', color: '#8b949e' }}>·</span>
                      <span>{ev.object_class}</span>
                      <span style={{ margin: '0 8px', color: '#8b949e' }}>·</span>
                      <span style={{ color: '#8b949e', fontSize: '.8rem' }}>{ev.started_at_utc}</span>
                    </div>
                    {ev.clip_path && (
                      <a
                        href={getClipUrl(ev.clip_path)}
                        target="_blank"
                        rel="noreferrer"
                        className="btn"
                        style={{ padding: '4px 10px', fontSize: '.8rem' }}
                      >
                        ▶ Watch Clip
                      </a>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

