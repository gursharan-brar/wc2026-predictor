import { useState, useEffect } from 'react';
import { api } from '../utils/api';
import { flag, TEAM_GROUP } from '../utils/flags';
import { nc } from '../utils/nationalColors';
import { useCountUp } from '../hooks/useCountUp';

/* Tabler-style trophy icon (inline SVG, no dependency) */
function TrophyIcon({ size = 16, color = 'var(--gold)' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
         stroke={color} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"
         aria-hidden="true">
      <path d="M8 21h8M12 17v4M7 4h10v8a5 5 0 0 1-10 0V4z"/>
      <path d="M5 9H3a2 2 0 0 0 0 4h2M19 9h2a2 2 0 0 0 0 4h-2"/>
    </svg>
  );
}

function StatPill({ label, value }) {
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ fontFamily: 'var(--font-heading)', fontSize: 22, color: 'var(--gold)', lineHeight: 1 }}>
        {value != null ? `${(value * 100).toFixed(0)}%` : '—'}
      </div>
      <div style={{ fontFamily: 'var(--font-body)', fontSize: 10, color: 'var(--text-muted)', marginTop: 3, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
        {label}
      </div>
    </div>
  );
}

function AnimNumber({ value, decimals = 1, suffix = '%', delay = 0 }) {
  const v = useCountUp(value, 900, delay);
  return <>{v.toFixed(decimals)}{suffix}</>;
}

function HeroCard({ team, sim, label, isChampion, onClick }) {
  const [hov, setHov] = useState(false);
  const natColor = nc(team);

  /* Card backgrounds: very dark tint matching team identity */
  const bg = isChampion ? '#0a1a10' : '#1a0a0a';
  const borderColor = isChampion
    ? 'rgba(201,168,76,0.3)'
    : 'rgba(192,57,43,0.3)';
  const winColor = isChampion ? 'var(--gold)' : 'var(--red)';
  const group = TEAM_GROUP[team] ?? '?';

  return (
    <div
      role="button" tabIndex={0}
      aria-label={`View ${team} profile`}
      onClick={() => onClick(team)}
      onKeyDown={(e) => e.key === 'Enter' && onClick(team)}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        flex: 1,
        minWidth: 260,
        background: hov ? (isChampion ? '#0d2015' : '#200d0d') : bg,
        border: `1px solid ${borderColor}`,
        borderRadius: 8,
        padding: 28,
        cursor: 'pointer',
        transition: 'background var(--t)',
        outline: 'none',
      }}
    >
      {/* Top row: trophy + label */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        {isChampion
          ? <TrophyIcon size={16} color="var(--gold)" />
          : <div style={{ width: 16 }} />
        }
        <span style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.15em' }}>
          {label}
        </span>
      </div>

      {/* Flag + group */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
        <span style={{ fontSize: 40, lineHeight: 1 }}>{flag(team)}</span>
        <span style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: '#444', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
          Group {group}
        </span>
      </div>

      {/* Team name */}
      <div style={{ fontFamily: 'var(--font-heading)', fontSize: 72, color: 'var(--text)', lineHeight: 0.9, marginBottom: 16, letterSpacing: '0.01em' }}>
        {team.toUpperCase()}
      </div>

      {/* Win probability */}
      <div style={{ marginBottom: 4 }}>
        <div style={{ fontFamily: 'var(--font-heading)', fontSize: 56, color: winColor, lineHeight: 1, letterSpacing: '0.01em' }}>
          {sim ? <AnimNumber value={sim.win_probability * 100} delay={isChampion ? 100 : 250} /> : '—%'}
        </div>
        <div style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em', marginTop: 2 }}>
          Win Probability
        </div>
      </div>

      {/* Divider */}
      <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', margin: '20px 0' }} />

      {/* Three stats */}
      {sim && (
        <div style={{ display: 'flex', justifyContent: 'space-around' }}>
          <StatPill label="Final"  value={sim.final_probability} />
          <StatPill label="Semi"   value={sim.semifinal_probability} />
          <StatPill label="QF"     value={sim.quarterfinal_probability} />
        </div>
      )}
    </div>
  );
}

function CenterVS() {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      padding: '0 12px', flexShrink: 0, gap: 10,
    }}>
      <img src="/wc2026.svg" height="28" alt="WC 2026" />
      <span style={{ fontFamily: 'var(--font-heading)', fontSize: 48, color: 'var(--gold)', lineHeight: 1 }}>
        VS
      </span>
    </div>
  );
}

export default function HeroSection({ onTeamClick }) {
  const [sim, setSim] = useState(null);

  useEffect(() => { api.simResults().then(setSim).catch(() => {}); }, []);

  if (!sim) return (
    <div style={{ minHeight: 280, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <span style={{ fontFamily: 'var(--font-body)', color: '#444', fontSize: 13 }}>Loading predictions…</span>
    </div>
  );

  const teams = sim.teams ?? [];
  if (teams.length < 2) return null;

  return (
    <div>
      <p className="section-label">
        Monte Carlo Predictions · {sim.simulations_run?.toLocaleString()} simulations
      </p>
      <div style={{ display: 'flex', gap: 0, alignItems: 'stretch' }}>
        <HeroCard team={teams[0].team} sim={teams[0]} label="Predicted Champion" isChampion={true}  onClick={onTeamClick} />
        <CenterVS />
        <HeroCard team={teams[1].team} sim={teams[1]} label="Predicted Finalist"  isChampion={false} onClick={onTeamClick} />
      </div>
    </div>
  );
}
