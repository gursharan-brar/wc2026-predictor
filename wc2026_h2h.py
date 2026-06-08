"""
World Cup 2026 Predictor — BUILD 1: Head-to-Head Records
Author: Gursharan Singh Brar

WHAT THIS FILE DOES:
  Computes every unique head-to-head rivalry from 32,290 historical matches
  (1990–2026) and stores them in the head_to_head table.  H2H features are
  then available as additional signals when the model predicts any matchup —
  because history between two specific opponents is more informative than
  general win rates.

HOW TO RUN:
  python wc2026_h2h.py
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

DB_PATH  = Path(r"C:\Users\gsb13\OneDrive\Desktop\predictor\wc2026.db")
DATA_DIR = Path(r"C:\Users\gsb13\OneDrive\Desktop\predictor\data")

pd.set_option("display.max_columns", 20)
pd.set_option("display.width",       160)
pd.set_option("display.float_format", "{:.3f}".format)

SEP = "=" * 70

# ─── NAME NORMALISATION ───────────────────────────────────────────────────
CANONICAL = {
    "IR Iran": "Iran",
    "Côte d'Ivoire": "Ivory Coast", "Cote d'Ivoire": "Ivory Coast",
    "Cote d Ivoire": "Ivory Coast",
    "Curaçao": "Curacao",
    "Cabo Verde": "Cape Verde",
    "Korea Republic": "South Korea", "Republic of Korea": "South Korea",
    "United States": "USA",
}

def cn(name: str) -> str:
    """
    LEARNING NOTE — Canonical name resolution:
    Returns the standardised name for a team so that joins across tables
    never fail due to spelling differences (e.g. 'IR Iran' vs 'Iran').
    """
    if not name or not isinstance(name, str):
        return name
    return CANONICAL.get(name.strip(), name.strip())

# ─── BIG TOURNAMENT DETECTION ─────────────────────────────────────────────
_BIG = [
    "FIFA World Cup",
    "UEFA Euro", "UEFA European Championship",
    "Copa América", "Copa America",
    "African Cup of Nations", "Africa Cup of Nations", "AFCON",
    "AFC Asian Cup",
    "CONCACAF Gold Cup", "Gold Cup",
    "FIFA Confederations Cup", "Confederations Cup",
]
_KNOCKOUT_KEYS = ["final", "semi", "quarter", "knockout", "round of"]

def is_big_tournament(competition: str) -> bool:
    """
    LEARNING NOTE — Big tournament filter:
    A World Cup qualifier between giants tells us something, but a 2-0 win
    in the World Cup final tells us far more.  We flag competitions whose
    outcome is uniquely pressured and meaningful for international football.
    """
    if not competition:
        return False
    c = competition.lower()
    return any(b.lower() in c for b in _BIG) and "qualif" not in c and "qualifier" not in c

# ─── WIN STREAK CALCULATION ───────────────────────────────────────────────

def longest_win_streak(results: list) -> int:
    """
    LEARNING NOTE — Win streak:
    Consecutive wins against a specific opponent signal psychological
    dominance that simple win-rate averages can miss.  We scan the
    chronological result list (W/D/L strings from team_a's perspective)
    and find the longest unbroken W sequence.
    """
    best = cur = 0
    for r in results:
        if r == "W":
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best

# ─── MAIN BUILD: HEAD-TO-HEAD TABLE ───────────────────────────────────────

def build_h2h_table():
    """
    LEARNING NOTE — Building pairwise statistics:
    For every unique team pair (A, B) we scan every match between them,
    track cumulative stats, and write a single summary row.

    KEY NORMALISATION: we always put the alphabetically earlier team as
    team_a.  This means the same rivalry is never stored twice under
    different orderings, and lookups can always normalise the query.

    Complexity: O(N) where N = number of matches — we process each match
    exactly once, grouping by the canonical pair.
    """
    print(SEP)
    print("BUILD 1 — Head-to-Head Records")
    print(SEP)

    conn = sqlite3.connect(DB_PATH)
    df   = pd.read_sql_query(
        "SELECT date, home_team, away_team, home_goals, away_goals, "
        "       result, competition "
        "FROM   match_results "
        "WHERE  date IS NOT NULL "
        "  AND  home_goals IS NOT NULL "
        "  AND  away_goals IS NOT NULL "
        "ORDER  BY date ASC",
        conn
    )
    conn.close()

    print(f"  Loaded {len(df):,} matches from match_results")

    # Apply canonical names
    df["home_team"] = df["home_team"].apply(cn)
    df["away_team"] = df["away_team"].apply(cn)

    # Canonical pair key: alphabetically sorted
    df["team_a"] = df[["home_team","away_team"]].min(axis=1)
    df["team_b"] = df[["home_team","away_team"]].max(axis=1)
    df["a_is_home"] = df["home_team"] == df["team_a"]

    # Result from team_a's perspective
    def a_result(row):
        if row["result"] == "draw":
            return "D"
        home_wins = row["result"] == "home_win"
        return "W" if (home_wins == row["a_is_home"]) else "L"

    df["a_res"] = df.apply(a_result, axis=1)
    df["a_gf"]  = df.apply(lambda r: r["home_goals"] if r["a_is_home"] else r["away_goals"], axis=1)
    df["a_ga"]  = df.apply(lambda r: r["away_goals"] if r["a_is_home"] else r["home_goals"], axis=1)
    df["big"]   = df["competition"].apply(is_big_tournament)
    df["date"]  = pd.to_datetime(df["date"], errors="coerce")

    cutoff_3y = pd.Timestamp.now() - pd.DateOffset(years=3)

    # Group by canonical pair
    rows_out = []
    for (ta, tb), grp in df.groupby(["team_a","team_b"]):
        grp = grp.sort_values("date")

        results_list = grp["a_res"].tolist()
        wins  = results_list.count("W")
        draws = results_list.count("D")
        losses= results_list.count("L")
        total = len(grp)

        # Last 5 form
        last5 = "".join(results_list[-5:])

        # Big tournament sub-stats
        big_grp = grp[grp["big"]]
        big_n   = len(big_grp)
        big_wr  = big_grp["a_res"].tolist().count("W") / big_n if big_n > 0 else np.nan

        # Last 3 years
        recent = grp[grp["date"] >= cutoff_3y]
        r3y_n  = len(recent)
        r3y_wr = recent["a_res"].tolist().count("W") / r3y_n if r3y_n > 0 else np.nan

        # Last meeting
        last_row = grp.iloc[-1]
        last_date   = last_row["date"].strftime("%Y-%m-%d") if pd.notna(last_row["date"]) else None
        last_result = last_row["result"]

        rows_out.append({
            "team_a":                   ta,
            "team_b":                   tb,
            "total_meetings":           total,
            "team_a_wins":              wins,
            "team_b_wins":              losses,
            "draws":                    draws,
            "team_a_win_rate_h2h":      round(wins / total, 4),
            "avg_goals_scored_h2h":     round(grp["a_gf"].mean(), 4),
            "avg_goals_conceded_h2h":   round(grp["a_ga"].mean(), 4),
            "last_5_form":              last5,
            "big_tournament_win_rate":  round(big_wr, 4) if pd.notna(big_wr) else None,
            "big_tournament_meetings":  big_n,
            "longest_win_streak":       longest_win_streak(results_list),
            "last_3_years_win_rate":    round(r3y_wr, 4) if pd.notna(r3y_wr) else None,
            "last_meeting_date":        last_date,
            "last_meeting_result":      last_result,
        })

    h2h_df = pd.DataFrame(rows_out)
    print(f"  Unique rivalries computed: {len(h2h_df):,}")

    # Write to DB
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS head_to_head")
    cursor.execute("""
        CREATE TABLE head_to_head (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            team_a                  TEXT,
            team_b                  TEXT,
            total_meetings          INTEGER,
            team_a_wins             INTEGER,
            team_b_wins             INTEGER,
            draws                   INTEGER,
            team_a_win_rate_h2h     REAL,
            avg_goals_scored_h2h    REAL,
            avg_goals_conceded_h2h  REAL,
            last_5_form             TEXT,
            big_tournament_win_rate REAL,
            big_tournament_meetings INTEGER,
            longest_win_streak      INTEGER,
            last_3_years_win_rate   REAL,
            last_meeting_date       TEXT,
            last_meeting_result     TEXT
        )
    """)
    for _, r in h2h_df.iterrows():
        cursor.execute("""
            INSERT INTO head_to_head VALUES
            (NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            r.team_a, r.team_b, int(r.total_meetings),
            int(r.team_a_wins), int(r.team_b_wins), int(r.draws),
            r.team_a_win_rate_h2h, r.avg_goals_scored_h2h,
            r.avg_goals_conceded_h2h, r.last_5_form,
            r.big_tournament_win_rate if r.big_tournament_win_rate is not None else None,
            int(r.big_tournament_meetings),
            int(r.longest_win_streak),
            r.last_3_years_win_rate if r.last_3_years_win_rate is not None else None,
            r.last_meeting_date, r.last_meeting_result,
        ))
    conn.commit()
    conn.close()
    print(f"  ✓ head_to_head table written to wc2026.db")
    return h2h_df


