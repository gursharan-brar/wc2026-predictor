"""
World Cup 2026 Predictor — BUILD 2: Time Decay & Match Weighting
Author: Gursharan Singh Brar

WHAT THIS FILE DOES:
  Raw win/draw/loss rates treat a 2024 World Cup qualifier the same as a
  1991 friendly.  That is wrong on two counts: (1) recent results predict
  the future better than old ones, and (2) a competitive match under
  pressure tells us more about a team than a meaningless friendly.  This
  build assigns every one of the 32,290+ historical matches a COMBINED
  WEIGHT = time_weight * competition_weight, then recomputes every core
  rate/average as a weighted statistic.  The results are written to
  team_stats as new weighted_* columns (existing columns are untouched).

HOW TO RUN:
  python wc2026_weighted_features.py
"""

import sqlite3
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path

DB_PATH  = Path(r"C:\Users\gsb13\OneDrive\Desktop\predictor\wc2026.db")
DATA_DIR = Path(r"C:\Users\gsb13\OneDrive\Desktop\predictor\data")

pd.set_option("display.max_columns", 20)
pd.set_option("display.width",       160)
pd.set_option("display.float_format", "{:.4f}".format)

SEP = "=" * 70

# ─── NAME NORMALISATION (same canonical map used in BUILD 1 / wc2026_h2h.py) ──
CANONICAL = {
    "IR Iran": "Iran",
    "Côte d'Ivoire": "Ivory Coast", "Cote d'Ivoire": "Ivory Coast",
    "Cote d Ivoire": "Ivory Coast",
    "Cabo Verde": "Cape Verde",
    "Korea Republic": "South Korea", "Republic of Korea": "South Korea",
    "United States": "USA",
}

def cn(name: str) -> str:
    """
    LEARNING NOTE — Canonical name resolution:
    Identical logic to wc2026_h2h.cn().  Re-declared here (rather than
    imported) so this file can run standalone — it keeps team names
    consistent with the head_to_head table and team_stats joins.
    """
    if not name or not isinstance(name, str):
        return name
    return CANONICAL.get(name.strip(), name.strip())


# ─── TIME DECAY ───────────────────────────────────────────────────────────

def time_weight(years_ago: float) -> float:
    """
    LEARNING NOTE — Exponential time decay:
    A match from 10 years ago should still count for SOMETHING (teams carry
    long traditions), but a match from last month should count for much
    more.  The formula 0.2 + 0.8*exp(-0.3*years_ago) decays from 1.0 (today)
    towards a floor of 0.2 (it never fully forgets history) — at ~2.3 years
    the weight has halved, and by ~10 years it has nearly bottomed out.
    """
    years_ago = max(0.0, years_ago)
    return 0.2 + 0.8 * np.exp(-0.3 * years_ago)


# ─── COMPETITION WEIGHTING ────────────────────────────────────────────────

_MAJOR_CONTINENTAL = [
    "uefa euro", "copa am",                       # "Copa Am" survives the
    "african cup of nations", "afcon",            # mojibake of "América"
    "afc asian cup", "gold cup", "concacaf gold cup",
]

def competition_weight(competition: str) -> float:
    """
    LEARNING NOTE — Competition importance weighting:
    Not all matches carry equal signal.  A friendly is often a glorified
    training session (squad rotation, no real tactics); a World Cup final
    is the most pressure-tested 90 minutes in football.  We bucket every
    competition string into one of six tiers, checking the most specific
    categories first so e.g. "FIFA World Cup qualification" is never
    mistaken for "FIFA World Cup" finals.

        FIFA World Cup finals                      → 3.0
        Major continental finals (Euro/Copa/AFCON/
          Asian Cup/Gold Cup)                      → 2.5
        Continental qualifying (any other "*qualification*")
                                                    → 2.0
        FIFA World Cup qualifying                  → 1.5
        Nations League (any confederation)         → 1.2
        Friendlies                                 → 0.5
        Everything else (cups, regional games...)  → 1.0  (default)
    """
    if not competition or not isinstance(competition, str):
        return 1.0
    c = competition.lower().strip()

    if "friendl" in c:
        return 0.5
    if "nations league" in c:
        return 1.2
    if "fifa world cup" in c:
        return 1.5 if "qualif" in c else 3.0
    is_major = any(m in c for m in _MAJOR_CONTINENTAL)
    if "qualif" in c:
        return 2.0
    if is_major:
        return 2.5
    return 1.0


