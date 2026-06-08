"""
World Cup 2026 Predictor — BUILD 3: Elo Rating System
Author: Gursharan Singh Brar

WHAT THIS FILE DOES:
  FIFA ranking points are a single static snapshot; win/draw/loss rates
  ignore opponent strength and match context entirely.  An Elo rating
  system fixes both: it is a continuously-updated number that rises when
  you beat strong opposition and falls when you lose to weak opposition,
  with the SIZE of each swing scaled by how surprising the result was, how
  important the competition was, and how big the winning margin was.  This
  build replays all ~49,000 historical matches in chronological order,
  producing a single current_elo per team plus a full elo_history ledger —
  both far more predictive signals than a static ranking snapshot.

HOW TO RUN:
  python wc2026_elo.py
"""

import sqlite3
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
from collections import defaultdict

DB_PATH  = Path(r"C:\Users\gsb13\OneDrive\Desktop\predictor\wc2026.db")
DATA_DIR = Path(r"C:\Users\gsb13\OneDrive\Desktop\predictor\data")

pd.set_option("display.max_columns", 20)
pd.set_option("display.width",       160)
pd.set_option("display.float_format", "{:.2f}".format)

SEP = "=" * 70

# ─── NAME NORMALISATION (same canonical map as BUILD 1 / BUILD 2) ────────
CANONICAL = {
    "IR Iran": "Iran",
    "Côte d'Ivoire": "Ivory Coast", "Cote d'Ivoire": "Ivory Coast",
    "Cote d Ivoire": "Ivory Coast",
    "Cabo Verde": "Cape Verde",
    "Korea Republic": "South Korea", "Republic of Korea": "South Korea",
    "United States": "USA",
}

def cn(name: str) -> str:
    """LEARNING NOTE — Canonical name resolution: identical to wc2026_h2h.cn()
    / wc2026_weighted_features.cn().  Re-declared so this file runs standalone."""
    if not name or not isinstance(name, str):
        return name
    return CANONICAL.get(name.strip(), name.strip())


def load_former_names_map() -> dict:
    """
    LEARNING NOTE — Historical name resolution:
    Nations change names (Zaire → DR Congo, Dahomey → Benin, Burma →
    Myanmar...).  former_names.csv records each old name with the modern
    equivalent it should be folded into.  We load it into a flat
    {former_name: current_name} dict — a quick check confirmed no former
    name maps to more than one current name, so a flat dict is safe (no
    date-range disambiguation needed).  Applied BEFORE cn() so e.g. "Zaire"
    becomes "DR Congo" and then passes through canonical spelling cleanup.
    """
    try:
        fn = pd.read_csv(DATA_DIR / "former_names.csv")
        return dict(zip(fn["former"].astype(str).str.strip(),
                        fn["current"].astype(str).str.strip()))
    except Exception as e:
        print(f"  ⚠ Could not load former_names.csv: {e}")
        return {}


def normalize_team(name: str, former_map: dict) -> str:
    """LEARNING NOTE — Two-stage normalisation: first resolve historical
    name changes (Zaire → DR Congo), THEN apply canonical spelling fixes
    (IR Iran → Iran).  Order matters — a former name might itself need
    canonical cleanup after translation to its modern form."""
    if not name or not isinstance(name, str):
        return name
    name = name.strip()
    name = former_map.get(name, name)
    return cn(name)


# ─── STARTING ELO ─────────────────────────────────────────────────────────

