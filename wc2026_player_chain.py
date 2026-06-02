"""
World Cup 2026 Predictor — Phase 7: Player Performance Chain
Author: Gursharan Singh Brar

WHAT THIS FILE DOES:
  Builds a complete player-to-nation performance chain by combining:
    • StatsBomb open event data (WC 2018/2022, Euro 2024, Copa América 2024)
    • FBRef club stats 2025-26 (players_data_light-2025_2026.csv)
    • Pre-computed squad features (test.csv)
    • Wikipedia WC 2026 squad caps data (for veteran flags)

  The resulting 16 new nation-level features are added to team_stats,
  the XGBoost model is retrained, and the full 10,000-run simulation
  is re-executed with the corrected official group draw.

HOW TO RUN:
  python wc2026_player_chain.py

  Approximate runtime: 8-15 minutes (StatsBomb parser is the slow step)

REQUIREMENTS:
  pip install rapidfuzz beautifulsoup4 requests xgboost scikit-learn
"""

import os, json, re, sqlite3, subprocess, sys, warnings
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
import requests
from bs4 import BeautifulSoup
from rapidfuzz import fuzz, process as rfprocess
from sklearn.linear_model    import LogisticRegression
from sklearn.preprocessing   import StandardScaler
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline        import Pipeline
from sklearn.metrics         import f1_score, accuracy_score
from xgboost                 import XGBClassifier

warnings.filterwarnings("ignore")

# ─── PATHS ─────────────────────────────────────────────────────────────────
SB_BASE  = Path(r"C:\statsbomb_raw\data")
PROJECT  = Path(r"C:\Users\gsb13\OneDrive\Desktop\predictor")
DATA_DIR = PROJECT / "data"
DB_PATH  = PROJECT / "wc2026.db"
MODEL_PATH    = PROJECT / "wc2026_model.pkl"
SIM_PATH      = PROJECT / "simulation_results.json"
SIM_SCRIPT    = PROJECT / "wc2026_simulator.py"
SB_PLAYER_CSV = DATA_DIR / "statsbomb_player_stats.csv"
NATION_CSV    = DATA_DIR / "nation_squad_scores.csv"

# ─── STATSBOMB COMPETITION TARGETS ─────────────────────────────────────────
# (competition_id, season_id, label)
SB_TARGETS = [
    (43,  3,   "WC 2018"),
    (43,  106, "WC 2022"),
    (55,  282, "Euro 2024"),
    (223, 282, "Copa America 2024"),
]

# ─── NAME NORMALISATION ────────────────────────────────────────────────────
# LEARNING NOTE — Why a canonical name map?
# The same nation appears under different spellings in different data sources:
# "IR Iran" in StatsBomb, "Iran" in our DB, "IRN" as a FIFA code in club CSVs.
# Joins that use raw strings will silently miss rows unless we normalise first.
# This single dict is the single source of truth for all name resolution.
_RAW_TO_CANONICAL = {
    # teams.csv variants → canonical
    "IR Iran":         "Iran",
    "Côte d'Ivoire":   "Ivory Coast",
    "Cote d'Ivoire":   "Ivory Coast",
    "Cote d Ivoire":   "Ivory Coast",
    "Curaçao":         "Curacao",
    "Cabo Verde":      "Cape Verde",
    # Other common DB / results.csv variants
    "Korea Republic":       "South Korea",
    "Republic of Korea":    "South Korea",
    "United States":        "USA",
    "United States of America": "USA",
    "US":                   "USA",
    # StatsBomb full names
    "Iran":             "Iran",
    "Ivory Coast":      "Ivory Coast",
    "Curacao":          "Curacao",
    "Cape Verde":       "Cape Verde",
    "South Korea":      "South Korea",
    # test.csv uses full English names — most already canonical
}

def canon(name: str) -> str:
    """
    LEARNING NOTE — Canonical name resolution:
    Strips whitespace, resolves known aliases, returns the canonical form.
    If the name isn't in our alias dict, it's returned unchanged (it may
    already be canonical, e.g. 'France', 'Brazil').
    """
    if not name or not isinstance(name, str):
        return name
    name = name.strip()
    return _RAW_TO_CANONICAL.get(name, name)

# ─── FIFA CODE → CANONICAL TEAM MAP ────────────────────────────────────────
# Built dynamically from teams.csv; supplemented with hardcoded corrections
# for codes that differ between FBRef and FIFA/StatsBomb conventions.
_EXTRA_CODE_MAP = {
    # FBRef uses different 3-letter codes for some nations
    "GER": "Germany",    "ENG": "England",    "FRA": "France",
    "ESP": "Spain",      "BRA": "Brazil",     "ARG": "Argentina",
    "POR": "Portugal",   "NED": "Netherlands","BEL": "Belgium",
    "ITA": "Italy",      "CRO": "Croatia",    "DEN": "Denmark",
    "URU": "Uruguay",    "COL": "Colombia",   "MEX": "Mexico",
    "USA": "USA",        "CAN": "Canada",     "JPN": "Japan",
    "KOR": "South Korea","AUS": "Australia",  "MAR": "Morocco",
    "SEN": "Senegal",    "CMR": "Cameroon",   "NGA": "Nigeria",
    "EGY": "Egypt",      "GHA": "Ghana",      "MLI": "Mali",
    "ALG": "Algeria",    "TUN": "Tunisia",    "RSA": "South Africa",
    "ECU": "Ecuador",    "PAR": "Paraguay",   "BOL": "Bolivia",
    "VEN": "Venezuela",  "PAN": "Panama",     "SLV": "El Salvador",
    "HON": "Honduras",   "HND": "Honduras",   "JAM": "Jamaica",
    "NZL": "New Zealand","IRN": "Iran",       "IRQ": "Iraq",
    "SAU": "Saudi Arabia","KSA": "Saudi Arabia","QAT": "Qatar",
    "JOR": "Jordan",     "UZB": "Uzbekistan", "SRB": "Serbia",
    "POL": "Poland",     "AUT": "Austria",    "SCO": "Scotland",
    "NOR": "Norway",     "SUI": "Switzerland","SWI": "Switzerland",
    "CIV": "Ivory Coast","CUR": "Curacao",    "CPV": "Cape Verde",
    "HAI": "Haiti",      "POR": "Portugal",
}

def build_fifa_code_map() -> dict:
    """
    LEARNING NOTE — Building a lookup from CSV:
    Instead of hardcoding every code, we read teams.csv and build the map
    programmatically.  That way if teams.csv is updated the code adapts
    automatically.  We then overlay _EXTRA_CODE_MAP to handle FBRef quirks.
    """
    code_map = {}
    try:
        df = pd.read_csv(DATA_DIR / "teams.csv")
        for _, row in df.iterrows():
            code = str(row["fifa_code"]).strip().upper()
            name = canon(str(row["team_name"]).strip())
            code_map[code] = name
    except Exception as e:
        print(f"  Warning: could not read teams.csv: {e}")
    code_map.update(_EXTRA_CODE_MAP)
    return code_map

def parse_nation_code(raw_nation: str) -> str:
    """
    LEARNING NOTE — FBRef Nation column format:
    FBRef stores nationality as 'xx XXX' e.g. 'fr FRA', 'us USA'.
    We split on space and take the last token (the 3-letter code).
    Some entries may just be the 3-letter code directly.
    """
    if not raw_nation or not isinstance(raw_nation, str):
        return ""
    parts = raw_nation.strip().split()
    code = parts[-1].upper() if parts else ""
    return code  # e.g. "FRA"

