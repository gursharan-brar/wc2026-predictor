/**
 * API client — all calls go through here so the base URL is one place to change.
 * In production, set VITE_API_URL to your Railway backend URL.
 */
export const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:3001';

const get = (path) =>
  fetch(`${API_BASE}${path}`).then((r) => {
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  });

export const api = {
  health:     ()     => get('/health'),
  rankings:   (n=48) => get(`/rankings?limit=${n}`),
  team:       (name) => get(`/team/${encodeURIComponent(name)}`),
  bracket:    ()     => get('/bracket'),
  simResults: ()     => get('/sim-results'),
  /** Returns an EventSource for SSE streaming. Caller must close it. */
  simulateStream: () => new EventSource(`${API_BASE}/simulate`),
};
