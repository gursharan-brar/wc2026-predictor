import { useState, useEffect } from 'react';
import { api } from '../utils/api';
import { flag } from '../utils/flags';
import { nc, colorGlow } from '../utils/nationalColors';
import { useCountUp } from '../hooks/useCountUp';

/* ─── TROPHY SVG ────────────────────────────────────────────────────────── */
function Trophy({ size = 52 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 48" fill="none" aria-hidden="true">
      {/* Cup body */}
      <path d="M8 4h24v16c0 8.837-5.373 14-12 14S8 28.837 8 20V4z"
            fill="var(--gold)" opacity="0.9"/>
      {/* Left handle */}
      <path d="M4 4h4v10c0 2.209-1.343 4-3 4A1 1 0 014 17V4z"
            fill="var(--gold)" opacity="0.55"/>
      {/* Right handle */}
      <path d="M32 4h4v13a1 1 0 01-1 1c-1.657 0-3-1.791-3-4V4z"
            fill="var(--gold)" opacity="0.55"/>
      {/* Stem */}
      <rect x="18" y="34" width="4" height="8" fill="var(--gold)" opacity="0.8"/>
      {/* Base */}
      <rect x="11" y="42" width="18" height="4" rx="2" fill="var(--gold)"/>
      {/* Shine */}
      <path d="M14 8c0-1 1-2 2-2v14c-1 0-2-4-2-12z"
            fill="white" opacity="0.15"/>
    </svg>
  );
}

/* ─── COUNT-UP NUMBER ───────────────────────────────────────────────────── */
function AnimatedPct({ value, color, size = 52, delay = 0 }) {
  const animated = useCountUp(value * 100, 900, delay);
  return (
    <span style={{
      fontFamily: 'var(--font-heading)',
      fontSize: size,
      fontWeight: 800,
      color,
      lineHeight: 1,
      display: 'block',
      letterSpacing: '-0.02em',
    }}>
      {animated.toFixed(1)}%
    </span>
  );
}

/* ─── STAGE PATH ────────────────────────────────────────────────────────── */
function StagePath({ group }) {
  const stages = [`GRP ${group}`, 'R32', 'R16', 'QF', 'SF', 'FINAL'];
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 0,
      flexWrap: 'wrap', rowGap: 4,
    }}>
      {stages.map((s, i) => (
        <span key={s} style={{ display: 'flex', alignItems: 'center' }}>
          <span style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            color: 'var(--gold)',
            fontWeight: 700,
            letterSpacing: '0.06em',
          }}>{s}</span>
          {i < stages.length - 1 && (
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 9,
              color: 'var(--c-text-dim)', margin: '0 4px',
            }}>→</span>
          )}
        </span>
      ))}
    </div>
  );
}