# ─── LOOKUP HELPER ────────────────────────────────────────────────────────

def get_h2h(conn, team_a: str, team_b: str) -> dict | None:
    """
    LEARNING NOTE — Symmetric lookup:
    The DB always stores the alphabetically-first team as team_a.
    This function normalises the query so callers don't need to know
    the storage order — get_h2h('France','Brazil') and
    get_h2h('Brazil','France') both return the same record, but with
    win rates flipped correctly for the requested team_a.
    """
    ta, tb = (min(cn(team_a), cn(team_b)), max(cn(team_a), cn(team_b)))
    row = conn.execute(
        "SELECT * FROM head_to_head WHERE team_a=? AND team_b=?", (ta, tb)
    ).fetchone()
    if not row:
        return None

    # BUGFIX (found during Build 4): PRAGMA table_info rows are
    # (cid, name, type, notnull, dflt_value, pk) — the column NAME is at
    # index 1, not 0 (index 0 is just the integer column position). The
    # original `d[0]` produced a dict keyed by 0,1,2... instead of by
    # column name, so every rec["total_meetings"] / rec["team_a_win_rate_h2h"]
    # lookup raised KeyError downstream in get_h2h_features().
    cols = [d[1] for d in conn.execute("PRAGMA table_info(head_to_head)").fetchall()]
    rec  = dict(zip(cols, row))

    # If the caller asked with team_b first, flip perspective
    if cn(team_a) != ta:
        rec["team_a_win_rate_h2h"]    = round(1 - rec["team_a_win_rate_h2h"] -
                                              (rec["draws"] / rec["total_meetings"]), 4)
        rec["avg_goals_scored_h2h"],  \
        rec["avg_goals_conceded_h2h"] = rec["avg_goals_conceded_h2h"], rec["avg_goals_scored_h2h"]
        # Flip last_5_form
        rec["last_5_form"] = "".join(
            "W" if c == "L" else "L" if c == "W" else "D"
            for c in rec["last_5_form"]
        )
    return rec