def load_fifa_points_map() -> dict:
    """LEARNING NOTE — Seeding Elo from FIFA points: the spec asks us to
    seed each team's very-first Elo rating with its FIFA ranking points
    (only 32 teams are in our fifa_rankings table — everyone else starts
    at the neutral baseline of 1200, per the spec)."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT team_name, points FROM fifa_rankings").fetchall()
    conn.close()
    return {team: float(pts) for team, pts in rows}


DEFAULT_START_ELO = 1200.0

def starting_elo(team: str, fifa_points: dict) -> float:
    """LEARNING NOTE — Per the spec: 'Use FIFA ranking points as starting
    value. Teams not in FIFA rankings: start at 1200.'  Applied the FIRST
    time a team is encountered chronologically (1990 onward) — this is a
    simplification (current FIFA points seed a 1990 rating) but it is
    exactly what the spec prescribes, and 35+ years of subsequent match
    processing washes out any seeding bias quickly."""
    return fifa_points.get(team, DEFAULT_START_ELO)


# ─── K-FACTOR (competition importance) ────────────────────────────────────

_MAJOR_CONTINENTAL = [
    "uefa euro", "copa am", "african cup of nations", "afcon",
    "afc asian cup", "gold cup", "concacaf gold cup",
]

def k_factor(competition: str) -> int:
    """
    LEARNING NOTE — K-factor = "how much should this single result move the
    rating?"  A World Cup shock should swing ratings hard; a dead-rubber
    friendly should barely register.  The spec gives 5 explicit tiers —
    World Cup (60), continental championships (50), WC qualifying (40),
    Nations League (30), friendlies (20).  Two tiers are NOT in the spec
    (continental qualifying, and the long tail of regional cups/games), so
    we INTERPOLATE sensibly between the given values and document it here:

        FIFA World Cup finals                        → 60   (spec)
        Major continental championship finals        → 50   (spec)
        FIFA World Cup qualifying                     → 40   (spec)
        Continental qualifying      [INTERPOLATED]    → 35   (between WCQ 40 and NL 30)
        Nations League                                → 30   (spec)
        Everything else (cups, regional tournaments)
                                    [INTERPOLATED]     → 25   (between NL 30 and Friendly 20)
        Friendlies                                     → 20   (spec)
    """
    if not competition or not isinstance(competition, str):
        return 25
    c = competition.lower().strip()

    if "friendl" in c:
        return 20
    if "nations league" in c:
        return 30
    if "fifa world cup" in c:
        return 40 if "qualif" in c else 60
    is_major = any(m in c for m in _MAJOR_CONTINENTAL)
    if "qualif" in c:
        return 35
    if is_major:
        return 50
    return 25


# ─── GOAL-DIFFERENCE MARGIN MULTIPLIER ─────────────────────────────────────

def margin_multiplier(goal_diff: int) -> float:
    """
    LEARNING NOTE — Margin of victory matters:
    Winning 1-0 barely proves superiority; winning 5-0 proves it
    emphatically.  We scale the K-factor up for blowouts so the rating
    reacts proportionally to the scale of the result, exactly per spec:
        |GD| 0   (draw)  → 1.00x
        |GD| 1           → 1.00x
        |GD| 2           → 1.50x
        |GD| 3 or 4      → 1.75x
        |GD| 5+          → 2.00x
    """
    gd = abs(goal_diff)
    if gd <= 1:
        return 1.0
    if gd == 2:
        return 1.5
    if gd in (3, 4):
        return 1.75
    return 2.0


# ─── LOAD MATCHES (chronological, with neutral-venue flag) ────────────────

def load_matches_chronological() -> pd.DataFrame:
    """
    LEARNING NOTE — Recovering the 'neutral venue' flag:
    match_results (our SQLite import) does NOT carry a neutral-venue column,
    but the original Kaggle source (data/results.csv, 49,353 rows) does.
    We left-join match_results back onto results.csv on
    (date, home_team, away_team) to recover `neutral` for ~98% of rows;
    the ~2% we can't match (mostly API-Football rows with slightly
    different spellings) default to neutral=False — i.e. we assume the
    listed home team had home advantage, the conservative default.
    """
    conn = sqlite3.connect(DB_PATH)
    mr = pd.read_sql_query(
        "SELECT id, date, home_team, away_team, home_goals, away_goals, "
        "       result, competition "
        "FROM   match_results "
        "WHERE  date IS NOT NULL "
        "  AND  home_goals IS NOT NULL "
        "  AND  away_goals IS NOT NULL",
        conn
    )
    conn.close()

    try:
        res = pd.read_csv(DATA_DIR / "results.csv",
                          usecols=["date", "home_team", "away_team", "neutral"])
        mr = mr.merge(res, on=["date", "home_team", "away_team"], how="left")
        recovered = mr["neutral"].notna().sum()
        print(f"  Neutral-venue flag recovered for {recovered:,} / {len(mr):,} matches "
              f"({recovered/len(mr)*100:.1f}%) via results.csv join")
    except Exception as e:
        print(f"  ⚠ Could not recover neutral flag from results.csv: {e}")
        mr["neutral"] = np.nan

    mr["neutral"] = mr["neutral"].infer_objects(copy=False).fillna(False).astype(bool)

    mr["date"] = pd.to_datetime(mr["date"], errors="coerce")
    mr = mr.dropna(subset=["date"])
    mr = mr[mr["date"] <= pd.Timestamp.now()]            # drop unplayed fixtures

    former_map = load_former_names_map()
    mr["home_team"] = mr["home_team"].apply(lambda t: normalize_team(t, former_map))
    mr["away_team"] = mr["away_team"].apply(lambda t: normalize_team(t, former_map))

    # CRITICAL: process strictly chronologically — Elo is a stateful, path-
    # dependent system.  Tie-break on the original row id for determinism.
    mr = mr.sort_values(["date", "id"]).reset_index(drop=True)
    return mr


# ─── CORE ELO PROCESSING LOOP ──────────────────────────────────────────────

def process_all_matches(matches: pd.DataFrame, fifa_points: dict):
    """
    LEARNING NOTE — The Elo update, step by step, for EVERY match:
      1. Look up (or seed) both teams' current ratings.
      2. Apply +100 home advantage UNLESS the venue is neutral.
      3. Compute the EXPECTED score via the logistic Elo formula:
             E_home = 1 / (1 + 10^((away_elo - eff_home_elo) / 400))
         (an evenly-matched game gives E_home = 0.50; a 200-point favourite
         gives roughly E_home ≈ 0.76)
      4. Compare to the ACTUAL score (win=1.0, draw=0.5, loss=0.0).
      5. The rating shift is:
             delta = K * margin_multiplier * (actual − expected)
         applied symmetrically: home gains exactly what away loses — Elo is
         a zero-sum accounting system, ratings only move relative to others.
    Returns: final ratings dict, starting ratings dict, and a long-format
    elo_history DataFrame (one row per team per match — 2 rows/match).
    """
    elo       = {}
    starting  = {}
    history   = []
    n         = len(matches)

    print(f"\n  Processing {n:,} matches chronologically "
          f"({matches['date'].min().date()} → {matches['date'].max().date()})...")

    for i, row in enumerate(matches.itertuples(index=False), 1):
        home, away = row.home_team, row.away_team
        if pd.isna(home) or pd.isna(away) or home == away:
            continue   # skip malformed rows — gracefully, with no crash

        if home not in elo:
            elo[home] = starting[home] = starting_elo(home, fifa_points)
        if away not in elo:
            elo[away] = starting[away] = starting_elo(away, fifa_points)

        home_elo, away_elo = elo[home], elo[away]
        eff_home_elo = home_elo + (0.0 if row.neutral else 100.0)

        expected_home = 1.0 / (1.0 + 10.0 ** ((away_elo - eff_home_elo) / 400.0))

        if row.result == "home_win":
            actual_home = 1.0
        elif row.result == "draw":
            actual_home = 0.5
        else:
            actual_home = 0.0

        gd   = int(row.home_goals) - int(row.away_goals)
        k    = k_factor(row.competition)
        mult = margin_multiplier(gd)
        delta = k * mult * (actual_home - expected_home)

        new_home_elo = home_elo + delta
        new_away_elo = away_elo - delta
        elo[home] = new_home_elo
        elo[away] = new_away_elo

        home_chr = "W" if actual_home == 1.0 else ("D" if actual_home == 0.5 else "L")
        away_chr = "L" if home_chr == "W" else ("D" if home_chr == "D" else "W")

        history.append({
            "date": row.date, "team_name": home, "opponent": away,
            "elo_before": round(home_elo, 2), "elo_after": round(new_home_elo, 2),
            "elo_change": round(delta, 2), "competition": row.competition,
            "k_factor": k, "margin_multiplier": mult,
            "is_home": 1, "neutral": int(row.neutral), "result": home_chr,
        })
        history.append({
            "date": row.date, "team_name": away, "opponent": home,
            "elo_before": round(away_elo, 2), "elo_after": round(new_away_elo, 2),
            "elo_change": round(-delta, 2), "competition": row.competition,
            "k_factor": k, "margin_multiplier": mult,
            "is_home": 0, "neutral": int(row.neutral), "result": away_chr,
        })

        if i % 5000 == 0 or i == n:
            print(f"    ...{i:,} / {n:,} matches processed "
                  f"({row.date.date()})  |  teams tracked: {len(elo)}")

    history_df = pd.DataFrame(history).sort_values(["team_name", "date"]).reset_index(drop=True)
    return elo, starting, history_df


# ─── WRITE elo_ratings AND elo_history TABLES ──────────────────────────────

def write_elo_tables(elo: dict, starting: dict, history_df: pd.DataFrame, matches: pd.DataFrame):
    """
    LEARNING NOTE — Two complementary tables:
      elo_ratings  → ONE row per team: final state (current_elo, starting
                     point, how many matches shaped it, when it last moved)
      elo_history  → ONE row per team PER MATCH: the full audit trail,
                     letting us answer "what was Brazil's Elo on 2018-07-06?"
                     or "show me the 10 biggest single-match rating swings"
    DROP + CREATE keeps this script idempotent (safe to re-run).
    Parameterised executemany — never raw string interpolation.
    """
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS elo_ratings")
    cursor.execute("""
        CREATE TABLE elo_ratings (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            team_name         TEXT UNIQUE,
            current_elo       REAL,
            starting_elo      REAL,
            matches_processed INTEGER,
            last_match_date   TEXT,
            net_change        REAL
        )
    """)
    last_date = (history_df.groupby("team_name")["date"].max()
                 .dt.strftime("%Y-%m-%d").to_dict())
    matches_n = history_df.groupby("team_name").size().to_dict()
    rating_rows = [
        (team, round(elo[team], 2), round(starting[team], 2),
         int(matches_n.get(team, 0)), last_date.get(team),
         round(elo[team] - starting[team], 2))
        for team in elo
    ]
    cursor.executemany(
        "INSERT INTO elo_ratings (team_name, current_elo, starting_elo, "
        "matches_processed, last_match_date, net_change) VALUES (?,?,?,?,?,?)",
        rating_rows
    )

    cursor.execute("DROP TABLE IF EXISTS elo_history")
    cursor.execute("""
        CREATE TABLE elo_history (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            date              TEXT,
            team_name         TEXT,
            opponent          TEXT,
            elo_before        REAL,
            elo_after         REAL,
            elo_change        REAL,
            competition       TEXT,
            k_factor          INTEGER,
            margin_multiplier REAL,
            is_home           INTEGER,
            neutral           INTEGER,
            result            TEXT
        )
    """)
    hist_rows = [
        (r.date.strftime("%Y-%m-%d"), r.team_name, r.opponent,
         r.elo_before, r.elo_after, r.elo_change, r.competition,
         int(r.k_factor), r.margin_multiplier, int(r.is_home), int(r.neutral), r.result)
        for r in history_df.itertuples(index=False)
    ]
    cursor.executemany(
        "INSERT INTO elo_history (date, team_name, opponent, elo_before, elo_after, "
        "elo_change, competition, k_factor, margin_multiplier, is_home, neutral, result) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        hist_rows
    )

    conn.commit()
    conn.close()
    print(f"\n  ✓ elo_ratings table written  : {len(rating_rows):,} teams")
    print(f"  ✓ elo_history table written  : {len(hist_rows):,} rows")


# ─── DERIVE team_stats ELO COLUMNS ─────────────────────────────────────────

ELO_COLUMNS = [
    "current_elo", "elo_trend_6m", "elo_trend_12m",
    "elo_vs_tournament_avg", "peak_elo_last_4y", "elo_volatility",
]


def _elo_as_of(team_hist: pd.DataFrame, cutoff: pd.Timestamp, fallback: float) -> float:
    """LEARNING NOTE — Point-in-time lookup: walks a team's chronological
    elo_history and returns the rating AFTER its most recent match on or
    before `cutoff`.  If the team had no matches yet at that point in time,
    we fall back to its starting Elo (the best available estimate)."""
    sub = team_hist[team_hist["date"] <= cutoff]
    if sub.empty:
        return fallback
    return float(sub.iloc[-1]["elo_after"])


def compute_elo_team_stats_columns(elo: dict, starting: dict, history_df: pd.DataFrame,
                                   wc_teams: list) -> pd.DataFrame:
    """
    LEARNING NOTE — Six derived signals from the raw Elo ledger:
      current_elo            → latest rating (the headline number)
      elo_trend_6m / 12m     → current minus the rating from 6/12 months
                               ago — is this team rising or fading RIGHT NOW?
      elo_vs_tournament_avg  → how this team compares to the average Elo of
                               the 42 confirmed WC 2026 teams (context: a
                               1700 rating means very different things in a
                               weak group vs a "Group of Death")
      peak_elo_last_4y       → highest rating reached in the last 4 years —
                               captures "have they shown they CAN play at
                               this level recently?" even if currently dipped
      elo_volatility         → standard deviation of single-match rating
                               swings over their last 20 games — high
                               volatility = unpredictable / streaky team
    """
    now      = pd.Timestamp.now()
    cutoff_6m  = now - pd.DateOffset(months=6)
    cutoff_12m = now - pd.DateOffset(months=12)
    cutoff_4y  = now - pd.DateOffset(years=4)

    tournament_avg = float(np.mean([elo[t] for t in wc_teams if t in elo]))

    grouped = {team: g.sort_values("date") for team, g in history_df.groupby("team_name")}

    rows = []
    for team in elo:
        g = grouped.get(team, history_df.iloc[0:0])
        cur = elo[team]

        elo_6m_ago  = _elo_as_of(g, cutoff_6m,  starting[team])
        elo_12m_ago = _elo_as_of(g, cutoff_12m, starting[team])

        recent4y = g[g["date"] >= cutoff_4y]
        peak_4y  = float(recent4y["elo_after"].max()) if len(recent4y) else cur

        last20 = g.tail(20)
        volatility = float(last20["elo_change"].std(ddof=0)) if len(last20) >= 2 else 0.0

        rows.append({
            "team_name":              team,
            "current_elo":            round(cur, 2),
            "elo_trend_6m":           round(cur - elo_6m_ago, 2),
            "elo_trend_12m":          round(cur - elo_12m_ago, 2),
            "elo_vs_tournament_avg":  round(cur - tournament_avg, 2),
            "peak_elo_last_4y":       round(peak_4y, 2),
            "elo_volatility":         round(volatility, 2),
        })

    return pd.DataFrame(rows).set_index("team_name")


def write_to_team_stats(elo_stats_df: pd.DataFrame):
    """LEARNING NOTE — Same additive-migration pattern as BUILD 2:
    ALTER TABLE ADD COLUMN guarded by PRAGMA table_info (idempotent),
    parameterised UPDATE per row (no string-built SQL)."""
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    existing = {r[1] for r in cursor.execute("PRAGMA table_info(team_stats)").fetchall()}
    added = []
    for col in ELO_COLUMNS:
        if col not in existing:
            cursor.execute(f"ALTER TABLE team_stats ADD COLUMN {col} REAL")
            added.append(col)
    conn.commit()
    print(f"  Columns added to team_stats: {len(added)} ({', '.join(added) if added else 'none — already present'})")

    set_clause = ", ".join(f"{c} = ?" for c in ELO_COLUMNS)
    updated, skipped = 0, 0
    for team_name, row in elo_stats_df.iterrows():
        values = [None if pd.isna(row[c]) else float(row[c]) for c in ELO_COLUMNS]
        cursor.execute(f"UPDATE team_stats SET {set_clause} WHERE team_name = ?",
                       (*values, team_name))
        updated += 1 if cursor.rowcount > 0 else 0
        skipped += 1 if cursor.rowcount == 0 else 0

    conn.commit()
    conn.close()
    print(f"  team_stats rows updated     : {updated}")
    if skipped:
        print(f"  ⚠ teams with no matching team_stats row (skipped): {skipped}")


# ─── HELPERS: WC 2026 TEAMS & GROUPS ───────────────────────────────────────

def load_wc_groups() -> dict:
    """LEARNING NOTE — Group draw from teams.csv: returns {letter: [teams]}
    for the 12 confirmed groups, using each team's ACTUAL teams.csv name
    (placeholder slots like 'Winner UEFA Playoff D' kept verbatim — we
    can't rate a team that doesn't exist yet)."""
    teams_df = pd.read_csv(DATA_DIR / "teams.csv")
    groups = defaultdict(list)
    for _, r in teams_df.iterrows():
        letter = str(r["group_letter"]).strip()
        name   = str(r["team_name"]).strip()
        groups[letter].append(name if (name.startswith("Winner") or name.startswith("TBD"))
                              else cn(name))
    return dict(sorted(groups.items()))


def load_wc_teams_confirmed() -> list:
    """LEARNING NOTE — The 42 real (non-placeholder) WC 2026 teams."""
    teams_df = pd.read_csv(DATA_DIR / "teams.csv")
    return sorted(set(
        cn(t) for t in teams_df["team_name"].tolist()
        if not str(t).startswith("Winner") and not str(t).startswith("TBD")
    ))


# ─── PRINT SECTION 1: ELO RANKING vs FIFA RANKING ──────────────────────────

def print_elo_vs_fifa(elo: dict, wc_teams: list):
    """LEARNING NOTE — Two different worldviews compared: FIFA points use a
    fairly opaque, slow-moving formula; Elo reacts to every match
    immediately.  When the two strongly disagree about a team, that's a
    signal worth digging into — either Elo has spotted a trend FIFA hasn't
    caught up with yet, or FIFA's rules (which discount certain games) are
    seeing something Elo's simpler model misses."""
    print(f"\n{SEP}")
    print("SECTION 1 — Elo Ranking vs FIFA Ranking (42 confirmed WC 2026 teams)")
    print(SEP)

    conn = sqlite3.connect(DB_PATH)
    fifa = pd.read_sql_query("SELECT team_name, rank, points FROM fifa_rankings", conn)
    conn.close()
    fifa_rank_map  = dict(zip(fifa["team_name"], fifa["rank"]))
    fifa_pts_map   = dict(zip(fifa["team_name"], fifa["points"]))

    elo_sorted = sorted(wc_teams, key=lambda t: elo.get(t, 0), reverse=True)
    elo_rank_map = {t: i + 1 for i, t in enumerate(elo_sorted)}

    rows = []
    for t in wc_teams:
        rows.append({
            "team": t,
            "elo": elo.get(t, np.nan),
            "elo_rank": elo_rank_map[t],
            "fifa_rank": fifa_rank_map.get(t),
            "fifa_pts": fifa_pts_map.get(t),
        })
    df = pd.DataFrame(rows)

    print(f"\n  {'#':<4} {'Team':<16} {'Elo':>8} {'Elo Rank':>9} {'FIFA Rank':>10} {'FIFA Pts':>9} {'Disagreement':>13}")
    print("  " + "─" * 75)
    for _, r in df.sort_values("elo_rank").iterrows():
        fr = r["fifa_rank"]
        if pd.notna(fr):
            disagreement = int(fr) - int(r["elo_rank"])     # +ve = Elo rates them HIGHER than FIFA
            dis_str = f"{disagreement:+d}"
            fr_str  = f"{int(fr)}"
            fp_str  = f"{r['fifa_pts']:.1f}"
        else:
            dis_str, fr_str, fp_str = "  N/A", "  N/A", "  N/A"
        print(f"  {int(r['elo_rank']):<4} {r['team']:<16} {r['elo']:>8.1f} {int(r['elo_rank']):>9} "
              f"{fr_str:>10} {fp_str:>9} {dis_str:>13}")

    return df


