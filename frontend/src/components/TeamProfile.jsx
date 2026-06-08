import { useState, useEffect } from 'react';
import { api } from '../utils/api';
import { flag, TEAM_GROUP } from '../utils/flags';
import { nc } from '../utils/nationalColors';
import { useCountUp } from '../hooks/useCountUp';

const pct  = (v) => v != null ? `${(v * 100).toFixed(1)}%` : '—';
const fmt2 = (v) => v != null ? Number(v).toFixed(2) : '—';

function StatBox({ label, value, gold }) {
  return (
    <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 6, padding: '12px 14px' }}>
      <div style={{ fontFamily: 'var(--font-body)', fontSize: 10, color: '#444', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 4 }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-heading)', fontSize: 24, color: gold ? 'var(--gold)' : 'var(--text)', lineHeight: 1 }}>{value}</div>
    </div>
  );
}

function Bar({ label, value, max = 1, color, fmt = pct }) {
  const w = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 80px 44px', alignItems: 'center', gap: 12, padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
      <span style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--text-muted)' }}>{label}</span>
      <div style={{ background: 'var(--surface-2)', height: 4, borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ height: '100%', background: color ?? 'var(--gold)', width: `${w}%`, transition: 'width 0.6s ease', borderRadius: 2 }} />
      </div>
      <span style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--text)', textAlign: 'right', fontWeight: 500 }}>{fmt(value)}</span>
    </div>
  );
}

function FormPill({ c }) {
  const cfg = { W: { bg: 'rgba(26,107,60,0.2)', border: '#1a6b3c', color: '#3ecf8e' }, D: { bg: 'rgba(201,168,76,0.15)', border: 'var(--gold)', color: 'var(--gold)' }, L: { bg: 'rgba(192,57,43,0.15)', border: '#c0392b', color: '#c0392b' } }[c] ?? { bg: 'var(--surface-2)', border: 'var(--border)', color: '#444' };
  return <span style={{ fontFamily: 'monospace', fontSize: 12, fontWeight: 600, color: cfg.color, background: cfg.bg, border: `1px solid ${cfg.border}`, padding: '3px 7px', borderRadius: 3 }}>{c}</span>;
}

function ProbRow({ label, value, big }) {
  const v = useCountUp((value ?? 0) * 100, 800);
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '7px 0', borderBottom: '1px solid var(--border)' }}>
      <span style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--text-muted)' }}>{label}</span>
      <span style={{ fontFamily: 'var(--font-heading)', fontSize: big ? 22 : 16, color: big ? 'var(--gold)' : 'var(--text)' }}>
        {v.toFixed(1)}%
      </span>
    </div>
  );
}