def get_h2h_features(team_home: str, team_away: str, conn) -> dict:
    """
    LEARNING NOTE — H2H feature vector for model prediction:
    Given a home vs away matchup, returns 6 H2H-derived features.
    Each is expressed as a DIFFERENCE (home - away perspective) so the
    ML model can learn 'home team historically dominates this opponent'.
    If teams have never met, all features default to 0.0 (neutral).
    """
    rec = get_h2h(conn, team_home, team_away)
    if not rec or rec["total_meetings"] == 0:
        return {k: 0.0 for k in [
            "h2h_win_rate_diff", "h2h_goals_diff",
            "h2h_big_tournament_advantage", "h2h_recent_momentum",
            "h2h_experience", "h2h_last_3y_advantage"
        ]}

    draw_rate  = rec["draws"] / rec["total_meetings"]
    home_wr    = rec["team_a_win_rate_h2h"]  # from home team perspective (already flipped if needed)

    # Recent momentum: W=3, D=1, L=0 normalised to 0-1
    form  = rec["last_5_form"] or ""
    pts   = sum({"W":3,"D":1,"L":0}.get(c,0) for c in form)
    max_p = 3 * max(len(form),1)
    momentum = pts / max_p

    return {
        "h2h_win_rate_diff":             round(home_wr - (1 - home_wr - draw_rate), 4),
        "h2h_goals_diff":                round(rec["avg_goals_scored_h2h"] - rec["avg_goals_conceded_h2h"], 4),
        "h2h_big_tournament_advantage":  round((rec["big_tournament_win_rate"] or 0.5) - 0.5, 4),
        "h2h_recent_momentum":           round(momentum - 0.5, 4),
        "h2h_experience":                float(rec["total_meetings"]),
        "h2h_last_3y_advantage":         round((rec["last_3_years_win_rate"] or 0.5) - 0.5, 4),
    }


# ─── PRINT SECTION 1: TOP 30 RIVALRIES ────────────────────────────────────

