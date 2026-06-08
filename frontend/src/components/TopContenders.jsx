import { useState, useEffect } from 'react';
import { api } from '../utils/api';
import { flag, TEAM_GROUP } from '../utils/flags';
import { nc } from '../utils/nationalColors';
import { useCountUp } from '../hooks/useCountUp';

function ContenderCard({ t, rank, onTeamClick }) {
  const [hov, setHov] = useState(false);
  const color = nc(t.team);
  const winPct = useCountUp(t.win_probability * 100, 800, rank * 50);
  const group  = TEAM_GROUP[t.team] ?? '?';

  return (
    <div
      role="button" tabIndex={0}
      aria-label={`View ${t.team}`}
      onClick={() => onTeamClick(t.team)}
      onKeyDown={(e) => e.key === 'Enter' && onTeamClick(t.team)}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        background: hov ? 'var(--surface-2)' : 'var(--surface)',
        border: '1px solid var(--border)',
        borderLeft: `3px solid ${color}`,
        borderRadius: 6,
        padding: 20,
        cursor: 'pointer',
        transition: 'background var(--t)',
        outline: 'none',
      }}
    >
      {/* Rank + flag */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 10 }}>
        <span style={{ fontSize: 32, lineHeight: 1 }}>{flag(t.team)}</span>
        <span style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: '#444' }}>
          #{rank} · GRP {group}
        </span>
      </div>

      {/* Team name */}
      <div style={{ fontFamily: 'var(--font-body)', fontSize: 15, fontWeight: 500, color: 'var(--text)', marginBottom: 8 }}>
        {t.team}
      </div>

      {/* Win % */}
      <div style={{ fontFamily: 'var(--font-heading)', fontSize: 36, color: 'var(--gold)', lineHeight: 1, marginBottom: 8 }}>
        {winPct.toFixed(1)}%
      </div>

      {/* Sub stats */}
      <div style={{ display: 'flex', gap: 16 }}>
        {[['Final', t.final_probability], ['Semi', t.semifinal_probability]].map(([lbl, v]) => (
          <div key={lbl}>
            <span style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--text-muted)' }}>
              {v != null ? `${(v * 100).toFixed(0)}%` : '—'}
            </span>
            <span style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: '#444', marginLeft: 4 }}>
              {lbl}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function TopContenders({ onTeamClick }) {
  const [teams, setTeams] = useState(null);

  useEffect(() => {
    api.simResults().then((d) => setTeams(d.teams?.slice(0, 8))).catch(() => {});
  }, []);

  return (
    <div>
      <p className="section-label">Top 8 Contenders</p>
      {!teams ? (
        <div style={{ color: '#444', fontSize: 13 }}>Loading…</div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          {teams.map((t, i) => (
            <ContenderCard key={t.team} t={t} rank={i + 1} onTeamClick={onTeamClick} />
          ))}
        </div>
      )}
    </div>
  );
}
