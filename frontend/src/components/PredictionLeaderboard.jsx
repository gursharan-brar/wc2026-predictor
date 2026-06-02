import { useState, useEffect } from 'react';
import { api } from '../utils/api';
import { flag, TEAM_GROUP } from '../utils/flags';
import { nc } from '../utils/nationalColors';

const pct = (v) => (v != null ? `${(v * 100).toFixed(1)}%` : '—');
const HOST_NATIONS = new Set(['USA', 'Canada', 'Mexico']);

const SORT_COLS = [
  { key: 'win_probability',              label: 'WIN%'   },
  { key: 'final_probability',            label: 'FINAL%' },
  { key: 'semifinal_probability',        label: 'SF%'    },
  { key: 'quarterfinal_probability',     label: 'QF%'    },
  { key: 'group_stage_exit_probability', label: 'EXIT%'  },
  { key: 'expected_goals_tournament',    label: 'GOALS'  },
];

function SortBtn({ col, label, active, dir, onClick }) {
  return (
    <button
      onClick={() => onClick(col)}
      style={{
        background: active ? 'var(--gold-dim)' : 'none',
        border: active ? '1px solid var(--gold-border)' : '1px solid transparent',
        borderRadius: 3,
        padding: '3px 9px',
        cursor: 'pointer',
        fontFamily: 'var(--font-mono)', fontSize: 9,
        color: active ? 'var(--gold)' : 'var(--c-text-dim)',
        fontWeight: active ? 700 : 400,
        textTransform: 'uppercase', letterSpacing: '0.07em',
        display: 'inline-flex', alignItems: 'center', gap: 3,
        transition: 'all var(--t)',
      }}
    >
      {label}
      {active && <span style={{ fontSize: 8 }}>{dir === 'desc' ? '▼' : '▲'}</span>}
    </button>
  );
}

function TeamRow({ rank, team: t, onClick }) {
  const [hovered, setHovered] = useState(false);
  const color   = nc(t.team);
  const group   = TEAM_GROUP[t.team] ?? '?';
  const isHost  = HOST_NATIONS.has(t.team);
  const isTop3  = rank <= 3;

  // 8% opacity tint from national color
  const rowBg = hovered
    ? `color-mix(in srgb, ${color} 14%, #0f0f0f)`
    : `color-mix(in srgb, ${color} 6%, #0a0a0a)`;

  return (
    <tr
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: rowBg,
        cursor: 'pointer',
        transition: 'background var(--t)',
        borderBottom: '1px solid var(--c-border)',
      }}
    >
      {/* National color left border via first td */}
      <td style={{
        width: 4, padding: 0,
        background: color,
      }} />

      {/* Rank */}
      <td style={{ padding: '10px 8px', width: 36, textAlign: 'center' }}>
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700,
          color: isTop3 ? 'var(--gold)' : 'var(--c-text-dim)',
        }}>
          {String(rank).padStart(2, '0')}
        </span>
      </td>

      {/* Flag + team */}
      <td style={{ padding: '10px 8px', minWidth: 180 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
          <span style={{ fontSize: 20, lineHeight: 1, flexShrink: 0 }}>{flag(t.team)}</span>
          <div>
            <div style={{
              fontFamily: 'var(--font-heading)', fontSize: 13, fontWeight: 800,
              color: 'var(--c-text)', textTransform: 'uppercase',
              letterSpacing: '0.03em', lineHeight: 1.2,
            }}>
              {t.team}
            </div>
            <div style={{ display: 'flex', gap: 4, marginTop: 3 }}>
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: 9,
                color, textTransform: 'uppercase', letterSpacing: '0.09em',
              }}>
                GRP {group}
              </span>
              {isHost && (
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 9,
                  color: 'var(--gold)', letterSpacing: '0.09em',
                }}>
                  · HOST
                </span>
              )}
            </div>
          </div>
        </div>
      </td>

      {/* Win % — big bold number */}
      <td style={{ padding: '10px 12px', minWidth: 80 }}>
        <span style={{
          fontFamily: 'var(--font-heading)', fontSize: 20, fontWeight: 800,
          color: isTop3 ? 'var(--gold-light)' : 'var(--c-text)',
          letterSpacing: '-0.01em',
        }}>
          {pct(t.win_probability)}
        </span>
      </td>

      {/* Final */}
      <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--c-text-muted)', whiteSpace: 'nowrap' }}>
        {pct(t.final_probability)}
      </td>

      {/* SF */}
      <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--c-text-muted)', whiteSpace: 'nowrap' }}>
        {pct(t.semifinal_probability)}
      </td>

      {/* QF */}
      <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--c-text-dim)', whiteSpace: 'nowrap' }}>
        {pct(t.quarterfinal_probability)}
      </td>

      {/* Group exit — red if high */}
      <td style={{
        padding: '10px 12px',
        fontFamily: 'var(--font-mono)', fontSize: 12,
        color: t.group_stage_exit_probability > 0.3 ? 'var(--c-red)' : 'var(--c-text-dim)',
        whiteSpace: 'nowrap',
      }}>
        {pct(t.group_stage_exit_probability)}
      </td>

      {/* Expected goals */}
      <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--c-text-dim)', whiteSpace: 'nowrap' }}>
        {t.expected_goals_tournament?.toFixed(2) ?? '—'}
      </td>
    </tr>
  );
}