# ─── OFFICIAL GROUP DRAW ───────────────────────────────────────────────────
# LEARNING NOTE — Why we load from teams.csv instead of hardcoding:
# The 2026 World Cup draw was announced Dec 5, 2024.  Our previous simulator
# used placeholder groups.  We now build GROUP_STAGE from the official CSV so
# the simulator, player chain, and leaderboard are all consistent.
def build_official_groups() -> dict:
    """
    Returns GROUP_STAGE dict: {letter: [canonical_team_name, ...]}
    Placeholder teams (UEFA/FIFA Playoffs not yet decided) are included as
    'TBD-{code}' strings so the simulator still has 4 teams per group.
    """
    groups = defaultdict(list)
    try:
        df = pd.read_csv(DATA_DIR / "teams.csv")
        for _, row in df.iterrows():
            letter = str(row["group_letter"]).strip().upper()
            raw    = str(row["team_name"]).strip()
            name   = canon(raw) if not raw.startswith("Winner") else f"TBD-{row['fifa_code']}"
            groups[letter].append(name)
    except Exception as e:
        print(f"  Warning: could not build groups from teams.csv: {e}")
    return dict(sorted(groups.items()))

# ─── DATABASE HELPERS ──────────────────────────────────────────────────────
def add_columns_if_missing(cursor, table: str, columns: list[tuple[str,str]]):
    """
    LEARNING NOTE — Safe schema migration:
    SQLite doesn't support IF NOT EXISTS on ALTER TABLE.
    We attempt each ADD COLUMN and silently swallow the error if the
    column already exists.  This makes the script safe to re-run.
    """
    for col_name, col_def in columns:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
        except sqlite3.OperationalError:
            pass  # column already exists

# ───────────────────────────────────────────────────────────────────────────
#  STEP 2 — STATSBOMB PARSER
# ───────────────────────────────────────────────────────────────────────────

def _parse_minutes(events: list) -> dict:
    """
    LEARNING NOTE — Player minutes from substitution events:
    StatsBomb doesn't store minutes_played directly.  We reconstruct it:
      • Starting XI players play from minute 0.
      • A 'Substitution' event records the player leaving (event["player"])
        and their replacement (event["substitution"]["replacement"]).
      • The match end minute ≈ the highest minute in the event list.
    Minutes played = sub_off_minute (or match_end if not subbed off)
    """
    starters:    set  = set()
    sub_off:     dict = {}   # player_name → minute left
    sub_on:      dict = {}   # player_name → minute entered
    match_end   = 90

    for ev in events:
        m = ev.get("minute", 0) or 0
        if m > match_end:
            match_end = m
        etype = (ev.get("type") or {}).get("name", "")

        if etype == "Starting XI":
            for slot in (ev.get("tactics") or {}).get("lineup", []):
                pname = (slot.get("player") or {}).get("name", "")
                if pname:
                    starters.add(pname)

        elif etype == "Substitution":
            out_name = (ev.get("player") or {}).get("name", "")
            in_name  = ((ev.get("substitution") or {})
                        .get("replacement") or {}).get("name", "")
            if out_name:
                sub_off[out_name] = m
            if in_name:
                sub_on[in_name] = m

    # All players seen in the match
    all_players = starters | set(sub_off.keys()) | set(sub_on.keys())
    minutes = {}
    for p in all_players:
        if p in starters:
            minutes[p] = sub_off.get(p, match_end)
        elif p in sub_on:
            on_min = sub_on[p]
            off_min = sub_off.get(p, match_end)
            minutes[p] = max(0, off_min - on_min)
    return minutes


def parse_statsbomb_events() -> str:
    """
    LEARNING NOTE — Event data parsing:
    StatsBomb stores every match action as a JSON object with a 'type' field.
    We scan each event for Shot, Pass (with goal_assist/shot_assist flags),
    Pressure, Duel, Dribble, and Bad Behaviour events to build a per-player
    performance profile across WC 2018, WC 2022, Euro 2024, Copa 2024.

    Returns the path to the saved CSV.
    """
    print("\n" + "="*65)
    print("STEP 2 — StatsBomb Parser")
    print("="*65)

    # player_key = (player_name, team_name)  →  stats dict
    agg: dict = defaultdict(lambda: {
        "competitions": set(),
        "matches": 0,
        "minutes":  0,
        "goals":    0,
        "assists":  0,
        "shots":    0,
        "sot":      0,   # shots on target
        "key_passes": 0,
        "pressures":  0,
        "duels_won":  0,
        "dribbles":   0,
        "yellow_cards": 0,
        "red_cards":    0,
    })

    total_matches = 0
    SOT_OUTCOMES  = {"Goal", "Saved", "Saved To Post"}

    for comp_id, season_id, label in SB_TARGETS:
        matches_file = SB_BASE / "matches" / str(comp_id) / f"{season_id}.json"
        if not matches_file.exists():
            print(f"  [SKIP] {label}: matches file not found at {matches_file}")
            continue

        try:
            with open(matches_file, encoding="utf-8") as f:
                matches = json.load(f)
        except Exception as e:
            print(f"  [SKIP] {label}: could not read matches file — {e}")
            continue

        match_ids = [int(m["match_id"]) for m in matches if "match_id" in m]
        print(f"\n  {label}: {len(match_ids)} matches")

        for idx, match_id in enumerate(match_ids):
            if idx > 0 and idx % 10 == 0:
                print(f"    ... {idx}/{len(match_ids)} matches processed", end="\r")

            ev_file = SB_BASE / "events" / f"{match_id}.json"
            if not ev_file.exists():
                continue
            try:
                with open(ev_file, encoding="utf-8") as f:
                    events = json.load(f)
            except Exception:
                continue

            minutes_map = _parse_minutes(events)
            total_matches += 1

            for ev in events:
                etype   = (ev.get("type") or {}).get("name", "")
                player  = (ev.get("player") or {})
                pname   = player.get("name", "")
                tname   = canon((ev.get("team") or {}).get("name", ""))
                if not pname or not tname:
                    continue

                key = (pname, tname)
                s   = agg[key]
                s["competitions"].add(label)

                if etype == "Shot":
                    s["shots"] += 1
                    outcome = ((ev.get("shot") or {})
                               .get("outcome") or {}).get("name", "")
                    if outcome == "Goal":
                        s["goals"] += 1
                    if outcome in SOT_OUTCOMES:
                        s["sot"] += 1

                elif etype == "Pass":
                    p_data = ev.get("pass") or {}
                    if p_data.get("goal_assist"):
                        s["assists"] += 1
                    if p_data.get("shot_assist"):
                        s["key_passes"] += 1

                elif etype == "Pressure":
                    s["pressures"] += 1

                elif etype == "Duel":
                    outcome = ((ev.get("duel") or {})
                               .get("outcome") or {}).get("name", "")
                    if "Won" in outcome or "Success" in outcome:
                        s["duels_won"] += 1

                elif etype == "Dribble":
                    outcome = ((ev.get("dribble") or {})
                               .get("outcome") or {}).get("name", "")
                    if outcome == "Complete":
                        s["dribbles"] += 1

                elif etype == "Bad Behaviour":
                    card = ((ev.get("bad_behaviour") or {})
                            .get("card") or {}).get("name", "")
                    if "Yellow" in card:
                        s["yellow_cards"] += 1
                    if "Red" in card:
                        s["red_cards"] += 1

            # Minutes played per player in this match
            for pname_k, tname_k in [k for k in agg if k[1] == tname or True]:
                pass  # handled below

        # After each competition, assign minutes from the last match's map
        # (We accumulate per-match so we need a second pass)

        # Re-process just for minutes: we tracked per-match separately
        for idx, match_id in enumerate(match_ids):
            ev_file = SB_BASE / "events" / f"{match_id}.json"
            if not ev_file.exists():
                continue
            try:
                with open(ev_file, encoding="utf-8") as f:
                    events = json.load(f)
            except Exception:
                continue

            minutes_map = _parse_minutes(events)
            # We need team name from the match file
            match_meta = next((m for m in matches if m.get("match_id") == match_id), {})
            teams_in_match = {
                canon((match_meta.get("home_team") or {}).get("home_team_name", "")),
                canon((match_meta.get("away_team") or {}).get("away_team_name", "")),
            }

            for pname, mins in minutes_map.items():
                # Find this player's team by looking at which keys exist for them
                for t in teams_in_match:
                    if t and (pname, t) in agg:
                        agg[(pname, t)]["minutes"] += mins
                        agg[(pname, t)]["matches"] += 1
                        break

        print(f"  ✓ {label}: done")

    print(f"\n  Total matches parsed: {total_matches}")
    print(f"  Total unique (player, team) pairs: {len(agg)}")

    # Convert to DataFrame
    rows = []
    for (pname, tname), s in agg.items():
        mins = max(s["minutes"], 1)
        n90  = mins / 90.0
        rows.append({
            "player_name":     pname,
            "team_name":       tname,
            "competitions":    "|".join(sorted(s["competitions"])),
            "matches_played":  s["matches"],
            "minutes_played":  mins,
            "goals":           s["goals"],
            "assists":         s["assists"],
            "shots_total":     s["shots"],
            "shots_on_target": s["sot"],
            "key_passes":      s["key_passes"],
            "pressures":       s["pressures"],
            "duels_won":       s["duels_won"],
            "dribbles_completed": s["dribbles"],
            "yellow_cards":    s["yellow_cards"],
            "red_cards":       s["red_cards"],
            "goals_per90":     round(s["goals"]     / n90, 4),
            "assists_per90":   round(s["assists"]   / n90, 4),
            "sot_per90":       round(s["sot"]       / n90, 4),
            "key_passes_per90":round(s["key_passes"]/ n90, 4),
            "pressures_per90": round(s["pressures"] / n90, 4),
        })

    df = pd.DataFrame(rows).sort_values("goals", ascending=False).reset_index(drop=True)
    df.to_csv(SB_PLAYER_CSV, index=False, encoding="utf-8")
    print(f"\n  Saved → {SB_PLAYER_CSV}  ({len(df)} rows)")

    # Top 10 by goals
    print("\n  Top 10 players by tournament goals:")
    print(f"  {'Player':<28} {'Team':<20} {'G':>4} {'A':>4} {'Mins':>6}")
    print("  " + "─"*64)
    for _, r in df.head(10).iterrows():
        print(f"  {r['player_name']:<28} {r['team_name']:<20} "
              f"{r['goals']:>4} {r['assists']:>4} {r['minutes_played']:>6}")

    return str(SB_PLAYER_CSV)


