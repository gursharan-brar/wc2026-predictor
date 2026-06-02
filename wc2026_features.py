"""
World Cup 2026 Predictor — Phase 2: Advanced Feature Engineering
Author: Gursharan Singh Brar

WHAT THIS FILE DOES:
  Reads raw match data and WC history from the SQLite database built in Phase 1,
  then computes 8 advanced features per team and writes them back to team_stats.

  These features are what the machine-learning model (Phase 3) will actually
  learn from. Better features → better predictions. This step is called
  "feature engineering" and is often the most important part of an ML project.

HOW TO RUN:
  python wc2026_features.py

REQUIREMENTS:
  Phase 1 must have been run first so wc2026.db exists and has data.
  pip install numpy pandas  (already installed from Phase 1)
"""

import sqlite3
import numpy as np
import pandas as pd
from datetime import datetime

DB_PATH = "wc2026.db"

# Teams hosting WC 2026 — they get a crowd/logistics advantage
HOST_NATIONS = {"USA", "Canada", "Mexico"}

# Stage → base points for tournament experience scoring
STAGE_POINTS = {
    "Winner":        10,
    "Runner-up":      7,
    "3rd place":      5,
    "4th place":      5,
    "Semi-final":     5,
    "Quarter-final":  3,
    "Round of 16":    1,
    "Group stage":    0,
}

# Recency weight per tournament year
YEAR_WEIGHTS = {2022: 1.0, 2018: 0.7, 2014: 0.4}


# ─── SCHEMA MIGRATION ─────────────────────────────────────────────────────────

def add_columns_if_missing():
    """
    LEARNING NOTE — Schema migration:
    We built team_stats in Phase 1 with only the basic columns.  Now we need
    to add 8 new columns.  SQLite doesn't support "ADD COLUMN IF NOT EXISTS"
    directly, but we can catch the error when the column already exists and
    move on.  This makes the script safe to re-run without destroying data.
    """
    new_columns = [
        ("home_win_rate",               "REAL DEFAULT 0"),
        ("away_win_rate",               "REAL DEFAULT 0"),
        ("big_game_win_rate",           "REAL DEFAULT 0"),
        ("goals_scored_last_5",         "REAL DEFAULT 0"),
        ("goals_conceded_last_5",       "REAL DEFAULT 0"),
        ("defensive_strength",          "REAL DEFAULT 1"),
        ("offensive_strength",          "REAL DEFAULT 1"),
        ("tournament_experience_score", "REAL DEFAULT 0"),
        ("host_nation_bonus",           "REAL DEFAULT 0"),
        ("form_momentum",               "REAL DEFAULT 0"),
    ]

    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for col_name, col_def in new_columns:
        try:
            cursor.execute(
                f"ALTER TABLE team_stats ADD COLUMN {col_name} {col_def}"
            )
            print(f"   + Added column: {col_name}")
        except sqlite3.OperationalError:
            pass   # column already exists — safe to skip

    conn.commit()
    conn.close()
    print("   ✅ Schema up to date")


# ─── FEATURE: HOME / AWAY WIN RATES ──────────────────────────────────────────

def compute_home_away_win_rates(team_name: str, matches_df: pd.DataFrame) -> dict:
    """
    LEARNING NOTE — Home vs away split:
    A team that wins 70% of games at home but only 30% away has a very different
    risk profile than one that wins 50% everywhere.  International tournaments
    are usually played at neutral venues, so away performance is often a better
    proxy.  Keeping both signals lets the model decide which matters more.

    Args:
        team_name:  The team we are computing for.
        matches_df: DataFrame of all their matches (home and away).

    Returns dict with home_win_rate and away_win_rate (0-1 floats).
    """
    home_games  = matches_df[matches_df["home_team"] == team_name]
    away_games  = matches_df[matches_df["away_team"] == team_name]

    home_wins   = (home_games["result"] == "home_win").sum()
    away_wins   = (away_games["result"] == "away_win").sum()

    home_wr = round(home_wins / len(home_games), 3) if len(home_games) > 0 else 0.0
    away_wr = round(away_wins / len(away_games), 3) if len(away_games) > 0 else 0.0

    return {"home_win_rate": home_wr, "away_win_rate": away_wr}