def print_top_rivalries(h2h_df: pd.DataFrame):
    """
    LEARNING NOTE — Rivalry analysis:
    The most-played matchups are the most statistically reliable — small
    samples can show misleading win rates that regress to the mean over time.
    The top rivalries also happen to be the most interesting football fixtures.
    """
    print(f"\n{SEP}")
    print("SECTION 1 — Top 30 Most Played Rivalries")
    print(SEP)

    top = h2h_df.nlargest(30, "total_meetings").copy()
    top["record"] = top.apply(
        lambda r: f"{int(r.team_a_wins)}W-{int(r.draws)}D-{int(r.team_b_wins)}L", axis=1
    )
    top["big_games"] = top["big_tournament_meetings"].astype(int)
    top["last_meet"] = top["last_meeting_date"].fillna("?")

    print(f"\n  {'#':<4} {'Team A':<22} {'Team B':<22} {'Played':>7} {'Record A':>12} {'A WR':>6} {'Big':>5} {'Last Form':>10} {'Last Met':>12}")
    print("  " + "─" * 102)
    for i, row in enumerate(top.itertuples(), 1):
        print(f"  {i:<4} {row.team_a:<22} {row.team_b:<22} {row.total_meetings:>7} "
              f"{row.record:>12} {row.team_a_win_rate_h2h*100:>5.1f}% "
              f"{row.big_games:>5} {row.last_5_form or '?':>10} {row.last_meet:>12}")


# ─── PRINT SECTION 2: 48x48 WC TEAM MATRIX ────────────────────────────────

def print_48x48_matrix(h2h_df: pd.DataFrame):
    """
    LEARNING NOTE — Win-rate matrix:
    A square matrix where cell [i,j] = team_i's H2H win rate against team_j.
    Values > 0.5 indicate historical advantage; NaN means never met.
    This is a quick way to spot which WC 2026 teams have psychological edges.
    """
    print(f"\n{SEP}")
    print("SECTION 2 — 48×48 WC Team H2H Win Rate Matrix")
    print(SEP)

    try:
        teams_df = pd.read_csv(DATA_DIR / "teams.csv")
        wc_teams = [cn(t) for t in teams_df["team_name"].tolist()
                    if not str(t).startswith("Winner") and not str(t).startswith("TBD")]
    except Exception:
        wc_teams = sorted(set(h2h_df["team_a"].tolist() + h2h_df["team_b"].tolist()))[:48]

    wc_teams = sorted(set(wc_teams))
    n = len(wc_teams)
    print(f"  WC 2026 teams found: {n}")

    # Build lookup dict for speed
    lookup = {}
    for _, row in h2h_df.iterrows():
        lookup[(row.team_a, row.team_b)] = row

    matrix = np.full((n, n), np.nan)
    has_data = 0
    for i, ta in enumerate(wc_teams):
        for j, tb in enumerate(wc_teams):
            if i == j:
                matrix[i][j] = np.nan
                continue
            ka, kb = (min(ta,tb), max(ta,tb))
            if (ka, kb) in lookup:
                rec = lookup[(ka, kb)]
                if ta == ka:
                    matrix[i][j] = rec.team_a_win_rate_h2h
                else:
                    d_rate = rec.draws / rec.total_meetings
                    matrix[i][j] = 1 - rec.team_a_win_rate_h2h - d_rate
                has_data += 1

    mat_df = pd.DataFrame(matrix, index=wc_teams, columns=wc_teams)

    # Print summary stats
    flat = matrix[~np.isnan(matrix)]
    covered = has_data
    total_pairs = n * (n - 1) // 2
    print(f"  Pairs with H2H data : {covered} / {total_pairs} ({covered/total_pairs*100:.1f}%)")
    print(f"  Mean H2H win rate   : {np.nanmean(flat):.3f}")
    print(f"  Pairs with > 5 meetings: {(h2h_df[h2h_df['team_a'].isin(wc_teams) & h2h_df['team_b'].isin(wc_teams)]['total_meetings'] > 5).sum()}")

    # Save full matrix to CSV
    out_path = DATA_DIR / "h2h_matrix_48x48.csv"
    mat_df.to_csv(out_path, float_format="%.3f")
    print(f"\n  Full 48×48 matrix saved → {out_path}")

    # Print short-name version in terminal (first 16 teams alphabetically, readable slice)
    print(f"\n  Sample: top 16 WC teams (alphabetical), win rate as decimal (— = never met):")
    sample_teams = wc_teams[:16]
    sub = mat_df.loc[sample_teams, sample_teams]
    sub_str = sub.applymap(lambda x: f"{x:.2f}" if pd.notna(x) else " — ")
    # Shorten names for display
    sub_str.columns = [t[:6] for t in sub_str.columns]
    sub_str.index   = [t[:12] for t in sub_str.index]
    print(sub_str.to_string())

    return mat_df, wc_teams


