"""
World Cup 2026 Predictor — Phase 4: Monte Carlo Tournament Simulator
Author: Gursharan Singh Brar

WHAT THIS FILE DOES:
  Simulates the entire FIFA World Cup 2026 tournament 10,000 times from
  group stage through to the final.  Each match in every simulation is
  decided by the XGBoost model trained in Phase 3.

  After 10,000 runs, every team has a probability of winning, reaching
  the final, semi-final, quarter-final, or exiting at the group stage.
  Results are saved to simulation_results.json for the API and frontend.

HOW TO RUN:
  python wc2026_simulator.py

REQUIREMENTS:
  Phase 3 must have been run first so wc2026_model.pkl exists.

NOTE ON GROUP DRAW:
  Groups below reflect the official FIFA World Cup 2026 draw announced
  December 5, 2024.  Verify against https://www.fifa.com if any team
  needs updating — simply edit the GROUP_STAGE dictionary below.
"""

import sys
import json
import sqlite3
import warnings
import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Build 4 — H2H-aware prediction needs the same pairwise lookup the retrain
# script used.  Imported lazily-safe: wc2026_h2h has no import-time side effects.
from wc2026_h2h import get_h2h_features

warnings.filterwarnings("ignore")

DB_PATH      = "wc2026.db"
MODEL_PATH   = "wc2026_model.pkl"
RESULTS_PATH = "simulation_results.json"

N_SIMULATIONS    = 10_000
LEAGUE_AVG_GOALS = 1.35    # average goals per team per international match
# FEATURE_COLS is loaded dynamically from the model pkl at runtime.
# The list below is only a fallback if the pkl can't be read.
_FEATURE_COLS_FALLBACK = [
    "win_rate", "avg_goals_scored", "avg_goals_conceded",
    "big_game_win_rate", "defensive_strength", "offensive_strength",
    "tournament_experience_score", "form_momentum",
]

# Build 4 — populated by load_model_and_stats() if the saved model carries
# H2H features.  Left empty/False here so older models behave exactly as
# before (predict_neutral simply skips the H2H block).
H2H_FEATURE_NAMES: list = []
USES_H2H:          bool = False
H2H_CACHE:         dict = {}

# ─── OFFICIAL GROUP DRAW ──────────────────────────────────────────────────────
# Source: FIFA WC 2026 draw, December 5 2024, Miami Florida
# Co-hosts USA / Mexico / Canada are seeded into Groups A / B / C respectively.
# UPDATE any team name here if it differs from your team_stats table.

GROUP_STAGE = {
    "A": ["Mexico", "South Africa", "South Korea", "TBD-UEPD"],
    "B": ["Canada", "TBD-UEPA", "Qatar", "Switzerland"],
    "C": ["Brazil", "Morocco", "Haiti", "Scotland"],
    "D": ["USA", "Paraguay", "Australia", "TBD-UEPC"],
    "E": ["Germany", "Curacao", "Ivory Coast", "Ecuador"],
    "F": ["Netherlands", "Japan", "TBD-UEPB", "Tunisia"],
    "G": ["Belgium", "Egypt", "Iran", "New Zealand"],
    "H": ["Spain", "Cape Verde", "Saudi Arabia", "Uruguay"],
    "I": ["France", "Senegal", "TBD-FP02", "Norway"],
    "J": ["Argentina", "Algeria", "Austria", "Jordan"],
    "K": ["Portugal", "TBD-FP01", "Uzbekistan", "Colombia"],
    "L": ["England", "Croatia", "Ghana", "Panama"],
}

# All 48 WC teams (derived from GROUP_STAGE for easy iteration)
ALL_WC_TEAMS = [t for group in GROUP_STAGE.values() for t in group]

# ─── ROUND OF 32 BRACKET TEMPLATE ────────────────────────────────────────────
# LEARNING NOTE — Pre-determined bracket:
# FIFA sets the knockout bracket before the tournament — it only depends on
# which position each team finishes in their group, not on their identity.
# "W_A" = winner of Group A, "R_A" = runner-up of Group A, "T_1" = best
# third-place finisher assigned to this section of the draw.
#
# Structure: 4 sections (A-C, D-F, G-I, J-L) of 8 teams each.
# Within each section, the two third-place slots go to the ranked thirds
# from that section's three groups.

