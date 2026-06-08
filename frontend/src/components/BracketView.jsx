import { useState, useEffect } from 'react';
import { api } from '../utils/api';
import { flag } from '../utils/flags';
import { nc } from '../utils/nationalColors';

const pct = (v) => v != null ? `${(v * 100).toFixed(1)}%` : '—';

function TeamRow({ teamData, rank, onClick }) {
  const [hov, setHov] = useState(false);
  const { team, simulation: sim } = teamData;
  const color = nc(team);

  return (
    <div
      role="button" tabIndex={0}
      aria-label={`View ${team}`}
      onClick={() => onClick(team)}
      onKeyDown={(e) => e.key === 'Enter' && onClick(team)}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        display: 'grid',
        gridTemplateColumns: '3px 26px 1fr auto',
        alignItems: 'center',
        gap: 8,
        padding: '7px 10px 7px 0',
        borderBottom: '1px solid var(--border)',
        cursor: 'pointer',
        background: hov ? 'var(--surface-2)' : 'transparent',
        transition: 'background var(--t)',
        outline: 'none',
      }}
    >
      {/* National colour strip */}
      <div style={{ background: color, borderRadius: 1, alignSelf: 'stretch', minHeight: 28 }} />

      {/* Flag */}
      <span style={{ fontSize: 16, lineHeight: 1 }}>{flag(team)}</span>

      {/* Name + crown */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
        <span style={{ fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 500, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {team}
        </span>
        {rank === 1 && (
          <span style={{ fontSize: 12 }} aria-label="Group favourite">👑</span>
        )}
      </div>

      {/* Win % */}
      <span style={{ fontFamily: 'var(--font-heading)', fontSize: 14, color: rank === 1 ? 'var(--gold)' : 'var(--text-muted)', textAlign: 'right', whiteSpace: 'nowrap' }}>
        {pct(sim?.win_probability)}
      </span>
    </div>
  );
}

function GroupCard({ letter, teams, onTeamClick }) {
  const sorted = [...teams].sort((a, b) => (b.simulation?.win_probability ?? 0) - (a.simulation?.win_probability ?? 0));
  const topColor = nc(sorted[0]?.team ?? '');

  return (
    <div style={{
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderTop: `2px solid ${topColor}`,
      borderRadius: 6,
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '10px 12px',
        background: 'var(--surface-2)',
        borderBottom: '1px solid var(--border)',
      }}>
        <span style={{ fontFamily: 'var(--font-heading)', fontSize: 16, color: 'var(--gold)', letterSpacing: '0.06em' }}>
          GROUP {letter}
        </span>
        <span style={{ fontFamily: 'var(--font-body)', fontSize: 10, color: '#444', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          Win Prob
        </span>
      </div>

      {/* Teams */}
      <div style={{ padding: '0 10px' }}>
        {sorted.map((t, i) => (
          <TeamRow key={t.team} teamData={t} rank={i + 1} onClick={onTeamClick} />
        ))}
      </div>
    </div>
  );
}

export default function BracketView({ onTeamClick }) {
  const [data, setData] = useState(null);
  const [err,  setErr]  = useState(null);

  useEffect(() => { api.bracket().then(setData).catch((e) => setErr(e.message)); }, []);

  if (err) return <div style={{ padding: 40, color: '#c0392b', fontFamily: 'var(--font-body)', fontSize: 13 }}>{err}</div>;
  if (!data) return <div style={{ padding: 60, color: '#444', fontFamily: 'var(--font-body)', textAlign: 'center', fontSize: 13 }}>Loading groups…</div>;

  const { groups, simulation_meta: meta } = data;
  const letters = Object.keys(groups).sort();

  return (
    <div className="fade-up">
      <p className="section-label">Group Stage Draw — Official FIFA WC 2026</p>
      <p style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: '#444', marginBottom: 24 }}>
        12 groups · 4 teams each · 👑 group favourite · top 2 advance + best 8 third-place
        {meta ? ` · ${meta.simulations_run?.toLocaleString()} simulations` : ''}
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14 }}>
        {letters.map((l) => (
          <GroupCard key={l} letter={l} teams={groups[l]} onTeamClick={onTeamClick} />
        ))}
      </div>
    </div>
  );
}