export default function TeamProfile({ team, onBack }) {
  const [data, setData] = useState(null);
  const [err,  setErr]  = useState(null);

  useEffect(() => { api.team(team).then(setData).catch((e) => setErr(e.message)); }, [team]);

  if (err) return (
    <div className="fade-up">
      <button className="btn" onClick={onBack} style={{ marginBottom: 20 }}>← Back</button>
      <p style={{ fontFamily: 'var(--font-body)', color: '#c0392b', fontSize: 13 }}>{err}</p>
    </div>
  );
  if (!data) return (
    <div className="fade-up" style={{ padding: 60, textAlign: 'center' }}>
      <span style={{ fontFamily: 'var(--font-body)', color: '#444', fontSize: 13 }}>Loading {team}…</span>
    </div>
  );

  const { stats, fifa_rank, recent_matches, simulation: sim } = data;
  const color = nc(team);
  const group = TEAM_GROUP[team] ?? '?';

  return (
    <div className="fade-up">
      <button className="btn" onClick={onBack} style={{ marginBottom: 24 }}>← Back</button>

      {/* Hero */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 20, padding: 24, background: 'var(--surface)', border: '1px solid var(--border)', borderLeft: `4px solid ${color}`, borderRadius: 8, marginBottom: 24, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 56, lineHeight: 1 }}>{flag(team)}</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontFamily: 'var(--font-heading)', fontSize: 48, color: 'var(--text)', lineHeight: 0.95, letterSpacing: '0.01em', marginBottom: 10 }}>{team.toUpperCase()}</div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            {[`Group ${group}`, fifa_rank ? `FIFA #${fifa_rank.rank}` : null, ['USA','Canada','Mexico'].includes(team) ? '2026 Host' : null].filter(Boolean).map((l) => (
              <span key={l} style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: 'var(--text-muted)', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 4, padding: '3px 8px', textTransform: 'uppercase', letterSpacing: '0.07em' }}>{l}</span>
            ))}
          </div>
        </div>
        {sim && (
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: '#444', marginBottom: 2, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Win Probability</div>
            <div style={{ fontFamily: 'var(--font-heading)', fontSize: 48, color: 'var(--gold)', lineHeight: 1 }}>{pct(sim.win_probability)}</div>
          </div>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>
        {/* Tournament probs */}
        <div className="card">
          <p style={{ fontFamily: 'var(--font-body)', fontSize: 11, fontWeight: 600, color: '#444', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 12 }}>Tournament Probabilities</p>
          {sim ? (
            <>
              {[['Win World Cup', sim.win_probability, true], ['Reach Final', sim.final_probability, false], ['Reach Semi', sim.semifinal_probability, false], ['Reach QF', sim.quarterfinal_probability, false], ['Reach R16', sim.r16_probability, false]].map(([l, v, b]) => (
                <ProbRow key={l} label={l} value={v} big={b} />
              ))}
              <div style={{ marginTop: 12, fontFamily: 'var(--font-body)', fontSize: 12, color: '#444' }}>
                Group exit: <span style={{ color: sim.group_stage_exit_probability > 0.3 ? '#c0392b' : 'var(--text-muted)', fontWeight: 500 }}>{pct(sim.group_stage_exit_probability)}</span>
                &emsp;Exp goals: <span style={{ color: 'var(--gold)', fontWeight: 500 }}>{sim.expected_goals_tournament?.toFixed(2)}</span>
              </div>
            </>
          ) : <p style={{ fontFamily: 'var(--font-body)', color: '#444', fontSize: 12 }}>Run /simulate first</p>}
        </div>

        {/* Stats */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
            <StatBox label="Win Rate"    value={pct(stats?.win_rate)}           gold />
            <StatBox label="Home W%"     value={pct(stats?.home_win_rate)}      />
            <StatBox label="Away W%"     value={pct(stats?.away_win_rate)}      />
            <StatBox label="Avg Goals"   value={fmt2(stats?.avg_goals_scored)}  />
            <StatBox label="Conceded"    value={fmt2(stats?.avg_goals_conceded)}/>
            <StatBox label="Big Games"   value={pct(stats?.big_game_win_rate)}  />
          </div>
          <div className="card" style={{ padding: 14 }}>
            <p style={{ fontFamily: 'var(--font-body)', fontSize: 10, color: '#444', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8 }}>Last 10 results</p>
            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
              {stats?.form_last_10 ? stats.form_last_10.split('').map((c, i) => <FormPill key={i} c={c} />)
                : <span style={{ fontFamily: 'var(--font-body)', color: '#444', fontSize: 12 }}>No data</span>}
            </div>
          </div>
        </div>
      </div>

      {/* ML features */}
      <div className="card" style={{ marginBottom: 20 }}>
        <p style={{ fontFamily: 'var(--font-body)', fontSize: 11, fontWeight: 600, color: '#444', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 14 }}>ML Feature Scores</p>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 32px' }}>
          {[['Offensive Strength', stats?.offensive_strength ?? 0, 3], ['Defensive Strength', stats?.defensive_strength ?? 0, 7], ['Big Game Win Rate', stats?.big_game_win_rate ?? 0, 1], ['Form Momentum', stats?.form_momentum ?? 0, 1]].map(([l, v, m]) => (
            <Bar key={l} label={l} value={v} max={m} color={color} fmt={(x) => Number(x).toFixed(3)} />
          ))}
          {[['Tournament Experience', stats?.tournament_experience_score ?? 0, 20], ['Goals Scored (last 5)', stats?.goals_scored_last_5 ?? 0, 5], ['Goals Conceded (last 5)', stats?.goals_conceded_last_5 ?? 0, 5], ['Host Nation Bonus', stats?.host_nation_bonus ?? 0, 0.1]].map(([l, v, m]) => (
            <Bar key={l} label={l} value={v} max={m} color='var(--gold)' fmt={(x) => Number(x).toFixed(2)} />
          ))}
        </div>
      </div>

      {/* Recent matches */}
      <div className="card">
        <p style={{ fontFamily: 'var(--font-body)', fontSize: 11, fontWeight: 600, color: '#444', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 14 }}>Last 5 Matches</p>
        {recent_matches?.length ? (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead><tr style={{ borderBottom: '1px solid var(--border)' }}>
              {['Date','Home','Score','Away','Competition'].map((h) => (
                <th key={h} style={{ padding: '6px 10px', textAlign: 'left', fontFamily: 'var(--font-body)', fontSize: 10, color: '#444', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 500 }}>{h}</th>
              ))}
            </tr></thead>
            <tbody>
              {recent_matches.map((m, i) => {
                const isHome = m.home_team?.toLowerCase() === team.toLowerCase();
                const won    = (isHome && m.result === 'home_win') || (!isHome && m.result === 'away_win');
                const drew   = m.result === 'draw';
                const sc     = won ? '#3ecf8e' : drew ? 'var(--gold)' : '#c0392b';
                return (
                  <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '8px 10px', fontFamily: 'var(--font-body)', fontSize: 12, color: '#444' }}>{m.date}</td>
                    <td style={{ padding: '8px 10px', fontFamily: 'var(--font-body)', fontSize: 13, color: isHome ? 'var(--text)' : 'var(--text-muted)', fontWeight: isHome ? 500 : 400 }}>{m.home_team}</td>
                    <td style={{ padding: '8px 10px', fontFamily: 'var(--font-heading)', fontSize: 16, color: sc, whiteSpace: 'nowrap' }}>{m.home_goals} – {m.away_goals}</td>
                    <td style={{ padding: '8px 10px', fontFamily: 'var(--font-body)', fontSize: 13, color: !isHome ? 'var(--text)' : 'var(--text-muted)', fontWeight: !isHome ? 500 : 400 }}>{m.away_team}</td>
                    <td style={{ padding: '8px 10px', fontFamily: 'var(--font-body)', fontSize: 11, color: '#444' }}>{m.competition}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : <p style={{ fontFamily: 'var(--font-body)', color: '#444', fontSize: 12 }}>No matches available</p>}
      </div>
    </div>
  );
}