R32_TEMPLATE = [
    # Section 1  (Groups A,B,C)
    ("W_A", "R_C"),   # match  1 → feeds QF1
    ("W_B", "T_1"),   # match  2 → feeds QF1
    ("W_C", "R_A"),   # match  3 → feeds QF2
    ("R_B", "T_2"),   # match  4 → feeds QF2
    # Section 2  (Groups D,E,F)
    ("W_D", "R_F"),   # match  5 → feeds QF3
    ("W_E", "T_3"),   # match  6 → feeds QF3
    ("W_F", "R_D"),   # match  7 → feeds QF4
    ("R_E", "T_4"),   # match  8 → feeds QF4
    # Section 3  (Groups G,H,I)
    ("W_G", "R_I"),   # match  9 → feeds QF5
    ("W_H", "T_5"),   # match 10 → feeds QF5
    ("W_I", "R_G"),   # match 11 → feeds QF6
    ("R_H", "T_6"),   # match 12 → feeds QF6
    # Section 4  (Groups J,K,L)
    ("W_J", "R_L"),   # match 13 → feeds QF7
    ("W_K", "T_7"),   # match 14 → feeds QF7
    ("W_L", "R_J"),   # match 15 → feeds QF8
    ("R_K", "T_8"),   # match 16 → feeds QF8
]

# QF / SF bracket: winners of matches are paired as (M1 winner vs M2 winner) etc.
QF_PAIRS = [(0,1),(2,3),(4,5),(6,7),(8,9),(10,11),(12,13),(14,15)]  # R32 match indices
SF_PAIRS = [(0,1),(2,3),(4,5),(6,7)]                                  # QF match indices
FINAL_PAIRS = [(0,1),(2,3)]                                           # SF match indices


# ─── LOAD MODEL AND STATS ONCE ───────────────────────────────────────────────

def load_model_and_stats() -> tuple:
    """
    LEARNING NOTE — Load once, use many times:
    Loading a trained model from disk takes ~0.5 seconds per call due to
    file I/O and object reconstruction.  With 10,000 simulations × ~100
    matches each = 1,000,000 predictions, loading the model each time would
    take 500,000 seconds.  Instead we load it ONCE here and pass the pipeline
    object around in memory.  Prediction then becomes pure numpy math: ~1 µs
    per call.  Total simulation time: under 60 seconds.

    Phase 7 update: we now read FEATURE_COLS from the saved model payload
    rather than using a hardcoded list, so the simulator automatically adapts
    when the model is retrained with an expanded feature set.

    Build 4 update: the retrained model may also carry pairwise H2H
    features (payload['uses_h2h'] / payload['h2h_feature_names']).  Unlike
    per-team stats, H2H values can't be looked up from a simple {team: row}
    dict — they require a (team_a, team_b) pair query against the
    `head_to_head` table.  We precompute every ordered pair among the 48 WC
    teams ONCE here (48*47 = 2,256 lookups) and hand the resulting cache
    down to predict_neutral / build_prob_cache, exactly mirroring the
    h2h_cache pattern used during training in wc2026_model_retrain.py.
    """
    payload     = joblib.load(MODEL_PATH)
    pipeline    = payload["pipeline"]
    label_names = payload["label_names"]   # ["away_win","draw","home_win"]

    h2h_feature_names = payload.get("h2h_feature_names", [])
    uses_h2h          = bool(payload.get("uses_h2h", False)) and len(h2h_feature_names) > 0

    # Read the raw (un-prefixed) feature column names the model was trained on.
    # The payload stores them as 'feature_names_raw' (Phase 7 model) or we
    # fall back to deriving them from 'feature_cols' (Phase 3 model).
    if "feature_names_raw" in payload:
        feature_cols = payload["feature_names_raw"]
    else:
        # Phase 3 model: feature_cols was home_X / away_X / diff_X triples
        # — take only the home_ prefixed names and strip the prefix
        fc_all = payload.get("feature_cols", [])
        feature_cols = [c[5:] for c in fc_all if c.startswith("home_")]
        if not feature_cols:
            feature_cols = _FEATURE_COLS_FALLBACK

    # Only select columns that actually exist in team_stats
    conn = sqlite3.connect(DB_PATH)
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(team_stats)").fetchall()}
    safe_cols = [c for c in feature_cols if c in existing_cols]
    if not safe_cols:
        safe_cols = [c for c in _FEATURE_COLS_FALLBACK if c in existing_cols]

    df = pd.read_sql_query(
        f"SELECT team_name, {', '.join(safe_cols)} FROM team_stats",
        conn
    )
    conn.close()

    df      = df.fillna(0)
    stats   = df.set_index("team_name")[safe_cols].to_dict("index")
    avg_row = {c: float(df[c].mean()) for c in safe_cols}

    # Expose the resolved feature list globally so predict_neutral can use it
    global FEATURE_COLS
    FEATURE_COLS = safe_cols

    # ── Build 4: precompute the H2H pairwise cache (if the model expects it) ──
    h2h_cache = {}
    if uses_h2h:
        conn2 = sqlite3.connect(DB_PATH)
        for t1 in ALL_WC_TEAMS:
            for t2 in ALL_WC_TEAMS:
                if t1 != t2:
                    h2h_cache[(t1, t2)] = get_h2h_features(t1, t2, conn2)
        conn2.close()
        print(f"   H2H pairwise cache built: {len(h2h_cache):,} ordered pairs "
              f"({len(h2h_feature_names)} features each)")

    global H2H_FEATURE_NAMES, USES_H2H, H2H_CACHE
    H2H_FEATURE_NAMES = h2h_feature_names
    USES_H2H          = uses_h2h
    H2H_CACHE         = h2h_cache

    return pipeline, stats, avg_row, label_names