# ─── BUILD PER-TEAM-PERSPECTIVE MATCH LOG ─────────────────────────────────

def build_perspective_log() -> pd.DataFrame:
    """
    LEARNING NOTE — Expanding matches into team perspectives:
    Each row in match_results describes ONE match between two teams.  To
    compute "Brazil's weighted win rate" we need ONE ROW PER TEAM PER MATCH
    (a match contributes a row for the home team AND a row for the away
    team, each with their own goals_for / goals_against / result).  This is
    the classic "wide-to-long" reshape — it lets every later aggregation
    (groupby team_name) see a uniform W/D/L + weight per row.
    """
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT date, home_team, away_team, home_goals, away_goals, "
        "       result, competition "
        "FROM   match_results "
        "WHERE  date IS NOT NULL "
        "  AND  home_goals IS NOT NULL "
        "  AND  away_goals IS NOT NULL",
        conn
    )
    conn.close()

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df = df[df["date"] <= pd.Timestamp.now()]          # drop unplayed fixtures
    df["home_team"] = df["home_team"].apply(cn)
    df["away_team"] = df["away_team"].apply(cn)

    now = pd.Timestamp.now()
    df["years_ago"]        = (now - df["date"]).dt.days / 365.25
    df["time_weight"]      = df["years_ago"].apply(time_weight)
    df["competition_weight"] = df["competition"].apply(competition_weight)
    df["combined_weight"]  = df["time_weight"] * df["competition_weight"]

    home = pd.DataFrame({
        "team":               df["home_team"],
        "opponent":           df["away_team"],
        "date":               df["date"],
        "goals_for":          df["home_goals"],
        "goals_against":      df["away_goals"],
        "result_chr":         np.where(df["result"] == "home_win", "W",
                                np.where(df["result"] == "draw", "D", "L")),
        "competition":        df["competition"],
        "time_weight":        df["time_weight"],
        "competition_weight": df["competition_weight"],
        "combined_weight":    df["combined_weight"],
        "years_ago":          df["years_ago"],
    })
    away = pd.DataFrame({
        "team":               df["away_team"],
        "opponent":           df["home_team"],
        "date":               df["date"],
        "goals_for":          df["away_goals"],
        "goals_against":      df["home_goals"],
        "result_chr":         np.where(df["result"] == "away_win", "W",
                                np.where(df["result"] == "draw", "D", "L")),
        "competition":        df["competition"],
        "time_weight":        df["time_weight"],
        "competition_weight": df["competition_weight"],
        "combined_weight":    df["combined_weight"],
        "years_ago":          df["years_ago"],
    })

    log = pd.concat([home, away], ignore_index=True).sort_values(["team", "date"])
    return log


# ─── WEIGHTED FEATURE COMPUTATION ─────────────────────────────────────────

_POINTS = {"W": 3, "D": 1, "L": 0}

def _wavg(values: np.ndarray, weights: np.ndarray) -> float:
    """LEARNING NOTE — Weighted average helper: guards against an
    all-zero weight vector (would otherwise divide by zero)."""
    wsum = weights.sum()
    return float((values * weights).sum() / wsum) if wsum > 0 else np.nan


