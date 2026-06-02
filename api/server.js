/**
 * World Cup 2026 Predictor — Phase 5: Node.js API Server
 * Author: Gursharan Singh Brar
 *
 * WHAT THIS FILE DOES:
 *   Express server that reads from wc2026.db (via sql.js — pure JS, no
 *   native build tools required) and simulation_results.json, exposes 5
 *   REST endpoints for the React dashboard, and runs a daily cron job
 *   to refresh all data automatically.
 *
 * HOW TO START:
 *   cd api
 *   node server.js
 *
 * ENDPOINTS:
 *   GET /health              — server status + last refresh time
 *   GET /rankings            — FIFA rankings (top 32)
 *   GET /team/:name          — full stat profile for one team
 *   GET /simulate            — SSE stream: re-runs Python simulator live
 *   GET /bracket             — group draw + simulation probabilities merged
 */

"use strict";

const express    = require("express");
const cors       = require("cors");
const fs         = require("fs");
const path       = require("path");
const { spawn }  = require("child_process");
const cron       = require("node-cron");
const initSqlJs  = require("sql.js");

// ─── PATHS ────────────────────────────────────────────────────────────────────

const DB_PATH         = path.resolve(__dirname, "..", "wc2026.db");
const SIM_PATH        = path.resolve(__dirname, "..", "simulation_results.json");
const PIPELINE_SCRIPT = path.resolve(__dirname, "..", "wc2026_data_pipeline.py");
const FEATURES_SCRIPT = path.resolve(__dirname, "..", "wc2026_features.py");
const SIMULATOR_SCRIPT= path.resolve(__dirname, "..", "wc2026_simulator.py");

// sql.js ships its WASM file inside its own dist/ folder
const WASM_DIR = path.join(__dirname, "node_modules", "sql.js", "dist");

// ─── STATE ────────────────────────────────────────────────────────────────────

let SQL         = null;   // sql.js module (loaded once at startup)
let db          = null;   // in-memory SQLite database object
let lastRefresh = null;   // ISO timestamp of last successful data refresh
let simRunning  = false;  // guard: prevent two simulations at once

const PORT = process.env.PORT || 3001;

// ─── SQL.JS HELPERS ───────────────────────────────────────────────────────────

/**
 * Load (or reload) the SQLite database file into sql.js memory.
 *
 * WHY RELOAD:
 *   sql.js loads the entire .db file into a JS ArrayBuffer — it is not a
 *   live connection.  After the Python cron job updates the database on disk,
 *   we call this function again to pick up the changes.
 */
async function loadDatabase() {
  if (!SQL) {
    SQL = await initSqlJs({
      locateFile: (file) => path.join(WASM_DIR, file),
    });
  }

  if (!fs.existsSync(DB_PATH)) {
    throw new Error(`Database not found at ${DB_PATH}. Run Phase 1 first.`);
  }

  const buf = fs.readFileSync(DB_PATH);
  if (db) db.close();                    // free previous in-memory copy
  db = new SQL.Database(buf);
  console.log(`[db] Loaded ${(buf.length / 1024).toFixed(0)} KB from ${DB_PATH}`);
}

/**
 * Convert a sql.js exec() result into a plain array of objects.
 *
 * sql.js returns:  [{ columns: ["col1","col2"], values: [[v1,v2], ...] }]
 * We want:         [{ col1: v1, col2: v2 }, ...]
 *
 * This matches what better-sqlite3 / pg would return, so the rest of the
 * code looks like any other SQL library.
 */
function toRows(results) {
  if (!results || results.length === 0) return [];
  const { columns, values } = results[0];
  return values.map((row) =>
    Object.fromEntries(columns.map((col, i) => [col, row[i]]))
  );
}

/**
 * Run a parameterized query and return rows as plain objects.
 *
 * sql.js uses :name or ? placeholders.
 * bindParams example: { ":team": "France" }
 */
function query(sql, bindParams = {}) {
  if (!db) throw new Error("Database not loaded");
  const stmt = db.prepare(sql);
  stmt.bind(bindParams);
  const rows = [];
  while (stmt.step()) {
    rows.push(stmt.getAsObject());
  }
  stmt.free();
  return rows;
}

// ─── SIMULATION RESULTS HELPER ────────────────────────────────────────────────

function loadSimResults() {
  if (!fs.existsSync(SIM_PATH)) return null;
  try {
    return JSON.parse(fs.readFileSync(SIM_PATH, "utf8"));
  } catch {
    return null;
  }
}

// ─── EXPRESS APP ──────────────────────────────────────────────────────────────