# ─── FAST PREDICTION ─────────────────────────────────────────────────────────

def predict_neutral(
    team1: str, team2: str,
    pipeline, stats: dict, avg_row: dict
) -> dict:
    """
    LEARNING NOTE — Neutral venue correction:
    The model was trained on home/away matches where the home team has a
    statistical advantage (familiar pitch, crowd noise, no travel).  World
    Cup matches are at neutral venues, so neither team is truly "home."

    We handle this by predicting the match TWICE:
      Pass 1: team1 as "home"  → gives us P(team1 wins as home)
      Pass 2: team2 as "home"  → gives us P(team1 wins as away)

    We average both perspectives.  This is equivalent to saying "we don't
    know which direction the home-field effect runs, so we cancel it out."

    The host-nation bonus (USA, Canada, Mexico) is already in team features
    so they still get a crowd advantage through the feature vector itself.

    Build 4 — H2H features in a neutral-venue, double-pass prediction:
    H2H features (e.g. h2h_win_rate_diff) are already DIRECTIONAL — they
    encode "home minus away" from the perspective of whichever team is
    listed as home in that lookup.  So for:
      Pass 1 (team1 as home) → look up H2H_CACHE[(team1, team2)]
      Pass 2 (team2 as home) → look up H2H_CACHE[(team2, team1)]
    This is the pairwise equivalent of the `diff` -> `neg_d` flip we already
    do for per-team stats — each pass gets the H2H block from the correct
    team's perspective, and averaging the two passes cancels out any
    "home advantage" baked into the historical H2H record, just like it
    does for the rest of the feature vector.
    """
    h = stats.get(team1, avg_row)
    a = stats.get(team2, avg_row)

    h_feats = [h[c] for c in FEATURE_COLS]
    a_feats = [a[c] for c in FEATURE_COLS]
    diff    = [h[c] - a[c] for c in FEATURE_COLS]
    neg_d   = [-d for d in diff]

    h2h_12 = h2h_21 = []
    if USES_H2H and H2H_FEATURE_NAMES:
        rec_12 = H2H_CACHE.get((team1, team2)) or {k: 0.0 for k in H2H_FEATURE_NAMES}
        rec_21 = H2H_CACHE.get((team2, team1)) or {k: 0.0 for k in H2H_FEATURE_NAMES}
        h2h_12 = [rec_12.get(k, 0.0) for k in H2H_FEATURE_NAMES]
        h2h_21 = [rec_21.get(k, 0.0) for k in H2H_FEATURE_NAMES]

    # Pass 1: team1 as home
    X1   = np.array([h_feats + a_feats + diff + h2h_12])
    p1   = pipeline.predict_proba(X1)[0]   # [away_win, draw, home_win]

    # Pass 2: team2 as home (team1 as away)
    X2   = np.array([a_feats + h_feats + neg_d + h2h_21])
    p2   = pipeline.predict_proba(X2)[0]

    # Average: team1 wins = home_win in pass1 = away_win in pass2
    t1_win = float((p1[2] + p2[0]) / 2)
    draw   = float((p1[1] + p2[1]) / 2)
    t2_win = float((p1[0] + p2[2]) / 2)

    return {"team1_win": t1_win, "draw": draw, "team2_win": t2_win}


