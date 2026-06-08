import { useState, useEffect } from 'react';
import { api } from '../utils/api';
import { flag, TEAM_GROUP, displayName } from '../utils/flags';
import { nc } from '../utils/nationalColors';

const pct = (v) => v != null ? `${(v * 100).toFixed(1)}%` : '—';
const HOST = new Set(['USA', 'Canada', 'Mexico']);

const SORT_OPTS = [
  { key: 'win_probability',              label: 'Win%'    },
  { key: 'final_probability',            label: 'Final%'  },
  { key: 'semifinal_probability',        label: 'SF%'     },
  { key: 'quarterfinal_probability',     label: 'QF%'     },
  { key: 'group_stage_exit_probability', label: 'Exit%'   },
  { key: 'expected_goals_tournament',    label: 'Goals'   },
];

const TH = {
  padding: '8px 12px',
  fontFamily: 'var(--font-body)',
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--text-muted)',
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
  textAlign: 'right',
  whiteSpace: 'nowrap',
  background: 'var(--surface-2)',
};

function Row({ team: t, rank, onClick }) {
  const [hov, setHov] = useState(false);
  const color  = nc(t.team);
  const group  = TEAM_GROUP[t.team] ?? '?';
  const top3   = rank <= 3;

  return (
    <tr
      onClick={onClick}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        background: hov ? 'var(--surface-2)' : 'transparent',
        cursor: 'pointer',
        borderBottom: '1px solid var(--border)',
        transition: 'background var(--t)',
      }}
    >
      {/* Left colour strip */}
      <td style={{ width: 3, padding: 0, background: color }} />

      {/* Rank */}
      <td style={{ padding: '10px 8px', width: 36, textAlign: 'center' }}>
        <span style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: top3 ? 'var(--gold)' : '#444', fontWeight: top3 ? 600 : 400 }}>
          {String(rank).padStart(2, '0')}
        </span>
      </td>

      {/* Flag + name */}
      <td style={{ padding: '10px 8px', minWidth: 170 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 20, lineHeight: 1, flexShrink: 0 }}>{flag(t.team)}</span>
          <div>
            <div style={{ fontFamily: 'var(--font-body)', fontSize: 14, fontWeight: 500, color: 'var(--text)' }}>
              {displayName(t.team)}
            </div>
            <div style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: '#444' }}>
              Group {group}{HOST.has(t.team) ? ' · Host' : ''}
            </div>
          </div>
        </div>
      </td>

      {/* Win % — big */}
      <td style={{ padding: '10px 12px', textAlign: 'right' }}>
        <span style={{ fontFamily: 'var(--font-heading)', fontSize: 22, color: top3 ? 'var(--gold)' : 'var(--text)', lineHeight: 1 }}>
          {pct(t.win_probability)}
        </span>
      </td>

      {/* Final, SF, QF, Exit, Goals */}
      {[t.final_probability, t.semifinal_probability, t.quarterfinal_probability].map((v, i) => (
        <td key={i} style={{ padding: '10px 12px', fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--text-muted)', textAlign: 'right', whiteSpace: 'nowrap' }}>
          {pct(v)}
        </td>
      ))}
      <td style={{ padding: '10px 12px', fontFamily: 'var(--font-body)', fontSize: 13, color: (t.group_stage_exit_probability ?? 0) > 0.3 ? '#c0392b' : '#444', textAlign: 'right', whiteSpace: 'nowrap' }}>
        {pct(t.group_stage_exit_probability)}
      </td>
      <td style={{ padding: '10px 12px', fontFamily: 'var(--font-body)', fontSize: 13, color: '#444', textAlign: 'right', whiteSpace: 'nowrap' }}>
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

  useEffect(() => { api.simResults().then(setData).catch((e) => setErr(e.message)); }, []);

  if (err) return <div style={{ padding: 40, fontFamily: 'var(--font-body)', color: '#c0392b', fontSize: 13 }}>{err}</div>;
  if (!data) return <div style={{ padding: 40, fontFamily: 'var(--font-body)', color: '#444', fontSize: 13 }}>Loading…</div>;

  const teams = data.teams ?? [];

  function toggleSort(col) {
    if (sortCol === col) setSortDir((d) => d === 'desc' ? 'asc' : 'desc');
    else { setSortCol(col); setSortDir('desc'); }
  }

  const sorted   = [...teams].sort((a, b) => sortDir === 'desc' ? (b[sortCol] ?? 0) - (a[sortCol] ?? 0) : (a[sortCol] ?? 0) - (b[sortCol] ?? 0));
  const filtered = filter ? sorted.filter((t) => t.team.toLowerCase().includes(filter.toLowerCase())) : sorted;

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 12 }}>
        <p className="section-label" style={{ margin: 0 }}>All {teams.length} Teams</p>
        <input
          className="input"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter team…"
          style={{ width: 140 }}
          aria-label="Filter teams"
        />
      </div>

      {/* Sort controls */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 1, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: '#444', textTransform: 'uppercase', letterSpacing: '0.08em', marginRight: 8, lineHeight: '28px' }}>Sort:</span>
        {SORT_OPTS.map(({ key, label }) => {
          const active = sortCol === key;
          return (
            <button key={key} onClick={() => toggleSort(key)} style={{
              padding: '4px 10px', border: `1px solid ${active ? 'var(--gold)' : 'var(--border)'}`,
              borderRadius: 4, background: active ? 'var(--gold-dim)' : 'transparent',
              color: active ? 'var(--gold)' : 'var(--text-muted)',
              fontFamily: 'var(--font-body)', fontSize: 11, fontWeight: active ? 600 : 400,
              textTransform: 'uppercase', letterSpacing: '0.06em', cursor: 'pointer',
              transition: 'all var(--t)',
            }}>
              {label}{active ? (sortDir === 'desc' ? ' ↓' : ' ↑') : ''}
            </button>
          );
        })}
      </div>

      {/* Table */}
      <div style={{ overflowX: 'auto', border: '1px solid var(--border)', borderRadius: 6 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <th style={{ ...TH, width: 3, padding: 0 }} />
              <th style={{ ...TH, textAlign: 'center' }}>#</th>
              <th style={{ ...TH, textAlign: 'left', paddingLeft: 8 }}>Team</th>
              <th style={TH}>Win%</th>
              <th style={TH}>Final</th>
              <th style={TH}>SF</th>
              <th style={TH}>QF</th>
              <th style={TH}>Exit%</th>
              <th style={TH}>Gls</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((t) => (
              <Row key={t.team} team={t} rank={sorted.indexOf(t) + 1} onClick={() => onTeamClick(t.team)} />
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={9} style={{ padding: 40, textAlign: 'center', fontFamily: 'var(--font-body)', color: '#444', fontSize: 13 }}>No teams match "{filter}"</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