const app = express();

app.use(cors());
app.use(express.json());

// Log every request in dev-friendly format
app.use((req, _res, next) => {
  console.log(`[${new Date().toISOString()}] ${req.method} ${req.path}`);
  next();
});

// ─── GET /health ──────────────────────────────────────────────────────────────

/**
 * ENDPOINT: Health check
 * Returns server status, database row counts, and last refresh timestamp.
 * Used by the frontend's StatsBar component and Railway's health probe.
 */
app.get("/health", (req, res) => {
  try {
    const rankings = query("SELECT COUNT(*) AS n FROM fifa_rankings")[0]?.n ?? 0;
    const matches  = query("SELECT COUNT(*) AS n FROM match_results")[0]?.n   ?? 0;
    const teams    = query("SELECT COUNT(*) AS n FROM team_stats")[0]?.n      ?? 0;
    const simData  = loadSimResults();

    res.json({
      status:          "ok",
      database:        "connected",
      fifa_rankings:   rankings,
      match_results:   matches,
      teams_in_stats:  teams,
      simulation_ready: !!simData,
      simulation_teams: simData?.teams?.length ?? 0,
      last_refresh:    lastRefresh,
      server_time:     new Date().toISOString(),
    });
  } catch (err) {
    res.status(503).json({ status: "error", message: err.message });
  }
});

// ─── GET /rankings ────────────────────────────────────────────────────────────

/**
 * ENDPOINT: FIFA Rankings
 * Returns top 32 FIFA-ranked teams with their current points.
 * Merges in simulation win_probability if simulation_results.json exists.
 */