def compute_weighted_features_for_team(grp: pd.DataFrame) -> dict:
    """
    LEARNING NOTE — One team's full weighted feature vector:
    `grp` is every historical match this team has played, sorted
    chronologically.  We derive 13 weighted statistics here, each using
    `combined_weight` (= time_weight * competition_weight) so that recent,
    high-stakes matches dominate the signal while old friendlies barely
    register.
    """
    w   = grp["combined_weight"].values
    res = grp["result_chr"].values
    is_w = (res == "W").astype(float)
    is_d = (res == "D").astype(float)
    is_l = (res == "L").astype(float)
    gf   = grp["goals_for"].values.astype(float)
    ga   = grp["goals_against"].values.astype(float)

    weighted_win_rate    = _wavg(is_w, w)
    weighted_draw_rate   = _wavg(is_d, w)
    weighted_loss_rate   = _wavg(is_l, w)
    weighted_gf_pg       = _wavg(gf, w)
    weighted_ga_pg       = _wavg(ga, w)
    weighted_gd_pg       = (weighted_gf_pg - weighted_ga_pg
                            if pd.notna(weighted_gf_pg) and pd.notna(weighted_ga_pg)
                            else np.nan)

    # weighted_form_momentum — last 10 matches, weighted by combined_weight,
    # points normalised to a 0-1 scale (W=3 -> 1.0, D=1 -> 0.333, L=0 -> 0.0)
    last10 = grp.tail(10)
    if len(last10):
        pts10 = last10["result_chr"].map(_POINTS).values.astype(float) / 3.0
        weighted_form_momentum = _wavg(pts10, last10["combined_weight"].values)
    else:
        weighted_form_momentum = np.nan

    # competitive_win_rate — only matches whose COMPETITION weight >= 1.5
    # (qualifiers and finals; excludes friendlies and Nations League games)
    comp_mask = grp["competition_weight"] >= 1.5
    if comp_mask.any():
        sub = grp[comp_mask]
        competitive_win_rate = _wavg(
            (sub["result_chr"].values == "W").astype(float),
            sub["combined_weight"].values
        )
    else:
        competitive_win_rate = np.nan

    # wc_specific_win_rate — only FIFA World Cup FINALS matches (weight == 3.0)
    wc_mask = np.isclose(grp["competition_weight"].values, 3.0)
    if wc_mask.any():
        sub = grp[wc_mask]
        wc_specific_win_rate = _wavg(
            (sub["result_chr"].values == "W").astype(float),
            sub["combined_weight"].values
        )
    else:
        wc_specific_win_rate = np.nan

    # recent_form_6m / 12m — weighted points-per-game (0-1) within the window
    recent_6m  = grp[grp["years_ago"] <= 0.5]
    recent_12m = grp[grp["years_ago"] <= 1.0]

    def _recent_form(sub: pd.DataFrame) -> float:
        if not len(sub):
            return np.nan
        pts = sub["result_chr"].map(_POINTS).values.astype(float) / 3.0
        return _wavg(pts, sub["combined_weight"].values)

    recent_form_6m  = _recent_form(recent_6m)
    recent_form_12m = _recent_form(recent_12m)

    # recent_competitive_form_12m — last 12 months AND competition_weight >= 1.5
    recent_comp_12m = recent_12m[recent_12m["competition_weight"] >= 1.5]
    recent_competitive_form_12m = _recent_form(recent_comp_12m)

    # big_game_clutch_rate — "knockout stage" proxy.
    #   match_results has NO per-match round/stage column, so a literal
    #   "knockout stages only" filter is impossible from this schema.  The
    #   closest available proxy is matches at the very top tier of
    #   competition (World Cup finals + major continental championship
    #   finals, competition_weight >= 2.5) — these are the highest-pressure,
    #   closest-to-knockout fixtures the data can identify.
    clutch_mask = grp["competition_weight"] >= 2.5
    if clutch_mask.any():
        sub = grp[clutch_mask]
        big_game_clutch_rate = _wavg(
            (sub["result_chr"].values == "W").astype(float),
            sub["combined_weight"].values
        )
    else:
        big_game_clutch_rate = np.nan

    return {
        "weighted_win_rate":               round(weighted_win_rate, 4)    if pd.notna(weighted_win_rate)    else None,
        "weighted_draw_rate":              round(weighted_draw_rate, 4)   if pd.notna(weighted_draw_rate)   else None,
        "weighted_loss_rate":              round(weighted_loss_rate, 4)   if pd.notna(weighted_loss_rate)   else None,
        "weighted_goals_scored_per_game":  round(weighted_gf_pg, 4)       if pd.notna(weighted_gf_pg)       else None,
        "weighted_goals_conceded_per_game":round(weighted_ga_pg, 4)       if pd.notna(weighted_ga_pg)       else None,
        "weighted_goal_difference_per_game":round(weighted_gd_pg, 4)      if pd.notna(weighted_gd_pg)       else None,
        "weighted_form_momentum":          round(weighted_form_momentum, 4) if pd.notna(weighted_form_momentum) else None,
        "competitive_win_rate":            round(competitive_win_rate, 4) if pd.notna(competitive_win_rate) else None,
        "wc_specific_win_rate":            round(wc_specific_win_rate, 4) if pd.notna(wc_specific_win_rate) else None,
        "recent_form_6m":                  round(recent_form_6m, 4)       if pd.notna(recent_form_6m)       else None,
        "recent_form_12m":                 round(recent_form_12m, 4)      if pd.notna(recent_form_12m)      else None,
        "recent_competitive_form_12m":     round(recent_competitive_form_12m, 4) if pd.notna(recent_competitive_form_12m) else None,
        "big_game_clutch_rate":            round(big_game_clutch_rate, 4) if pd.notna(big_game_clutch_rate) else None,
        "_matches_used":                   int(len(grp)),
    }