export default function PredictionLeaderboard({ onTeamClick }) {
  const [data,    setData]    = useState(null);
  const [err,     setErr]     = useState(null);
  const [sortCol, setSortCol] = useState('win_probability');
  const [sortDir, setSortDir] = useState('desc');
  const [filter,  setFilter]  = useState('');

  useEffect(() => {
    api.simResults().then(setData).catch((e) => setErr(e.message));
  }, []);

  if (err) return (
    <div style={{ padding: 40, textAlign: 'center' }}>
      <p style={{ fontFamily: 'var(--font-mono)', color: 'var(--c-red)', marginBottom: 8 }}>
        Failed to load simulation results
      </p>
      <p style={{ fontFamily: 'var(--font-mono)', color: 'var(--c-text-dim)', fontSize: 11 }}>
        Start the API: <span style={{ color: 'var(--gold)' }}>node api/server.js</span>
      </p>
    </div>
  );

  if (!data) return (
    <div style={{ padding: 60, textAlign: 'center' }}>
      <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--c-text-dim)' }}>Loading leaderboard…</span>
    </div>
  );

  const teams = data.teams ?? [];

  function handleSort(col) {
    if (sortCol === col) setSortDir((d) => d === 'desc' ? 'asc' : 'desc');
    else { setSortCol(col); setSortDir('desc'); }
  }

  const sorted = [...teams].sort((a, b) => {
    const va = a[sortCol] ?? 0, vb = b[sortCol] ?? 0;
    return sortDir === 'desc' ? vb - va : va - vb;
  });

  const filtered = filter
    ? sorted.filter((t) => t.team.toLowerCase().includes(filter.toLowerCase()))
    : sorted;

  return (
    <div>
      {/* Header row */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        flexWrap: 'wrap', gap: 12, marginBottom: 14,
      }}>
        <div>
          <div className="section-label">All {teams.length} Teams — Full Rankings</div>
        </div>
        <input
          className="input-gold"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter team…"
          style={{ width: 150 }}
          aria-label="Filter teams"
        />
      </div>

      {/* Sort controls */}
      <div style={{
        display: 'flex', gap: 6, flexWrap: 'wrap',
        padding: '8px 12px', marginBottom: 1,
        background: 'var(--c-surface)',
        border: '1px solid var(--c-border)',
        borderRadius: '6px 6px 0 0',
        borderBottom: 'none',
        alignItems: 'center',
      }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--c-text-dim)', textTransform: 'uppercase', letterSpacing: '0.1em', marginRight: 4 }}>
          Sort
        </span>
        {SORT_COLS.map((c) => (
          <SortBtn key={c.key} col={c.key} label={c.label}
            active={sortCol === c.key} dir={sortDir} onClick={handleSort} />
        ))}
      </div>

      {/* Table */}
      <div style={{ overflowX: 'auto', borderRadius: '0 0 var(--r-card) var(--r-card)', overflow: 'hidden', border: '1px solid var(--c-border)' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'auto' }}>
          <thead>
            <tr style={{ background: 'var(--c-raised)', borderBottom: '1px solid var(--c-border-md)' }}>
              <th style={{ width: 4, padding: 0 }} />
              <th style={th}>#</th>
              <th style={{ ...th, textAlign: 'left', paddingLeft: 8 }}>Team</th>
              <th style={th}>Win %</th>
              <th style={th}>Final</th>
              <th style={th}>SF</th>
              <th style={th}>QF</th>
              <th style={th}>Exit %</th>
              <th style={th}>Exp Goals</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((team) => (
              <TeamRow
                key={team.team}
                rank={sorted.indexOf(team) + 1}
                team={team}
                onClick={() => onTeamClick(team.team)}
              />
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={9} style={{ padding: 40, textAlign: 'center', fontFamily: 'var(--font-mono)', color: 'var(--c-text-dim)', fontSize: 12 }}>
                  No teams match "{filter}"
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const th = {
  padding: '8px 12px',
  textAlign: 'right',
  fontFamily: 'var(--font-mono)',
  fontSize: 9,
  color: 'var(--c-text-dim)',
  textTransform: 'uppercase',
  letterSpacing: '0.09em',
  fontWeight: 400,
  whiteSpace: 'nowrap',
};
