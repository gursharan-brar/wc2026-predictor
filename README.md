# ⚽ WC 2026 Predictor

A live, self-updating World Cup 2026 prediction site powered by XGBoost and 10,000 Monte Carlo simulations.

**Author:** Gursharan Singh Brar  
**Live demo:** `https://your-username.github.io/predictor`  ← update after deploy  
**API endpoint:** `https://your-project.up.railway.app`    ← update after deploy

---

## What it does

- Scrapes live FIFA rankings and fetches recent match results via API-Football  
- Engineers 24 features per team including StatsBomb tournament performance, FBRef club form, and pre-computed squad metrics  
- Trains an XGBoost 3-class classifier (home win / draw / away win) on 32,000+ historical international matches  
- Runs 10,000 full-tournament Monte Carlo simulations across the official 48-team bracket  
- Serves win probabilities via an Express API backed by SQLite (sql.js — no native build needed)  
- React dashboard with national color themes, animated probability bars, and live simulation streaming

---

## Architecture

```
predictor/
├── wc2026_data_pipeline.py   Phase 1 — data ingestion (FIFA rankings + match results)
├── wc2026_features.py        Phase 2 — feature engineering (8 statistical features)
├── wc2026_model.py           Phase 3 — XGBoost training + 5-fold CV
├── wc2026_simulator.py       Phase 4 — Monte Carlo tournament simulator
├── wc2026_player_chain.py    Phase 7 — StatsBomb + FBRef player performance chain
├── api/
│   └── server.js             Phase 5 — Express API (sql.js, 6 endpoints)
├── frontend/
│   └── src/                  Phase 6 — React dashboard (Vite)
├── data/                     CSVs: results, rankings, squad features, StatsBomb output
├── wc2026.db                 SQLite database (committed — baseline data)
├── wc2026_model.pkl          Trained XGBoost model (committed — 24 features)
└── simulation_results.json   Latest 10,000-run results (committed — 48 teams)
```

---

## Local development

### Prerequisites

| Tool | Version |
|---|---|
| Python | 3.13+ |
| Node.js | 22 LTS |
| API-Football account | Free tier (100 req/day) |

### Setup

```bash
# 1. Clone
git clone https://github.com/your-username/predictor.git
cd predictor

# 2. Environment
cp .env.example .env
# Edit .env and add your API_FOOTBALL_KEY

# 3. Python dependencies
pip install -r requirements.txt

# 4. Node dependencies
cd api && npm install && cd ..

# 5. Frontend dependencies
cd frontend && npm install && cd ..
```

### Run the full pipeline (first time only)

```bash
# Build the database and train the model (~10 minutes on free API tier)
python wc2026_data_pipeline.py
python wc2026_features.py
python wc2026_model.py
python wc2026_simulator.py

# Optional: run the player performance chain (~1 minute)
python wc2026_player_chain.py
```

### Run in development

```bash
# Terminal 1 — API server
cd api
node server.js
# → http://localhost:3001

# Terminal 2 — React dashboard
cd frontend
npm run dev
# → http://localhost:5173
```

---

## API endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Server status, DB row counts, simulation readiness |
| `GET` | `/rankings?limit=N` | FIFA top-N teams with win probabilities |
| `GET` | `/team/:name` | Full stats + recent matches + simulation for one team |
| `GET` | `/bracket` | All 12 groups with team stats and probabilities |
| `GET` | `/sim-results` | Full 48-team simulation results (JSON) |
| `GET` | `/simulate` | SSE stream — re-runs Python simulator live |

---

## Deployment

### Docker (local test)

```bash
# Build
docker build -t wc2026 .

# Run (pass secret via env var — NEVER bake into image)
docker run -p 3001:3001 \
  -e API_FOOTBALL_KEY=your_key_here \
  -e NODE_ENV=production \
  wc2026

# Test
curl http://localhost:3001/health
```

---

### Railway (production backend)

#### One-time setup

