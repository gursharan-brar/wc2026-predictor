import { useState, useEffect } from 'react';
import { api } from '../utils/api';

export default function StatsBar() {
  const [health, setHealth] = useState(null);
  const [err,    setErr]    = useState(false);

  useEffect(() => { api.health().then(setHealth).catch(() => setErr(true)); }, []);

  const pipe = (
    <span style={{ margin: '0 14px', color: '#333', userSelect: 'none' }}>|</span>
  );

  const barStyle = {
    background: 'var(--surface)',
    borderBottom: '1px solid var(--border)',
    height: 36,
  };
  const innerStyle = {
    maxWidth: 1200, margin: '0 auto',
    padding: '0 24px',
    height: '100%',
    display: 'flex', alignItems: 'center',
    fontFamily: 'var(--font-body)',
    fontSize: 12,
    color: 'var(--text-muted)',
    whiteSpace: 'nowrap',
    overflowX: 'auto',
    scrollbarWidth: 'none',
  };

  if (err) return (
    <div style={barStyle}>
      <div style={innerStyle}>
        <span style={{ color: '#c0392b' }}>API offline — run: node api/server.js</span>
      </div>
    </div>
  );

  return (
    <div style={barStyle}>
      <div style={innerStyle}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span className="live-dot" />
          <span style={{ color: '#3ecf8e', fontWeight: 500 }}>LIVE</span>
        </span>
        {pipe}
        <span>{health ? health.match_results?.toLocaleString() : '…'} MATCHES</span>
        {pipe}
        <span>{health?.simulation_teams ?? 48} TEAMS</span>
        {pipe}
        <span>10,000 SIMS</span>
        {pipe}
        <span>XGBOOST</span>
        {pipe}
        <span>57.7% ACCURACY</span>
        {health?.last_refresh && (
          <>
            {pipe}
            <span>Updated {new Date(health.last_refresh).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
          </>
        )}
      </div>
    </div>
  );
}
