"""
World Cup 2026 Predictor — Bugfix 1: Club-form score for sparse-FBRef nations
Author: Gursharan Singh Brar

WHAT THIS FILE DOES:
  Several WC 2026 nations (Brazil, Argentina, Iran, Ecuador, ...) have very
  few players matched against the FBRef 2025-26 club-data CSV, so their
  club-form columns in `nation_squad_scores` (starter_quality_score,
  depth_score, ...) sit at or near 0 — not because those squads are weak,
  but because we simply couldn't MATCH most of their players to club rows.

  This script adds a `club_form_score` column to `nation_squad_scores` and
  fills it, for the 14 affected nations, with a historical-performance
  proxy (a normalised blend of Build 2's weighted_win_rate and
  weighted_goals_scored_per_game) instead of leaving the signal at 0.

  It then re-runs the Monte Carlo simulator and prints a before/after
  win-probability comparison for the 14 nations.

HOW TO RUN:
  PYTHONIOENCODING=utf-8 python wc2026_bugfix_clubform.py

NOTE — why win probabilities are not expected to move:
  `nation_squad_scores` is a STAGING / API-display table (see
  wc2026_player_chain.aggregate_nation_features — it writes squad-derived
  scores here AND copies them into team_stats, but only when the player-
  chain pipeline runs).  The currently-deployed Build 4 model reads its 27
  raw features straight from `team_stats`, and `club_form_score` is not one
  of them (nor were any of the squad-derived columns it would have replaced
  — Build 4's pruning step removed starter_quality_score / depth_score /
  avg_goals_per90_squad / etc. for having ~0 importance).  So writing
  `club_form_score` into `nation_squad_scores` corrects the DISPLAY/API
  data the bug report was about, without silently re-wiring the model
  (which the user explicitly asked us not to touch).
"""

import sys
import sqlite3
from pathlib import Path

import pandas as pd

PROJECT  = Path(__file__).resolve().parent
DB_PATH  = str(PROJECT / "wc2026.db")
SIM_PATH = str(PROJECT / "simulation_results.json")

NATIONS = [
    "Brazil", "Argentina", "Colombia", "Mexico", "Japan",
    "South Korea", "Morocco", "Senegal", "Iran", "Algeria",
    "Ivory Coast", "Ecuador", "Uruguay", "Paraguay",
]

W_WIN_RATE  = 0.5   # weight given to weighted_win_rate in the blend
W_GOALS     = 0.5   # weight given to (normalised) weighted_goals_scored_per_game


# ─── STEP 1: ADD COLUMN (idempotent) ─────────────────────────────────────────

def add_club_form_column(cursor):
    """
    LEARNING NOTE — Idempotent ALTER TABLE:
    SQLite has no `ADD COLUMN IF NOT EXISTS`.  We check PRAGMA table_info
    first so re-running this script never raises "duplicate column name".
    """
    cols = [row[1] for row in cursor.execute("PRAGMA table_info(nation_squad_scores)").fetchall()]
    if "club_form_score" not in cols:
        cursor.execute("ALTER TABLE nation_squad_scores ADD COLUMN club_form_score REAL DEFAULT 0")
        print("   Added column: nation_squad_scores.club_form_score")
    else:
        print("   Column nation_squad_scores.club_form_score already exists — skipping ALTER")


# ─── STEP 2: COMPUTE + WRITE THE SCORE ───────────────────────────────────────

def compute_and_write_scores(conn) -> pd.DataFrame:
    """
    LEARNING NOTE — Normalising before blending:
    weighted_win_rate is already a 0-1 rate.  weighted_goals_scored_per_game
    is NOT (it ranges roughly 0-8 goals/game across all 320 teams in
    team_stats).  Blending a 0-1 number with a 0-8 number would let goals
    dominate the average by sheer scale.  We min-max normalise goals to 0-1
    using the GLOBAL range across every team in team_stats — the same
    reference frame Build 2's own weighted features use — then take a
    50/50 weighted average.  Result: club_form_score is itself a clean 0-1
    "how good has this team historically been" signal.
    """
    all_goals = pd.read_sql_query(
        "SELECT weighted_goals_scored_per_game FROM team_stats", conn
    )["weighted_goals_scored_per_game"]
    g_min, g_max = float(all_goals.min()), float(all_goals.max())
    g_range = (g_max - g_min) or 1.0   # guard against div-by-zero

    placeholders = ",".join("?" * len(NATIONS))
    df = pd.read_sql_query(
        f"SELECT team_name, weighted_win_rate, weighted_goals_scored_per_game "
        f"FROM team_stats WHERE team_name IN ({placeholders})",
        conn, params=NATIONS
    ).set_index("team_name")

    cursor = conn.cursor()
    rows = []
    for nation in NATIONS:
        if nation not in df.index:
            print(f"   [WARN] {nation}: no team_stats row found — skipped")
            continue

        win_rate     = float(df.loc[nation, "weighted_win_rate"])
        goals_raw    = float(df.loc[nation, "weighted_goals_scored_per_game"])
        goals_norm   = (goals_raw - g_min) / g_range
        club_form    = round(W_WIN_RATE * win_rate + W_GOALS * goals_norm, 4)

        cursor.execute(
            "UPDATE nation_squad_scores SET club_form_score = ? WHERE team_name = ?",
            (club_form, nation)
        )
        rows.append({
            "team_name": nation, "weighted_win_rate": win_rate,
            "goals_per_game": goals_raw, "goals_normalised": round(goals_norm, 4),
            "club_form_score": club_form,
        })

    conn.commit()
    return pd.DataFrame(rows)