# ───────────────────────────────────────────────────────────────────────────
#  STEP 3 — CLUB FORM SCORER
# ───────────────────────────────────────────────────────────────────────────

def compute_club_form_scores(code_map: dict) -> pd.DataFrame:
    """
    LEARNING NOTE — Club form as a predictive signal:
    A player's current-season club performance reveals their fitness, form,
    and peak-year status far better than historical averages.  We aggregate
    up to the nation level because we're predicting team outcomes.

    Process:
    1. Load players_data_light-2025_2026.csv (53 cols, season 2025-26)
    2. Parse the 3-letter Nation code from the 'Nation' column
    3. Map code → canonical WC team name using code_map
    4. For each WC nation, compute starter + depth quality scores
    """
    print("\n" + "="*65)
    print("STEP 3 — Club Form Scorer (2025-26 season)")
    print("="*65)

    csv_path = DATA_DIR / "players_data_light-2025_2026.csv"
    if not csv_path.exists():
        print(f"  [SKIP] File not found: {csv_path}")
        return pd.DataFrame()

    df = pd.read_csv(csv_path, encoding="utf-8", low_memory=False)
    print(f"  Loaded {len(df):,} rows, {len(df.columns)} columns")

    # Parse Nation code
    df["nation_code"] = df["Nation"].apply(parse_nation_code)
    df["wc_team"]     = df["nation_code"].map(code_map)

    # Keep only players whose nation maps to a WC 2026 team
    wc_players = df[df["wc_team"].notna()].copy()
    print(f"  Players mapping to WC 2026 nations: {len(wc_players):,}")

    # Fill NaN with 0 for numeric columns we use
    num_cols = ["90s", "Gls", "Ast", "Sh", "SoT", "TklW", "Int"]
    for c in num_cols:
        if c in wc_players.columns:
            wc_players[c] = pd.to_numeric(wc_players[c], errors="coerce").fillna(0)

    # Combine duplicate rows per player (same player, multiple clubs)
    grouped = (wc_players
               .groupby(["Player", "wc_team"], as_index=False)
               .agg({
                   "90s": "sum",
                   "Gls": "sum",
                   "Ast": "sum",
                   "Sh":  "sum",
                   "SoT": "sum",
                   "TklW": "sum",
                   "Int":  "sum",
               }))

    # Per-90 stats
    grouped["g_a_per90"]  = (grouped["Gls"] + grouped["Ast"]) / grouped["90s"].replace(0, np.nan)
    grouped["def_per90"]  = (grouped["TklW"] + grouped["Int"]) / grouped["90s"].replace(0, np.nan)
    grouped["gls_per90"]  = grouped["Gls"] / grouped["90s"].replace(0, np.nan)
    grouped["ast_per90"]  = grouped["Ast"] / grouped["90s"].replace(0, np.nan)
    grouped = grouped.fillna(0)

    # Build nation-level features
    nation_rows = []
    for team, grp in grouped.groupby("wc_team"):
        grp_sorted = grp.sort_values("g_a_per90", ascending=False)
        starters   = grp_sorted.head(11)
        depth      = grp_sorted.iloc[11:]

        nation_rows.append({
            "team_name":            team,
            "starter_quality_score":round(starters["g_a_per90"].mean(), 4),
            "depth_score":          round(depth["g_a_per90"].mean() if len(depth) else 0, 4),
            "avg_goals_per90_squad":round(grp["gls_per90"].mean(), 4),
            "avg_assists_per90_squad": round(grp["ast_per90"].mean(), 4),
            "defensive_score":      round(grp["def_per90"].mean(), 4),
            "players_found":        len(grp),
        })

    result = pd.DataFrame(nation_rows)
    print(f"\n  Club form scores computed for {len(result)} nations")

    # Print sample
    top = result.sort_values("starter_quality_score", ascending=False).head(10)
    print(f"\n  Top 10 nations by starter quality:")
    print(f"  {'Team':<22} {'Starter Q':>10} {'Depth':>8} {'Gls/90':>8} {'Def':>8} {'N Players':>10}")
    print("  " + "─"*64)
    for _, r in top.iterrows():
        print(f"  {r['team_name']:<22} {r['starter_quality_score']:>10.4f} "
              f"{r['depth_score']:>8.4f} {r['avg_goals_per90_squad']:>8.4f} "
              f"{r['defensive_score']:>8.4f} {r['players_found']:>10}")

    return result