# ─── FEATURE: BIG GAME WIN RATE ───────────────────────────────────────────────

def compute_big_game_win_rate(
    team_name: str,
    matches_df: pd.DataFrame,
    top20_teams: set
) -> float:
    """
    LEARNING NOTE — Quality of opposition filter:
    Beating minnows tells you very little.  A team that wins consistently
    against top-20 ranked sides has proven it can perform under real pressure.
    This feature captures that signal by filtering the match list to games
    where the opponent was ranked top-20 at the time we scraped rankings.

    Note: we use the *current* top-20 list as a proxy because historical
    ranking snapshots aren't stored.  This is a deliberate simplification —
    good enough for a first model, and can be improved with time-series ranking
    data later.
    """
    big_games = matches_df[
        ((matches_df["home_team"] == team_name) & (matches_df["away_team"].isin(top20_teams))) |
        ((matches_df["away_team"] == team_name) & (matches_df["home_team"].isin(top20_teams)))
    ]

    if len(big_games) == 0:
        return 0.0

    wins = 0
    for _, row in big_games.iterrows():
        is_home = row["home_team"] == team_name
        if (is_home and row["result"] == "home_win") or \
           (not is_home and row["result"] == "away_win"):
            wins += 1

    return round(wins / len(big_games), 3)


# ─── FEATURE: GOALS LAST 5 ────────────────────────────────────────────────────

def compute_goals_last_5(team_name: str, matches_df: pd.DataFrame) -> dict:
    """
    LEARNING NOTE — Recency window:
    A team's last 5 games reflect *current* attacking and defensive form far
    better than a 20-game average.  If a team has conceded 8 goals in 5 games,
    their defence is in trouble right now even if their season average looks ok.
    We compute average goals scored and conceded over the most recent 5 matches.
    """
    recent = matches_df.sort_values("date", ascending=False).head(5)
    if recent.empty:
        return {"goals_scored_last_5": 0.0, "goals_conceded_last_5": 0.0}

    gf = gc = 0
    for _, row in recent.iterrows():
        is_home = row["home_team"] == team_name
        gf += row["home_goals"] if is_home else row["away_goals"]
        gc += row["away_goals"] if is_home else row["home_goals"]

    n = len(recent)
    return {
        "goals_scored_last_5":   round(gf / n, 2),
        "goals_conceded_last_5": round(gc / n, 2),
    }


# ─── FEATURE: DEFENSIVE / OFFENSIVE STRENGTH ─────────────────────────────────

def compute_strength_scores(all_stats: list[dict]) -> list[dict]:
    """
    LEARNING NOTE — Normalization:
    Raw goal counts are hard to compare across datasets.  A team that scores
    1.8 goals per game sounds good — but is it?  Normalization tells you *how
    good relative to everyone else*.

    Here we divide each team's average goals by the mean across all teams.
    - Score > 1.0 → better than average
    - Score < 1.0 → worse than average
    - Score = 1.0 → exactly average

    This is called "ratio normalization" (or sometimes just scaling against
    the tournament mean).  The ML model can now directly compare teams.

    defensive_strength: LOW is better (fewer goals conceded).
                        We invert it so HIGH = strong defence.
    offensive_strength: HIGH is better (more goals scored).
    """
    avg_scored    = np.mean([s["avg_goals_scored"]   for s in all_stats]) or 1.0
    avg_conceded  = np.mean([s["avg_goals_conceded"] for s in all_stats]) or 1.0

    for s in all_stats:
        raw_off = s["avg_goals_scored"]   / avg_scored   if avg_scored   > 0 else 1.0
        raw_def = s["avg_goals_conceded"] / avg_conceded if avg_conceded > 0 else 1.0

        s["offensive_strength"] = round(raw_off, 3)
        # Invert: conceding less than average → score > 1 (strong defence)
        s["defensive_strength"] = round(1 / raw_def if raw_def > 0 else 1.0, 3)

    return all_stats