def build_prob_cache(teams: list, pipeline, stats: dict, avg_row: dict) -> dict:
    """
    LEARNING NOTE — Probability cache:
    Before running 10,000 simulations we pre-compute every possible matchup
    between the 48 WC teams.  48 × 47 = 2,256 ordered pairs.  This takes a
    few seconds upfront but makes each simulation ~50× faster because all
    10,000 simulations draw from the cache via instant dictionary lookups
    instead of re-running the model each time.
    """
    cache = {}
    for t1 in teams:
        for t2 in teams:
            if t1 != t2:
                cache[(t1, t2)] = predict_neutral(t1, t2, pipeline, stats, avg_row)
    return cache


# ─── GOAL SIMULATION ─────────────────────────────────────────────────────────

def simulate_goals(
    team1: str, team2: str, outcome: str,
    stats: dict, avg_row: dict
) -> tuple[int, int]:
    """
    LEARNING NOTE — Poisson goal model:
    Poisson distribution is the standard model for football goal counts.
    It describes "how many independent random events (goals) happen in a
    fixed time interval (90 minutes)" — which matches how goals work.

    Expected goals per team = league_average × attack_strength / defence_strength
    We use offensive_strength and defensive_strength from team_stats (Phase 2).

    After sampling, we nudge the scores to be consistent with the match
    outcome the ML model already determined — this avoids contradiction
    (e.g. model said "home_win" but Poisson happened to give away more goals).
    """
    t1 = stats.get(team1, avg_row)
    t2 = stats.get(team2, avg_row)

    off1 = max(t1["offensive_strength"], 0.3)
    def1 = max(t1["defensive_strength"], 0.3)
    off2 = max(t2["offensive_strength"], 0.3)
    def2 = max(t2["defensive_strength"], 0.3)

    lam1 = max(0.2, LEAGUE_AVG_GOALS * off1 / def2)
    lam2 = max(0.2, LEAGUE_AVG_GOALS * off2 / def1)

    g1 = int(np.random.poisson(lam1))
    g2 = int(np.random.poisson(lam2))

    # Nudge to match outcome
    if outcome == "team1" and g1 <= g2:
        g1 = g2 + 1
    elif outcome == "team2" and g2 <= g1:
        g2 = g1 + 1
    elif outcome == "draw":
        g1 = g2 = min(g1, g2)

    return g1, g2


# ─── MATCH SAMPLING ───────────────────────────────────────────────────────────

def sample_match(
    team1: str, team2: str,
    prob_cache: dict,
    stats: dict, avg_row: dict,
    knockout: bool = False
) -> tuple[str, str, int, int]:
    """
    LEARNING NOTE — Sampling from a probability distribution:
    np.random.choice(outcomes, p=probabilities) is the core sampling step.
    Think of it like a weighted coin flip: if team1 has 0.60 win probability,
    team2 has 0.25, and draw is 0.15, we're rolling a die with those weights.

    In group stage: draws count as 1 point each.
    In knockout: if we sample a draw, we simulate a penalty shootout (50/50).
    Penalty shootouts are deliberately random — historically they ARE nearly
    50/50 even between mismatched teams.

    Returns: (winner_or_draw_result, loser_or_draw, team1_goals, team2_goals)
    """
    probs = prob_cache.get((team1, team2),
                           {"team1_win": 0.40, "draw": 0.25, "team2_win": 0.35})

    t1_p   = probs["team1_win"]
    draw_p = probs["draw"]
    t2_p   = probs["team2_win"]

    total  = t1_p + draw_p + t2_p
    p_arr  = np.array([t1_p, draw_p, t2_p]) / total   # normalise

    outcome_idx = int(np.random.choice(3, p=p_arr))

    if outcome_idx == 0:
        outcome = "team1"
    elif outcome_idx == 1:
        if knockout:
            outcome = "team1" if np.random.random() < 0.5 else "team2"
        else:
            outcome = "draw"
    else:
        outcome = "team2"

    g1, g2 = simulate_goals(team1, team2, outcome, stats, avg_row)
    return outcome, g1, g2


