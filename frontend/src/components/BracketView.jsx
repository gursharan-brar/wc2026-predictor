import { useState, useEffect } from 'react';
import { api } from '../utils/api';
import { flag } from '../utils/flags';
import { nc } from '../utils/nationalColors';

const pct = (v) => (v != null ? `${(v * 100).toFixed(1)}%` : '—');

function GroupTeamRow({ teamData, maxWin, rank, onClick }) {
  const [hovered, setHovered] = useState(false);
  const { team, simulation: sim } = teamData;
  const winP  = sim?.win_probability ?? 0;
  const color = nc(team);
  const isFavourite = rank === 1;

  return (
    <div
      onClick={() => onClick(team)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      role="button"
      tabIndex={0}
      aria-label={`View ${team} profile`}
      onKeyDown={(e) => e.key === 'Enter' && onClick(team)}
      style={{
        display: 'grid',
        gridTemplateColumns: '3px 26px 1fr 48px',
        alignItems: 'center',
        gap: 8,
        padding: '8px 10px 8px 0',
        borderBottom: '1px solid var(--c-border)',
        cursor: 'pointer',
        background: hovered ? `color-mix(in srgb, ${color} 10%, #111)` : 'transparent',
        transition: 'background var(--t)',
      }}
    >
      {/* Color strip */}
      <div style={{ width: 3, height: '100%', background: color, borderRadius: 2, alignSelf: 'stretch' }} />

      {/* Flag */}
      <span style={{ fontSize: 17, lineHeight: 1 }}>{flag(team)}</span>

      {/* Name + crown for favourite */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600,
          color: 'var(--c-text)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {team}
        </span>
        {isFavourite && (
          <span style={{ fontSize: 11, lineHeight: 1 }} aria-label="Group favourite">👑</span>
        )}
      </div>

      {/* Win % */}
      <span style={{
        fontFamily: 'var(--font-heading)', fontSize: 13, fontWeight: 800,
        color: isFavourite ? 'var(--gold-light)' : 'var(--c-text-muted)',
        textAlign: 'right',
      }}>
        {pct(winP)}
      </span>
    </div>
  );
}

function GroupCard({ letter, teams, onTeamClick }) {
  const sorted = [...teams].sort(
    (a, b) => (b.simulation?.win_probability ?? 0) - (a.simulation?.win_probability ?? 0)
  );
  const maxWin = sorted[0]?.simulation?.win_probability ?? 0;
  const topColor = nc(sorted[0]?.team ?? '');

  return (
    <div style={{
      background: 'var(--c-surface)',
      border: '1px solid var(--c-border)',
      borderTop: `3px solid ${topColor}`,
      borderRadius: 'var(--r-card)',
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '9px 12px',
        background: 'var(--c-raised)',
        borderBottom: '1px solid var(--c-border)',
      }}>
        <span style={{
          fontFamily: 'var(--font-heading)', fontSize: 13, fontWeight: 800,
          color: 'var(--gold)', letterSpacing: '0.10em', textTransform: 'uppercase',
        }}>
          GROUP {letter}
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--c-text-dim)' }}>
          WIN PROB
        </span>
      </div>

      {/* Teams */}
      <div style={{ padding: '0 10px' }}>
        {sorted.map((t, i) => (
          <GroupTeamRow
            key={t.team}
            teamData={t}
            maxWin={maxWin}
            rank={i + 1}
            onClick={onTeamClick}
          />
        ))}
      </div>
    </div>
  );
}

export default function BracketView({ onTeamClick }) {
  const [data, setData] = useState(null);
  const [err,  setErr]  = useState(null);

  useEffect(() => {
    api.bracket().then(setData).catch((e) => setErr(e.message));
  }, []);

  if (err) return (
    <div style={{ padding: 40, textAlign: 'center' }}>
      <p style={{ fontFamily: 'var(--font-mono)', color: 'var(--c-red)' }}>
        Could not load bracket: {err}
      </p>
    </div>
  );

  if (!data) return (
    <div style={{ padding: 60, textAlign: 'center' }}>
      <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--c-text-dim)' }}>Loading groups…</span>
    </div>
  );

  const { groups, simulation_meta: meta } = data;
  const groupLetters = Object.keys(groups).sort();

  return (
    <div className="fade-up">
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <div className="section-label" style={{ marginBottom: 8 }}>
          Group Stage Draw — Official FIFA WC 2026 (Dec 5, 2024)
        </div>
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--c-text-dim)' }}>
          12 groups · 4 teams each · 👑 = group favourite by win probability
          {meta && ` · ${meta.simulations_run?.toLocaleString()} simulations`}
        </p>
      </div>

      {/* Group grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
        gap: 14,
      }}>
        {groupLetters.map((letter) => (
          <GroupCard
            key={letter}
            letter={letter}
            teams={groups[letter]}
            onTeamClick={onTeamClick}
          />
        ))}
      </div>
    </div>
  );
}
