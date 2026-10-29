import React, { useState, useEffect } from 'react';
import {
  searchVisual,
  fetchEvents,
  fetchSearchStatus,
  reindexEvents,
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

function ChevronIcon({ open }) {
  return (
    <svg
      className={`ev-chevron ${open ? 'open' : ''}`}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="9 18 15 12 9 6" />
    </svg>
  );
}

function RefreshIcon({ spinning }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={spinning ? { animation: 'spin 1s linear infinite' } : {}}
    >
      <polyline points="23 4 23 10 17 10" />
      <polyline points="1 20 1 14 7 14" />
      <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
    </svg>
  );
}

function ExternalLinkIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
      <polyline points="15 3 21 3 21 9" />
      <line x1="10" y1="14" x2="21" y2="3" />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  );
}

function PlayIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="5 3 19 12 5 21 5 3" />
    </svg>
  );
}

function SwitchIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="16 3 21 3 21 8" />
      <line x1="4" y1="20" x2="21" y2="3" />
      <polyline points="21 16 21 21 16 21" />
      <line x1="15" y1="15" x2="21" y2="21" />
      <line x1="4" y1="4" x2="9" y2="9" />
    </svg>
  );
}

export default function EventsView({ cameras = [] }) {
  // Mode selection: 'nl' = Natural Language Visual Search, 'time' = Video Clip by Time Range
  const [mode, setMode] = useState('nl');

  // Combined Example Queries sidebar collapse & expand
  const [queriesOpen, setQueriesOpen] = useState(true);
  const [showAllQueries, setShowAllQueries] = useState(false);

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
  const [timeSearching, setTimeSearching] = useState(false);
  const [timeEvents, setTimeEvents] = useState(null);

  // Combined single list of example queries / quick prompts
  const allExampleQueries = [
    'person with white clothes',
    'person wearing dark jacket',
    'someone in blue jeans',
    'person carrying backpack',
    'red color car',
    'two people standing together',
    'person in uniform',
    'vehicle parked near entrance',
    'someone running across scene',
    'delivery person with package',
  ];

  // Show top 5 by default, expand full list on view more
  const displayedQueries = showAllQueries
    ? allExampleQueries
    : allExampleQueries.slice(0, 5);

  useEffect(() => {
    fetchSearchStatus().then(setSearchStatus).catch(() => {});
  }, []);

  const handleSelectQuery = (text) => {
    setQueryText(text);
    if (mode !== 'nl') setMode('nl');
  };

  const handleToggleMode = () => {
    setMode((prev) => (prev === 'nl' ? 'time' : 'nl'));
  };

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
    setTimeSearching(true);
    setTimeEvents(null);
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
    } finally {
      setTimeSearching(false);
    }
  };

  const handleResetSearch = () => {
    setQueryText('');
    setSearchResults(null);
    setStartTime('');
    setEndTime('');
  };

  return (
    <section id="events-view">
      {/* Alert banner */}
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

      {/* Top Bar: Simple Mode Toggle Switch & Index status */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
        <button
          type="button"
          className="ev-toggle-switch-btn"
          onClick={handleToggleMode}
          title="Click to switch search mode"
        >
          <SwitchIcon />
          <span>
            Mode: <strong>{mode === 'nl' ? 'Search' : 'Time Range Filter'}</strong>
          </span>
          <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)', marginLeft: '4px' }}>
            (Switch to {mode === 'nl' ? 'Time Range Filter' : 'Search'})
          </span>
        </button>

        {mode === 'nl' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
              {searchStatus?.total_vectors ?? 0} vectors indexed
            </span>
            <button
              type="button"
              className="btn"
              style={{ padding: '5px 12px', fontSize: '0.78rem' }}
              onClick={handleReindex}
              disabled={reindexing}
            >
              <RefreshIcon spinning={reindexing} />
              <span>{reindexing ? 'Indexing...' : 'Index Past Clips'}</span>
            </button>
          </div>
        )}
      </div>

      {/* 2-Column Layout */}
      <div className="ev-layout">
        {/* Left Sidebar: Single Combined Example Queries Section */}
        <aside className="ev-sidebar">
          <div className="ev-sidebar-group">
            <div
              className="ev-sidebar-group-header"
              onClick={() => setQueriesOpen(!queriesOpen)}
            >
              <span>Example Queries</span>
              <ChevronIcon open={queriesOpen} />
            </div>

            {queriesOpen && (
              <div className="ev-sidebar-group-body">
                {displayedQueries.map((q, idx) => (
                  <button
                    key={idx}
                    type="button"
                    className="ev-prompt-item"
                    onClick={() => handleSelectQuery(q)}
                  >
                    {q}
                  </button>
                ))}

                {allExampleQueries.length > 5 && (
                  <button
                    type="button"
                    className="ev-view-more-btn"
                    onClick={() => setShowAllQueries(!showAllQueries)}
                  >
                    <span>{showAllQueries ? 'Show Less' : `View More (${allExampleQueries.length - 5} more)`}</span>
                    <svg
                      width="12"
                      height="12"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      style={{ transform: showAllQueries ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s ease' }}
                    >
                      <polyline points="6 9 12 15 18 9" />
                    </svg>
                  </button>
                )}
              </div>
            )}
          </div>
        </aside>

        {/* Right Main Content */}
        <div className="ev-main">
          {mode === 'nl' ? (
            /* NATURAL LANGUAGE SEARCH VIEW */
            <div>
              <div className="ev-main-head">
                <div>
                  <div className="ev-main-title">Search</div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
                  </div>
                </div>
              </div>

              <div className="ev-main-body">
                <form onSubmit={handleVisualSearch}>
                  {/* Query input */}
                  <div className="form-group" style={{ marginBottom: '16px' }}>
                    <label className="form-label">
                      Describe Person / Clothing / Vehicle
                    </label>
                    <div style={{ position: 'relative' }}>
                      <input
                        type="text"
                        className="form-input"
                        style={{ paddingLeft: '34px', width: '100%' }}
                        placeholder="e.g. person with white clothes"
                        value={queryText}
                        onChange={(e) => setQueryText(e.target.value)}
                        required
                      />
                      <span
                        style={{
                          position: 'absolute',
                          left: '11px',
                          top: '50%',
                          transform: 'translateY(-50%)',
                          color: 'var(--text-muted)',
                          display: 'flex',
                          alignItems: 'center',
                        }}
                      >
                        <SearchIcon />
                      </span>
                    </div>
                  </div>

                  {/* Filter row */}
                  <div className="ev-form-row" style={{ marginBottom: '16px' }}>
                    <div className="form-group">
                      <label className="form-label">Camera Filter</label>
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
                      <label className="form-label">Matches</label>
                      <select
                        className="form-select"
                        value={topK}
                        onChange={(e) => setTopK(e.target.value)}
                      >
                        <option value="2">Top 2</option>
                        <option value="5">Top 5</option>
                        <option value="10">Top 10</option>
                      </select>
                    </div>

                    <div className="form-group">
                      <label className="form-label">Start Time (Optional)</label>
                      <input
                        type="datetime-local"
                        className="form-input"
                        value={startTime}
                        onChange={(e) => setStartTime(e.target.value)}
                      />
                    </div>

                    <div className="form-group">
                      <label className="form-label">End Time (Optional)</label>
                      <input
                        type="datetime-local"
                        className="form-input"
                        value={endTime}
                        onChange={(e) => setEndTime(e.target.value)}
                      />
                    </div>
                  </div>

                  {/* Actions */}
                  <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                    <button
                      type="submit"
                      className="btn active-green"
                      disabled={searching}
                    >
                      <SearchIcon />
                      <span>{searching ? 'Searching...' : 'Search Clips'}</span>
                    </button>
                    <button
                      type="button"
                      className="btn"
                      onClick={handleResetSearch}
                    >
                      Reset
                    </button>
                  </div>
                </form>

                {/* Search Results Display */}
                {searchResults !== null && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginTop: '10px' }}>
                    <hr className="ev-divider" />
                    <div className="ev-results-header">
                      {searchResults.length === 0
                        ? 'No visual matches found matching query and time constraints.'
                        : `Top ${searchResults.length} Visual Matches for "${queryText}"`}
                    </div>

                    {searchResults.map((item, idx) => {
                      const started = item.started_at_utc
                        ? new Date(item.started_at_utc.replace('Z', '+00:00'))
                        : new Date();
                      const matchPercent =
                        item.similarity_percent || Math.round((item.similarity || 0) * 100);
                      const badgeClass =
                        matchPercent >= 75 ? 'high' : matchPercent >= 60 ? 'mid' : 'low';
                      const clipUrl = item.clip_url ? item.clip_url : getClipUrl(item.clip_path || '');
                      const snapUrl = item.snapshot_url
                        ? item.snapshot_url
                        : item.snapshot_path
                        ? getSnapshotUrl(item.snapshot_path)
                        : null;

                      return (
                        <div key={idx} className="ev-result-card">
                          <div className="ev-result-head">
                            <div className="ev-result-meta">
                              <span className={`ev-match-badge ${badgeClass}`}>
                                Match {idx + 1} · {matchPercent}%
                              </span>
                              <span className="ev-result-cam">{item.camera_id}</span>
                              <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                                Event {item.event_id}
                              </span>
                            </div>
                            <div className="ev-result-time">
                              {started.toLocaleString()}
                            </div>
                          </div>

                          <div className="ev-result-body">
                            {/* Left: Snapshot */}
                            <div>
                              <div className="ev-snap-label">
                                {(item.object_class || 'Object').toUpperCase()} Snapshot
                              </div>
                              {snapUrl ? (
                                <a href={snapUrl} target="_blank" rel="noreferrer">
                                  <img
                                    src={snapUrl}
                                    alt="Detection Snapshot"
                                    className="ev-snap-img"
                                  />
                                </a>
                              ) : (
                                <div className="ev-snap-placeholder">
                                  No snapshot image
                                </div>
                              )}
                            </div>

                            {/* Right: AI Description & Video Clip */}
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                              <div className="ev-ai-desc-box">
                                <div className="ev-ai-desc-label">AI Visual Description</div>
                                <div>
                                  {item.description || 'Detection indexed in FAISS vector store.'}
                                </div>
                              </div>

                              <video
                                controls
                                className="ev-video"
                                preload="metadata"
                              >
                                <source src={clipUrl} type="video/mp4" />
                                Your browser does not support video playback.
                              </video>

                              <div className="ev-clip-actions">
                                <a
                                  href={clipUrl}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="btn"
                                  style={{ padding: '5px 12px', fontSize: '0.78rem', textDecoration: 'none' }}
                                >
                                  <ExternalLinkIcon />
                                  <span>Open in New Tab</span>
                                </a>
                                <a
                                  href={clipUrl}
                                  download
                                  className="btn"
                                  style={{ padding: '5px 12px', fontSize: '0.78rem', textDecoration: 'none' }}
                                >
                                  <DownloadIcon />
                                  <span>Download Clip</span>
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
            </div>
          ) : (
            /* TIME RANGE QUERY VIEW */
            <div>
              <div className="ev-main-head">
                <div>
                  <div className="ev-main-title">Time Range Filter</div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
                  </div>
                </div>
              </div>

              <div className="ev-main-body">
                <form onSubmit={handleTimeQuery}>
                  <div className="ev-form-row" style={{ marginBottom: '16px' }}>
                    <div className="form-group">
                      <label className="form-label">Camera ID</label>
                      <select
                        className="form-select"
                        value={timeCam}
                        onChange={(e) => setTimeCam(e.target.value)}
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
                        value={timeStart}
                        onChange={(e) => setTimeStart(e.target.value)}
                        required
                      />
                    </div>

                    <div className="form-group">
                      <label className="form-label">End Time</label>
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

                  <div style={{ display: 'flex', gap: '10px' }}>
                    <button
                      type="submit"
                      className="btn active-green"
                      disabled={timeSearching}
                    >
                      <SearchIcon />
                      <span>{timeSearching ? 'Searching...' : 'Find Clips'}</span>
                    </button>
                  </div>
                </form>

                {/* Time Query Results */}
                {timeEvents !== null && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '10px' }}>
                    <hr className="ev-divider" />
                    <div className="ev-results-header">
                      {timeEvents.length === 0
                        ? 'No recorded events found for this time range.'
                        : `Found ${timeEvents.length} recorded events with video clips`}
                    </div>

                    {timeEvents.map((ev, idx) => (
                      <div key={idx} className="ev-event-row">
                        <div className="ev-event-info">
                          <span className="ev-event-cam">{ev.camera_id}</span>
                          <span className="ev-event-sep">·</span>
                          <span className="ev-event-class">{ev.object_class}</span>
                          <span className="ev-event-sep">·</span>
                          <span className="ev-event-ts">{ev.started_at_utc}</span>
                        </div>
                        {ev.clip_path && (
                          <a
                            href={getClipUrl(ev.clip_path)}
                            target="_blank"
                            rel="noreferrer"
                            className="btn"
                            style={{ padding: '4px 10px', fontSize: '0.78rem', textDecoration: 'none' }}
                          >
                            <PlayIcon />
                            <span>Watch Clip</span>
                          </a>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