WEIGHTED_COLUMNS = [
    "weighted_win_rate", "weighted_draw_rate", "weighted_loss_rate",
    "weighted_goals_scored_per_game", "weighted_goals_conceded_per_game",
    "weighted_goal_difference_per_game", "weighted_form_momentum",
    "competitive_win_rate", "wc_specific_win_rate",
    "recent_form_6m", "recent_form_12m", "recent_competitive_form_12m",
    "big_game_clutch_rate",
]


def compute_all_weighted_features(log: pd.DataFrame) -> pd.DataFrame:
    """
    LEARNING NOTE — Per-team aggregation:
    groupby(team) hands each team's full match log to
    compute_weighted_features_for_team(); we collect the resulting dicts
    into one DataFrame indexed by team_name, ready to merge into team_stats.
    """
    rows = []
    for team, grp in log.groupby("team"):
        feats = compute_weighted_features_for_team(grp.sort_values("date"))
        feats["team_name"] = team
        rows.append(feats)
    return pd.DataFrame(rows).set_index("team_name")


# ─── WRITE NEW COLUMNS TO team_stats ──────────────────────────────────────

def write_to_team_stats(weighted_df: pd.DataFrame):
    """
    LEARNING NOTE — Additive schema migration:
    `ALTER TABLE ... ADD COLUMN` is the safe way to extend an existing
    table without touching its current data.  We check PRAGMA table_info
    first so re-running this script is idempotent (no "duplicate column"
    errors).  Every value is written via a parameterised UPDATE — never by
    string-formatting SQL — to eliminate injection risk entirely.
    """
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    existing_cols = {row[1] for row in cursor.execute("PRAGMA table_info(team_stats)").fetchall()}
    added = []
    for col in WEIGHTED_COLUMNS:
        if col not in existing_cols:
            cursor.execute(f"ALTER TABLE team_stats ADD COLUMN {col} REAL")
            added.append(col)
    conn.commit()
    print(f"  Columns added to team_stats: {len(added)} ({', '.join(added) if added else 'none — already present'})")

    updated, skipped = 0, 0
    set_clause = ", ".join(f"{c} = ?" for c in WEIGHTED_COLUMNS)
    for team_name, row in weighted_df.iterrows():
        values = [row[c] for c in WEIGHTED_COLUMNS]
        values = [None if (v is None or (isinstance(v, float) and np.isnan(v))) else v for v in values]
        cursor.execute(
            f"UPDATE team_stats SET {set_clause} WHERE team_name = ?",
            (*values, team_name)
        )
        if cursor.rowcount > 0:
            updated += 1
        else:
            skipped += 1   # team not present in team_stats — warn, don't crash

    conn.commit()
    conn.close()
    print(f"  team_stats rows updated : {updated}")
    if skipped:
        print(f"  ⚠ teams with no matching team_stats row (skipped): {skipped}")