# ───────────────────────────────────────────────────────────────────────────
#  STEP 4 — SQUAD SCRAPER (Wikipedia — simplified)
# ───────────────────────────────────────────────────────────────────────────

def scrape_wc_squads() -> dict:
    """
    LEARNING NOTE — Web scraping for squad data:
    Wikipedia's WC 2026 squads page contains a table per nation with
    player name, position, caps, goals, club.  We only need player names
    to cross-reference against StatsBomb WC 2018/2022 data for veteran flags.

    Returns: { player_name_lower: {country, caps, club} }
    Handles errors gracefully — if scraping fails we return an empty dict
    and the rest of the pipeline continues without veteran flags.
    """
    print("\n" + "="*65)
    print("STEP 4 — Wikipedia Squad Scraper")
    print("="*65)

    url = "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_squads"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )
    }
    players: dict = {}

    try:
        print(f"  GET {url} ...")
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"  [SKIP] Could not fetch Wikipedia page: {e}")
        print("  Veteran flags will be set to 0 for all nations.")
        return players

    soup = BeautifulSoup(resp.text, "html.parser")

    # Each nation's squad is in an <h3> followed by a wikitable
    nation = "Unknown"
    tables = soup.find_all("table", class_=re.compile(r"wikitable"))
    h_tags = soup.find_all(re.compile(r"^h[23]$"))

    # Build mapping: table position → nearest preceding h2/h3 heading text
    # Walk all elements in order
    current_country = "Unknown"
    processed = 0

    for element in soup.find_all(["h2", "h3", "table"]):
        if element.name in ("h2", "h3"):
            heading = element.get_text(strip=True).replace("[edit]", "").strip()
            # Filter: only accept headings that look like country names
            # (not "Contents", "References", etc.)
            if len(heading) > 2 and not any(x in heading.lower()
                    for x in ["content", "reference", "group", "see also",
                               "external", "note", "qualifier", "playoff"]):
                current_country = canon(heading)

        elif element.name == "table" and "wikitable" in element.get("class", []):
            if current_country in ("Unknown", "Contents"):
                continue

            rows = element.find_all("tr")[1:]  # skip header
            for row in rows:
                cols = row.find_all(["td", "th"])
                if len(cols) < 3:
                    continue
                try:
                    # Typical column order: # | Player | Pos | DOB | Caps | Goals | Club
                    # But structure varies — find player name heuristically
                    # Player name usually has a link
                    pname = ""
                    for col in cols:
                        link = col.find("a")
                        text = col.get_text(strip=True)
                        if link and len(text) > 2 and not text.isdigit():
                            # Avoid country names / positions
                            if not any(p in text for p in ["GK","DF","MF","FW",
                                       "January","February","March","April","May",
                                       "June","July","August","September",
                                       "October","November","December"]):
                                pname = text
                                break

                    if not pname:
                        raw = cols[1].get_text(strip=True) if len(cols) > 1 else ""
                        pname = re.sub(r"\(.*?\)", "", raw).strip()

                    # Caps: find numeric cell after player name
                    caps = 0
                    for col in cols:
                        val = col.get_text(strip=True)
                        if val.isdigit() and 0 < int(val) < 300:
                            caps = int(val)
                            break

                    # Club: last text cell
                    club = cols[-1].get_text(strip=True) if cols else ""

                    if pname and len(pname) > 1:
                        players[pname.lower()] = {
                            "country": current_country,
                            "caps":    caps,
                            "club":    club,
                        }
                        processed += 1
                except Exception:
                    continue

    print(f"  Scraped {processed} player entries across {len(set(v['country'] for v in players.values()))} nations")

    # Save to wc2026_squads table
    if players:
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS wc2026_squads (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                player_name TEXT,
                country     TEXT,
                caps        INTEGER,
                club        TEXT,
                scraped_at  TEXT
            )
        """)
        cursor.execute("DELETE FROM wc2026_squads")
        now = datetime.now().isoformat()
        for pname_lower, info in players.items():
            cursor.execute(
                "INSERT INTO wc2026_squads (player_name, country, caps, club, scraped_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (pname_lower, info["country"], info["caps"], info["club"], now)
            )
        conn.commit()
        conn.close()
        print(f"  Saved to wc2026_squads table in wc2026.db")
    else:
        print("  No squad data saved (scrape returned empty result)")

    return players


# ───────────────────────────────────────────────────────────────────────────
#  STEP 5 — NATION FEATURE AGGREGATION
# ───────────────────────────────────────────────────────────────────────────

def _get_wc_veterans_by_nation(sb_csv: str) -> dict:
    """
    LEARNING NOTE — WC veteran detection:
    Any player who appeared in WC 2018 or WC 2022 StatsBomb data is a
    'WC veteran' — they've experienced the pressure of a World Cup.
    We return a dict: {canonical_team_name: count_of_wc_veterans}
    We also build a set of player names for Wikipedia cross-referencing.
    """
    try:
        df = pd.read_csv(sb_csv, encoding="utf-8")
    except Exception:
        return {}

    wc_df   = df[df["competitions"].str.contains("WC", na=False)]
    veteran_names = set(wc_df["player_name"].str.lower().tolist())
    nation_vets   = wc_df.groupby("team_name")["player_name"].nunique().to_dict()
    return nation_vets, veteran_names


def aggregate_nation_features(
    sb_csv:   str,
    club_df:  pd.DataFrame,
    squads:   dict,
    groups:   dict,
) -> pd.DataFrame:
    """
    LEARNING NOTE — Three-source feature fusion:
    We combine three independent data sources for each WC nation:
      A) test.csv   — pre-computed squad aggregates (market value, avg age, etc.)
      B) Club CSV   — 2025-26 season form (goals/assists per 90, defensive actions)
      C) StatsBomb  — historical WC/tournament performance metrics

    The fusion is a LEFT JOIN on team name: test.csv is the master spine
    (it has all 48 WC teams).  If a team has no club data or StatsBomb data,
    those features default to 0 (league average after normalisation).
    """
    print("\n" + "="*65)
    print("STEP 5 — Nation Feature Aggregation")
    print("="*65)

    # ── Source A: test.csv ─────────────────────────────────────────────
    test_path = DATA_DIR / "test.csv"
    test_df   = pd.read_csv(test_path, encoding="utf-8")
    test_df["team"] = test_df["team"].apply(canon)
    print(f"  test.csv: {len(test_df)} rows")

    # ── Source C: StatsBomb aggregated per nation ──────────────────────
    nation_vets, veteran_names = _get_wc_veterans_by_nation(sb_csv)
    try:
        sb_df = pd.read_csv(sb_csv, encoding="utf-8")
        sb_agg = (sb_df.groupby("team_name")
                  .agg(
                      wc_goals_per90    = ("goals_per90",     "mean"),
                      wc_assists_per90  = ("assists_per90",   "mean"),
                      wc_pressure_rate  = ("pressures_per90", "mean"),
                      wc_sot_per90      = ("sot_per90",       "mean"),
                  )
                  .reset_index()
                  .rename(columns={"team_name": "team"}))
        sb_agg["team"] = sb_agg["team"].apply(canon)
    except Exception as e:
        print(f"  Warning: StatsBomb CSV read failed: {e}")
        sb_agg = pd.DataFrame(columns=["team","wc_goals_per90","wc_assists_per90",
                                        "wc_pressure_rate","wc_sot_per90"])

    # ── Source B: club form ────────────────────────────────────────────
    if not club_df.empty:
        club_df = club_df.copy()
        club_df["team_name"] = club_df["team_name"].apply(canon)

    # ── Merge all three sources ────────────────────────────────────────
    merged = test_df.copy()

    # Merge club form
    if not club_df.empty:
        merged = merged.merge(
            club_df.rename(columns={"team_name": "team"}),
            on="team", how="left"
        )
    else:
        for col in ["starter_quality_score","depth_score",
                    "avg_goals_per90_squad","avg_assists_per90_squad","defensive_score"]:
            merged[col] = 0.0

    # Merge StatsBomb
    merged = merged.merge(sb_agg, on="team", how="left")

    # WC veteran count from StatsBomb
    merged["wc_veteran_count"] = merged["team"].map(nation_vets).fillna(0).astype(int)

    # ── Wikipedia cross-reference for additional veteran count ─────────
    if squads and veteran_names:
        extra_vets: dict = defaultdict(int)
        for pname_lower, info in squads.items():
            country = info["country"]
            # Fuzzy match against veteran_names set
            result = rfprocess.extractOne(
                pname_lower, veteran_names,
                scorer=fuzz.token_sort_ratio,
                score_cutoff=82
            )
            if result:
                extra_vets[country] += 1
        # Average with existing StatsBomb count
        for i, row in merged.iterrows():
            team = row["team"]
            if extra_vets.get(team, 0) > 0:
                merged.at[i, "wc_veteran_count"] = max(
                    merged.at[i, "wc_veteran_count"],
                    extra_vets[team]
                )

    # ── Fill nulls ─────────────────────────────────────────────────────
    fill_zero = [
        "starter_quality_score", "depth_score", "avg_goals_per90_squad",
        "avg_assists_per90_squad", "defensive_score",
        "wc_goals_per90", "wc_assists_per90", "wc_pressure_rate",
        "wc_sot_per90", "wc_veteran_count"
    ]
    for col in fill_zero:
        if col in merged.columns:
            merged[col] = merged[col].fillna(0)

    # ── Log-scale market value (wide range → compress it) ──────────────
    if "squad_total_market_value_eur" in merged.columns:
        merged["squad_market_value_log"] = np.log1p(
            pd.to_numeric(merged["squad_total_market_value_eur"], errors="coerce").fillna(0)
        )
    else:
        merged["squad_market_value_log"] = 0.0

    # ── Invert FIFA rank so higher = better ────────────────────────────
    if "fifa_rank_pre_tournament" in merged.columns:
        rank_max = pd.to_numeric(merged["fifa_rank_pre_tournament"], errors="coerce").max()
        merged["fifa_rank_inv"] = (rank_max + 1) - pd.to_numeric(
            merged["fifa_rank_pre_tournament"], errors="coerce").fillna(rank_max)
    else:
        merged["fifa_rank_inv"] = 0.0

    print(f"  Merged features for {len(merged)} nations")

    # Print full table sorted by starter quality
    display_cols = ["team", "starter_quality_score", "depth_score",
                    "wc_goals_per90", "wc_veteran_count",
                    "squad_market_value_log", "squad_avg_age",
                    "world_cup_participations_before"]
    avail = [c for c in display_cols if c in merged.columns]
    top = merged.sort_values("starter_quality_score", ascending=False)
    print(f"\n  All nations (sorted by starter quality):")
    pd.set_option("display.float_format", "{:.3f}".format)
    pd.set_option("display.max_columns", 20)
    pd.set_option("display.width", 160)
    print(top[avail].to_string(index=False))

    return merged


def save_nation_features_to_db(features_df: pd.DataFrame):
    """
    LEARNING NOTE — Persisting derived features:
    We store the aggregated nation features in two places:
      1. The wc2026.db 'nation_squad_scores' table — for the API to query
      2. A CSV export — for inspection and version control

    We also UPDATE the 'team_stats' table to add the 16 new feature columns
    so the model retraining picks them up automatically.
    """
    print("\n  Saving nation features to database ...")

    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create / replace nation_squad_scores table
    cursor.execute("DROP TABLE IF EXISTS nation_squad_scores")
    cursor.execute("""
        CREATE TABLE nation_squad_scores (
            id                       INTEGER PRIMARY KEY AUTOINCREMENT,
            team_name                TEXT,
            squad_market_value_log   REAL DEFAULT 0,
            squad_avg_age            REAL DEFAULT 0,
            wc_participations        REAL DEFAULT 0,
            goals_scored_last_4y     REAL DEFAULT 0,
            wins_last_4y             REAL DEFAULT 0,
            fifa_rank_inv            REAL DEFAULT 0,
            is_host_nation           INTEGER DEFAULT 0,
            starter_quality_score    REAL DEFAULT 0,
            depth_score              REAL DEFAULT 0,
            avg_goals_per90_squad    REAL DEFAULT 0,
            avg_assists_per90_squad  REAL DEFAULT 0,
            defensive_score          REAL DEFAULT 0,
            wc_goals_per90           REAL DEFAULT 0,
            wc_assists_per90         REAL DEFAULT 0,
            wc_pressure_rate         REAL DEFAULT 0,
            wc_veteran_count         INTEGER DEFAULT 0,
            calculated_at            TEXT
        )
    """)

    # Add new columns to team_stats (safe ALTER TABLE)
    NEW_TS_COLS = [
        ("squad_market_value_log",  "REAL DEFAULT 0"),
        ("squad_avg_age",           "REAL DEFAULT 0"),
        ("wc_participations",       "REAL DEFAULT 0"),
        ("goals_scored_last_4y",    "REAL DEFAULT 0"),
        ("wins_last_4y",            "REAL DEFAULT 0"),
        ("fifa_rank_inv",           "REAL DEFAULT 0"),
        ("is_host_nation",          "INTEGER DEFAULT 0"),
        ("starter_quality_score",   "REAL DEFAULT 0"),
        ("depth_score",             "REAL DEFAULT 0"),
        ("avg_goals_per90_squad",   "REAL DEFAULT 0"),
        ("avg_assists_per90_squad", "REAL DEFAULT 0"),
        ("defensive_score",         "REAL DEFAULT 0"),
        ("wc_goals_per90",          "REAL DEFAULT 0"),
        ("wc_assists_per90",        "REAL DEFAULT 0"),
        ("wc_pressure_rate",        "REAL DEFAULT 0"),
        ("wc_veteran_count",        "INTEGER DEFAULT 0"),
    ]
    add_columns_if_missing(cursor, "team_stats", NEW_TS_COLS)
    conn.commit()

    now = datetime.now().isoformat()

    COL_MAP = {
        "squad_market_value_log":  "squad_market_value_log",
        "squad_avg_age":           "squad_avg_age",
        "world_cup_participations_before": "wc_participations",
        "goals_scored_last_4y":    "goals_scored_last_4y",
        "wins_last_4y":            "wins_last_4y",
        "fifa_rank_inv":           "fifa_rank_inv",
        "is_host":                 "is_host_nation",
        "starter_quality_score":   "starter_quality_score",
        "depth_score":             "depth_score",
        "avg_goals_per90_squad":   "avg_goals_per90_squad",
        "avg_assists_per90_squad": "avg_assists_per90_squad",
        "defensive_score":         "defensive_score",
        "wc_goals_per90":          "wc_goals_per90",
        "wc_assists_per90":        "wc_assists_per90",
        "wc_pressure_rate":        "wc_pressure_rate",
        "wc_veteran_count":        "wc_veteran_count",
    }

    updated_ts = 0
    for _, row in features_df.iterrows():
        team = row["team"]

        # Collect values
        vals = {}
        for src_col, dst_col in COL_MAP.items():
            vals[dst_col] = float(row[src_col]) if src_col in row.index and pd.notna(row[src_col]) else 0.0

        # Insert into nation_squad_scores
        cursor.execute("""
            INSERT INTO nation_squad_scores
            (team_name, squad_market_value_log, squad_avg_age, wc_participations,
             goals_scored_last_4y, wins_last_4y, fifa_rank_inv, is_host_nation,
             starter_quality_score, depth_score, avg_goals_per90_squad,
             avg_assists_per90_squad, defensive_score, wc_goals_per90,
             wc_assists_per90, wc_pressure_rate, wc_veteran_count, calculated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            team,
            vals["squad_market_value_log"],
            vals["squad_avg_age"],
            vals["wc_participations"],
            vals["goals_scored_last_4y"],
            vals["wins_last_4y"],
            vals["fifa_rank_inv"],
            int(vals["is_host_nation"]),
            vals["starter_quality_score"],
            vals["depth_score"],
            vals["avg_goals_per90_squad"],
            vals["avg_assists_per90_squad"],
            vals["defensive_score"],
            vals["wc_goals_per90"],
            vals["wc_assists_per90"],
            vals["wc_pressure_rate"],
            int(vals["wc_veteran_count"]),
            now,
        ))

        # Update team_stats (fuzzy match team names)
        ts_names = cursor.execute("SELECT team_name FROM team_stats").fetchall()
        ts_name_list = [r[0] for r in ts_names]
        match = rfprocess.extractOne(
            team, ts_name_list,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=75
        )
        if match:
            matched_name = match[0]
            set_clause = ", ".join(f"{k} = ?" for k in vals.keys())
            update_sql = f"UPDATE team_stats SET {set_clause} WHERE team_name = ?"
            cursor.execute(update_sql, list(vals.values()) + [matched_name])
            updated_ts += 1

    conn.commit()
    conn.close()

    # Export CSV
    features_df.to_csv(NATION_CSV, index=False, encoding="utf-8")

    print(f"  ✓ nation_squad_scores table: {len(features_df)} rows")
    print(f"  ✓ team_stats updated: {updated_ts} rows")
    print(f"  ✓ CSV exported → {NATION_CSV}")