# ─── FEATURE: TOURNAMENT EXPERIENCE SCORE ─────────────────────────────────────

def compute_tournament_experience(team_name: str, wc_df: pd.DataFrame) -> float:
    """
    LEARNING NOTE — Temporal decay weighting:
    A team that won the World Cup in 2014 but hasn't done well since is less
    dangerous than one that reached the semi-finals in 2022.  We apply a
    "decay factor" — each older tournament is worth less than the most recent.

    2022 weight = 1.0  (full credit, most relevant)
    2018 weight = 0.7  (some decay)
    2014 weight = 0.4  (most decayed)

    Points per stage:  Winner=10, Runner-up=7, Semi=5, QF=3, R16=1, Group=0

    The final score is the sum of (stage_points × year_weight) across all
    three tournaments the team participated in.  Max possible ≈ 10+7+4 = 21.
    """
    team_history = wc_df[wc_df["team_name"] == team_name]
    if team_history.empty:
        return 0.0

    score = 0.0
    for _, row in team_history.iterrows():
        year   = row["year"]
        stage  = row["stage_reached"]
        pts    = STAGE_POINTS.get(stage, 0)
        weight = YEAR_WEIGHTS.get(year, 0.0)
        score += pts * weight

    return round(score, 3)


# ─── FEATURE: HOST NATION BONUS ───────────────────────────────────────────────

def compute_host_bonus(team_name: str) -> float:
    """
    LEARNING NOTE — Domain knowledge as a feature:
    Pure statistics miss things that football fans know intuitively.  Host
    nations have home crowds, no travel fatigue, familiar pitches, and
    psychological momentum.  We encode this as a flat +0.08 bonus that gets
    added to the team's win probability in the simulator.

    USA, Canada, and Mexico are co-hosts for 2026.
    """
    return 0.08 if team_name in HOST_NATIONS else 0.0


# ─── FEATURE: FORM MOMENTUM ───────────────────────────────────────────────────

def compute_form_momentum(form_string: str) -> float:
    """
    LEARNING NOTE — Recency-weighted string encoding:
    The form string (e.g. "WWDLWWLWDW") is human-readable but useless to an
    ML model.  We convert each character to points (W=3, D=1, L=0) and then
    apply *exponentially higher weights to more recent matches* so that the
    most recent result matters most.

    Weight formula: w_i = 1 / (1 + i) where i=0 is the most recent game.
    After computing the weighted sum, we divide by the maximum possible score
    (all wins with the same weights) to get a 0-1 normalised value.

    Example: "WWW" → higher score than "LLW" even though both have one recent W,
    because "WWW" has three consecutive wins with full recency weighting.
    """
    if not form_string:
        return 0.0

    points_map = {"W": 3, "D": 1, "L": 0}
    total      = 0.0
    max_total  = 0.0

    for i, char in enumerate(form_string):
        weight     = 1.0 / (1.0 + i)   # most recent (i=0) gets weight 1.0
        pts        = points_map.get(char.upper(), 0)
        total     += pts * weight
        max_total += 3 * weight         # 3 is max (win)

    return round(total / max_total, 4) if max_total > 0 else 0.0


# ─── ORCHESTRATOR: COMPUTE ALL FEATURES FOR ONE TEAM ─────────────────────────

def compute_all_features_for_team(
    team_name: str,
    matches_df: pd.DataFrame,
    wc_df: pd.DataFrame,
    top20_teams: set,
    form_string: str
) -> dict:
    """
    LEARNING NOTE — Composing features:
    Each feature function above is small and focused on one thing.  This
    orchestrator calls all of them for a single team and merges the results
    into one dictionary.  Clean separation makes debugging easy — if one
    feature is wrong you know exactly which function to fix.
    """
    team_matches = matches_df[
        (matches_df["home_team"] == team_name) |
        (matches_df["away_team"] == team_name)
    ].copy()

    features = {"team_name": team_name}

    features.update(compute_home_away_win_rates(team_name, team_matches))
    features["big_game_win_rate"]           = compute_big_game_win_rate(team_name, team_matches, top20_teams)
    features.update(compute_goals_last_5(team_name, team_matches))
    features["tournament_experience_score"] = compute_tournament_experience(team_name, wc_df)
    features["host_nation_bonus"]           = compute_host_bonus(team_name)
    features["form_momentum"]               = compute_form_momentum(form_string)

    # defensive_strength and offensive_strength are filled in a second pass
    # (they need the full-group average — see compute_strength_scores)

    return features