# ─── GROUP STAGE SIMULATION ───────────────────────────────────────────────────

def simulate_group(
    group_teams: list,
    prob_cache: dict,
    stats: dict, avg_row: dict
) -> dict:
    """
    LEARNING NOTE — Round-robin scheduling:
    In a group of 4 teams, every team plays every other team once.
    That's C(4,2) = 6 matches per group.  We generate all unique pairs
    using a nested loop (i < j avoids duplicates).

    Points system: Win=3, Draw=1, Loss=0
    Tiebreaker order: points → goal difference → goals scored (standard FIFA)

    Returns a dict: team → {points, gf, ga, gd} for this group.
    """
    standings = {t: {"points": 0, "gf": 0, "ga": 0} for t in group_teams}

    for i in range(len(group_teams)):
        for j in range(i + 1, len(group_teams)):
            t1   = group_teams[i]
            t2   = group_teams[j]
            outcome, g1, g2 = sample_match(t1, t2, prob_cache, stats, avg_row)

            standings[t1]["gf"] += g1
            standings[t1]["ga"] += g2
            standings[t2]["gf"] += g2
            standings[t2]["ga"] += g1

            if outcome == "team1":
                standings[t1]["points"] += 3
            elif outcome == "team2":
                standings[t2]["points"] += 3
            else:
                standings[t1]["points"] += 1
                standings[t2]["points"] += 1

    for t in standings:
        standings[t]["gd"] = standings[t]["gf"] - standings[t]["ga"]

    return standings


def rank_group(standings: dict) -> list:
    """Sort a group standings dict → list of teams [1st, 2nd, 3rd, 4th]."""
    return sorted(
        standings.keys(),
        key=lambda t: (
            standings[t]["points"],
            standings[t]["gd"],
            standings[t]["gf"],
        ),
        reverse=True,
    )


def get_best_thirds(all_thirds: list[tuple]) -> list:
    """
    LEARNING NOTE — Best third-place rule:
    With 12 groups only 2 teams per group advance automatically.  An extra
    8 spots go to the best third-place teams across all 12 groups, creating
    a 32-team knockout bracket.  We rank all 12 thirds by points, then goal
    difference, then goals scored — exactly as FIFA does — and take the top 8.

    all_thirds: list of (team_name, standings_dict) tuples.
    Returns: list of 8 team names (best → worst).
    """
    ranked = sorted(
        all_thirds,
        key=lambda x: (
            x[1]["points"],
            x[1]["gd"],
            x[1]["gf"],
        ),
        reverse=True,
    )
    return [t for t, _ in ranked[:8]]


# ─── KNOCKOUT BRACKET BUILDER ─────────────────────────────────────────────────

def resolve_bracket(
    group_winners: dict,    # {"A": "France", "B": "Mexico", ...}
    runners_up: dict,       # {"A": "Morocco", ...}
    best_thirds: list,      # list of 8 team names, best first
) -> list:
    """
    LEARNING NOTE — Bracket resolution:
    The R32 bracket template uses symbolic placeholders like "W_A" (winner of
    group A).  This function replaces each placeholder with the actual team
    name for this simulation run.  T_1 through T_8 are the 8 best thirds in
    performance order.

    Returns a list of 16 (team1, team2) tuples for the Round of 32.
    """
    thirds_map = {f"T_{i+1}": best_thirds[i] for i in range(8)}

    def resolve(key: str) -> str:
        if key.startswith("W_"):
            return group_winners[key[2:]]
        if key.startswith("R_"):
            return runners_up[key[2:]]
        if key.startswith("T_"):
            return thirds_map[key]
        return key

    return [(resolve(a), resolve(b)) for a, b in R32_TEMPLATE]


# ─── KNOCKOUT ROUND SIMULATION ────────────────────────────────────────────────

def simulate_knockout_round(
    matches: list,
    prob_cache: dict,
    stats: dict, avg_row: dict,
    goal_tracker: dict,
) -> list:
    """
    LEARNING NOTE — Single-elimination bracket:
    In knockout football there are no draws — you win or go home (via
    penalties if level after 90 mins).  We simulate each match and collect
    the winners to pass to the next round.

    goal_tracker accumulates each team's goals for expected_goals calculation.
    """
    winners = []
    for t1, t2 in matches:
        outcome, g1, g2 = sample_match(
            t1, t2, prob_cache, stats, avg_row, knockout=True
        )
        winner = t1 if outcome == "team1" else t2
        winners.append(winner)
        goal_tracker[t1] += g1
        goal_tracker[t2] += g2
    return winners


