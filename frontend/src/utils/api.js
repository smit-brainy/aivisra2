/**
 * API Client for AIVISRA StreamCore Backend.
 * Automatically targets current host or proxies during development.
 */

const BASE_URL = '';

async function authRequest(path, options = {}) {
  let res;
  try {
    res = await fetch(`${BASE_URL}${path}`, { credentials: 'include', ...options, headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } });
  } catch (error) {
    throw new Error('The backend is offline. Please start the FastAPI server and try again.');
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `Request failed (${res.status})`);
  return body;
}

export function login(payload) { return authRequest('/api/auth/login', { method: 'POST', body: JSON.stringify(payload) }); }
export function signup(payload) { return authRequest('/api/auth/signup', { method: 'POST', body: JSON.stringify(payload) }); }
export function fetchAuthSetup() { return authRequest('/api/auth/setup'); }
export function logout() { return authRequest('/api/auth/logout', { method: 'POST' }); }
export function fetchUsers() { return authRequest('/api/auth/users'); }
export function updateUser(userId, payload) { return authRequest(`/api/auth/users/${encodeURIComponent(userId)}`, { method: 'PATCH', body: JSON.stringify(payload) }); }
export function deleteUser(userId) { return authRequest(`/api/auth/users/${encodeURIComponent(userId)}`, { method: 'DELETE' }); }
export function updateUserApproval(userId, payload) { return authRequest(`/api/auth/users/${encodeURIComponent(userId)}/approval`, { method: 'PATCH', body: JSON.stringify(payload) }); }
export function updateUserPassword(userId, password) { return authRequest(`/api/auth/users/${encodeURIComponent(userId)}/password`, { method: 'PATCH', body: JSON.stringify({ password }) }); }

export async function fetchStatus() {
  const res = await fetch(`${BASE_URL}/api/status`);
  if (!res.ok) throw new Error(`Status HTTP ${res.status}`);
  return res.json();
}

export async function fetchSystemInfo() {
  const res = await fetch(`${BASE_URL}/api/system-info`);
  if (!res.ok) throw new Error(`System info HTTP ${res.status}`);
  return res.json();
}
export async function fetchStorageInfo() { const res = await fetch(`${BASE_URL}/api/storage`); if (!res.ok) throw new Error(`Storage HTTP ${res.status}`); return res.json(); }
export async function updateStorage(payload) { const res = await fetch(`${BASE_URL}/api/storage`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }); if (!res.ok) throw new Error(`Storage update HTTP ${res.status}`); return res.json(); }

export async function fetchCameras() {
  let lastError;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 8000);
    try {
      const res = await fetch(`${BASE_URL}/api/cameras`, { signal: controller.signal, cache: 'no-store' });
      if (!res.ok) throw new Error(`Cameras HTTP ${res.status}`);
      return await res.json();
    } catch (error) {
      lastError = error?.name === 'AbortError' ? new Error('Camera list request timed out') : error;
      if (attempt < 2) await new Promise(resolve => window.setTimeout(resolve, 250 * (attempt + 1)));
    } finally {
      window.clearTimeout(timer);
    }
  }
  throw lastError || new Error('Unable to load cameras');
}

export async function fetchCamera(cameraId) {
  const res = await fetch(`${BASE_URL}/api/cameras/${cameraId}`);
  if (!res.ok) throw new Error(`Camera HTTP ${res.status}`);
  return res.json();
}

export async function updateCameraMetadata(cameraId, payload) {
  const res = await fetch(`${BASE_URL}/api/cameras/${cameraId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Camera Update HTTP ${res.status}`);
  return res.json();
}

export async function fetchAreas() {
  const res = await fetch(`${BASE_URL}/api/areas`);
  if (!res.ok) throw new Error(`Areas HTTP ${res.status}`);
  return res.json();
}