def print_biggest_disagreements(df: pd.DataFrame):
    """LEARNING NOTE — Sorting by |disagreement|: a team Elo ranks 25 spots
    higher than FIFA does is either a hidden gem or a red flag for the
    model — either way, worth flagging explicitly."""
    print(f"\n{SEP}")
    print("SECTION 1b — Biggest Elo vs FIFA Disagreements")
    print(SEP)

    has_fifa = df.dropna(subset=["fifa_rank"]).copy()
    has_fifa["disagreement"] = has_fifa["fifa_rank"].astype(int) - has_fifa["elo_rank"].astype(int)
    has_fifa["abs_dis"]      = has_fifa["disagreement"].abs()

    top = has_fifa.nlargest(10, "abs_dis")
    print(f"\n  {'Team':<16} {'Elo Rank':>9} {'FIFA Rank':>10} {'Verdict':<28}")
    print("  " + "─" * 65)
    for _, r in top.sort_values("abs_dis", ascending=False).iterrows():
        d = int(r["disagreement"])
        verdict = (f"Elo rates them {abs(d)} spots HIGHER" if d > 0
                   else f"Elo rates them {abs(d)} spots LOWER")
        print(f"  {r['team']:<16} {int(r['elo_rank']):>9} {int(r['fifa_rank']):>10}   {verdict:<28}")