/* ─── HERO CARD ─────────────────────────────────────────────────────────── */
function HeroCard({ team, label, sim, rank = 1, onTeamClick }) {
  const [hovered, setHovered] = useState(false);
  const color = nc(team);
  const isChampion = rank === 1;

  // Tinted background: mix national color at low opacity
  const bgStyle = {
    background: `linear-gradient(135deg, #0a0a0a 0%, color-mix(in srgb, ${color} 12%, #0a0a0a) 100%)`,
  };

  const borderColor = isChampion ? 'var(--gold)' : color;
  const probColor   = isChampion ? 'var(--gold-light)' : color;

  const cardStyle = {
    ...bgStyle,
    flex: 1,
    minWidth: 260,
    border: `1px solid ${hovered ? borderColor : isChampion ? 'rgba(212,175,55,0.45)' : `${color}55`}`,
    borderRadius: 'var(--r-card)',
    padding: '32px 28px 28px',
    cursor: 'pointer',
    position: 'relative',
    overflow: 'hidden',
    transition: 'border-color var(--t), box-shadow var(--t)',
    boxShadow: hovered
      ? isChampion
        ? `0 0 48px rgba(212,175,55,0.35), 0 0 12px rgba(212,175,55,0.2)`
        : colorGlow(team, 0.3)
      : isChampion
        ? `0 0 24px rgba(212,175,55,0.15)`
        : `0 0 16px ${color}22`,
  };

  // Subtle radial glow behind team name
  const glowStyle = {
    position: 'absolute',
    top: 0, left: 0, right: 0, bottom: 0,
    background: `radial-gradient(ellipse at 50% 30%, ${color}18 0%, transparent 65%)`,
    pointerEvents: 'none',
  };

  const group = sim?.r32_probability != null ? '?' : '?';

  return (
    <div
      style={cardStyle}
      onClick={() => onTeamClick(team)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      role="button"
      tabIndex={0}
      aria-label={`View ${team} profile`}
      onKeyDown={(e) => e.key === 'Enter' && onTeamClick(team)}
    >
      <div style={glowStyle} />

      {/* Label */}
      <div style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 10, fontWeight: 700,
        color: isChampion ? 'var(--gold)' : color,
        textTransform: 'uppercase',
        letterSpacing: '0.14em',
        marginBottom: 20,
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        {isChampion && <Trophy size={16} />}
        {label}
      </div>

      {/* Flag */}
      <div style={{ fontSize: 56, lineHeight: 1, marginBottom: 14 }}>
        {flag(team)}
      </div>

      {/* Team name */}
      <div style={{
        fontFamily: 'var(--font-heading)',
        fontSize: 46,
        fontWeight: 800,
        color: 'var(--c-text)',
        lineHeight: 0.95,
        letterSpacing: '-0.02em',
        marginBottom: 16,
        textTransform: 'uppercase',
      }}>
        {team}
      </div>

      {/* Win probability */}
      <div style={{ marginBottom: 8 }}>
        <AnimatedPct
          value={sim?.win_probability ?? 0}
          color={probColor}
          size={44}
          delay={rank === 1 ? 100 : 250}
        />
        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          color: 'var(--c-text-muted)',
          textTransform: 'uppercase',
          letterSpacing: '0.1em',
          display: 'block',
          marginTop: 4,
        }}>
          Win Probability
        </span>
      </div>

      {/* Secondary stats */}
      <div style={{
        display: 'flex', gap: 20, marginTop: 16,
        paddingTop: 16,
        borderTop: `1px solid ${isChampion ? 'var(--gold-divider)' : `${color}22`}`,
      }}>
        {[
          ['Final', sim?.final_probability],
          ['Semi', sim?.semifinal_probability],
          ['QF', sim?.quarterfinal_probability],
        ].map(([lbl, val]) => (
          <div key={lbl}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 700, color: 'var(--c-text)' }}>
              {val != null ? `${(val * 100).toFixed(0)}%` : '—'}
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--c-text-dim)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              {lbl}
            </div>
          </div>
        ))}
      </div>

      {/* Path */}
      <div style={{ marginTop: 16 }}>
        <StagePath group="?" />
      </div>

      {/* Corner accent for champion */}
      {isChampion && (
        <div style={{
          position: 'absolute', top: 12, right: 14,
          fontFamily: 'var(--font-mono)', fontSize: 9,
          color: 'var(--gold)', letterSpacing: '0.1em',
          opacity: 0.7,
        }}>
          #1 RANKED
        </div>
      )}
    </div>
  );
}

/* ─── CENTER VS ─────────────────────────────────────────────────────────── */
function CenterVS() {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      gap: 12, padding: '0 8px', flexShrink: 0,
    }}>
      <Trophy size={48} />
      <div style={{
        fontFamily: 'var(--font-heading)',
        fontSize: 36,
        fontWeight: 800,
        color: 'var(--gold)',
        letterSpacing: '0.04em',
        lineHeight: 1,
        textShadow: '0 0 24px rgba(212,175,55,0.5)',
      }}>
        VS
      </div>
      <div style={{
        width: 1, height: 80,
        background: 'linear-gradient(to bottom, transparent, var(--gold-divider), transparent)',
      }} />
    </div>
  );
}

/* ─── MAIN COMPONENT ─────────────────────────────────────────────────────── */
export default function HeroSection({ onTeamClick }) {
  const [simData, setSimData] = useState(null);

  useEffect(() => {
    api.simResults().then(setSimData).catch(() => {});
  }, []);

  if (!simData) {
    return (
      <div style={{
        minHeight: 300, display: 'flex', alignItems: 'center',
        justifyContent: 'center',
      }}>
        <span style={{ color: 'var(--c-text-dim)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
          Loading predictions…
        </span>
      </div>
    );
  }

  const teams = simData.teams ?? [];
  const champion = teams[0];
  const finalist  = teams[1];

  if (!champion || !finalist) return null;

  return (
    <div className="fade-up" style={{ marginBottom: 8 }}>
      {/* Section label */}
      <div className="section-label" style={{ marginBottom: 20 }}>
        Monte Carlo Predictions · {simData.simulations_run?.toLocaleString()} simulations
      </div>

      {/* Hero cards */}
      <div style={{
        display: 'flex',
        gap: 0,
        alignItems: 'stretch',
      }}>
        <HeroCard
          team={champion.team}
          label="Predicted Champion"
          sim={champion}
          rank={1}
          onTeamClick={onTeamClick}
        />
        <CenterVS />
        <HeroCard
          team={finalist.team}
          label="Predicted Finalist"
          sim={finalist}
          rank={2}
          onTeamClick={onTeamClick}
        />
      </div>
    </div>
  );
}
