import { useState, useEffect } from 'react';
import { api } from '../utils/api';
import { flag } from '../utils/flags';
import { nc } from '../utils/nationalColors';

/**
 * Shows stage-by-stage CONDITIONAL win probability for the top 4 teams.
 * "If France reaches the semi-final, they win it 68% of the time."
 * Computed from simulation data: P(advance | reached stage) = next_stage / this_stage
 */

const STAGES = [
  { key: 'r32_probability',            label: 'Survive Group',    short: 'GROUP'  },
  { key: 'r16_probability',            label: 'Win Rd. of 32',    short: 'R32'    },
  { key: 'quarterfinal_probability',   label: 'Win Rd. of 16',    short: 'R16'    },
  { key: 'semifinal_probability',      label: 'Win Quarter-final', short: 'QF'    },
  { key: 'final_probability',          label: 'Win Semi-final',   short: 'SF'     },
  { key: 'win_probability',            label: 'Win the Final',    short: 'FINAL'  },
];

function calcConditional(sim) {
  const chain = [];
  for (let i = 0; i < STAGES.length; i++) {
    const curr = sim[STAGES[i].key] ?? 0;
    const prev = i === 0 ? 1 : (sim[STAGES[i - 1].key] ?? 1);
    const cond = prev > 0 ? curr / prev : 0;
    chain.push({ ...STAGES[i], cond: Math.min(cond, 1) });
  }
  return chain;
}

function TeamPath({ team, sim, onTeamClick }) {
  const [hovered, setHovered] = useState(false);
  const color = nc(team);
  const chain = calcConditional(sim);

  return (
    <div
      style={{
        background: hovered ? `color-mix(in srgb, ${color} 8%, #111)` : 'var(--c-surface)',
        border: `1px solid ${hovered ? `${color}44` : 'var(--c-border)'}`,
        borderLeft: `3px solid ${color}`,
        borderRadius: 'var(--r-card)',
        padding: '14px 16px',
        cursor: 'pointer',
        transition: 'background var(--t), border-color var(--t)',
        marginBottom: 8,
      }}
      onClick={() => onTeamClick(team)}
      role="button"
      tabIndex={0}
      aria-label={`View ${team} predicted path`}
      onKeyDown={(e) => e.key === 'Enter' && onTeamClick(team)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Team header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        marginBottom: 12,
      }}>
        <span style={{ fontSize: 18, lineHeight: 1 }}>{flag(team)}</span>
        <span style={{
          fontFamily: 'var(--font-heading)', fontSize: 14, fontWeight: 800,
          color: 'var(--c-text)', textTransform: 'uppercase', letterSpacing: '0.04em',
        }}>
          {team}
        </span>
        <span style={{
          marginLeft: 'auto',
          fontFamily: 'var(--font-heading)', fontSize: 20, fontWeight: 800,
          color: 'var(--gold-light)',
        }}>
          {(sim.win_probability * 100).toFixed(1)}%
        </span>
      </div>

      {/* Stage chain */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        {chain.map(({ short, cond }, i) => {
          const barW = `${(cond * 100).toFixed(0)}%`;
          const isLast = i === chain.length - 1;
          return (
            <div key={short} style={{
              display: 'grid',
              gridTemplateColumns: '46px 1fr 36px',
              alignItems: 'center',
              gap: 8,
            }}>
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: 9,
                color: isLast ? 'var(--gold)' : 'var(--c-text-dim)',
                fontWeight: isLast ? 700 : 400,
                textTransform: 'uppercase', letterSpacing: '0.07em',
              }}>
                {short}
              </span>
              <div style={{
                height: 3, background: 'var(--c-raised)',
                borderRadius: 2, overflow: 'hidden',
              }}>
                <div style={{
                  height: '100%', borderRadius: 2,
                  background: isLast ? 'var(--gold)' : color,
                  width: barW,
                  transition: `width 0.6s cubic-bezier(.22,1,.36,1) ${i * 60}ms`,
                  opacity: isLast ? 1 : 0.65,
                }} />
              </div>
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700,
                color: isLast ? 'var(--gold)' : 'var(--c-text-muted)',
                textAlign: 'right',
              }}>
                {(cond * 100).toFixed(0)}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function BracketPath({ onTeamClick }) {
  const [teams, setTeams] = useState(null);

  useEffect(() => {
    api.simResults()
      .then((d) => setTeams(d.teams?.slice(0, 4) ?? []))
      .catch(() => {});
  }, []);

  return (
    <div>
      <div className="section-label" style={{ marginBottom: 4 }}>
        Predicted Tournament Path
      </div>
      <p style={{
        fontFamily: 'var(--font-mono)', fontSize: 10,
        color: 'var(--c-text-dim)', marginBottom: 16,
      }}>
        Conditional win rate at each stage — top 4 teams
      </p>

      {!teams ? (
        <div style={{ color: 'var(--c-text-dim)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
          Loading…
        </div>
      ) : (
        teams.map((t) => (
          <TeamPath key={t.team} team={t.team} sim={t} onTeamClick={onTeamClick} />
        ))
      )}
    </div>
  );
}