# ─── DATABASE READ / WRITE ────────────────────────────────────────────────────

def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, set]:
    """
    LEARNING NOTE — Loading data for feature engineering:
    We pull three tables from SQLite into pandas DataFrames.  A DataFrame is
    like a spreadsheet in memory — rows and columns with fast filtering and
    math.  We also build the set of top-20 team names for the big_game filter.
    """
    conn = sqlite3.connect(DB_PATH)

    matches_df = pd.read_sql_query(
        "SELECT * FROM match_results ORDER BY date DESC",
        conn
    )
    wc_df = pd.read_sql_query(
        "SELECT * FROM wc_history",
        conn
    )
    stats_df = pd.read_sql_query(
        "SELECT team_name, avg_goals_scored, avg_goals_conceded, form_last_10 "
        "FROM team_stats",
        conn
    )
    rankings_df = pd.read_sql_query(
        "SELECT team_name FROM fifa_rankings ORDER BY rank LIMIT 20",
        conn
    )

    conn.close()

    top20 = set(rankings_df["team_name"].tolist())
    return matches_df, wc_df, stats_df, top20


def save_features(features_list: list[dict]):
    """
    LEARNING NOTE — Parameterized UPDATE:
    We use SQL UPDATE with ? placeholders instead of building strings like
    f"UPDATE ... SET col = {value}".  String formatting is a SQL injection
    risk and can also break on special characters (e.g. team names with
    apostrophes).  Parameterized queries are always the safe choice.
    """
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now    = datetime.now().isoformat()

    for f in features_list:
        cursor.execute("""
            UPDATE team_stats SET
                home_win_rate               = ?,
                away_win_rate               = ?,
                big_game_win_rate           = ?,
                goals_scored_last_5         = ?,
                goals_conceded_last_5       = ?,
                defensive_strength          = ?,
                offensive_strength          = ?,
                tournament_experience_score = ?,
                host_nation_bonus           = ?,
                form_momentum               = ?,
                calculated_at               = ?
            WHERE team_name = ?
        """, (
            f["home_win_rate"],
            f["away_win_rate"],
            f["big_game_win_rate"],
            f["goals_scored_last_5"],
            f["goals_conceded_last_5"],
            f["defensive_strength"],
            f["offensive_strength"],
            f["tournament_experience_score"],
            f["host_nation_bonus"],
            f["form_momentum"],
            now,
            f["team_name"],
        ))

    conn.commit()
    conn.close()
    print(f"   💾 Saved advanced features for {len(features_list)} teams")


# ─── TEAMS NOT YET IN team_stats (history-only teams) ────────────────────────

def ensure_all_wc_teams_have_stats(wc_df: pd.DataFrame):
    """
    LEARNING NOTE — Data completeness:
    Some teams appear in wc_history but have no match_results (e.g. they
    weren't in the API call list in Phase 1).  We still want their tournament
    experience score so we insert a skeleton row into team_stats for them.
    This prevents NULL-related crashes in Phase 3 when we join tables.
    """
    conn    = sqlite3.connect(DB_PATH)
    cursor  = conn.cursor()
    now     = datetime.now().isoformat()

    existing = {row[0] for row in cursor.execute("SELECT team_name FROM team_stats")}
    wc_teams = set(wc_df["team_name"].tolist())
    missing  = wc_teams - existing

    for team in missing:
        cursor.execute("""
            INSERT INTO team_stats
            (team_name, team_id, matches_played, wins, draws, losses,
             goals_scored, goals_conceded, win_rate, avg_goals_scored,
             avg_goals_conceded, form_last_10, calculated_at)
            VALUES (?, 0, 0, 0, 0, 0, 0, 0, 0.0, 0.0, 0.0, '', ?)
        """, (team, now))

    conn.commit()
    conn.close()

    if missing:
        print(f"   + Inserted skeleton rows for {len(missing)} WC history teams: {missing}")