# ───────────────────────────────────────────────────────────────────────────
#  STEP 6 — MODEL RETRAINING + SIMULATOR UPDATE
# ───────────────────────────────────────────────────────────────────────────

# Expanded feature set (8 original + 16 new)
FEATURE_COLS_NEW = [
    # ── Original 8 ─────────────────────────────────────────────────────
    "win_rate", "avg_goals_scored", "avg_goals_conceded",
    "big_game_win_rate", "defensive_strength", "offensive_strength",
    "tournament_experience_score", "form_momentum",
    # ── From test.csv ───────────────────────────────────────────────────
    "squad_market_value_log", "squad_avg_age", "wc_participations",
    "goals_scored_last_4y", "wins_last_4y", "fifa_rank_inv",
    "is_host_nation",
    # ── From club data ──────────────────────────────────────────────────
    "starter_quality_score", "depth_score",
    "avg_goals_per90_squad", "avg_assists_per90_squad", "defensive_score",
    # ── From StatsBomb ──────────────────────────────────────────────────
    "wc_goals_per90", "wc_assists_per90", "wc_pressure_rate",
    "wc_veteran_count",
]

LABEL_MAP   = {"away_win": 0, "draw": 1, "home_win": 2}
LABEL_NAMES = ["away_win", "draw", "home_win"]