# ─── PRINT SECTION 2: MOST IMPROVED / DECLINED LAST 12 MONTHS ──────────────

def print_trend_leaders(elo_stats_df: pd.DataFrame, wc_teams: list):
    """LEARNING NOTE — elo_trend_12m is current_elo minus the rating from a
    year ago: a clean, directly comparable "momentum" number across every
    team regardless of their absolute rating level."""
    print(f"\n{SEP}")
    print("SECTION 2 — Most Improved / Declined Elo, Last 12 Months")
    print(SEP)

    sub = elo_stats_df.loc[elo_stats_df.index.isin(wc_teams)].copy()
    sub = sub.sort_values("elo_trend_12m", ascending=False)

    print(f"\n  ▲ TOP 10 MOST IMPROVED (last 12 months)")
    print("  " + "─" * 55)
    for team, r in sub.head(10).iterrows():
        print(f"    {team:<16}  {r['current_elo']:>8.1f} Elo   ({r['elo_trend_12m']:+7.1f} vs 12mo ago)")

    print(f"\n  ▼ TOP 10 MOST DECLINED (last 12 months)")
    print("  " + "─" * 55)
    for team, r in sub.tail(10).sort_values("elo_trend_12m").iterrows():
        print(f"    {team:<16}  {r['current_elo']:>8.1f} Elo   ({r['elo_trend_12m']:+7.1f} vs 12mo ago)")


