import { useState, useEffect } from 'react';
import { api } from '../utils/api';
import { flag, TEAM_GROUP } from '../utils/flags';
import { nc, colorGlow } from '../utils/nationalColors';
import { useCountUp } from '../hooks/useCountUp';

const pct  = (v) => (v != null ? `${(v * 100).toFixed(1)}%` : '—');
const fmt2 = (v) => (v != null ? Number(v).toFixed(2) : '—');
const fmt3 = (v) => (v != null ? Number(v).toFixed(3) : '—');

function StatBox({ label, value, gold, subtitle }) {
  return (
    <div style={{
      background: 'var(--c-raised)', border: '1px solid var(--c-border)',
      borderRadius: 'var(--r-card)', padding: '14px 16px',
    }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--c-text-dim)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 5 }}>
        {label}
      </div>
      <div style={{
        fontFamily: 'var(--font-heading)', fontSize: 22, fontWeight: 800, lineHeight: 1,
        color: gold ? 'var(--gold-light)' : 'var(--c-text)',
      }}>
        {value}
      </div>
      {subtitle && (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--c-text-dim)', marginTop: 4 }}>
          {subtitle}
        </div>
      )}
    </div>
  );
}

function FeatureRow({ label, value, max = 1, format = fmt3, color }) {
  const barPct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  return (
    <div style={{
      display: 'grid', gridTemplateColumns: '1fr 100px 52px',
      alignItems: 'center', gap: 12,
      padding: '7px 0', borderBottom: '1px solid var(--c-border)',
    }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--c-text-muted)' }}>{label}</span>
      <div style={{ background: 'var(--c-raised)', height: 4, borderRadius: 2, overflow: 'hidden' }}>
        <div style={{
          height: '100%', borderRadius: 2,
          background: color ?? 'var(--gold)',
          width: `${barPct}%`,
          transition: 'width 0.7s cubic-bezier(.22,1,.36,1)',
        }} />
      </div>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--c-text)', textAlign: 'right', fontWeight: 700 }}>
        {format(value)}
      </span>
    </div>
  );
}

function FormPill({ char }) {
  const cfg = {
    W: { bg: 'rgba(45,198,83,0.15)', border: '#2dc653', color: '#2dc653' },
    D: { bg: 'rgba(245,200,66,0.15)', border: 'var(--c-yellow)', color: 'var(--c-yellow)' },
    L: { bg: 'rgba(230,57,70,0.15)', border: 'var(--c-red)', color: 'var(--c-red)' },
  }[char] ?? { bg: 'var(--c-raised)', border: 'var(--c-border)', color: 'var(--c-text-dim)' };

  return (
    <span style={{
      fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700,
      color: cfg.color, background: cfg.bg,
      border: `1px solid ${cfg.border}`,
      padding: '3px 7px', borderRadius: 3,
    }}>
      {char}
    </span>
  );
}

function ProbRow({ label, value, isTop }) {
  const animated = useCountUp((value ?? 0) * 100, 800);
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '8px 0', borderBottom: '1px solid var(--c-border)',
    }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--c-text-muted)' }}>
        {label}
      </span>
      <span style={{
        fontFamily: 'var(--font-heading)', fontSize: isTop ? 22 : 15, fontWeight: 800,
        color: isTop ? 'var(--gold-light)' : 'var(--c-text)',
        letterSpacing: '-0.01em',
      }}>
        {animated.toFixed(1)}%
      </span>
    </div>
  );
}