# ─── PRINT SECTION: OLD vs WEIGHTED COMPARISON FOR ALL 48 WC TEAMS ────────

def load_wc_teams() -> list:
    """LEARNING NOTE — WC 2026 roster: pulled from teams.csv, filtering
    out placeholder rows ('Winner Group X', 'TBD...') that aren't real
    national teams yet."""
    teams_df = pd.read_csv(DATA_DIR / "teams.csv")
    return sorted(set(
        cn(t) for t in teams_df["team_name"].tolist()
        if not str(t).startswith("Winner") and not str(t).startswith("TBD")
    ))


def print_comparison(weighted_df: pd.DataFrame):
    """
    LEARNING NOTE — Old vs new, side by side:
    The whole point of weighting is to correct misleading raw stats.  This
    section prints, for all 48 WC 2026 teams, the unweighted win_rate
    already stored in team_stats next to the new weighted_win_rate, then
    ranks the deltas to surface which teams' "true" strength differs most
    from their face-value record — and flags teams whose raw record looks
    inflated mostly by friendlies (a big drop from win_rate to
    competitive_win_rate is the tell).
    """
    print(f"\n{SEP}")
    print("SECTION — Old win_rate vs weighted_win_rate (all 48 WC 2026 teams)")
    print(SEP)

    wc_teams = load_wc_teams()
    print(f"  WC 2026 teams loaded: {len(wc_teams)}")

    conn = sqlite3.connect(DB_PATH)
    old = pd.read_sql_query(
        "SELECT team_name, win_rate, matches_played FROM team_stats", conn
    ).set_index("team_name")
    conn.close()

    rows = []
    for team in wc_teams:
        old_wr = old.loc[team, "win_rate"] if team in old.index else None
        played = old.loc[team, "matches_played"] if team in old.index else None
        new_wr = weighted_df.loc[team, "weighted_win_rate"] if team in weighted_df.index else None
        comp_wr = weighted_df.loc[team, "competitive_win_rate"] if team in weighted_df.index else None
        rows.append({
            "team": team,
            "matches_played": played,
            "old_win_rate": old_wr,
            "weighted_win_rate": new_wr,
            "competitive_win_rate": comp_wr,
            "delta": (new_wr - old_wr) if (new_wr is not None and old_wr is not None) else None,
            "friendly_inflation": (old_wr - comp_wr) if (old_wr is not None and comp_wr is not None) else None,
        })
    cmp_df = pd.DataFrame(rows)

    print(f"\n  {'Team':<16} {'Played':>7} {'Old WR':>9} {'Weighted WR':>13} {'Competitive WR':>15} {'Delta':>8}")
    print("  " + "─" * 75)
    for _, r in cmp_df.sort_values("team").iterrows():
        def fmt(x): return f"{x*100:6.1f}%" if pd.notna(x) else "    N/A"
        delta_str = f"{r['delta']*100:+6.1f}%" if pd.notna(r["delta"]) else "    N/A"
        print(f"  {r['team']:<16} {int(r['matches_played']) if pd.notna(r['matches_played']) else 0:>7} "
              f"{fmt(r['old_win_rate']):>9} {fmt(r['weighted_win_rate']):>13} "
              f"{fmt(r['competitive_win_rate']):>15} {delta_str:>8}")

    valid = cmp_df.dropna(subset=["delta"])

    print(f"\n{SEP}")
    print("  TOP 10 IMPROVED  (weighted_win_rate notably higher than old win_rate)")
    print(SEP)
    for _, r in valid.nlargest(10, "delta").iterrows():
        print(f"    {r['team']:<16}  old {r['old_win_rate']*100:5.1f}%  →  weighted {r['weighted_win_rate']*100:5.1f}%   ({r['delta']*100:+.1f} pts)")

    print(f"\n{SEP}")
    print("  TOP 10 DROPPED   (weighted_win_rate notably lower than old win_rate)")
    print(SEP)
    for _, r in valid.nsmallest(10, "delta").iterrows():
        print(f"    {r['team']:<16}  old {r['old_win_rate']*100:5.1f}%  →  weighted {r['weighted_win_rate']*100:5.1f}%   ({r['delta']*100:+.1f} pts)")

    inflated = cmp_df.dropna(subset=["friendly_inflation"]).nlargest(10, "friendly_inflation")
    print(f"\n{SEP}")
    print("  TOP 10 'FRIENDLY-INFLATED' TEAMS  (old win_rate >> competitive_win_rate)")
    print("  i.e. their headline record leans heavily on low-stakes friendlies")
    print(SEP)
    for _, r in inflated.iterrows():
        print(f"    {r['team']:<16}  old {r['old_win_rate']*100:5.1f}%   competitive-only {r['competitive_win_rate']*100:5.1f}%   "
              f"(gap {r['friendly_inflation']*100:+.1f} pts)")