# ─── PRINT SECTION 3: ELO WIN PROBABILITY FOR GROUP STAGE MATCHUPS ─────────

def elo_win_probability(elo_a: float, elo_b: float) -> float:
    """LEARNING NOTE — Standard Elo expected-score formula at a NEUTRAL
    venue (no home advantage — group stage WC matches are played at neutral
    sites): P(A beats B) = 1 / (1 + 10^((elo_b − elo_a)/400)).  This treats
    a draw as "half a win" for both sides — fine for ranking purposes, but
    the simulation in Section 4 splits this into real W/D/L probabilities."""
    return 1.0 / (1.0 + 10.0 ** ((elo_b - elo_a) / 400.0))


def print_group_stage_probabilities(elo: dict, groups: dict, avg_elo: float):
    """LEARNING NOTE — Pre-computing every group fixture's Elo-implied
    odds: with 12 groups of 4, that's C(4,2)=6 fixtures × 12 = 72 group
    matches.  Placeholder slots ('Winner UEFA Playoff D' etc.) don't have
    an Elo yet — we substitute the AVERAGE Elo of the 42 confirmed teams as
    a neutral stand-in and label them clearly."""
    print(f"\n{SEP}")
    print("SECTION 3 — Elo Win Probability for Every Group-Stage Matchup")
    print(SEP)

    from itertools import combinations
    total = 0
    placeholder_subs = 0

    for letter, teams in groups.items():
        print(f"\n  ── Group {letter}: {' · '.join(teams)} ──")
        for ta, tb in combinations(teams, 2):
            total += 1
            ea = elo.get(ta)
            eb = elo.get(tb)
            ta_label, tb_label = ta, tb
            if ea is None:
                ea = avg_elo
                ta_label += " (TBD→avg)"
                placeholder_subs += 1
            if eb is None:
                eb = avg_elo
                tb_label += " (TBD→avg)"
                placeholder_subs += 1
            p_a = elo_win_probability(ea, eb)
            print(f"    {ta_label:<26} ({ea:>6.0f})  vs  {tb_label:<26} ({eb:>6.0f})   "
                  f"→  {ta:<14} {p_a*100:5.1f}%   {tb:<14} {(1-p_a)*100:5.1f}%")

    print(f"\n  Total group-stage fixtures: {total}  |  Placeholder substitutions: {placeholder_subs}")