export async function createArea(payload) {
  const res = await fetch(`${BASE_URL}/api/areas`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Create Area HTTP ${res.status}`);
  return res.json();
}

export async function updateArea(areaId, payload) {
  const res = await fetch(`${BASE_URL}/api/areas/${encodeURIComponent(areaId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Update Area HTTP ${res.status}`);
  return res.json();
}

export async function deleteArea(areaId) {
  const res = await fetch(`${BASE_URL}/api/areas/${encodeURIComponent(areaId)}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Delete Area HTTP ${res.status}`);
  return res.json();
}

export async function updateCameraArea(cameraId, areaId) {
  return updateCameraMetadata(cameraId, { area_id: areaId || null });
}

export async function fetchDetections(cameraId) {
  const url = cameraId ? `${BASE_URL}/api/detections/${cameraId}` : `${BASE_URL}/api/detections`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Detections HTTP ${res.status}`);
  return res.json();
}

export async function fetchTracks(cameraId) {
  const url = cameraId ? `${BASE_URL}/api/tracks/${cameraId}` : `${BASE_URL}/api/tracks`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Tracks HTTP ${res.status}`);
  return res.json();
}

export async function fetchFramesBatch(sinceMap = {}) {
  const param = encodeURIComponent(JSON.stringify(sinceMap));
  const res = await fetch(`${BASE_URL}/api/frames/batch?since=${param}`);
  if (!res.ok) throw new Error(`Batch HTTP ${res.status}`);
  return res.json();
}

export async function fetchCapabilities() {
  const res = await fetch(`${BASE_URL}/api/capabilities`);
  if (!res.ok) throw new Error(`Capabilities HTTP ${res.status}`);
  return res.json();
}

export async function fetchCameraCapabilities(cameraId) {
  const res = await fetch(`${BASE_URL}/api/cameras/${cameraId}/capabilities`);
  if (!res.ok) throw new Error(`Camera Capabilities HTTP ${res.status}`);
  return res.json();
}

export async function applyCameraCapabilities(cameraId, payload) {
  const res = await fetch(`${BASE_URL}/api/cameras/${cameraId}/capabilities`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Apply Capabilities HTTP ${res.status}`);
  return res.json();
}

export async function registerCamera(payload) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 15000);
  try {
    const res = await fetch(`${BASE_URL}/api/cameras`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || `Register Camera HTTP ${res.status}`);
    return body;
  } catch (error) {
    if (error?.name === 'AbortError') throw new Error('Camera registration timed out. Check whether the camera was saved before retrying.');
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

export async function importCameras(file) {
  const csv = await file.text();
  const res = await fetch(`${BASE_URL}/api/cameras/import`, {
    method: 'POST',
    headers: { 'Content-Type': 'text/csv; charset=utf-8' },
    body: csv,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `Camera CSV import HTTP ${res.status}`);
  return body;
}

export async function deleteCamera(cameraId) {
  const res = await fetch(`${BASE_URL}/api/cameras/${encodeURIComponent(cameraId)}`, { method: 'DELETE' });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `Delete Camera HTTP ${res.status}`);
  return body;
}

export async function getOnboardingStatus(cameraId) {
  const res = await fetch(`${BASE_URL}/api/cameras/${cameraId}/onboarding/status`);
  if (!res.ok) throw new Error(`Onboarding Status HTTP ${res.status}`);
  return res.json();
}

export async function triggerCameraAnalysis(cameraId, payload) {
  const res = await fetch(`${BASE_URL}/api/cameras/${cameraId}/onboarding/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Analyze HTTP ${res.status}`);
  return res.json();
}

export async function getCameraRecommendations(cameraId) {
  const res = await fetch(`${BASE_URL}/api/cameras/${cameraId}/recommendations`);
  if (!res.ok) throw new Error(`Recommendations HTTP ${res.status}`);
  return res.json();
}

export async function resetCameraOnboarding(cameraId) {
  const res = await fetch(`${BASE_URL}/api/cameras/${cameraId}/onboarding/reset`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`Reset Onboarding HTTP ${res.status}`);
  return res.json();
}

export async function fetchZones(cameraId) {
  const res = await fetch(`${BASE_URL}/api/cameras/${cameraId}/zones`);
  if (!res.ok) throw new Error(`Zones HTTP ${res.status}`);
  return res.json();
}

export async function updateZones(cameraId, zones, expectedVersion) {
  const res = await fetch(`${BASE_URL}/api/cameras/${cameraId}/zones`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ zones, expected_version: expectedVersion }),
  });
  if (!res.ok) throw new Error(`Update Zones HTTP ${res.status}`);
  return res.json();
}

