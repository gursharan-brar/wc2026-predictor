# ══════════════════════════════════════════════════════════════════════
#  WC 2026 Predictor — Production Dockerfile
#  Base: Python 3.13-slim + Node.js 22 LTS
#
#  Build:   docker build -t wc2026 .
#  Run:     docker run -p 3001:3001 -e API_FOOTBALL_KEY=xxx wc2026
# ══════════════════════════════════════════════════════════════════════

FROM python:3.13-slim

# ── System labels ──────────────────────────────────────────────────────
LABEL maintainer="Gursharan Singh Brar"
LABEL description="World Cup 2026 ML Predictor — API server"

# ── Environment (no secrets here — all injected at runtime) ────────────
ENV PYTHONIOENCODING=utf-8
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV NODE_ENV=production
ENV PORT=3001
# DB_PATH, API_FOOTBALL_KEY injected by Railway at runtime

# ── Install Node.js 22 LTS via NodeSource ──────────────────────────────
# We use the official NodeSource script so the Node version is pinned
# and matches production (not whatever Debian's apt has).
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get purge -y curl \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# ── Working directory ──────────────────────────────────────────────────
WORKDIR /app

# ── Python dependencies ────────────────────────────────────────────────
# Copy requirements first so this layer is cached unless deps change.
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── Node.js dependencies ───────────────────────────────────────────────
# Copy package files, install production deps only (--omit=dev).
# sql.js ships its own WASM file — no native compilation needed.
COPY api/package*.json ./api/
RUN cd api && npm ci --omit=dev

# ── Application code ───────────────────────────────────────────────────
# Copy everything that isn't in .dockerignore/.gitignore.
# This includes wc2026.db, wc2026_model.pkl, simulation_results.json
# (committed to git as baseline data — updated by daily cron in prod).
COPY . .

# ── Validate baseline data exists ──────────────────────────────────────
RUN python - <<'EOF'
import os, sys
required = ["wc2026.db", "wc2026_model.pkl", "simulation_results.json"]
missing  = [f for f in required if not os.path.exists(f)]
if missing:
    print(f"WARNING: missing baseline files: {missing}")
    print("API will start but some endpoints may return empty data.")
    print("Run the pipeline scripts locally and rebuild the image.")
else:
    import sqlite3, json, pathlib
    db_size   = pathlib.Path("wc2026.db").stat().st_size // 1024
    model_size= pathlib.Path("wc2026_model.pkl").stat().st_size // 1024
    sim       = json.load(open("simulation_results.json"))
    print(f"  wc2026.db            {db_size} KB")
    print(f"  wc2026_model.pkl     {model_size} KB")
    print(f"  simulation_results   {sim.get('simulations_run',0):,} sims, "
          f"{len(sim.get('teams',[]))} teams")
    print("Baseline data OK.")
EOF

# ── Port ───────────────────────────────────────────────────────────────
EXPOSE 3001

# ── Health check ───────────────────────────────────────────────────────
# Railway uses this to determine when the container is ready.
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3001/health', r => { \
        process.exit(r.statusCode === 200 ? 0 : 1) }). \
        on('error', () => process.exit(1))"

# ── Start ──────────────────────────────────────────────────────────────
# The Express server in api/server.js handles all routes and runs
# the Python cron chain daily at 03:00 UTC.
CMD ["node", "api/server.js"]