1. Create a Railway account at [railway.app](https://railway.app)
2. Create a new **Empty Project**
3. Add a **New Service → GitHub Repo** and connect this repository
4. Railway auto-detects `railway.json` and will use the `Dockerfile`

#### ⚠️ Environment Variables — set these in Railway dashboard

Go to: **Railway Dashboard → Your Project → Your Service → Variables**

| Variable | Value | Required |
|---|---|---|
| `API_FOOTBALL_KEY` | Your key from api-football.com | **Yes** |
| `NODE_ENV` | `production` | **Yes** |
| `DB_PATH` | `/app/wc2026.db` | **Yes** |
| `PORT` | `3001` | Recommended |

> **Security:** Never put `API_FOOTBALL_KEY` anywhere in the codebase.  
> Railway injects it as an environment variable at runtime — it never appears in logs or Docker layers.

#### Get your Railway service URL

After first deploy: **Railway Dashboard → Your Service → Settings → Domains**  
Copy the URL (e.g. `https://predictor-production.up.railway.app`)

---

### GitHub Pages (production frontend)

#### One-time setup

1. Go to **GitHub → Your Repo → Settings → Pages**
2. Set Source: **GitHub Actions**
3. Go to **Settings → Environments** → Create environment named `github-pages`

#### GitHub Secrets and Variables

Go to: **GitHub → Settings → Secrets and variables → Actions**

**Secrets** (sensitive — encrypted):

| Secret | Value |
|---|---|
| `RAILWAY_TOKEN` | Railway API token (railway.app → Account Settings → Tokens → New Token) |

**Variables** (non-sensitive — visible in logs):

| Variable | Value |
|---|---|
| `RAILWAY_SERVICE_ID` | Found in Railway Dashboard URL: `.../project/PROJECT_ID/service/SERVICE_ID` |
| `VITE_API_URL` | Your Railway backend URL, e.g. `https://predictor-production.up.railway.app` |

#### Deploy

```bash
git add .
git commit -m "Initial deployment"
git push origin main
```

GitHub Actions will:
1. Run smoke tests on the DB, model, and API syntax
2. Deploy the Docker image to Railway
3. Build the React app with `VITE_API_URL` pointing at Railway
4. Deploy the static build to GitHub Pages

---

### Data refresh

The API server runs a cron job at **03:00 UTC daily** that chains:
1. `python wc2026_data_pipeline.py` — fresh FIFA rankings + match data
2. `python wc2026_features.py` — recalculate all features
3. `python wc2026_simulator.py` — fresh 10,000-run simulation

To trigger a manual refresh, hit `GET /simulate` from the frontend Simulate tab.

> **Railway note:** The SQLite database is stored inside the container at `/app/wc2026.db`.  
> Each new deploy resets the DB to the committed baseline. For true data persistence across deploys,  
> add a **Railway Volume** mounted at `/app` and set `DB_PATH=/app/wc2026.db`.

---

## Model details

| Property | Value |
|---|---|
| Algorithm | XGBoost (3-class: home win / draw / away win) |
| Training data | 32,262 international matches |
| Features per team | 24 (8 Phase-2 stats + 16 Phase-7 player chain) |
| Total features | 72 (home × away × diff) |
| CV Accuracy | 57.7% (5-fold, macro) |
| CV F1 | 0.456 (macro) |
| Simulations | 10,000 per run, ~17 seconds |

**Feature groups:**
- Phase 2: win rate, goals scored/conceded, big-game win rate, offensive/defensive strength, tournament experience, form momentum
- Phase 7: squad market value, avg age, WC participations, recent goals/wins, starter quality, depth score, StatsBomb tournament goals/assists per 90, WC veteran count

---

## Project timeline

| Phase | Description |
|---|---|
| 1 | Data pipeline — FIFA rankings, API-Football match results, SQLite |
| 2 | Advanced feature engineering — 10 new features |
| 3 | XGBoost match prediction model — 57.7% CV accuracy |
| 4 | Monte Carlo simulator — 10,000 tournament simulations |
| 5 | Node.js Express API — 6 endpoints, SSE streaming |
| 6 | React dashboard — gold/black theme, national color tints |
| 7 | Player performance chain — StatsBomb + FBRef + Wikipedia |
| 8 | Deployment — Docker + Railway + GitHub Actions + GitHub Pages |

---

## License

MIT — built for learning. All football data © respective providers (StatsBomb open data, API-Football, FBRef).