export async function fetchLines(cameraId) {
  const res = await fetch(`${BASE_URL}/api/cameras/${cameraId}/lines`);
  if (!res.ok) throw new Error(`Lines HTTP ${res.status}`);
  return res.json();
}

export async function updateLines(cameraId, lines, expectedVersion) {
  const res = await fetch(`${BASE_URL}/api/cameras/${cameraId}/lines`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lines, expected_version: expectedVersion }),
  });
  if (!res.ok) throw new Error(`Update Lines HTTP ${res.status}`);
  return res.json();
}

export async function fetchRules(cameraId) {
  const res = await fetch(`${BASE_URL}/api/cameras/${cameraId}/rules`);
  if (!res.ok) throw new Error(`Rules HTTP ${res.status}`);
  return res.json();
}

export async function updateRules(cameraId, rules, expectedVersion) {
  const res = await fetch(`${BASE_URL}/api/cameras/${cameraId}/rules`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rules, expected_version: expectedVersion }),
  });
  if (!res.ok) throw new Error(`Update Rules HTTP ${res.status}`);
  return res.json();
}

export async function fetchOccupancy(cameraId) {
  const res = await fetch(`${BASE_URL}/api/cameras/${cameraId}/occupancy`);
  if (!res.ok) throw new Error(`Occupancy HTTP ${res.status}`);
  return res.json();
}

export async function fetchActiveSpatialEvents(cameraId) {
  const res = await fetch(`${BASE_URL}/api/cameras/${cameraId}/events/active`);
  if (!res.ok) throw new Error(`Active Events HTTP ${res.status}`);
  return res.json();
}

export async function fetchRecentSpatialEvents(cameraId) {
  const res = await fetch(`${BASE_URL}/api/cameras/${cameraId}/events`);
  if (!res.ok) throw new Error(`Recent Spatial Events HTTP ${res.status}`);
  return res.json();
}

export async function fetchEvents(params = {}) {
  const qs = new URLSearchParams(params).toString();
  const res = await fetch(`${BASE_URL}/api/events?${qs}`);
  if (!res.ok) throw new Error(`Events HTTP ${res.status}`);
  return res.json();
}

export async function fetchObjectCounts(date) {
  const query = date ? `?date=${encodeURIComponent(date)}` : '';
  const res = await fetch(`${BASE_URL}/api/object-counts${query}`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`Object counts HTTP ${res.status}`);
  return res.json();
}

export async function fetchEvent(eventId) {
  const res = await fetch(`${BASE_URL}/api/events/${encodeURIComponent(eventId)}`);
  if (!res.ok) throw new Error(`Event HTTP ${res.status}`);
  return res.json();
}

export function getStreamUrl(cameraId) {
  return `${BASE_URL}/stream/${cameraId}`;
}

export function getFrameUrl(cameraId) {
  return `${BASE_URL}/frame/${cameraId}.jpg`;
}

export function getClipUrl(clipPath) {
  return `${BASE_URL}/api/clips/${clipPath}`;
}

export function getEventClipUrl(eventId) {
  return `${BASE_URL}/api/event-clips/${encodeURIComponent(eventId)}`;
}

export function getSnapshotUrl(filename) {
  return `${BASE_URL}/api/snapshots/${filename}`;
}

export function getEvidenceUrl(filename) {
  return `${BASE_URL}/api/evidence/${filename}`;
}