# ─── MAIN ─────────────────────────────────────────────────────────────────

def run_build2():
    t0 = datetime.now()
    print(f"\n{SEP}")
    print("BUILD 2 — Time Decay & Match Weighting")
    print(SEP)
    print(f"  Start time: {t0.strftime('%H:%M:%S')}")
    print(f"  time_weight(years_ago) = 0.2 + 0.8 * exp(-0.3 * years_ago)")
    print(f"  combined_weight = time_weight * competition_weight")

    # 1. Build the long (team-perspective) match log with weights attached
    log = build_perspective_log()
    print(f"\n  Perspective rows built : {len(log):,}  (2 per match, played matches only)")
    print(f"  Unique teams found     : {log['team'].nunique():,}")
    print(f"  Date range             : {log['date'].min().date()} → {log['date'].max().date()}")

    # Spot-check the weighting formulas with a few example matches
    sample = log.sample(min(5, len(log)), random_state=42)
    print(f"\n  Sample weight calculations:")
    print(f"  {'Team':<14}{'Date':<12}{'Competition':<28}{'Yrs ago':>8}{'TimeW':>8}{'CompW':>8}{'Combined':>10}")
    for _, r in sample.iterrows():
        print(f"  {r['team']:<14}{r['date'].date()!s:<12}{r['competition'][:27]:<28}"
              f"{r['years_ago']:>8.2f}{r['time_weight']:>8.3f}{r['competition_weight']:>8.2f}{r['combined_weight']:>10.3f}")

    # 2. Compute the 13 weighted features for every team
    weighted_df = compute_all_weighted_features(log)
    print(f"\n  Weighted feature vectors computed for {len(weighted_df):,} teams")
    print(f"  Avg matches used per team (weighted history): {weighted_df['_matches_used'].mean():.1f}")

    # 3. Write new columns into team_stats (additive — never overwrites)
    print(f"\n{SEP}")
    print("  Writing weighted_* columns to team_stats")
    print(SEP)
    write_to_team_stats(weighted_df)

    # 4. Print the full old-vs-new comparison for the 48 WC 2026 teams
    print_comparison(weighted_df)

    elapsed = (datetime.now() - t0).total_seconds()
    print(f"\n{SEP}")
    print(f"BUILD 2 COMPLETE — {elapsed:.1f}s")
    print(f"  {len(WEIGHTED_COLUMNS)} new weighted_* columns added to team_stats:")
    for c in WEIGHTED_COLUMNS:
        print(f"    - {c}")
    print(f"\nSay 'continue' for BUILD 3 — Elo rating system.")
    print(SEP)


if __name__ == "__main__":
    run_build2()
