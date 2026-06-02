import { useState, useEffect } from 'react';
import { api } from '../utils/api';
import { flag, TEAM_GROUP } from '../utils/flags';
import { nc } from '../utils/nationalColors';
import { useCountUp } from '../hooks/useCountUp';

function ContenderCard({ team, rank, onTeamClick, animDelay = 0 }) {
  const [hovered, setHovered] = useState(false);
  const color = nc(team.team);
  const winPct = useCountUp(team.win_probability * 100, 800, animDelay);
  const group  = TEAM_GROUP[team.team] ?? '?';

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`View ${team.team} profile`}
      onClick={() => onTeamClick(team.team)}
      onKeyDown={(e) => e.key === 'Enter' && onTeamClick(team.team)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: hovered
          ? `linear-gradient(135deg, #161616 0%, color-mix(in srgb, ${color} 14%, #111) 100%)`
          : `linear-gradient(135deg, #111111 0%, color-mix(in srgb, ${color} 9%, #111) 100%)`,
        border: `1px solid ${hovered ? `${color}66` : `${color}28`}`,
        borderRadius: 'var(--r-card)',
        borderLeft: `3px solid ${color}`,
        padding: '16px',
        cursor: 'pointer',
        transition: 'background var(--t), border-color var(--t), box-shadow var(--t)',
        boxShadow: hovered ? `0 4px 24px ${color}22` : 'none',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Rank badge */}
      <div style={{
        position: 'absolute', top: 10, right: 12,
        fontFamily: 'var(--font-mono)', fontSize: 10,
        color: rank <= 3 ? 'var(--gold)' : 'var(--c-text-dim)',
        fontWeight: 700,
      }}>
        #{rank}
      </div>

      {/* Flag + group */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span style={{ fontSize: 28, lineHeight: 1 }}>{flag(team.team)}</span>
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: 9,
          color, textTransform: 'uppercase', letterSpacing: '0.1em', fontWeight: 700,
        }}>
          GRP {group}
        </span>
      </div>

      {/* Team name */}
      <div style={{
        fontFamily: 'var(--font-heading)',
        fontSize: 15,
        fontWeight: 800,
        color: 'var(--c-text)',
        textTransform: 'uppercase',
        letterSpacing: '0.04em',
        marginBottom: 10,
        lineHeight: 1.1,
      }}>
        {team.team}
      </div>

      {/* Big win % */}
      <div style={{
        fontFamily: 'var(--font-heading)',
        fontSize: 34,
        fontWeight: 800,
        color: rank <= 2 ? 'var(--gold-light)' : color,
        lineHeight: 1,
        letterSpacing: '-0.02em',
        marginBottom: 10,
      }}>
        {winPct.toFixed(1)}%
      </div>

      {/* Sub stats */}
      <div style={{ display: 'flex', gap: 12 }}>
        {[
          ['Final', team.final_probability],
          ['SF', team.semifinal_probability],
        ].map(([lbl, val]) => (
          <div key={lbl}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700, color: 'var(--c-text-muted)' }}>
              {val != null ? `${(val * 100).toFixed(0)}%` : '—'}
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--c-text-dim)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
              {lbl}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function TopContenders({ onTeamClick }) {
  const [teams, setTeams] = useState(null);

  useEffect(() => {
    api.simResults()
      .then((d) => setTeams(d.teams?.slice(0, 8) ?? []))
      .catch(() => {});
  }, []);

  return (
    <div>
      <div className="section-label" style={{ marginBottom: 16 }}>
        Top 8 Contenders
      </div>

      {!teams ? (
        <div style={{ padding: 40, color: 'var(--c-text-dim)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
          Loading…
        </div>
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(2, 1fr)',
          gap: 10,
        }}>
          {teams.map((t, i) => (
            <ContenderCard
              key={t.team}
              team={t}
              rank={i + 1}
              onTeamClick={onTeamClick}
              animDelay={i * 60}
            />
          ))}
        </div>
      )}
    </div>
  );
}
