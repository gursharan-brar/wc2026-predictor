import { useState, useEffect } from 'react';
import { api } from '../utils/api';
import { flag } from '../utils/flags';
import { nc } from '../utils/nationalColors';

const STAGES = [
  { key: 'r32_probability',          short: 'Group' },
  { key: 'r16_probability',          short: 'R32'   },
  { key: 'quarterfinal_probability', short: 'R16'   },
  { key: 'semifinal_probability',    short: 'QF'    },
  { key: 'final_probability',        short: 'SF'    },
  { key: 'win_probability',          short: 'Final' },
];

function calcConditional(sim) {
  return STAGES.map((s, i) => {
    const curr = sim[s.key] ?? 0;
    const prev = i === 0 ? 1 : (sim[STAGES[i - 1].key] ?? 1);
    return { ...s, cond: prev > 0 ? Math.min(curr / prev, 1) : 0 };
  });
}

export default function BracketPath({ onTeamClick }) {
  const [teams, setTeams] = useState(null);

  useEffect(() => {
    api.simResults().then((d) => setTeams(d.teams?.slice(0, 4))).catch(() => {});
  }, []);

  return (
    <div>
      <p className="section-label">Predicted Tournament Path</p>
      <p style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: '#444', marginBottom: 16 }}>
        Conditional win rate at each stage — top 4 teams
      </p>

      {!teams ? (
        <div style={{ color: '#444', fontSize: 13 }}>Loading…</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {teams.map((t) => {
            const chain = calcConditional(t);
            const color = nc(t.team);
            return (
              <div
                key={t.team}
                role="button" tabIndex={0}
                onClick={() => onTeamClick(t.team)}
                onKeyDown={(e) => e.key === 'Enter' && onTeamClick(t.team)}
                style={{
                  background: 'var(--surface)',
                  border: '1px solid var(--border)',
                  borderLeft: `3px solid ${color}`,
                  borderRadius: 6,
                  padding: '14px 16px',
                  cursor: 'pointer',
                  outline: 'none',
                }}
              >
                {/* Header */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 18 }}>{flag(t.team)}</span>
                    <span style={{ fontFamily: 'var(--font-body)', fontSize: 14, fontWeight: 500, color: 'var(--text)' }}>
                      {t.team}
                    </span>
                  </div>
                  <span style={{ fontFamily: 'var(--font-heading)', fontSize: 20, color: 'var(--gold)' }}>
                    {(t.win_probability * 100).toFixed(1)}%
                  </span>
                </div>

                {/* Stage chain */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                  {chain.map(({ short, cond }, i) => (
                    <div key={short} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <div style={{ textAlign: 'center' }}>
                        <div style={{
                          fontFamily: 'var(--font-body)', fontSize: 10,
                          color: i === chain.length - 1 ? 'var(--gold)' : 'var(--text-muted)',
                          fontWeight: i === chain.length - 1 ? 600 : 400,
                          letterSpacing: '0.06em', textTransform: 'uppercase',
                        }}>
                          {short}
                        </div>
                        <div style={{
                          fontFamily: 'var(--font-heading)', fontSize: 15,
                          color: i === chain.length - 1 ? 'var(--gold)' : 'var(--text-muted)',
                          lineHeight: 1.1,
                        }}>
                          {(cond * 100).toFixed(0)}%
                        </div>
                      </div>
                      {i < chain.length - 1 && (
                        <span style={{ color: '#333', fontSize: 12 }}>→</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