def pair_winners(winners: list) -> list:
    """Convert a flat list of winners into matchup pairs for the next round."""
    return [(winners[i], winners[i + 1]) for i in range(0, len(winners), 2)]


# ─── SINGLE TOURNAMENT SIMULATION ────────────────────────────────────────────

def run_single_simulation(
    prob_cache: dict,
    stats: dict, avg_row: dict,
) -> dict:
    """
    LEARNING NOTE — One Monte Carlo sample:
    This function simulates one complete World Cup — all 104 matches from
    group stage to final.  The result is a snapshot: which teams advanced
    how far, and how many goals each team scored.

    We run this 10,000 times.  Across all runs, the LAW OF LARGE NUMBERS
    ensures our probabilities converge to their true expected values.  If
    France wins 5,800 out of 10,000 simulations, their win probability is ~58%.

    Returns: {team: stage_reached, "_goals": {team: int}}
    """
    stage_reached = {t: "group_stage" for t in ALL_WC_TEAMS}
    goal_tracker  = defaultdict(int)

    # ── Group stage ────────────────────────────────────────────────────────
    group_winners = {}
    runners_up    = {}
    all_thirds    = []

    for group_letter, teams in GROUP_STAGE.items():
        standings  = simulate_group(teams, prob_cache, stats, avg_row)
        ranked     = rank_group(standings)

        group_winners[group_letter] = ranked[0]
        runners_up[group_letter]    = ranked[1]
        all_thirds.append((ranked[2], standings[ranked[2]]))

        # Track group stage goals
        for t in teams:
            goal_tracker[t] += standings[t]["gf"]

        # Mark top-2 as advanced past group stage
        stage_reached[ranked[0]] = "r32"
        stage_reached[ranked[1]] = "r32"

    best_thirds = get_best_thirds(all_thirds)
    for t in best_thirds:
        stage_reached[t] = "r32"

    # ── Round of 32 ────────────────────────────────────────────────────────
    r32_matches = resolve_bracket(group_winners, runners_up, best_thirds)
    r32_winners = simulate_knockout_round(
        r32_matches, prob_cache, stats, avg_row, goal_tracker
    )
    for w in r32_winners:
        stage_reached[w] = "r16"

    # ── Round of 16 ────────────────────────────────────────────────────────
    r16_matches = pair_winners(r32_winners)
    r16_winners = simulate_knockout_round(
        r16_matches, prob_cache, stats, avg_row, goal_tracker
    )
    for w in r16_winners:
        stage_reached[w] = "qf"

    # ── Quarter-finals ─────────────────────────────────────────────────────
    qf_matches = pair_winners(r16_winners)
    qf_winners = simulate_knockout_round(
        qf_matches, prob_cache, stats, avg_row, goal_tracker
    )
    for w in qf_winners:
        stage_reached[w] = "sf"

    # ── Semi-finals ────────────────────────────────────────────────────────
    sf_matches = pair_winners(qf_winners)
    sf_winners = simulate_knockout_round(
        sf_matches, prob_cache, stats, avg_row, goal_tracker
    )
    for w in sf_winners:
        stage_reached[w] = "final"

    # ── Final ──────────────────────────────────────────────────────────────
    champion_outcome, fg1, fg2 = sample_match(
        sf_winners[0], sf_winners[1],
        prob_cache, stats, avg_row, knockout=True
    )
    champion = sf_winners[0] if champion_outcome == "team1" else sf_winners[1]
    goal_tracker[sf_winners[0]] += fg1
    goal_tracker[sf_winners[1]] += fg2
    stage_reached[champion] = "winner"

    return {"stage": stage_reached, "goals": dict(goal_tracker)}


# ─── MONTE CARLO AGGREGATOR ───────────────────────────────────────────────────

