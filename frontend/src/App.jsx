import { useState } from 'react';
import StatsBar              from './components/StatsBar';
import HeroSection           from './components/HeroSection';
import TopContenders         from './components/TopContenders';
import BracketPath           from './components/BracketPath';
import ModelAccuracy         from './components/ModelAccuracy';
import PredictionLeaderboard from './components/PredictionLeaderboard';
import TeamProfile           from './components/TeamProfile';
import BracketView           from './components/BracketView';
import SimulationRunner      from './components/SimulationRunner';

/* ─── NAV ───────────────────────────────────────────────────────────────── */
const TABS = [
  { id: 'leaderboard', label: 'Predictions' },
  { id: 'bracket',     label: 'Groups'      },
  { id: 'simulate',    label: 'Simulate'    },
];

export default function App() {
  const [view,         setView]         = useState('leaderboard');
  const [selectedTeam, setSelectedTeam] = useState(null);
  const [prevView,     setPrevView]     = useState('leaderboard');

  function openTeam(name) {
    setPrevView(view === 'team' ? prevView : view);
    setSelectedTeam(name);
    setView('team');
  }

  function goBack() {
    setSelectedTeam(null);
    setView(prevView);
  }

  function switchTab(id) {
    setSelectedTeam(null);
    setView(id);
  }

  const activeTab = view === 'team' ? prevView : view;

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>

      {/* ── Header ───────────────────────────────────────────────── */}
      <header style={{
        position: 'sticky', top: 0, zIndex: 100,
        background: 'rgba(10,10,10,0.95)',
        backdropFilter: 'blur(12px)',
        borderBottom: '1px solid var(--c-border)',
      }}>
        {/* Top gold accent line */}
        <div style={{ height: 2, background: 'linear-gradient(90deg, transparent, var(--gold), var(--gold-light), var(--gold), transparent)' }} />

        <div style={{
          maxWidth: 1320, margin: '0 auto', padding: '0 24px',
          display: 'flex', alignItems: 'center', height: 52, gap: 24,
        }}>
          {/* Wordmark */}
          <div style={{
            fontFamily: 'var(--font-heading)',
            fontSize: 14, fontWeight: 800,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            display: 'flex', alignItems: 'center', gap: 8,
            flexShrink: 0,
          }}>
            <span style={{ fontSize: 18 }}>⚽</span>
            <span style={{ color: 'var(--gold)' }}>WC 2026</span>
            <span style={{ color: 'var(--c-text-dim)', fontWeight: 400 }}>/</span>
            <span style={{ color: 'var(--c-text-muted)' }}>PREDICTOR</span>
          </div>

          {/* Nav */}
          <nav role="navigation" aria-label="Main navigation" style={{ display: 'flex', gap: 2 }}>
            {TABS.map((t) => {
              const active = activeTab === t.id;
              return (
                <button
                  key={t.id}
                  onClick={() => switchTab(t.id)}
                  aria-current={active ? 'page' : undefined}
                  style={{
                    padding: '6px 16px',
                    border: 'none',
                    borderBottom: active ? '2px solid var(--gold)' : '2px solid transparent',
                    borderRadius: 0,
                    background: active ? 'var(--gold-dim)' : 'transparent',
                    color: active ? 'var(--gold)' : 'var(--c-text-muted)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11, fontWeight: active ? 700 : 400,
                    letterSpacing: '0.07em',
                    textTransform: 'uppercase',
                    cursor: 'pointer',
                    transition: 'all var(--t)',
                    minHeight: 36,
                  }}
                  onMouseEnter={(e) => { if (!active) e.target.style.color = 'var(--c-text)'; }}
                  onMouseLeave={(e) => { if (!active) e.target.style.color = 'var(--c-text-muted)'; }}
                >
                  {t.label}
                </button>
              );
            })}
          </nav>

          {/* Byline */}
          <div style={{
            marginLeft: 'auto',
            fontFamily: 'var(--font-mono)', fontSize: 10,
            color: 'var(--c-text-dim)', letterSpacing: '0.06em',
            whiteSpace: 'nowrap',
          }}>
            by Gursharan Singh Brar
          </div>
        </div>
      </header>

      {/* ── Stats strip ────────────────────────────────────────────── */}
      <StatsBar />

      {/* ── Main ───────────────────────────────────────────────────── */}
      <main style={{
        flex: 1,
        maxWidth: 1320, margin: '0 auto',
        padding: '28px 24px',
        width: '100%',
      }}>

        {/* PREDICTIONS TAB */}
        {view === 'leaderboard' && (
          <div>
            {/* Hero champion vs finalist */}
            <HeroSection onTeamClick={openTeam} />

            <hr className="gold-divider" />

            {/* Three-panel mid section */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr 300px',
              gap: 24,
              marginBottom: 8,
              alignItems: 'start',
            }}>
              <TopContenders onTeamClick={openTeam} />
              <BracketPath   onTeamClick={openTeam} />
              <ModelAccuracy />
            </div>

            <hr className="gold-divider" />

            {/* Full leaderboard */}
            <PredictionLeaderboard onTeamClick={openTeam} />
          </div>
        )}

        {/* GROUPS TAB */}
        {view === 'bracket' && <BracketView onTeamClick={openTeam} />}

        {/* SIMULATE TAB */}
        {view === 'simulate' && <SimulationRunner />}

        {/* TEAM PROFILE */}
        {view === 'team' && (
          <TeamProfile key={selectedTeam} team={selectedTeam} onBack={goBack} />
        )}
      </main>

      {/* ── Footer ─────────────────────────────────────────────────── */}
      <footer style={{
        borderTop: '1px solid var(--c-border)',
        padding: '12px 24px',
        maxWidth: 1320, margin: '0 auto', width: '100%',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        flexWrap: 'wrap', gap: 8,
      }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--c-text-dim)' }}>
          WC 2026 PREDICTOR · XGBOOST · MONTE CARLO · 10,000 SIMULATIONS
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--gold)', letterSpacing: '0.06em' }}>
          GURSHARAN SINGH BRAR · {new Date().getFullYear()}
        </span>
      </footer>
    </div>
  );
}
