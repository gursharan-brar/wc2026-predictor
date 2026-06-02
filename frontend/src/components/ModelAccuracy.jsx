import { useCountUp } from '../hooks/useCountUp';

const STATS = [
  { label: 'Training matches',  value: 32290,  suffix: '',   prefix: '',   decimals: 0, gold: false },
  { label: 'CV Accuracy',       value: 57.69,  suffix: '%',  prefix: '',   decimals: 1, gold: true  },
  { label: 'Model',             value: null,   display: 'XGBoost',         gold: false },
  { label: 'Simulations',       value: 10000,  suffix: '',   prefix: '',   decimals: 0, gold: false },
];

function BigStat({ label, value, suffix = '', decimals = 0, gold, display, delay = 0 }) {
  const animated = useCountUp(value ?? 0, 900, delay);
  const shown = display ?? (
    value != null
      ? `${animated.toFixed(decimals)}${suffix}`
      : '—'
  );

  return (
    <div style={{
      padding: '14px 0',
      borderBottom: '1px solid var(--c-border)',
    }}>
      <div style={{
        fontFamily: 'var(--font-heading)',
        fontSize: display ? 22 : 28,
        fontWeight: 800,
        color: gold ? 'var(--gold-light)' : 'var(--c-text)',
        lineHeight: 1,
        marginBottom: 4,
        letterSpacing: display ? '0.04em' : '-0.01em',
      }}>
        {shown}
      </div>
      <div style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 10,
        color: 'var(--c-text-dim)',
        textTransform: 'uppercase',
        letterSpacing: '0.09em',
      }}>
        {label}
      </div>
    </div>
  );
}

export default function ModelAccuracy() {
  return (
    <div style={{
      background: '#0a0a0a',
      border: '1px solid var(--c-border)',
      borderRadius: 'var(--r-card)',
      borderTop: '3px solid var(--gold)',
      padding: '20px',
      height: '100%',
    }}>
      {/* Header */}
      <div style={{ marginBottom: 16 }}>
        <div style={{
          fontFamily: 'var(--font-heading)', fontSize: 14, fontWeight: 800,
          color: 'var(--c-text)', textTransform: 'uppercase',
          letterSpacing: '0.06em', marginBottom: 6,
        }}>
          Model Accuracy
        </div>
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 10,
          color: 'var(--c-text-muted)', lineHeight: 1.6,
        }}>
          XGBoost classifier trained on international football results.
          Each match is predicted as home win, draw, or away win using 24
          features derived from team stats, big-game performance, and
          World Cup history.
        </div>
      </div>

      {/* Stats */}
      <div>
        {STATS.map((s, i) => (
          <BigStat key={s.label} {...s} delay={i * 80} />
        ))}
      </div>

      {/* Footer note */}
      <div style={{
        marginTop: 14,
        fontFamily: 'var(--font-mono)', fontSize: 10,
        color: 'var(--c-text-dim)', lineHeight: 1.6,
      }}>
        <div style={{ color: 'var(--gold)', fontWeight: 700, marginBottom: 4 }}>
          HOW IT WORKS
        </div>
        5-fold cross-validation · 3-class classification · 24 engineered
        features including offensive/defensive strength, tournament experience
        decay, form momentum, and big-game win rate vs. top-20 ranked opponents.
        Win probabilities from 10,000 full-tournament Monte Carlo simulations.
      </div>
    </div>
  );
}