def run_monte_carlo(
    pipeline, stats: dict, avg_row: dict,
    n_sims: int = N_SIMULATIONS
) -> dict:
    """
    LEARNING NOTE — Monte Carlo simulation:
    Named after the famous casino, Monte Carlo methods use random sampling
    to solve problems that would be intractable to solve analytically.

    A 48-team World Cup has an astronomically large number of possible
    outcomes (48! paths just for team ordering, then multiply by match
    probabilities).  We can't enumerate them all.  Instead we run many
    random simulations and count how often each outcome occurs.

    Key insight: as n_sims → ∞, sample frequency → true probability.
    At 10,000 simulations, our win probability estimates have a margin of
    error of roughly ±1.0% (95% confidence interval).  That's precise enough
    for a prediction website.
    """
    print(f"\n   Building probability cache for {len(ALL_WC_TEAMS)} teams ...")
    prob_cache = build_prob_cache(ALL_WC_TEAMS, pipeline, stats, avg_row)
    print(f"   Cache built: {len(prob_cache):,} team-pair probabilities")

    # Counters
    counts = {
        t: {
            "winner":         0,
            "final":          0,
            "sf":             0,
            "qf":             0,
            "r16":            0,
            "r32":            0,
            "group_stage":    0,
            "total_goals":    0.0,
        }
        for t in ALL_WC_TEAMS
    }

    STAGE_ORDER = ["group_stage","r32","r16","qf","sf","final","winner"]
    STAGE_KEY   = {
        "group_stage": "group_stage",
        "r32":         "r32",
        "r16":         "r16",
        "qf":          "qf",
        "sf":          "sf",
        "final":       "final",
        "winner":      "winner",
    }

    print(f"   Running {n_sims:,} simulations ...\n")
    report_every = n_sims // 10

    for sim_i in range(n_sims):
        if sim_i % report_every == 0 and sim_i > 0:
            pct = sim_i / n_sims * 100
            # Quick top-3 preview
            top3 = sorted(counts.items(),
                          key=lambda x: x[1]["winner"], reverse=True)[:3]
            preview = "  |  ".join(
                f"{t}: {c['winner']/sim_i*100:.1f}%" for t,c in top3
            )
            print(f"   {pct:5.0f}%  ({sim_i:,}/{n_sims:,})   Top 3 → {preview}")

        result = run_single_simulation(prob_cache, stats, avg_row)

        for team, stage in result["stage"].items():
            # Increment the counter for this team's deepest stage reached
            counts[team][STAGE_KEY[stage]] += 1
            counts[team]["total_goals"]    += result["goals"].get(team, 0)

    print(f"\n   100%  ({n_sims:,}/{n_sims:,})  Done.")
    return counts


# ─── RESULTS FORMATTER ────────────────────────────────────────────────────────

def format_results(counts: dict, n_sims: int) -> list[dict]:
    """
    LEARNING NOTE — Converting counts to probabilities:
    Probability = (times event occurred) / (total trials).
    We also add group_stage_exit_probability = 1 - probability of advancing.

    The results are sorted by win_probability so the frontend can render a
    leaderboard without any additional sorting.
    """
    results = []

    for team, c in counts.items():
        win_prob    = round(c["winner"]      / n_sims, 5)
        final_prob  = round((c["winner"] + c["final"]) / n_sims, 5)
        sf_prob     = round((c["winner"] + c["final"] + c["sf"]) / n_sims, 5)
        qf_prob     = round((c["winner"] + c["final"] + c["sf"] + c["qf"]) / n_sims, 5)
        r16_prob    = round((c["winner"] + c["final"] + c["sf"] +
                             c["qf"] + c["r16"]) / n_sims, 5)
        r32_prob    = round((c["winner"] + c["final"] + c["sf"] +
                             c["qf"] + c["r16"] + c["r32"]) / n_sims, 5)
        group_exit  = round(c["group_stage"] / n_sims, 5)
        avg_goals   = round(c["total_goals"] / n_sims, 3)

        results.append({
            "team":                       team,
            "win_probability":            win_prob,
            "final_probability":          final_prob,
            "semifinal_probability":      sf_prob,
            "quarterfinal_probability":   qf_prob,
            "r16_probability":            r16_prob,
            "r32_probability":            r32_prob,
            "group_stage_exit_probability": group_exit,
            "expected_goals_tournament":  avg_goals,
            "simulations_run":            n_sims,
        })

    results.sort(key=lambda x: x["win_probability"], reverse=True)
    return results


# ─── SAVE & REPORT ────────────────────────────────────────────────────────────

