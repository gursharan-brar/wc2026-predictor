import { useState, useEffect } from 'react';
import { api } from '../utils/api';

function Stat({ label, value, gold, first }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8,
      padding: '0 20px',
      borderLeft: first ? 'none' : '1px solid var(--c-border)',
      height: '100%',
      flexShrink: 0,
      whiteSpace: 'nowrap',
    }}>
      <span style={{
        fontFamily: 'var(--font-mono)', fontSize: 9,
        color: 'var(--c-text-dim)', textTransform: 'uppercase',
        letterSpacing: '0.10em',
      }}>
        {label}
      </span>
      <span style={{
        fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700,
        color: gold ? 'var(--gold)' : 'var(--c-text)',
      }}>
        {value}
      </span>
    </div>
  );
}

export default function StatsBar() {
  const [health, setHealth] = useState(null);
  const [err,    setErr]    = useState(false);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setErr(true));
  }, []);

  const wrapStyle = {
    background: 'var(--c-surface)',
    borderBottom: '1px solid var(--c-border)',
    height: 34,
    overflowX: 'auto',
    scrollbarWidth: 'none',
  };
  const innerStyle = {
    maxWidth: 1320, margin: '0 auto',
    display: 'flex', alignItems: 'center',
    height: '100%', padding: '0 4px',
  };

  if (err) return (
    <div style={wrapStyle}>
      <div style={innerStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 20px' }}>
          <span className="dot-red" />
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--c-red)' }}>
            API OFFLINE — start: node api/server.js
          </span>
        </div>
      </div>
    </div>
  );

  if (!health) return (
    <div style={wrapStyle}>
      <div style={innerStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 20px' }}>
          <span className="dot-dim" />
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--c-text-dim)' }}>
            Connecting…
          </span>
        </div>
      </div>
    </div>
  );

  const refreshed = health.last_refresh
    ? new Date(health.last_refresh).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : '—';

  return (
    <div style={wrapStyle}>
      <div style={innerStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 20px', flexShrink: 0 }}>
          <span className="live-dot" />
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700, color: 'var(--gold)', letterSpacing: '0.08em' }}>
            LIVE
          </span>
        </div>
        <Stat label="Matches"     value={health.match_results?.toLocaleString() ?? '—'} />
        <Stat label="Teams"       value={health.teams_in_stats?.toLocaleString() ?? '—'} />
        <Stat label="WC Teams"    value={health.simulation_teams ?? '—'} />
        <Stat label="Simulations" value="10,000" gold />
        <Stat label="Model"       value="XGBOOST" gold />
        <Stat label="CV Accuracy" value="57.7%" gold />
        <Stat label="Refreshed"   value={refreshed} />
      </div>
    </div>
  );
}
