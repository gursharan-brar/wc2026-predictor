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

  useEffect(() => { api.simResults().then(setResults).catch(() => {}); }, []);
  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, [log]);
  useEffect(() => () => { esRef.current?.close(); clearInterval(timerRef.current); }, []);

  const addLog = (text, type = 'info') => setLog((p) => [...p, { text, type }]);
  const parsePct = (line) => { const m = line.match(/(\d+)%/); return m ? parseInt(m[1]) : null; };

  function start() {
    esRef.current?.close(); clearInterval(timerRef.current);
    setStatus('running'); setLog([]); setProgress(0); setElapsed(0);
    t0.current = Date.now();
    timerRef.current = setInterval(() => setElapsed(Math.floor((Date.now() - t0.current) / 1000)), 1000);
    addLog('Starting simulation…', 'dim');
    const es = new EventSource(`${API_BASE}/simulate`);
    esRef.current = es;
    es.addEventListener('start',    (e) => addLog(JSON.parse(e.data).message, 'gold'));
    es.addEventListener('progress', (e) => { const { line } = JSON.parse(e.data); if (!line) return; const p = parsePct(line); if (p) setProgress(p); addLog(line, 'info'); });
    es.addEventListener('warning',  (e) => { const l = JSON.parse(e.data).line; if (l) addLog(`⚠ ${l}`, 'warn'); });
    es.addEventListener('done', (e) => {
      const d = JSON.parse(e.data); clearInterval(timerRef.current); es.close(); esRef.current = null;
      if (d.success) { setProgress(100); setStatus('done'); setResults(d.results); addLog('Simulation complete.', 'gold'); }
      else { setStatus('error'); addLog(`Error: ${d.error}`, 'error'); }
    });
    es.onerror = () => { clearInterval(timerRef.current); setStatus('error'); addLog('Connection lost.', 'error'); es.close(); };
  }

  function cancel() {
    esRef.current?.close(); esRef.current = null;
    clearInterval(timerRef.current); setStatus('idle'); addLog('Cancelled.', 'dim');
  }

  const top5 = results?.teams?.slice(0, 5) ?? [];
  const logColors = { gold: 'var(--gold)', info: '#666', dim: '#444', warn: '#c9a84c', error: '#c0392b' };

  return (
    <div className="fade-up">
      <p className="section-label">Monte Carlo Simulator</p>
      <p style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--text-muted)', marginBottom: 24 }}>
        Re-runs 10,000 complete World Cup simulations and updates all win probabilities.
      </p>

      {/* Control row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        <button className="btn-gold btn" onClick={start} disabled={status === 'running'}>
          {status === 'running' ? '⟳ Running…' : status === 'done' ? '↺ Re-simulate' : '▶ Run Simulation'}
        </button>
        {status === 'running' && <button className="btn" onClick={cancel}>■ Cancel</button>}

        <span style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--text-muted)' }}>
          {status === 'running' && `${elapsed}s · ${progress}%`}
          {status === 'done'    && <span style={{ color: 'var(--gold)' }}>Done in {elapsed}s</span>}
          {status === 'error'   && <span style={{ color: '#c0392b' }}>Failed — check log</span>}
        </span>

        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          {['10,000 SIMS', '48 TEAMS', '~104 MATCHES'].map((t) => (
            <span key={t} style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: '#444', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              {t}
            </span>
          ))}
        </div>
      </div>

      {/* Progress bar */}
      {(status === 'running' || status === 'done') && (
        <div style={{ height: 2, background: 'var(--surface-2)', borderRadius: 1, marginBottom: 20, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${progress}%`, background: 'var(--gold)', transition: 'width 0.4s ease' }} />
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: 16, alignItems: 'start' }}>
        {/* Terminal log */}
        <div style={{ background: '#0a0a0a', border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden' }}>
          <div style={{ padding: '8px 14px', background: 'var(--surface-2)', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 7, height: 7, borderRadius: '50%', background: status === 'running' ? '#3ecf8e' : '#333', transition: 'background var(--t)' }} />
            <span style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: '#444' }}>simulation.log</span>
          </div>
          <div ref={logRef} style={{ fontFamily: 'monospace', fontSize: 12, lineHeight: 1.7, padding: '12px 16px', height: 380, overflowY: 'auto' }} aria-live="polite">
            {log.length === 0
              ? <span style={{ color: '#333' }}>{'> Run simulation to see live output\n> Takes approximately 20 seconds'}</span>
              : log.map((e, i) => <div key={i} style={{ color: logColors[e.type] ?? '#666' }}>{e.text}</div>)
            }
          </div>
        </div>

        {/* Top 5 */}
        <div>
          <p style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: '#444', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 12 }}>
            Current Top 5
          </p>
          {top5.length === 0 ? (
            <div style={{ padding: 20, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 6, fontFamily: 'var(--font-body)', fontSize: 12, color: '#444' }}>
              Run simulation to see results
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {top5.map((t, i) => {
                const color = nc(t.team);
                return (
                  <div key={t.team} style={{ display: 'grid', gridTemplateColumns: '18px 22px 1fr 44px', alignItems: 'center', gap: 8, padding: '10px 12px', background: 'var(--surface)', border: '1px solid var(--border)', borderLeft: `3px solid ${color}`, borderRadius: 6 }}>
                    <span style={{ fontFamily: 'var(--font-body)', fontSize: 11, color: '#444' }}>{String(i + 1).padStart(2, '0')}</span>
                    <span style={{ fontSize: 16 }}>{flag(t.team)}</span>
                    <div>
                      <div style={{ fontFamily: 'var(--font-body)', fontSize: 12, fontWeight: 500, color: 'var(--text)' }}>{t.team}</div>
                      <div style={{ fontFamily: 'var(--font-body)', fontSize: 10, color: '#444' }}>Final {(t.final_probability * 100).toFixed(0)}%</div>
                    </div>
                    <span style={{ fontFamily: 'var(--font-heading)', fontSize: 18, color: 'var(--gold)', textAlign: 'right' }}>
                      {(t.win_probability * 100).toFixed(1)}%
                    </span>
                  </div>
                );
              })}
            </div>
          )}

          {results && (
            <div style={{ marginTop: 12, padding: '10px 12px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 6, fontFamily: 'var(--font-body)', fontSize: 11, color: '#444', lineHeight: 1.8 }}>
              <div>Sims: <span style={{ color: 'var(--text)' }}>{results.simulations_run?.toLocaleString()}</span></div>
              <div>Teams: <span style={{ color: 'var(--text)' }}>{results.teams?.length}</span></div>
              <div>Updated: <span style={{ color: 'var(--text)' }}>{results.generated_at ? new Date(results.generated_at).toLocaleString() : '—'}</span></div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