app.get("/rankings", (req, res) => {
  try {
    const limit = parseInt(req.query.limit) || 32;
    const rows  = query(
      `SELECT rank, team_name, points, fetched_at
       FROM   fifa_rankings
       ORDER  BY rank
       LIMIT  :limit`,
      { ":limit": limit }
    );

    // Merge simulation win probabilities
    const simData = loadSimResults();
    const simMap  = {};
    if (simData?.teams) {
      simData.teams.forEach((t) => { simMap[t.team] = t; });
    }

    const enriched = rows.map((r) => ({
      ...r,
      win_probability:   simMap[r.team_name]?.win_probability   ?? null,
      final_probability: simMap[r.team_name]?.final_probability ?? null,
    }));

    res.json({ count: enriched.length, rankings: enriched });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ─── GET /team/:name ──────────────────────────────────────────────────────────

/**
 * ENDPOINT: Team Profile
 * Returns every stat column for one team, merged with their simulation
 * probabilities and last 5 match results.
 */
app.get("/team/:name", (req, res) => {
  try {
    const name = decodeURIComponent(req.params.name);

    const statsRows = query(
      `SELECT *
       FROM   team_stats
       WHERE  LOWER(team_name) = LOWER(:name)
       LIMIT  1`,
      { ":name": name }
    );

    if (statsRows.length === 0) {
      return res.status(404).json({ error: `Team '${name}' not found in stats` });
    }

    const stats = statsRows[0];

    // Last 5 matches
    const recent = query(
      `SELECT date, home_team, away_team, home_goals, away_goals, result, competition
       FROM   match_results
       WHERE  LOWER(home_team) = LOWER(:name) OR LOWER(away_team) = LOWER(:name)
       ORDER  BY date DESC
       LIMIT  5`,
      { ":name": name }
    );

    // FIFA ranking
    const rankRow = query(
      `SELECT rank, points
       FROM   fifa_rankings
       WHERE  LOWER(team_name) = LOWER(:name)
       LIMIT  1`,
      { ":name": name }
    );

    // Simulation data
    const simData = loadSimResults();
    const simTeam = simData?.teams?.find(
      (t) => t.team.toLowerCase() === name.toLowerCase()
    ) ?? null;

    res.json({
      team:        stats.team_name,
      stats,
      fifa_rank:   rankRow[0] ?? null,
      recent_matches: recent,
      simulation:  simTeam,
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ─── GET /bracket ─────────────────────────────────────────────────────────────

/**
 * ENDPOINT: Tournament Bracket
 * Returns the 12 WC 2026 groups with each team's stats and simulation
 * probabilities merged together — everything the BracketView component needs.
 */
app.get("/bracket", (req, res) => {
  try {
    // Load sim data for probability enrichment
    const simData = loadSimResults();
    const simMap  = {};
    if (simData?.teams) {
      simData.teams.forEach((t) => { simMap[t.team] = t; });
    }

    // Load all team stats into a lookup map
    const allStats = query(
      `SELECT team_name, win_rate, home_win_rate, away_win_rate,
              big_game_win_rate, offensive_strength, defensive_strength,
              tournament_experience_score, host_nation_bonus, form_momentum,
              form_last_10, avg_goals_scored, avg_goals_conceded
       FROM   team_stats`
    );
    const statsMap = {};
    allStats.forEach((r) => { statsMap[r.team_name] = r; });

    // Hard-coded group structure (matches wc2026_simulator.py)
    const GROUP_STAGE = {
      A: ["USA",        "Ecuador",      "Morocco",      "Saudi Arabia"],
      B: ["Mexico",     "Colombia",     "Algeria",      "Iran"        ],
      C: ["Canada",     "Uruguay",      "Egypt",        "Australia"   ],
      D: ["Argentina",  "Japan",        "Ivory Coast",  "Jordan"      ],
      E: ["Brazil",     "South Korea",  "Nigeria",      "Iraq"        ],
      F: ["France",     "Senegal",      "Cameroon",     "Qatar"       ],
      G: ["Spain",      "Croatia",      "South Africa", "Honduras"    ],
      H: ["England",    "Serbia",       "Mali",         "Jamaica"     ],
      I: ["Germany",    "Denmark",      "Switzerland",  "Bolivia"     ],
      J: ["Belgium",    "Turkey",       "Scotland",     "New Zealand" ],
      K: ["Portugal",   "Austria",      "Panama",       "El Salvador" ],
      L: ["Netherlands","Poland",       "Romania",      "Venezuela"   ],
    };

    const bracket = {};
    Object.entries(GROUP_STAGE).forEach(([letter, teams]) => {
      bracket[letter] = teams.map((team) => ({
        team,
        stats:      statsMap[team]  ?? null,
        simulation: simMap[team]    ?? null,
      }));
    });

    res.json({
      groups:           bracket,
      simulation_meta:  simData
        ? { generated_at: simData.generated_at, simulations_run: simData.simulations_run }
        : null,
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ─── GET /simulate ────────────────────────────────────────────────────────────

/**
 * ENDPOINT: Run simulator with live progress streaming
 *
 * Uses Server-Sent Events (SSE) so the browser receives real-time progress
 * updates as the Python simulator runs its 10,000 iterations.
 *
 * SSE format: each line prefixed with "data: " followed by JSON.
 * The browser's EventSource API handles reconnection automatically.
 *
 * Add ?cached=true to skip re-running and just return existing results.
 */
app.get("/simulate", (req, res) => {
  // ── Return cached results immediately ──────────────────────────────────
  if (req.query.cached === "true") {
    const simData = loadSimResults();
    if (!simData) {
      return res.status(404).json({ error: "No simulation results found. Run without ?cached=true first." });
    }
    return res.json(simData);
  }

  // ── Guard: only one simulation at a time ───────────────────────────────
  if (simRunning) {
    return res.status(409).json({ error: "Simulation already running. Try again shortly." });
  }

  // ── Set up SSE headers ─────────────────────────────────────────────────
  res.setHeader("Content-Type",  "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection",    "keep-alive");
  res.setHeader("X-Accel-Buffering", "no");  // disable nginx buffering on Railway
  res.flushHeaders();

  function send(eventName, data) {
    res.write(`event: ${eventName}\ndata: ${JSON.stringify(data)}\n\n`);
  }

  simRunning = true;
  send("start", { message: "Starting simulation…", timestamp: new Date().toISOString() });

  // ── Spawn Python simulator ─────────────────────────────────────────────
  const python = process.platform === "win32" ? "python" : "python3";
  const proc   = spawn(python, [SIMULATOR_SCRIPT], {
    cwd: path.dirname(SIMULATOR_SCRIPT),
    env: { ...process.env, PYTHONIOENCODING: "utf-8" },
  });

  proc.stdout.on("data", (chunk) => {
    const lines = chunk.toString().split("\n").filter(Boolean);
    lines.forEach((line) => {
      send("progress", { line: line.trim() });
    });
  });

  proc.stderr.on("data", (chunk) => {
    // Python warnings → treat as info, not fatal errors
    send("warning", { line: chunk.toString().trim() });
  });

  proc.on("close", async (code) => {
    simRunning = false;
    if (code === 0) {
      // Reload DB in case pipeline also ran
      try { await loadDatabase(); } catch (_) {}
      const simData = loadSimResults();
      send("done", { success: true, results: simData });
    } else {
      send("done", { success: false, error: `Process exited with code ${code}` });
    }
    res.end();
  });

  // Clean up if client disconnects
  req.on("close", () => {
    if (!proc.killed) {
      proc.kill();
      simRunning = false;
    }
  });
});

// ─── GET /sim-results ────────────────────────────────────────────────────────

/**
 * ENDPOINT: Latest simulation results (no SSE, plain JSON)
 * Convenience endpoint for the leaderboard component.
 */
app.get("/sim-results", (req, res) => {
  const simData = loadSimResults();
  if (!simData) {
    return res.status(404).json({
      error: "simulation_results.json not found. Hit GET /simulate first.",
    });
  }
  res.json(simData);
});

// ─── 404 HANDLER ──────────────────────────────────────────────────────────────

app.use((req, res) => {
  res.status(404).json({
    error:     "Not found",
    path:      req.path,
    available: ["/health", "/rankings", "/team/:name", "/simulate", "/bracket", "/sim-results"],
  });
});

// ─── GLOBAL ERROR HANDLER ─────────────────────────────────────────────────────

app.use((err, _req, res, _next) => {
  console.error("[error]", err);
  res.status(500).json({ error: "Internal server error", message: err.message });
});

// ─── CRON: DAILY DATA REFRESH ────────────────────────────────────────────────

/**
 * Runs at 03:00 UTC every day.
 * Executes the Python pipeline chain:
 *   1. wc2026_data_pipeline.py  — fresh FIFA rankings + match data
 *   2. wc2026_features.py       — recalculate features
 *   3. wc2026_simulator.py      — regenerate win probabilities
 * Then reloads the database into memory.
 */
function runRefreshPipeline() {
  console.log("[cron] Starting daily data refresh …");

  const python  = process.platform === "win32" ? "python" : "python3";
  const scripts = [PIPELINE_SCRIPT, FEATURES_SCRIPT, SIMULATOR_SCRIPT];
  const cwd     = path.dirname(PIPELINE_SCRIPT);

  let idx = 0;

  function runNext() {
    if (idx >= scripts.length) {
      loadDatabase()
        .then(() => {
          lastRefresh = new Date().toISOString();
          console.log(`[cron] Refresh complete at ${lastRefresh}`);
        })
        .catch((e) => console.error("[cron] DB reload failed:", e.message));
      return;
    }

    const script = scripts[idx++];
    console.log(`[cron] Running ${path.basename(script)} …`);

    const proc = spawn(python, [script], {
      cwd,
      env: { ...process.env, PYTHONIOENCODING: "utf-8" },
    });

    proc.stdout.on("data", (d) =>
      process.stdout.write(`  [py] ${d.toString()}`)
    );
    proc.stderr.on("data", (d) =>
      process.stderr.write(`  [py-err] ${d.toString()}`)
    );
    proc.on("close", (code) => {
      if (code === 0) {
        runNext();
      } else {
        console.error(`[cron] ${path.basename(script)} failed (exit ${code}). Stopping chain.`);
      }
    });
  }

  runNext();
}

// Schedule: every day at 03:00 UTC
cron.schedule("0 3 * * *", runRefreshPipeline, { timezone: "UTC" });

// ─── STARTUP ──────────────────────────────────────────────────────────────────

async function start() {
  console.log("──────────────────────────────────────────");
  console.log(" World Cup 2026 Predictor — API Server");
  console.log("──────────────────────────────────────────");

  try {
    await loadDatabase();
    lastRefresh = new Date().toISOString();
  } catch (err) {
    console.error("[startup] Could not load database:", err.message);
    console.error("  Make sure you have run Phase 1 (wc2026_data_pipeline.py) first.");
    process.exit(1);
  }

  const simData = loadSimResults();
  console.log(`[startup] simulation_results.json: ${simData ? `found (${simData.teams?.length ?? 0} teams)` : "NOT FOUND — run /simulate"}`);

  app.listen(PORT, () => {
    console.log(`\n[ready] API running at http://localhost:${PORT}`);
    console.log(`  GET http://localhost:${PORT}/health`);
    console.log(`  GET http://localhost:${PORT}/rankings`);
    console.log(`  GET http://localhost:${PORT}/team/France`);
    console.log(`  GET http://localhost:${PORT}/bracket`);
    console.log(`  GET http://localhost:${PORT}/simulate`);
    console.log(`  GET http://localhost:${PORT}/sim-results`);
    console.log(`\n[cron] Daily refresh scheduled at 03:00 UTC`);
    console.log("──────────────────────────────────────────\n");
  });
}

start();
