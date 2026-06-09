import { useCountUp } from '../hooks/useCountUp';

function BigNum({ target, decimals = 1, suffix = '', delay = 0 }) {
  const v = useCountUp(target, 900, delay);
  return <>{v.toFixed(decimals)}{suffix}</>;
}

export default function ModelAccuracy() {
  return (
    <div style={{
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderTop: '2px solid var(--gold)',
      borderRadius: 6,
      padding: 24,
    }}>
      <p style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.12em', marginBottom: 16 }}>
        Model Accuracy
      </p>

      {/* Big accuracy number */}
      <div style={{ fontFamily: 'var(--font-heading)', fontSize: 48, color: 'var(--gold)', lineHeight: 1, marginBottom: 4 }}>
        <BigNum target={64.4} delay={0} />%
      </div>
      <p style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: '#444', marginBottom: 20 }}>
        5-fold cross-validation
      </p>

      {/* Stats */}
      {[
        { label: 'Training matches', value: 32290, fmt: (v) => Math.round(v).toLocaleString() },
        { label: 'Simulations',      value: 10000, fmt: (v) => Math.round(v).toLocaleString() },
      ].map(({ label, value, fmt }) => (
        <div key={label} style={{
          display: 'flex', justifyContent: 'space-between',
          padding: '8px 0', borderBottom: '1px solid var(--border)',
        }}>
          <span style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--text-muted)' }}>{label}</span>
          <span style={{ fontFamily: 'var(--font-heading)', fontSize: 16, color: 'var(--text)' }}>
            {fmt(value)}
          </span>
        </div>
      ))}

      <div style={{ marginTop: 16, fontFamily: 'var(--font-body)', fontSize: 12, color: '#444', lineHeight: 1.6 }}>
        XGBoost trained on 87 features per match — club form, tournament history,
        StatsBomb event data, and squad market value.
      </div>
    </div>
  );
}