def _build_feature_matrix(feature_cols: list) -> tuple:
    """
    LEARNING NOTE — Feature matrix with expanded features:
    This is the same logic as wc2026_model.py's build_feature_matrix()
    but using the expanded FEATURE_COLS_NEW list.  For any feature that
    a team doesn't have data for (new columns default to 0), the model
    will treat it as 'no data signal' — which is the correct behaviour
    since the old model effectively had the same value by not including
    the feature at all.
    """
    conn = sqlite3.connect(DB_PATH)
    df   = pd.read_sql_query(
        f"SELECT team_name, {', '.join(feature_cols)} FROM team_stats",
        conn
    )
    matches_df = pd.read_sql_query(
        "SELECT home_team, away_team, result FROM match_results "
        "WHERE result IN ('home_win','draw','away_win')", conn
    )
    conn.close()

    df = df.fillna(0)
    stats = df.set_index("team_name")[feature_cols].to_dict("index")
    known = set(stats.keys())
    avg_row = {c: float(df[c].mean()) for c in feature_cols}

    rows, labels, skipped = [], [], 0
    for _, m in matches_df.iterrows():
        h, a = m["home_team"], m["away_team"]
        if h not in known or a not in known:
            skipped += 1
            continue
        hf = [stats[h][c] for c in feature_cols]
        af = [stats[a][c] for c in feature_cols]
        df_ = [hf[i] - af[i] for i in range(len(feature_cols))]
        rows.append(hf + af + df_)
        labels.append(LABEL_MAP[m["result"]])

    col_names = (
        [f"home_{c}" for c in feature_cols] +
        [f"away_{c}" for c in feature_cols] +
        [f"diff_{c}" for c in feature_cols]
    )
    X = np.array(rows,   dtype=np.float64)
    y = np.array(labels, dtype=np.int32)
    return X, y, col_names, skipped, avg_row


def _run_cv(name: str, pipeline, X: np.ndarray, y: np.ndarray, n_splits=5) -> dict:
    """
    LEARNING NOTE — 5-fold cross-validation (same as Phase 3):
    Identical CV setup to Phase 3 so results are comparable.
    Returns mean accuracy and F1.
    """
    cv   = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    accs, f1s = [], []
    print(f"\n   {name} — {n_splits}-fold CV")
    print(f"   {'Fold':<6} {'Accuracy':>9} {'F1':>8}")
    print(f"   {'─'*28}")
    for fold, (tr, te) in enumerate(cv.split(X, y), 1):
        pipeline.fit(X[tr], y[tr])
        pred = pipeline.predict(X[te])
        acc  = accuracy_score(y[te], pred)
        f1   = f1_score(y[te], pred, average="macro", zero_division=0)
        accs.append(acc); f1s.append(f1)
        print(f"   {fold:<6} {acc:>9.4f} {f1:>8.4f}")
    print(f"   {'─'*28}")
    print(f"   {'Mean':<6} {np.mean(accs):>9.4f} {np.mean(f1s):>8.4f}")
    return {"name": name,
            "mean_accuracy": round(float(np.mean(accs)), 4),
            "mean_f1":       round(float(np.mean(f1s)),  4),
            "pipeline":      pipeline}