# ─── PRINT SECTION 3: ONE-SIDED RIVALRIES ─────────────────────────────────

def print_one_sided_rivalries(h2h_df: pd.DataFrame):
    """
    LEARNING NOTE — One-sided rivalries:
    Some matchups are historically predictable regardless of current form.
    A team with an 85%+ win rate over 5+ meetings has demonstrated a
    persistent structural advantage worth encoding as a model feature.
    """
    print(f"\n{SEP}")
    print("SECTION 3 — Most One-Sided Rivalries (min 5 meetings)")
    print(SEP)

    filtered = h2h_df[h2h_df["total_meetings"] >= 5].copy()
    filtered["dominance"] = (filtered["team_a_win_rate_h2h"] - 0.5).abs()
    top = filtered.nlargest(20, "dominance")

    print(f"\n  {'Team A':<22} {'Team B':<22} {'Played':>7} {'Winner':<22} {'WR':>6} {'Big WR':>8}")
    print("  " + "─" * 90)
    for _, r in top.iterrows():
        dominant = r.team_a if r.team_a_win_rate_h2h >= 0.5 else r.team_b
        wr = max(r.team_a_win_rate_h2h, 1 - r.team_a_win_rate_h2h -
                 r.draws / r.total_meetings) if r.total_meetings > 0 else 0
        bwr = r.big_tournament_win_rate
        bwr_str = f"{bwr*100:.0f}%" if pd.notna(bwr) and r.big_tournament_meetings > 0 else "N/A"
        print(f"  {r.team_a:<22} {r.team_b:<22} {int(r.total_meetings):>7} "
              f"{dominant:<22} {wr*100:>5.0f}% {bwr_str:>8}")


# ─── PRINT SECTION 4: BIGGEST UPSETS ──────────────────────────────────────

def print_upset_records(h2h_df: pd.DataFrame):
    """
    LEARNING NOTE — Upset analysis:
    Teams ranked low by FIFA often perform better against specific opponents
    than their overall standing suggests.  Upset records reveal structural
    weaknesses (e.g. a top team that struggles against high-press opposition)
    that FIFA points miss entirely.
    """
    print(f"\n{SEP}")
    print("SECTION 4 — Most Frequent Upsets vs Higher-Ranked Opponents (min 5 meetings)")
    print(SEP)

    conn = sqlite3.connect(DB_PATH)
    rankings = pd.read_sql_query(
        "SELECT team_name, rank FROM fifa_rankings ORDER BY rank", conn
    )
    conn.close()

    rank_map = dict(zip(rankings["team_name"], rankings["rank"]))

    upset_rows = []
    for _, r in h2h_df[h2h_df["total_meetings"] >= 5].iterrows():
        ra = rank_map.get(r.team_a, 999)
        rb = rank_map.get(r.team_b, 999)
        if ra == rb:
            continue
        # Underdog is the higher-ranked number (worse FIFA rank)
        if ra > rb:   # team_a is underdog
            underdog = r.team_a;  favourite = r.team_b
            upset_wr = r.team_a_win_rate_h2h
            rank_gap = ra - rb
        else:         # team_b is underdog
            underdog = r.team_b;  favourite = r.team_a
            d = r.draws / r.total_meetings
            upset_wr = 1 - r.team_a_win_rate_h2h - d
            rank_gap = rb - ra

        if upset_wr > 0.3:
            upset_rows.append({
                "underdog":  underdog,  "favourite": favourite,
                "upset_wr":  upset_wr,  "rank_gap":  rank_gap,
                "meetings":  r.total_meetings,
            })

    upsets = pd.DataFrame(upset_rows).sort_values("upset_wr", ascending=False).head(20)

    print(f"\n  {'Underdog':<22} {'Favourite':<22} {'Win%':>6} {'Gap':>5} {'Games':>6}")
    print("  " + "─" * 70)
    for _, r in upsets.iterrows():
        print(f"  {r['underdog']:<22} {r['favourite']:<22} {r['upset_wr']*100:>5.0f}% "
              f"{int(r['rank_gap']):>5} {int(r['meetings']):>6}")


# ─── PRINT SECTION 5: GROUP STAGE H2H ────────────────────────────────────