# ─── PRINT SECTION 4: ELO-ONLY TOURNAMENT SIMULATION ───────────────────────

R32_TEMPLATE = [
    ("W_A", "R_C"), ("W_B", "T_1"), ("W_C", "R_A"), ("R_B", "T_2"),
    ("W_D", "R_F"), ("W_E", "T_3"), ("W_F", "R_D"), ("R_E", "T_4"),
    ("W_G", "R_I"), ("W_H", "T_5"), ("W_I", "R_G"), ("R_H", "T_6"),
    ("W_J", "R_L"), ("W_K", "T_7"), ("W_L", "R_J"), ("R_K", "T_8"),
]
QF_PAIRS    = [(0,1),(2,3),(4,5),(6,7),(8,9),(10,11),(12,13),(14,15)]
SF_PAIRS    = [(0,1),(2,3),(4,5),(6,7)]
FINAL_PAIRS = [(0,1),(2,3)]

LEAGUE_AVG_DRAW_RATE = 0.24   # historical international-football average


def _wdl_probabilities(elo_a: float, elo_b: float, knockout: bool, rng) -> tuple:
    """
    LEARNING NOTE — Elo → Win/Draw/Loss split:
    Pure Elo only outputs an "expected score" (0=A loses, 1=A wins, with a
    draw worth 0.5) — it has NO native concept of a draw probability.  To
    run a realistic group stage we need actual W/D/L odds, so we apply a
    simple, transparent, well-documented split:
        expected      = elo_win_probability(A, B)     (A's expected score)
        P(draw)       = 0  if knockout (no draws in a single-elim match —
                            the match would go to penalties, modelled as a
                            coin-flip-ish 50/50-ish shootout on the residual)
                      = LEAGUE_AVG_DRAW_RATE  in the group stage — a constant
                        approximation of football's long-run ~24% draw rate
        P(A wins)     = (expected − 0.5·P(draw)) / (1 − P(draw))   [rescaled]
        P(B wins)     = 1 − P(draw) − P(A wins)
    This is a SIMPLER model than the full ML+Monte-Carlo simulator (Phase 4)
    — it exists purely to show what Elo ALONE predicts, as a sanity check
    and a point of comparison.
    """
    expected = elo_win_probability(elo_a, elo_b)
    if knockout:
        p_draw = 0.0
    else:
        # Draws are most likely between evenly matched teams; scale the
        # constant league-average rate down as the Elo gap widens.
        gap_factor = np.exp(-abs(elo_a - elo_b) / 400.0)
        p_draw = LEAGUE_AVG_DRAW_RATE * gap_factor

    p_draw = min(max(p_draw, 0.0), 0.9)
    p_a = max(0.0, min(1.0, (expected - 0.5 * p_draw) / (1.0 - p_draw))) if p_draw < 1.0 else 0.5
    p_b = 1.0 - p_draw - p_a
    return p_a, p_draw, p_b