export default function TeamProfile({ team, onBack }) {
  const [data, setData] = useState(null);
  const [err,  setErr]  = useState(null);

  useEffect(() => {
    api.team(team).then(setData).catch((e) => setErr(e.message));
  }, [team]);

  if (err) return (
    <div className="fade-up">
      <button className="btn" onClick={onBack} style={{ marginBottom: 20 }}>← Back</button>
      <p style={{ fontFamily: 'var(--font-mono)', color: 'var(--c-red)' }}>{err}</p>
    </div>
  );

  if (!data) return (
    <div className="fade-up" style={{ padding: 60, textAlign: 'center' }}>
      <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--c-text-dim)' }}>Loading {team}…</span>
    </div>
  );

  const { stats, fifa_rank, recent_matches, simulation: sim } = data;
  const color = nc(team);
  const group = TEAM_GROUP[team] ?? '?';

  return (
    <div className="fade-up">
      <button className="btn" onClick={onBack} style={{ marginBottom: 24 }}>← Back</button>

      {/* ── Hero ─────────────────────────────────────────────────── */}
      <div style={{
        background: `linear-gradient(135deg, #0a0a0a 0%, color-mix(in srgb, ${color} 12%, #0a0a0a) 100%)`,
        border: `1px solid ${color}44`,
        borderLeft: `4px solid ${color}`,
        borderRadius: 'var(--r-card)',
        padding: '28px 28px',
        marginBottom: 24,
        display: 'flex', alignItems: 'center', gap: 20, flexWrap: 'wrap',
        boxShadow: colorGlow(team, 0.15),
      }}>
        <span style={{ fontSize: 64, lineHeight: 1 }}>{flag(team)}</span>

        <div style={{ flex: 1 }}>
          <div style={{
            fontFamily: 'var(--font-heading)', fontSize: 42, fontWeight: 800,
            color: 'var(--c-text)', textTransform: 'uppercase',
            letterSpacing: '-0.02em', lineHeight: 1, marginBottom: 10,
          }}>
            {team}
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <span className="chip chip-gold">GROUP {group}</span>
            {fifa_rank && <span className="chip">FIFA #{fifa_rank.rank}</span>}
            {fifa_rank && <span className="chip">{Number(fifa_rank.points).toFixed(0)} PTS</span>}
            {['USA','Canada','Mexico'].includes(team) && <span className="chip chip-gold">2026 HOST</span>}
          </div>
        </div>

        {sim && (
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--c-text-dim)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 4 }}>
              Win Probability
            </div>
            <div style={{
              fontFamily: 'var(--font-heading)', fontSize: 52, fontWeight: 800,
              color: 'var(--gold-light)', lineHeight: 1, letterSpacing: '-0.02em',
            }}>
              {pct(sim.win_probability)}
            </div>
          </div>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>
        {/* Tournament probabilities */}
        <div className="card" style={{ padding: 20 }}>
          <div style={{
            fontFamily: 'var(--font-heading)', fontSize: 12, fontWeight: 800,
            color: 'var(--c-text-muted)', textTransform: 'uppercase',
            letterSpacing: '0.07em', marginBottom: 12,
          }}>
            Tournament Probabilities
          </div>
          {sim ? (
            <>
              {[
                ['Win the World Cup',   sim.win_probability,             true ],
                ['Reach the Final',     sim.final_probability,           false],
                ['Reach Semi-final',    sim.semifinal_probability,       false],
                ['Reach Quarter-final', sim.quarterfinal_probability,    false],
                ['Reach Round of 16',   sim.r16_probability,             false],
                ['Reach Round of 32',   sim.r32_probability,             false],
              ].map(([lbl, val, top]) => (
                <ProbRow key={lbl} label={lbl} value={val} isTop={top} />
              ))}
              <div style={{ marginTop: 12, fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--c-text-dim)' }}>
                Group exit: <span style={{ color: sim.group_stage_exit_probability > 0.3 ? 'var(--c-red)' : 'var(--c-text-muted)', fontWeight: 700 }}>
                  {pct(sim.group_stage_exit_probability)}
                </span>
                &emsp;Exp goals: <span style={{ color: 'var(--gold)', fontWeight: 700 }}>
                  {sim.expected_goals_tournament?.toFixed(2)}
                </span>
              </div>
            </>
          ) : (
            <p style={{ fontFamily: 'var(--font-mono)', color: 'var(--c-text-dim)', fontSize: 11 }}>
              Run /simulate to generate probabilities
            </p>
          )}
        </div>

        {/* Performance stats */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10 }}>
            <StatBox label="Win Rate"     value={pct(stats?.win_rate)}           gold />
            <StatBox label="Home W%"      value={pct(stats?.home_win_rate)}       />
            <StatBox label="Away W%"      value={pct(stats?.away_win_rate)}       />
            <StatBox label="Avg Goals"    value={fmt2(stats?.avg_goals_scored)}   subtitle="scored/game" />
            <StatBox label="Avg Conceded" value={fmt2(stats?.avg_goals_conceded)} subtitle="conceded/game" />
            <StatBox label="Big Games"    value={pct(stats?.big_game_win_rate)}   subtitle="vs top-20" />
          </div>

          <div className="card" style={{ padding: 14 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--c-text-dim)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 10 }}>
              Last 10 Results
            </div>
            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
              {stats?.form_last_10
                ? stats.form_last_10.split('').map((c, i) => <FormPill key={i} char={c} />)
                : <span style={{ color: 'var(--c-text-dim)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>No data</span>
              }
            </div>
          </div>
        </div>
      </div>

      {/* ML Features */}
      <div className="card" style={{ padding: 20, marginBottom: 20 }}>
        <div style={{
          fontFamily: 'var(--font-heading)', fontSize: 12, fontWeight: 800,
          color: 'var(--c-text-muted)', textTransform: 'uppercase',
          letterSpacing: '0.07em', marginBottom: 14,
        }}>
          ML Feature Scores
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 40px' }}>
          <div>
            <FeatureRow label="Offensive Strength"    value={stats?.offensive_strength ?? 0}          max={3}  format={fmt3} color={color} />
            <FeatureRow label="Defensive Strength"    value={stats?.defensive_strength ?? 0}          max={7}  format={fmt3} color={color} />
            <FeatureRow label="Big Game Win Rate"     value={stats?.big_game_win_rate ?? 0}           max={1}  format={pct}  color={color} />
            <FeatureRow label="Form Momentum"         value={stats?.form_momentum ?? 0}               max={1}  format={fmt3} color={color} />
          </div>
          <div>
            <FeatureRow label="Tournament Experience" value={stats?.tournament_experience_score ?? 0} max={20} format={(v) => Number(v).toFixed(1)} />
            <FeatureRow label="Goals Scored (last 5)" value={stats?.goals_scored_last_5 ?? 0}         max={5}  format={fmt2} />
            <FeatureRow label="Goals Conceded (last 5)" value={stats?.goals_conceded_last_5 ?? 0}     max={5}  format={fmt2} />
            <FeatureRow label="Host Nation Bonus"     value={stats?.host_nation_bonus ?? 0}           max={0.1} format={fmt3} color="var(--gold)" />
          </div>
        </div>
      </div>

      {/* Recent matches */}
      <div className="card" style={{ padding: 20 }}>
        <div style={{
          fontFamily: 'var(--font-heading)', fontSize: 12, fontWeight: 800,
          color: 'var(--c-text-muted)', textTransform: 'uppercase',
          letterSpacing: '0.07em', marginBottom: 14,
        }}>
          Last 5 Matches
        </div>
        {recent_matches?.length ? (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--c-border)' }}>
                {['Date','Home','Score','Away','Competition'].map((h) => (
                  <th key={h} style={{ padding: '6px 10px', textAlign: 'left', fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--c-text-dim)', textTransform: 'uppercase', letterSpacing: '0.09em', fontWeight: 400 }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {recent_matches.map((m, i) => {
                const isHome = m.home_team?.toLowerCase() === team.toLowerCase();
                const won    = (isHome && m.result === 'home_win') || (!isHome && m.result === 'away_win');
                const drew   = m.result === 'draw';
                const scoreColor = won ? '#2dc653' : drew ? 'var(--c-yellow)' : 'var(--c-red)';
                return (
                  <tr key={i} style={{ borderBottom: '1px solid var(--c-border)' }}>
                    <td style={{ padding: '9px 10px', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--c-text-dim)' }}>{m.date}</td>
                    <td style={{ padding: '9px 10px', fontFamily: 'var(--font-mono)', fontSize: 11, color: isHome ? 'var(--c-text)' : 'var(--c-text-muted)', fontWeight: isHome ? 700 : 400 }}>{m.home_team}</td>
                    <td style={{ padding: '9px 10px', fontFamily: 'var(--font-heading)', fontSize: 14, fontWeight: 800, color: scoreColor, whiteSpace: 'nowrap' }}>
                      {m.home_goals} – {m.away_goals}
                    </td>
                    <td style={{ padding: '9px 10px', fontFamily: 'var(--font-mono)', fontSize: 11, color: !isHome ? 'var(--c-text)' : 'var(--c-text-muted)', fontWeight: !isHome ? 700 : 400 }}>{m.away_team}</td>
                    <td style={{ padding: '9px 10px', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--c-text-dim)' }}>{m.competition}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <p style={{ fontFamily: 'var(--font-mono)', color: 'var(--c-text-dim)', fontSize: 11 }}>No recent matches available</p>
        )}
      </div>
    </div>
  );
}