# ─── REPORT ───────────────────────────────────────────────────────────────────

def print_feature_report():
    """Print a summary table of all computed features so you can sanity-check."""
    conn = sqlite3.connect(DB_PATH)
    df   = pd.read_sql_query("""
        SELECT
            team_name,
            win_rate,
            home_win_rate,
            away_win_rate,
            big_game_win_rate,
            offensive_strength,
            defensive_strength,
            tournament_experience_score,
            host_nation_bonus,
            form_momentum
        FROM team_stats
        ORDER BY tournament_experience_score DESC
    """, conn)
    conn.close()

    print("\n" + "="*90)
    print("📊  ADVANCED FEATURE REPORT")
    print("="*90)
    pd.set_option("display.max_columns", 20)
    pd.set_option("display.width",       200)
    pd.set_option("display.float_format", "{:.3f}".format)
    print(df.to_string(index=False))
    print("="*90)


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def run_phase2():
    """
    LEARNING NOTE — Pipeline pattern:
    A data pipeline is a sequence of steps where each step's output feeds the
    next step's input.  Here:
      1. Migrate schema    → make room for new columns
      2. Load raw data     → pull from SQLite into memory
      3. Ensure coverage   → add skeleton rows for any missing teams
      4. Compute features  → one team at a time
      5. Normalise         → defensive/offensive strength need the full group
      6. Save              → write back to SQLite
      7. Report            → human-readable sanity check
    """
    print("🌍 World Cup 2026 Predictor — Phase 2: Advanced Feature Engineering")
    print("="*70)

    print("\n[1/6] Migrating schema ...")
    add_columns_if_missing()

    print("\n[2/6] Loading data from database ...")
    matches_df, wc_df, stats_df, top20_teams = load_data()
    print(f"   Loaded {len(matches_df)} match records, "
          f"{len(wc_df)} WC history rows, "
          f"{len(stats_df)} team-stat rows")
    print(f"   Top-20 teams for big-game filter: {sorted(top20_teams)}")

    print("\n[3/6] Ensuring all WC history teams have stat rows ...")
    ensure_all_wc_teams_have_stats(wc_df)

    # Reload stats_df after potential inserts
    conn     = sqlite3.connect(DB_PATH)
    stats_df = pd.read_sql_query(
        "SELECT team_name, avg_goals_scored, avg_goals_conceded, form_last_10 FROM team_stats",
        conn
    )
    conn.close()

    print(f"\n[4/6] Computing individual features for {len(stats_df)} teams ...")
    all_features = []

    for _, row in stats_df.iterrows():
        team    = row["team_name"]
        form    = row["form_last_10"] or ""
        feats   = compute_all_features_for_team(
            team_name   = team,
            matches_df  = matches_df,
            wc_df       = wc_df,
            top20_teams = top20_teams,
            form_string = form,
        )
        # Carry over avg_goals stats needed for strength normalisation
        feats["avg_goals_scored"]   = row["avg_goals_scored"]
        feats["avg_goals_conceded"] = row["avg_goals_conceded"]
        all_features.append(feats)

    print(f"\n[5/6] Normalising offensive / defensive strength scores ...")
    all_features = compute_strength_scores(all_features)

    print(f"\n[6/6] Saving features to database ...")
    save_features(all_features)

    print_feature_report()

    print("\n" + "="*70)
    print("✅  Phase 2 complete.")
    print("   All advanced features written to team_stats table.")
    print("="*70)
    print("\n📁  Database: wc2026.db")
    print("🚀  Next command:  python wc2026_features.py")
    print("    Then say 'next' to start Phase 3 — Match Prediction Model")


if __name__ == "__main__":
    run_phase2()