def _sample_outcome(p_a: float, p_draw: float, p_b: float, rng) -> str:
    """LEARNING NOTE — Categorical sampling via a single uniform draw:
    splits [0,1) into three buckets sized p_a / p_draw / p_b."""
    r = rng.random()
    if r < p_a:
        return "A"
    if r < p_a + p_draw:
        return "D"
    return "B"


def _rank_group(standings: dict) -> list:
    return sorted(standings.keys(),
                  key=lambda t: (standings[t]["pts"], standings[t]["gd"], standings[t]["gf"]),
                  reverse=True)


def _simulate_group(teams: list, elo_lookup: dict, rng) -> dict:
    """LEARNING NOTE — Round robin (6 matches per group of 4). Goal margins
    aren't modelled by pure Elo, so wins are credited a notional 2-0 and
    draws 1-1 — good enough to break standings ties via goal difference
    without inventing a full goals model (that's the main simulator's job)."""
    standings = {t: {"pts": 0, "gf": 0, "ga": 0, "gd": 0} for t in teams}
    from itertools import combinations
    for ta, tb in combinations(teams, 2):
        p_a, p_d, p_b = _wdl_probabilities(elo_lookup[ta], elo_lookup[tb], knockout=False, rng=rng)
        outcome = _sample_outcome(p_a, p_d, p_b, rng)
        if outcome == "A":
            standings[ta]["pts"] += 3; standings[ta]["gf"] += 2; standings[ta]["ga"] += 0
            standings[tb]["gf"] += 0; standings[tb]["ga"] += 2
        elif outcome == "B":
            standings[tb]["pts"] += 3; standings[tb]["gf"] += 2; standings[tb]["ga"] += 0
            standings[ta]["gf"] += 0; standings[ta]["ga"] += 2
        else:
            standings[ta]["pts"] += 1; standings[tb]["pts"] += 1
            standings[ta]["gf"] += 1; standings[ta]["ga"] += 1
            standings[tb]["gf"] += 1; standings[tb]["ga"] += 1
    for t in standings:
        standings[t]["gd"] = standings[t]["gf"] - standings[t]["ga"]
    return standings


def _knockout_round(pairs: list, elo_lookup: dict, rng) -> list:
    winners = []
    for ta, tb in pairs:
        p_a, _, p_b = _wdl_probabilities(elo_lookup[ta], elo_lookup[tb], knockout=True, rng=rng)
        winners.append(ta if rng.random() < p_a else tb)
    return winners


def run_elo_only_simulation(elo: dict, groups: dict, avg_elo: float,
                            n_sims: int = 3000, seed: int = 42) -> list:
    """
    LEARNING NOTE — A lightweight, Elo-ONLY Monte Carlo:
    Same bracket structure as the full Phase-4 simulator (12 groups → R32 →
    R16 → QF → SF → Final, with the official best-third-place rules and the
    pre-set R32 draw template) but every match is decided by Elo win
    probability alone — no ML model, no squad data, no goals model.  Run
    `n_sims` times and count tournament wins to see what Elo ALONE believes,
    as a clean point of comparison against the full-feature simulator.
    Placeholder teams ('Winner UEFA Playoff D'...) are seeded at the
    confirmed-team average Elo — a neutral stand-in since we don't yet know
    who they'll be.
    """
    rng = np.random.default_rng(seed)
    elo_lookup = {t: elo.get(t, avg_elo) for grp in groups.values() for t in grp}
    win_counts = defaultdict(int)
    final_counts = defaultdict(int)
    semi_counts  = defaultdict(int)

    for _ in range(n_sims):
        group_winners, runners_up, all_thirds = {}, {}, []
        for letter, teams in groups.items():
            standings = _simulate_group(teams, elo_lookup, rng)
            ranked = _rank_group(standings)
            group_winners[letter] = ranked[0]
            runners_up[letter]    = ranked[1]
            all_thirds.append((ranked[2], standings[ranked[2]]))

        ranked_thirds = sorted(all_thirds,
                               key=lambda x: (x[1]["pts"], x[1]["gd"], x[1]["gf"]),
                               reverse=True)
        best_thirds = [t for t, _ in ranked_thirds[:8]]
        thirds_map  = {f"T_{i+1}": best_thirds[i] for i in range(8)}

        def resolve(key):
            if key.startswith("W_"): return group_winners[key[2:]]
            if key.startswith("R_"): return runners_up[key[2:]]
            return thirds_map[key]

        r32 = [(resolve(a), resolve(b)) for a, b in R32_TEMPLATE]
        r32_winners = _knockout_round(r32, elo_lookup, rng)

        r16_pairs = [(r32_winners[a], r32_winners[b]) for a, b in QF_PAIRS]
        r16_winners = _knockout_round(r16_pairs, elo_lookup, rng)

        qf_pairs = [(r16_winners[i], r16_winners[i+1]) for i in range(0, 8, 2)]
        qf_winners = _knockout_round(qf_pairs, elo_lookup, rng)
        for t in qf_winners:                  # the 4 teams that REACHED the semifinal
            semi_counts[t] += 1

        sf_pairs = [(qf_winners[i], qf_winners[i+1]) for i in range(0, 4, 2)]
        sf_winners = _knockout_round(sf_pairs, elo_lookup, rng)
        final_pair = (sf_winners[0], sf_winners[1])
        for t in final_pair:                  # the 2 teams that REACHED the final
            final_counts[t] += 1
        champion = _knockout_round([final_pair], elo_lookup, rng)[0]
        win_counts[champion] += 1

    leaderboard = []
    for team in elo_lookup:
        leaderboard.append({
            "team":            team,
            "title_pct":       win_counts.get(team, 0) / n_sims * 100,
            "final_pct":       final_counts.get(team, 0) / n_sims * 100,
            "semifinal_pct":   semi_counts.get(team, 0) / n_sims * 100,
            "elo":             elo_lookup[team],
        })
    leaderboard.sort(key=lambda r: r["title_pct"], reverse=True)
    return leaderboard