def retrain_model(old_accuracy: float, old_f1: float) -> tuple[float, float]:
    """
    LEARNING NOTE — Incremental model improvement:
    By adding 16 new features we give the model more signal to distinguish
    between strong and weak teams.  We retrain from scratch (not fine-tune)
    because the feature vector dimension has changed — the old model's
    weights don't apply to the new 72-dimensional input space.

    We compare CV accuracy before and after to verify the new features
    actually improve predictions rather than introducing noise.
    """
    print("\n" + "="*65)
    print("STEP 6 — Model Retraining (expanded feature set)")
    print("="*65)
    print(f"  Old model baseline: accuracy={old_accuracy:.4f}, F1={old_f1:.4f}")
    print(f"  Old feature count : 24 features (8 × home/away/diff)")
    print(f"  New feature count : {len(FEATURE_COLS_NEW) * 3} features "
          f"({len(FEATURE_COLS_NEW)} × home/away/diff)")

    print("\n  Building expanded feature matrix ...")
    X, y, col_names, skipped, avg_row = _build_feature_matrix(FEATURE_COLS_NEW)
    print(f"  Matrix shape : {X.shape}")
    print(f"  Matches used : {len(X):,}  (skipped {skipped:,})")
    lc = {name: int((y==i).sum()) for i, name in enumerate(LABEL_NAMES)}
    print(f"  Label counts : {lc}")

    lr_pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("model",  LogisticRegression(max_iter=2000, C=1.0,
                                      solver="lbfgs", random_state=42))
    ])
    xgb_pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("model",  XGBClassifier(
            n_estimators=400, max_depth=5, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            use_label_encoder=False, eval_metric="mlogloss",
            random_state=42, verbosity=0,
        ))
    ])

    print("\n  Running 5-fold cross-validation ...")
    lr_scores  = _run_cv("Logistic Regression", lr_pipeline,  X, y)
    xgb_scores = _run_cv("XGBoost",             xgb_pipeline, X, y)

    print(f"\n  Model comparison:")
    print(f"  {'Model':<25} {'Accuracy':>9} {'F1':>8}")
    print(f"  {'─'*44}")
    for s in [lr_scores, xgb_scores]:
        arrow_acc = ("↑" if s["mean_accuracy"] > old_accuracy else
                     "↓" if s["mean_accuracy"] < old_accuracy else "=")
        print(f"  {s['name']:<25} {s['mean_accuracy']:>9.4f} {arrow_acc} "
              f"{s['mean_f1']:>8.4f}")

    winner = xgb_scores if xgb_scores["mean_f1"] >= lr_scores["mean_f1"] else lr_scores
    print(f"\n  Winner: {winner['name']}  "
          f"(accuracy={winner['mean_accuracy']:.4f}, F1={winner['mean_f1']:.4f})")

    # Train final model on full dataset
    print("  Training final model on 100% of data ...")
    winner["pipeline"].fit(X, y)

    # Save
    payload = {
        "pipeline":     winner["pipeline"],
        "model_name":   winner["name"],
        "feature_cols": col_names,
        "label_map":    LABEL_MAP,
        "label_names":  LABEL_NAMES,
        "cv_scores":    winner,
        "trained_at":   datetime.now().isoformat(),
        "avg_row":      avg_row,
        "feature_names_raw": FEATURE_COLS_NEW,
    }
    joblib.dump(payload, MODEL_PATH)
    size_kb = MODEL_PATH.stat().st_size // 1024
    print(f"  Saved → {MODEL_PATH}  ({size_kb} KB)")

    new_acc = winner["mean_accuracy"]
    new_f1  = winner["mean_f1"]

    delta_acc = new_acc - old_accuracy
    delta_f1  = new_f1  - old_f1
    sign_acc  = "+" if delta_acc >= 0 else ""
    sign_f1   = "+" if delta_f1  >= 0 else ""
    print(f"\n  Accuracy change : {sign_acc}{delta_acc:+.4f}  ({old_accuracy:.4f} → {new_acc:.4f})")
    print(f"  F1 change       : {sign_f1}{delta_f1:+.4f}  ({old_f1:.4f} → {new_f1:.4f})")

    return new_acc, new_f1


def update_simulator_groups(groups: dict):
    """
    LEARNING NOTE — Updating the simulator with the official draw:
    The simulator's GROUP_STAGE dict was built from placeholder guesses.
    We programmatically replace it with the official draw loaded from
    teams.csv so the simulation reflects reality.

    We write the new GROUP_STAGE as a Python literal string and use
    a regex replace to swap it into the simulator file.
    """
    print("\n  Updating GROUP_STAGE in wc2026_simulator.py ...")

    sim_file = SIM_SCRIPT
    if not sim_file.exists():
        print(f"  [SKIP] Simulator not found at {sim_file}")
        return

    # Build the GROUP_STAGE literal
    lines = ["GROUP_STAGE = {\n"]
    for letter in sorted(groups.keys()):
        teams = groups[letter]
        quoted = ", ".join(f'"{t}"' for t in teams)
        lines.append(f'    "{letter}": [{quoted}],\n')
    lines.append("}\n")
    new_gs_str = "".join(lines)

    # Replace the existing GROUP_STAGE block
    src = sim_file.read_text(encoding="utf-8")
    pattern = r"GROUP_STAGE\s*=\s*\{[^}]+\}"
    if re.search(pattern, src, re.DOTALL):
        new_src = re.sub(pattern, new_gs_str.rstrip(), src, flags=re.DOTALL)
        sim_file.write_text(new_src, encoding="utf-8")
        print(f"  ✓ GROUP_STAGE updated ({sum(len(v) for v in groups.values())} teams)")
    else:
        print("  Could not locate GROUP_STAGE pattern — simulator not modified")

    # Also update ALL_WC_TEAMS derivation (it re-derives from GROUP_STAGE so no change needed)


def run_simulator():
    """
    LEARNING NOTE — Running simulation as subprocess:
    The simulator script (wc2026_simulator.py) was fully tested in Phase 4.
    We call it as a subprocess rather than importing it to get a clean
    execution environment with the updated model and group draw.
    """
    print("\n  Running 10,000-simulation Monte Carlo (this takes ~30s) ...")
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, str(SIM_SCRIPT)],
        cwd=str(PROJECT),
        capture_output=True, text=True, env=env, timeout=300
    )
    if result.returncode == 0:
        # Extract key lines from output
        for line in result.stdout.splitlines():
            if any(x in line for x in ["%", "✓", "complete", "saved", "Saved", "Phase 4"]):
                print(f"  {line.strip()}")
        print("  ✓ Simulation complete")
    else:
        print(f"  [ERROR] Simulator returned exit code {result.returncode}")
        if result.stderr:
            for line in result.stderr.splitlines()[:10]:
                print(f"  stderr: {line}")


# ───────────────────────────────────────────────────────────────────────────
#  STEP 7 — VALIDATION REPORT
# ───────────────────────────────────────────────────────────────────────────

