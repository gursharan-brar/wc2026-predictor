import { useState, useEffect, useRef } from 'react';
import { api, API_BASE } from '../utils/api';
import { flag } from '../utils/flags';
import { nc } from '../utils/nationalColors';

export default function SimulationRunner() {
  const [status,   setStatus]   = useState('idle');
  const [log,      setLog]      = useState([]);
  const [results,  setResults]  = useState(null);
  const [progress, setProgress] = useState(0);
  const [elapsed,  setElapsed]  = useState(0);
  const esRef    = useRef(null);
  const logRef   = useRef(null);
  const timerRef = useRef(null);
  const t0       = useRef(null);

  useEffect(() => {
    api.simResults().then(setResults).catch(() => {});
  }, []);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [log]);

  useEffect(() => () => {
    esRef.current?.close();
    clearInterval(timerRef.current);
  }, []);

  const addLog = (text, type = 'info') =>
    setLog((p) => [...p, { text, type }]);

  const parseProgress = (line) => {
    const m = line.match(/(\d+)%/);
    return m ? parseInt(m[1], 10) : null;
  };

  function startSimulation() {
    esRef.current?.close();
    clearInterval(timerRef.current);
    setStatus('running');
    setLog([]);
    setProgress(0);
    setElapsed(0);
    t0.current = Date.now();

    timerRef.current = setInterval(() =>
      setElapsed(Math.floor((Date.now() - t0.current) / 1000)), 1000);

    addLog('▶ Connecting to simulation engine…', 'gold');

    const es = new EventSource(`${API_BASE}/simulate`);
    esRef.current = es;

    es.addEventListener('start',    (e) => addLog(`▶ ${JSON.parse(e.data).message}`, 'gold'));
    es.addEventListener('warning',  (e) => { const l = JSON.parse(e.data).line; if (l) addLog(`⚠ ${l}`, 'warn'); });
    es.addEventListener('progress', (e) => {
      const { line } = JSON.parse(e.data);
      if (!line) return;
      const p = parseProgress(line);
      if (p !== null) setProgress(p);
      addLog(line, 'info');
    });
    es.addEventListener('done', (e) => {
      const d = JSON.parse(e.data);
      clearInterval(timerRef.current);
      es.close(); esRef.current = null;
      if (d.success) {
        setProgress(100); setStatus('done'); setResults(d.results);
        addLog('✓ Simulation complete', 'gold');
      } else {
        setStatus('error');
        addLog(`✗ ${d.error}`, 'error');
      }
    });
    es.onerror = () => {
      clearInterval(timerRef.current);
      setStatus('error');
      addLog('✗ Connection lost — is the API running?', 'error');
      es.close();
    };
  }

  function cancelSimulation() {
    esRef.current?.close(); esRef.current = null;
    clearInterval(timerRef.current);
    setStatus('idle');
    addLog('— Cancelled', 'dim');
  }

  const top5 = results?.teams?.slice(0, 5) ?? [];

  const logColors = {
    gold:  'var(--gold)',
    info:  'var(--c-text-muted)',
    dim:   'var(--c-text-dim)',
    warn:  'var(--c-yellow)',
    error: 'var(--c-red)',
  };

  return (
    <div className="fade-up">
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <div className="section-label" style={{ marginBottom: 8 }}>
          Monte Carlo Simulator
        </div>
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--c-text-muted)' }}>
          Re-runs 10,000 complete World Cup simulations · streams live progress · updates all win probabilities
        </p>
      </div>

      {/* Control bar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
        padding: '14px 16px',
        background: 'var(--c-surface)',
        border: '1px solid var(--c-border)',
        borderTop: '2px solid var(--gold-border)',
        borderRadius: 'var(--r-card)',
        marginBottom: 16,
      }}>
        <button
          className={`btn ${status !== 'running' ? 'btn-gold' : ''}`}
          onClick={startSimulation}
          disabled={status === 'running'}
          style={{ minWidth: 148 }}
        >
          {status === 'running' ? '⟳ RUNNING…'
           : status === 'done'  ? '↺ RE-SIMULATE'
           : '▶ RUN SIMULATION'}
        </button>

        {status === 'running' && (
          <button className="btn" onClick={cancelSimulation}>■ CANCEL</button>
        )}

        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--c-text-muted)' }}>
          {status === 'running' && `${elapsed}s · ${progress}%`}
          {status === 'done'    && <span style={{ color: 'var(--gold)' }}>✓ Done in {elapsed}s</span>}
          {status === 'error'   && <span style={{ color: 'var(--c-red)' }}>✗ Failed</span>}
        </span>

        <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
          {['10,000 SIMS', '48 TEAMS', '~104 MATCHES/RUN'].map((t) => (
            <span key={t} className="chip">{t}</span>
          ))}
        </div>
      </div>

      {/* Progress bar */}
      {(status === 'running' || status === 'done') && (
        <div style={{
          height: 2, background: 'var(--c-raised)',
          marginBottom: 16, borderRadius: 1, overflow: 'hidden',
        }}>
          <div style={{
            height: '100%',
            width: `${progress}%`,
            background: 'linear-gradient(90deg, var(--gold) 0%, var(--gold-light) 100%)',
            transition: 'width 0.4s ease',
            boxShadow: '0 0 10px var(--gold-glow)',
          }} />
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: 16, alignItems: 'start' }}>
        {/* Terminal log */}
        <div style={{
          background: '#050505',
          border: '1px solid var(--c-border)',
          borderRadius: 'var(--r-card)',
          overflow: 'hidden',
        }}>
          <div style={{
            padding: '8px 14px',
            borderBottom: '1px solid var(--c-border)',
            background: 'var(--c-raised)',
            display: 'flex', alignItems: 'center', gap: 8,
          }}>
            <div style={{
              width: 8, height: 8, borderRadius: '50%',
              background: status === 'running' ? 'var(--gold)' : 'var(--c-text-dim)',
              boxShadow: status === 'running' ? '0 0 8px var(--gold-glow)' : 'none',
              transition: 'background var(--t), box-shadow var(--t)',
            }} />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--c-text-dim)' }}>
              simulation.log
            </span>
            {status === 'running' && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--gold)', marginLeft: 4, animation: 'shimmer 1.5s ease infinite' }}>
                LIVE
              </span>
            )}
          </div>

          <div
            ref={logRef}
            style={{
              fontFamily: 'var(--font-mono)', fontSize: 11, lineHeight: 1.75,
              padding: '12px 16px', height: 400, overflowY: 'auto',
              background: '#050505',
            }}
            aria-live="polite"
            aria-label="Simulation progress log"
          >
            {log.length === 0 ? (
              <div style={{ color: 'var(--c-text-dim)' }}>
                <div>{'>'} Press RUN SIMULATION to start</div>
                <div>{'>'} Progress streams here in real-time</div>
                <div>{'>'} Completes in ~30 seconds</div>
              </div>
            ) : (
              log.map((e, i) => (
                <div key={i} style={{ color: logColors[e.type] ?? 'var(--c-text-muted)' }}>
                  {e.text}
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right: top 5 cards */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 9, fontWeight: 700,
            color: 'var(--gold)', textTransform: 'uppercase', letterSpacing: '0.12em',
            marginBottom: 4,
          }}>
            Current Top 5
          </div>

          {top5.length === 0 ? (
            <div style={{
              padding: 20, background: 'var(--c-surface)',
              border: '1px solid var(--c-border)', borderRadius: 'var(--r-card)',
              fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--c-text-dim)',
            }}>
              Run simulation to see results
            </div>
          ) : (
            top5.map((t, i) => {
              const color = nc(t.team);
              return (
                <div key={t.team} style={{
                  display: 'grid', gridTemplateColumns: '20px 26px 1fr 52px',
                  alignItems: 'center', gap: 8,
                  padding: '10px 12px',
                  background: 'var(--c-surface)',
                  border: `1px solid ${color}28`,
                  borderLeft: `3px solid ${color}`,
                  borderRadius: 'var(--r-card)',
                }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--c-text-dim)' }}>
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <span style={{ fontSize: 16, lineHeight: 1 }}>{flag(t.team)}</span>
                  <div>
                    <div style={{ fontFamily: 'var(--font-heading)', fontSize: 12, fontWeight: 800, color: 'var(--c-text)', textTransform: 'uppercase' }}>
                      {t.team}
                    </div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--c-text-dim)', marginTop: 1 }}>
                      Final {(t.final_probability * 100).toFixed(0)}%
                    </div>
                  </div>
                  <span style={{ fontFamily: 'var(--font-heading)', fontSize: 16, fontWeight: 800, color: 'var(--gold-light)', textAlign: 'right' }}>
                    {(t.win_probability * 100).toFixed(1)}%
                  </span>
                </div>
              );
            })
          )}

          {results && (
            <div style={{
              marginTop: 4, padding: '10px 12px',
              background: 'var(--c-surface)', border: '1px solid var(--c-border)',
              borderRadius: 'var(--r-card)',
              fontFamily: 'var(--font-mono)', fontSize: 9,
              color: 'var(--c-text-dim)', lineHeight: 1.9,
            }}>
              <div>SIMS: <span style={{ color: 'var(--gold)' }}>{results.simulations_run?.toLocaleString()}</span></div>
              <div>TEAMS: <span style={{ color: 'var(--c-text)' }}>{results.teams?.length}</span></div>
              <div>UPDATED: <span style={{ color: 'var(--c-text)' }}>
                {results.generated_at ? new Date(results.generated_at).toLocaleString() : '—'}
              </span></div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