def print_group_matchups(h2h_df: pd.DataFrame):
    """
    LEARNING NOTE — Group stage H2H importance:
    In the group stage each matchup is deterministic — France WILL play
    Senegal because they are in the same group.  Knowing France's H2H
    record against Senegal specifically is more predictive than France's
    general win rate.  This section pre-computes all 72 group matchups.
    """
    print(f"\n{SEP}")
    print("SECTION 5 — WC 2026 Group Stage H2H Records")
    print(SEP)

    try:
        teams_df = pd.read_csv(DATA_DIR / "teams.csv")
    except Exception as e:
        print(f"  Cannot load teams.csv: {e}")
        return

    groups = {}
    for _, row in teams_df.iterrows():
        letter = str(row["group_letter"]).strip()
        name   = cn(str(row["team_name"]).strip())
        if str(row["team_name"]).startswith("Winner") or str(row["team_name"]).startswith("TBD"):
            continue
        groups.setdefault(letter, []).append(name)

    # Build H2H lookup
    lookup = {}
    for _, row in h2h_df.iterrows():
        lookup[(row.team_a, row.team_b)] = row

    def h2h_str(ta, tb):
        ka, kb = min(cn(ta), cn(tb)), max(cn(ta), cn(tb))
        if (ka, kb) not in lookup:
            return None
        rec = lookup[(ka, kb)]
        aw = int(rec.team_a_wins) if ka == ta else int(rec.team_b_wins)
        bw = int(rec.team_b_wins) if ka == ta else int(rec.team_a_wins)
        form = rec.last_5_form or ""
        if ka != ta:
            form = "".join("W" if c == "L" else "L" if c == "W" else "D" for c in form)
        return aw, int(rec.draws), bw, form, int(rec.total_meetings)

    total_matchups = 0
    has_h2h = 0

    for letter in sorted(groups.keys()):
        teams = groups[letter]
        if len(teams) < 2:
            continue
        print(f"\n  ── Group {letter}: {' · '.join(teams)} ──")
        from itertools import combinations
        for ta, tb in combinations(teams, 2):
            total_matchups += 1
            rec = h2h_str(ta, tb)
            if rec:
                has_h2h += 1
                aw, d, bw, form, n = rec
                wr = aw / n if n > 0 else 0
                print(f"    {ta:<22} vs {tb:<22} "
                      f"H2H: {aw}W-{d}D-{bw}L  ({n} games, "
                      f"{wr*100:.0f}% {ta[:8]})  Last 5: {form or '?'}")
            else:
                print(f"    {ta:<22} vs {tb:<22} — No H2H data (never met)")

    print(f"\n  Total group matchups: {total_matchups} | With H2H data: {has_h2h} ({has_h2h/total_matchups*100:.0f}%)")


# ─── MAIN ─────────────────────────────────────────────────────────────────

def run_build1():
    t0 = datetime.now()
    print(f"\n  Start time: {t0.strftime('%H:%M:%S')}")

    # 1. Build H2H table
    h2h_df = build_h2h_table()

    print(f"\n{SEP}")
    print(f"  Total unique rivalries in DB: {len(h2h_df):,}")
    print(f"  Rivalries with 10+ meetings : {(h2h_df['total_meetings'] >= 10).sum():,}")
    print(f"  Rivalries with big-game data: {(h2h_df['big_tournament_meetings'] > 0).sum():,}")
    print(f"  Avg meetings per rivalry    : {h2h_df['total_meetings'].mean():.2f}")
    print(f"  Max meetings in one rivalry : {h2h_df['total_meetings'].max()} "
          f"({h2h_df.loc[h2h_df['total_meetings'].idxmax(), 'team_a']} vs "
          f"{h2h_df.loc[h2h_df['total_meetings'].idxmax(), 'team_b']})")
    print(SEP)

    # 2. Top 30 rivalries
    print_top_rivalries(h2h_df)

    # 3. 48x48 matrix
    mat_df, wc_teams = print_48x48_matrix(h2h_df)

    # 4. One-sided rivalries
    print_one_sided_rivalries(h2h_df)

    # 5. Upset records
    print_upset_records(h2h_df)

    # 6. Group stage matchups
    print_group_matchups(h2h_df)

    elapsed = (datetime.now() - t0).total_seconds()
    print(f"\n{SEP}")
    print(f"BUILD 1 COMPLETE — {elapsed:.1f}s")
    print(f"head_to_head table: {len(h2h_df):,} rows in wc2026.db")
    print(f"48×48 matrix: data/h2h_matrix_48x48.csv")
    print(f"\nSay 'continue' for BUILD 2 — Time decay and match weighting.")
    print(SEP)


if __name__ == "__main__":
    run_build1()