def save_results(results: list[dict]):
    """
    LEARNING NOTE — JSON as the data-exchange format:
    JSON (JavaScript Object Notation) is the universal language between a
    Python backend and a React frontend.  Python's json module serialises
    our list of dicts into a text file the Node.js API can serve directly
    and the React dashboard can fetch and render.
    """
    payload = {
        "generated_at":    datetime.now().isoformat(),
        "simulations_run": N_SIMULATIONS,
        "teams":           results,
    }
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    size_kb = len(json.dumps(payload)) // 1024
    print(f"\n   Saved: {RESULTS_PATH}  ({size_kb} KB, {len(results)} teams)")


def print_leaderboard(results: list[dict], top_n: int = 16):
    """Print a ranked table of top_n teams and their tournament probabilities."""
    print("\n" + "=" * 90)
    print("WORLD CUP 2026 WIN PROBABILITIES — TOP 16")
    print("=" * 90)
    print(f"\n  {'#':<4} {'Team':<18} {'Win%':>6} {'Final%':>7} {'Semi%':>6} "
          f"{'QF%':>6} {'R16%':>5} {'Group exit%':>12} {'Exp Gls':>8}")
    print(f"  {'─'*88}")

    for i, r in enumerate(results[:top_n], 1):
        print(
            f"  {i:<4} {r['team']:<18} "
            f"{r['win_probability']*100:>5.1f}%  "
            f"{r['final_probability']*100:>6.1f}%  "
            f"{r['semifinal_probability']*100:>5.1f}%  "
            f"{r['quarterfinal_probability']*100:>5.1f}%  "
            f"{r['r16_probability']*100:>4.1f}%  "
            f"{r['group_stage_exit_probability']*100:>10.1f}%  "
            f"{r['expected_goals_tournament']:>7.2f}"
        )

    print(f"\n  Based on {N_SIMULATIONS:,} Monte Carlo simulations")
    print("=" * 90)


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def run_phase4():
    """
    LEARNING NOTE — Why Monte Carlo for a tournament?
    A tournament bracket is a sequential, path-dependent process: who you
    play in the quarter-final depends on who wins the other matches in your
    half of the bracket.  This kind of dependent-event chain is extremely
    hard to solve with algebra.  Monte Carlo sidesteps the math entirely —
    just simulate the whole thing and count outcomes.  Simple, powerful,
    and easy to extend with new features.
    """
    print("World Cup 2026 Predictor — Phase 4: Monte Carlo Simulator")
    print("=" * 65)
    print(f"  Groups : 12  |  Teams per group : 4  |  Total teams : 48")
    print(f"  Format : Group stage → R32 → R16 → QF → SF → Final")
    print(f"  Sims   : {N_SIMULATIONS:,}")

    print("\n[1/4] Loading model and team stats ...")
    pipeline, stats, avg_row, _ = load_model_and_stats()
    print(f"   Model loaded: {MODEL_PATH}")
    print(f"   Teams in stats: {len(stats)}")

    wc_teams_with_stats  = [t for t in ALL_WC_TEAMS if t in stats]
    wc_teams_using_avg   = [t for t in ALL_WC_TEAMS if t not in stats]
    print(f"   WC teams with stats   : {len(wc_teams_with_stats)}")
    if wc_teams_using_avg:
        print(f"   WC teams using avg    : {wc_teams_using_avg}")

    print("\n[2/4] Running Monte Carlo simulations ...")
    t_start = datetime.now()
    counts  = run_monte_carlo(pipeline, stats, avg_row, N_SIMULATIONS)
    elapsed = (datetime.now() - t_start).total_seconds()
    print(f"\n   Completed in {elapsed:.1f} seconds")

    print("\n[3/4] Formatting results ...")
    results = format_results(counts, N_SIMULATIONS)

    print("\n[4/4] Saving results ...")
    save_results(results)

    print_leaderboard(results)

    print("\n" + "=" * 65)
    print("Phase 4 complete.")
    print(f"  Results file : {RESULTS_PATH}")
    print(f"  Simulations  : {N_SIMULATIONS:,}")
    print(f"  Runtime      : {elapsed:.1f}s")
    print("=" * 65)
    print("\nNext command: python wc2026_simulator.py")
    print("Say 'next' when ready for Phase 5 — Node.js API")


if __name__ == "__main__":
    run_phase4()
