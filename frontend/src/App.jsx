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

const TABS = [
  { id: 'leaderboard', label: 'Predictions' },
  { id: 'bracket',     label: 'Groups'      },
  { id: 'simulate',    label: 'Simulate'    },
];

const W = { maxWidth: 1200, margin: '0 auto', padding: '0 24px', width: '100%' };

export default function App() {
  const [view,         setView]         = useState('leaderboard');
  const [selectedTeam, setSelectedTeam] = useState(null);
  const [prevView,     setPrevView]     = useState('leaderboard');

  const openTeam = (name) => { setPrevView(view === 'team' ? prevView : view); setSelectedTeam(name); setView('team'); };
  const goBack   = ()     => { setSelectedTeam(null); setView(prevView); };
  const switchTab = (id)  => { setSelectedTeam(null); setView(id); };

  const activeTab = view === 'team' ? prevView : view;

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg)' }}>

      {/* ── Header ─────────────────────────────────────────── */}
      <header style={{
        position: 'sticky', top: 0, zIndex: 100,
        background: 'rgba(13,13,13,0.97)',
        backdropFilter: 'blur(8px)',
        borderBottom: '1px solid var(--border)',
      }}>
        <div style={{ ...W, display: 'flex', alignItems: 'center', height: 56, gap: 32 }}>

          {/* Logo */}
          <img src="/wc2026.svg" height="32" alt="WC 2026" style={{ flexShrink: 0 }} />

          {/* Nav */}
          <nav style={{ display: 'flex', gap: 0 }} role="navigation" aria-label="Main navigation">
            {TABS.map((t) => {
              const active = activeTab === t.id;
              return (
                <button
                  key={t.id}
                  onClick={() => switchTab(t.id)}
                  aria-current={active ? 'page' : undefined}
                  style={{
                    padding: '0 20px',
                    height: 56,
                    border: 'none',
                    borderBottom: active ? '2px solid var(--gold)' : '2px solid transparent',
                    background: 'transparent',
                    color: active ? 'var(--text)' : 'var(--text-muted)',
                    fontFamily: 'var(--font-body)',
                    fontSize: 13,
                    fontWeight: 500,
                    letterSpacing: '0.04em',
                    textTransform: 'uppercase',
                    cursor: 'pointer',
                    transition: 'color var(--t), border-color var(--t)',
                  }}
                  onMouseEnter={(e) => { if (!active) e.target.style.color = 'var(--text)'; }}
                  onMouseLeave={(e) => { if (!active) e.target.style.color = 'var(--text-muted)'; }}
                >
                  {t.label}
                </button>
              );
            })}
          </nav>

          <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-body)', fontSize: 11, color: '#444' }}>
            Gursharan Singh Brar
          </span>
        </div>
      </header>

      {/* ── Stats bar ───────────────────────────────────────── */}
      <StatsBar />

      {/* ── Main ────────────────────────────────────────────── */}
      <main style={{ flex: 1, ...W, padding: '40px 24px' }}>

        {view === 'leaderboard' && (
          <div className="fade-up">
            <HeroSection onTeamClick={openTeam} />
            <hr className="divider" />
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 280px', gap: 24, marginBottom: 40 }}>
              <TopContenders onTeamClick={openTeam} />
              <BracketPath   onTeamClick={openTeam} />
              <ModelAccuracy />
            </div>
            <hr className="divider" />
            <PredictionLeaderboard onTeamClick={openTeam} />
          </div>
        )}

        {view === 'bracket'  && <BracketView    onTeamClick={openTeam} />}
        {view === 'simulate' && <SimulationRunner />}
        {view === 'team'     && <TeamProfile key={selectedTeam} team={selectedTeam} onBack={goBack} />}
      </main>

      {/* ── Footer ──────────────────────────────────────────── */}
      <footer style={{
        borderTop: '1px solid var(--border)',
        padding: '16px 24px',
        ...W,
        display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8,
      }}>
        <span style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: '#444' }}>
          WC 2026 Predictor · XGBoost · Monte Carlo · 10,000 simulations
        </span>
        <span style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: '#444' }}>
          Gursharan Singh Brar · {new Date().getFullYear()}
        </span>
      </footer>
    </div>
  );
}