def print_score_table(scores_df: pd.DataFrame):
    print("\n" + "=" * 78)
    print(f"CLUB-FORM SCORE — written to nation_squad_scores ({len(scores_df)} nations)")
    print(f"  Formula: {W_WIN_RATE:.1f} x weighted_win_rate + {W_GOALS:.1f} x normalise(weighted_goals_scored_per_game)")
    print("=" * 78)
    print(f"\n  {'Team':<14} {'win_rate':>10} {'gls/game':>10} {'gls_norm':>10} {'club_form_score':>16}")
    print(f"  {'─'*64}")
    for _, r in scores_df.sort_values("club_form_score", ascending=False).iterrows():
        print(f"  {r['team_name']:<14} {r['weighted_win_rate']:>10.4f} {r['goals_per_game']:>10.4f} "
              f"{r['goals_normalised']:>10.4f} {r['club_form_score']:>16.4f}")


# ─── STEP 3: BEFORE / AFTER WIN-PROBABILITY COMPARISON ───────────────────────

def load_win_probs(path: str) -> dict:
    import json
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {t["team"]: t["win_probability"] for t in data["teams"]}


def print_before_after(before: dict, after: dict):
    print("\n" + "=" * 78)
    print("WIN PROBABILITY — BEFORE vs AFTER club_form_score fix (14 affected nations)")
    print("=" * 78)
    print(f"\n  {'Team':<14} {'Before':>10} {'After':>10} {'Δ':>10}")
    print(f"  {'─'*48}")
    any_change = False
    for nation in NATIONS:
        b = before.get(nation)
        a = after.get(nation)
        if b is None or a is None:
            print(f"  {nation:<14} {'n/a':>10} {'n/a':>10} {'—':>10}")
            continue
        delta = a - b
        if abs(delta) > 1e-9:
            any_change = True
        sign = "+" if delta >= 0 else ""
        print(f"  {nation:<14} {b*100:>9.2f}% {a*100:>9.2f}% {sign}{delta*100:>9.2f}%")

    print(f"\n  {'─'*48}")
    if not any_change:
        print("  No change — EXPECTED (see note below).")
    print("\n  NOTE: club_form_score lives in `nation_squad_scores`, a staging/")
    print("  display table that is NOT read by team_stats, the saved Build 4")
    print("  model (its 27 features are read straight from team_stats and do")
    print("  not include club_form_score or any squad-derived column — those")
    print("  were pruned for ~0 importance), or the simulator. Writing it here")
    print("  fixes the underlying DISPLAY/API data bug without silently")
    print("  re-wiring the prediction model, which we were told not to touch.")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def run_fix1():
    print("World Cup 2026 Predictor - Bugfix 1: Club-form score (sparse-FBRef nations)")
    print("=" * 78)

    print("\n[1/4] Capturing BEFORE win probabilities from current simulation_results.json ...")
    before = load_win_probs(SIM_PATH)
    for n in NATIONS:
        print(f"   {n:<14} {before.get(n, 0)*100:>6.2f}%")

    print("\n[2/4] Adding club_form_score column and writing scores ...")
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    add_club_form_column(cursor)
    conn.commit()
    scores_df = compute_and_write_scores(conn)
    conn.close()
    print_score_table(scores_df)

    print("\n[3/4] Re-running wc2026_simulator.py ...")
    import subprocess
    result = subprocess.run(
        [sys.executable, str(PROJECT / "wc2026_simulator.py")],
        cwd=str(PROJECT), capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        print("   [ERROR] simulator failed:")
        print(result.stdout[-3000:])
        print(result.stderr[-3000:])
        sys.exit(1)
    print("   Simulator finished — simulation_results.json regenerated.")

    print("\n[4/4] Comparing AFTER win probabilities ...")
    after = load_win_probs(SIM_PATH)
    print_before_after(before, after)

    print("\n" + "=" * 78)
    print("BUGFIX 1 COMPLETE — club_form_score written for 14 nations")
    print("=" * 78)


if __name__ == "__main__":
    run_fix1()