def print_elo_only_simulation(leaderboard: list, n_sims: int):
    print(f"\n{SEP}")
    print(f"SECTION 4 — Elo-ONLY Tournament Simulation  ({n_sims:,} runs, full 48-team bracket)")
    print("  (No ML model, no squad data, no goals model — Elo win-probability alone)")
    print(SEP)

    print(f"\n  {'#':<4} {'Team':<18} {'Elo':>7} {'Title %':>9} {'Final %':>9} {'Semi %':>8}")
    print("  " + "─" * 60)
    for i, r in enumerate(leaderboard[:10], 1):
        print(f"  {i:<4} {r['team']:<18} {r['elo']:>7.0f} {r['title_pct']:>8.2f}% "
              f"{r['final_pct']:>8.2f}% {r['semifinal_pct']:>7.2f}%")


# ─── MAIN ─────────────────────────────────────────────────────────────────

def run_build3():
    t0 = datetime.now()
    print(f"\n{SEP}")
    print("BUILD 3 — Elo Rating System")
    print(SEP)
    print(f"  Start time: {t0.strftime('%H:%M:%S')}")
    print("  Formula: E_home = 1 / (1 + 10^((away_elo - eff_home_elo)/400))")
    print("           delta  = K * margin_multiplier * (actual - expected)")
    print("           Home advantage: +100 Elo (skipped at neutral venues)")

    fifa_points = load_fifa_points_map()
    print(f"\n  FIFA points loaded for {len(fifa_points)} teams (seed value for their first Elo)")
    print(f"  All other teams seed at the spec default: {DEFAULT_START_ELO:.0f}")

    matches = load_matches_chronological()

    # 1. Process every match chronologically
    elo, starting, history_df = process_all_matches(matches, fifa_points)
    print(f"\n  Final Elo computed for {len(elo):,} teams")
    print(f"  Total elo_history rows : {len(history_df):,}")

    # 2. Persist elo_ratings + elo_history
    write_elo_tables(elo, starting, history_df, matches)

    # 3. Derive the 6 team_stats Elo columns
    wc_teams = load_wc_teams_confirmed()
    elo_stats_df = compute_elo_team_stats_columns(elo, starting, history_df, wc_teams)
    print(f"\n{SEP}")
    print("  Writing Elo columns to team_stats")
    print(SEP)
    write_to_team_stats(elo_stats_df)

    # 4. Print: Elo ranking vs FIFA ranking + disagreements
    cmp_df = print_elo_vs_fifa(elo, wc_teams)
    print_biggest_disagreements(cmp_df)

    # 5. Print: most improved / declined last 12 months
    print_trend_leaders(elo_stats_df, wc_teams)

    # 6. Print: Elo win probability for every group-stage matchup
    groups  = load_wc_groups()
    avg_elo = float(np.mean([elo[t] for t in wc_teams if t in elo]))
    print(f"\n  Average Elo across {len(wc_teams)} confirmed WC 2026 teams: {avg_elo:.1f}  "
          f"(used as a neutral stand-in for the 6 still-undecided playoff slots)")
    print_group_stage_probabilities(elo, groups, avg_elo)

    # 7. Print: Elo-only tournament simulation top 10
    n_sims = 3000
    leaderboard = run_elo_only_simulation(elo, groups, avg_elo, n_sims=n_sims)
    print_elo_only_simulation(leaderboard, n_sims)

    elapsed = (datetime.now() - t0).total_seconds()
    print(f"\n{SEP}")
    print(f"BUILD 3 COMPLETE — {elapsed:.1f}s")
    print(f"  elo_ratings  : {len(elo):,} teams")
    print(f"  elo_history  : {len(history_df):,} rows")
    print(f"  team_stats   : +{len(ELO_COLUMNS)} columns ({', '.join(ELO_COLUMNS)})")
    print(f"\nSay 'continue' for BUILD 4 — Model retraining.")
    print(SEP)


if __name__ == "__main__":
    run_build3()