def validation_report(
    old_acc: float, new_acc: float,
    old_f1:  float, new_f1:  float,
    nb_players_sb: int,
    nations_complete: int, nations_partial: int,
):
    """
    LEARNING NOTE — Why a validation report matters:
    Adding new features can actually HURT a model if they're noisy.
    The validation report gives us:
      1. Accuracy comparison — quantifies the improvement
      2. Biggest movers — sanity check: do the teams that moved make sense?
         (e.g. Norway rising after strong 2025-26 season would be expected)
      3. Confidence intervals — from 10,000 simulations the margin of
         error on win probability is ≈ ±1% (95% CI = ±2×sqrt(p(1-p)/N))
    """
    print("\n" + "="*70)
    print("STEP 7 — VALIDATION REPORT")
    print("="*70)

    print(f"\n  DATA SOURCES")
    print(f"  {'─'*50}")
    print(f"  StatsBomb competitions parsed   : {len(SB_TARGETS)}")
    print(f"  Players in StatsBomb pipeline   : {nb_players_sb:,}")
    print(f"  Nations with full data           : {nations_complete}")
    print(f"  Nations with partial data        : {nations_partial}")
    print(f"  test.csv features direct-fed    : 7 pre-computed squad features")
    print(f"  Club form features (2025-26)     : 5")
    print(f"  StatsBomb tournament features   : 4")
    print(f"  Total new features per team      : 16")
    print(f"  Total model features (×3)        : {len(FEATURE_COLS_NEW)*3}")

    print(f"\n  MODEL ACCURACY COMPARISON")
    print(f"  {'─'*50}")
    print(f"  Phase 3 (24 features)  : accuracy={old_acc:.4f}  F1={old_f1:.4f}")
    print(f"  Phase 7 (72 features)  : accuracy={new_acc:.4f}  F1={new_f1:.4f}")
    delta_acc = new_acc - old_acc
    delta_f1  = new_f1  - old_f1
    print(f"  Change                 : acc {'+' if delta_acc>=0 else ''}{delta_acc:+.4f}  "
          f"F1 {'+' if delta_f1>=0 else ''}{delta_f1:+.4f}")

    # Load simulation results (new)
    try:
        with open(SIM_PATH, encoding="utf-8") as f:
            new_sim = json.load(f)
        new_teams = {t["team"]: t for t in new_sim.get("teams", [])}
    except Exception:
        new_sim = None
        new_teams = {}

    if new_teams:
        print(f"\n  TOP 10 WIN PROBABILITIES (new simulation, {new_sim.get('simulations_run',0):,} runs)")
        print(f"  {'#':<4} {'Team':<22} {'Win%':>7} {'Final%':>8} {'Semi%':>7} "
              f"{'QF%':>6} {'Exp Gls':>8}  95% CI")
        print(f"  {'─'*72}")
        top10 = sorted(new_teams.values(), key=lambda x: x["win_probability"], reverse=True)[:10]
        for i, t in enumerate(top10, 1):
            wp  = t["win_probability"]
            n   = new_sim.get("simulations_run", 10000)
            ci  = 1.96 * np.sqrt(wp * (1 - wp) / n)
            print(
                f"  {i:<4} {t['team']:<22} {wp*100:>6.1f}% {t['final_probability']*100:>7.1f}% "
                f"{t['semifinal_probability']*100:>6.1f}% {t['quarterfinal_probability']*100:>5.1f}% "
                f"{t['expected_goals_tournament']:>7.2f}   ±{ci*100:.1f}%"
            )

    print(f"\n  OFFICIAL WC 2026 GROUP DRAW (from teams.csv)")
    print(f"  {'─'*50}")
    groups = build_official_groups()
    for letter in sorted(groups.keys()):
        teams = [t for t in groups[letter] if not t.startswith("TBD")]
        tbds  = [t for t in groups[letter] if t.startswith("TBD")]
        line  = f"  Group {letter}: {', '.join(teams)}"
        if tbds:
            line += f"  + {len(tbds)} TBD"
        print(line)

    print(f"\n  ✅ Player chain complete.")
    print(f"  Updated files:")
    print(f"    {SB_PLAYER_CSV}")
    print(f"    {NATION_CSV}")
    print(f"    {MODEL_PATH}  (new model with {len(FEATURE_COLS_NEW)*3} features)")
    print(f"    {SIM_PATH}    (fresh 10,000-run simulation)")
    print(f"    {SIM_SCRIPT}  (GROUP_STAGE corrected to official draw)")
    print("="*70)


# ───────────────────────────────────────────────────────────────────────────
#  MAIN
# ───────────────────────────────────────────────────────────────────────────

def run_player_chain():
    """
    LEARNING NOTE — The full player chain pipeline:
    Each step feeds the next:
      Step 2 → raw player-level tournament stats
      Step 3 → nation-level club form aggregation
      Step 4 → veteran flags from squad caps data
      Step 5 → single merged feature table per nation
      Step 6 → retrained XGBoost + corrected simulator
      Step 7 → before/after comparison report
    """
    t_start = datetime.now()
    print("="*65)
    print("World Cup 2026 Predictor — Phase 7: Player Performance Chain")
    print("="*65)
    print(f"  Start time : {t_start.strftime('%H:%M:%S')}")
    print(f"  DB         : {DB_PATH}")
    print(f"  StatsBomb  : {SB_BASE}")

    # Load baseline model metrics BEFORE retraining
    try:
        old_payload  = joblib.load(MODEL_PATH)
        OLD_ACCURACY = old_payload["cv_scores"]["mean_accuracy"]
        OLD_F1       = old_payload["cv_scores"]["mean_f1"]
    except Exception:
        OLD_ACCURACY = 0.5769
        OLD_F1       = 0.4518

    print(f"  Baseline   : accuracy={OLD_ACCURACY:.4f}, F1={OLD_F1:.4f}, "
          f"{len(old_payload.get('feature_names_raw', old_payload.get('feature_cols',[])))//3 or 8} features")

    # Build mappings
    code_map = build_fifa_code_map()
    groups   = build_official_groups()
    print(f"\n  Official groups loaded: {len(groups)} groups, "
          f"{sum(len(v) for v in groups.values())} team slots")

    # ── Step 2 ─────────────────────────────────────────────────────────
    sb_csv = parse_statsbomb_events()

    # ── Step 3 ─────────────────────────────────────────────────────────
    club_df = compute_club_form_scores(code_map)

    # ── Step 4 ─────────────────────────────────────────────────────────
    squads = scrape_wc_squads()

    # ── Step 5 ─────────────────────────────────────────────────────────
    features_df = aggregate_nation_features(sb_csv, club_df, squads, groups)
    save_nation_features_to_db(features_df)

    # Count complete vs partial data coverage
    has_club = (features_df["starter_quality_score"] > 0).sum()
    has_sb   = (features_df["wc_goals_per90"] > 0).sum()
    nations_complete = int((features_df["starter_quality_score"] > 0).sum())
    nations_partial  = len(features_df) - nations_complete

    # Count StatsBomb players
    try:
        nb_players_sb = len(pd.read_csv(sb_csv))
    except Exception:
        nb_players_sb = 0

    # ── Step 6 ─────────────────────────────────────────────────────────
    new_acc, new_f1 = retrain_model(OLD_ACCURACY, OLD_F1)
    update_simulator_groups(groups)
    run_simulator()

    # ── Step 7 ─────────────────────────────────────────────────────────
    validation_report(
        old_acc=OLD_ACCURACY, new_acc=new_acc,
        old_f1=OLD_F1,        new_f1=new_f1,
        nb_players_sb=nb_players_sb,
        nations_complete=nations_complete,
        nations_partial=nations_partial,
    )

    elapsed = (datetime.now() - t_start).total_seconds()
    print(f"\n  Total runtime: {elapsed/60:.1f} minutes")


if __name__ == "__main__":
    run_player_chain()
