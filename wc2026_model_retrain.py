"""
World Cup 2026 Predictor — Build 4: Model Retraining with Enriched Features
Author: Gursharan Singh Brar

WHAT THIS FILE DOES:
  Retrains the match-outcome model using THREE new feature families that
  were not available when wc2026_player_chain.py last trained the model:

    1. Head-to-head (H2H)     — 6 pairwise features  (wc2026_h2h.py / Build 1)
    2. Time-decay weighted    — 13 per-team features (wc2026_weighted_features.py / Build 2)
    3. Elo ratings            — 6 per-team features  (wc2026_elo.py / Build 3)

  We measure the marginal value of each family with a 5-stage comparison
  (baseline → +H2H → +weighted → +Elo → all-combined-pruned), weight every
  training sample by its competition importance, run feature importance
  analysis, prune dead weight (< 0.001 importance), retrain the final model
  on the pruned feature set, and overwrite wc2026_model.pkl.

HOW TO RUN:
  PYTHONIOENCODING=utf-8 python wc2026_model_retrain.py

REQUIREMENTS:
  Builds 1, 2 and 3 must have been run (head_to_head, team_stats.weighted_*,
  team_stats.current_elo / elo_ratings all populated).
"""

import sys
import warnings
import sqlite3
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import joblib

from sklearn.preprocessing   import StandardScaler
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline        import Pipeline
from sklearn.linear_model    import LogisticRegression
from sklearn.metrics         import accuracy_score, f1_score
from xgboost import XGBClassifier

warnings.filterwarnings("ignore")

PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT))

# Re-use the feature builders from the earlier Builds rather than duplicating
# their logic — this guarantees the retrain uses EXACTLY the same numbers
# that were printed (and verified) during Builds 1-3.
from wc2026_h2h import get_h2h_features
from wc2026_weighted_features import competition_weight, WEIGHTED_COLUMNS
from wc2026_elo import ELO_COLUMNS

DB_PATH    = str(PROJECT / "wc2026.db")
MODEL_PATH = str(PROJECT / "wc2026_model.pkl")

PRUNE_THRESHOLD = 0.001

# ─── FEATURE GROUPS ───────────────────────────────────────────────────────────
# LEARNING NOTE — Why import instead of hardcode?
# WEIGHTED_COLUMNS / ELO_COLUMNS are the *exact* lists Builds 2 & 3 wrote into
# team_stats.  Hardcoding a second copy here risks drift if those builds are
# ever re-run with a tweaked feature set.  BASELINE_COLS mirrors the 24-column
# FEATURE_COLS_NEW from wc2026_player_chain.py — that is the feature set the
# CURRENTLY-DEPLOYED model was trained on, so it is our fair "baseline".

BASELINE_COLS = [
    "win_rate", "avg_goals_scored", "avg_goals_conceded",
    "big_game_win_rate", "defensive_strength", "offensive_strength",
    "tournament_experience_score", "form_momentum",
    "squad_market_value_log", "squad_avg_age", "wc_participations",
    "goals_scored_last_4y", "wins_last_4y", "fifa_rank_inv",
    "is_host_nation",
    "starter_quality_score", "depth_score",
    "avg_goals_per90_squad", "avg_assists_per90_squad", "defensive_score",
    "wc_goals_per90", "wc_assists_per90", "wc_pressure_rate",
    "wc_veteran_count",
]

WEIGHTED_COLS = list(WEIGHTED_COLUMNS)   # 13 — Build 2
ELO_COLS      = list(ELO_COLUMNS)        # 6  — Build 3

H2H_COLS = [
    "h2h_win_rate_diff", "h2h_goals_diff", "h2h_big_tournament_advantage",
    "h2h_recent_momentum", "h2h_experience", "h2h_last_3y_advantage",
]

ALL_RAW_COLS = BASELINE_COLS + WEIGHTED_COLS + ELO_COLS   # 24 + 13 + 6 = 43

LABEL_MAP   = {"away_win": 0, "draw": 1, "home_win": 2}
LABEL_NAMES = ["away_win", "draw", "home_win"]


# ─── STEP 0: LOAD MATCHES + TEAM STATS ────────────────────────────────────────

def load_matches() -> pd.DataFrame:
    """
    LEARNING NOTE — One query, every stage:
    All five stages train on the SAME set of matches (only the feature
    columns change), so we load the match table exactly once.  We also pull
    `competition` here — Build 4's spec requires every training sample to be
    weighted by `competition_weight(competition)`.
    """
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT home_team, away_team, result, competition FROM match_results "
        "WHERE result IN ('home_win','draw','away_win')",
        conn
    )
    conn.close()
    print(f"   Matches loaded : {len(df):,}")
    return df


def load_team_stats_lookup(raw_cols: list) -> tuple[dict, dict]:
    """
    LEARNING NOTE — One lookup table for all 43 raw columns:
    Rather than re-querying team_stats per stage (24 cols, then 37, then 43),
    we load the UNION of every raw column we might need just once.  Each
    stage then simply selects a SUBSET of this dict's columns when it builds
    its feature matrix — cheap dict indexing, no repeat SQL.
    """
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        f"SELECT team_name, {', '.join(raw_cols)} FROM team_stats", conn
    )
    conn.close()

    df = df.fillna(0)
    stats   = df.set_index("team_name")[raw_cols].to_dict("index")
    avg_row = {c: float(df[c].mean()) for c in raw_cols}
    return stats, avg_row


def build_h2h_cache(matches_df: pd.DataFrame) -> dict:
    """
    LEARNING NOTE — Caching pairwise lookups:
    get_h2h_features() needs a DB connection and queries the `head_to_head`
    table — which is STATIC (it doesn't change match-by-match, only by team
    pair).  Calling it once per training row (32k+ times) would mean 32k
    redundant DB round-trips for what is really only ~2,000 unique pairs.
    We compute it once per (home_team, away_team) ordered pair and cache the
    6-feature dict — turning 32k DB queries into ~2,000.
    """
    conn  = sqlite3.connect(DB_PATH)
    cache = {}
    pairs = matches_df[["home_team", "away_team"]].drop_duplicates()

    for _, row in pairs.iterrows():
        key = (row["home_team"], row["away_team"])
        if key not in cache:
            cache[key] = get_h2h_features(row["home_team"], row["away_team"], conn)

    conn.close()
    print(f"   H2H pairs cached : {len(cache):,} (from {len(matches_df):,} matches)")
    return cache


# ─── STEP 1: FEATURE MATRIX BUILDER (parameterised by feature family) ────────

def build_feature_matrix(
    matches_df: pd.DataFrame,
    raw_cols: list,
    stats: dict,
    h2h_cache: dict | None = None,
) -> tuple:
    """
    LEARNING NOTE — One builder, five configurations:
    Every stage of Build 4 differs only in WHICH columns go into the matrix:
      Stage 1 (baseline)     → raw_cols = 24 baseline,           h2h_cache=None
      Stage 2 (+H2H)         → raw_cols = 24 baseline,           h2h_cache=<dict>
      Stage 3 (+weighted)    → raw_cols = 24 + 13 weighted,      h2h_cache=<dict>
      Stage 4 (+Elo)         → raw_cols = 24 + 13 + 6 Elo (=43), h2h_cache=<dict>
      Stage 5 (all combined) → raw_cols = pruned subset of 43,   h2h_cache=<dict>

    For per-team raw columns we build the familiar home/away/diff TRIPLE
    (so the simulator's existing "raw_cols → 3x expansion" logic keeps
    working unmodified).  H2H features are inherently directional
    (home-minus-away already), so they're appended once, undoubled.

    Sample weights: every row is weighted by competition_weight(competition)
    — World Cup finals carry ~6x the signal of a friendly.  XGBoost and
    LogisticRegression both accept `sample_weight` at fit time.
    """
    known = set(stats.keys())
    use_h2h = h2h_cache is not None

    rows, labels, weights = [], [], []
    skipped = 0

    for _, m in matches_df.iterrows():
        home, away, comp = m["home_team"], m["away_team"], m["competition"]

        if home not in known or away not in known:
            skipped += 1
            continue

        h, a = stats[home], stats[away]
        h_feats = [h[c] for c in raw_cols]
        a_feats = [a[c] for c in raw_cols]
        d_feats = [h_feats[i] - a_feats[i] for i in range(len(raw_cols))]

        feat_row = h_feats + a_feats + d_feats

        if use_h2h:
            h2h = h2h_cache.get((home, away))
            if h2h is None:
                h2h = {k: 0.0 for k in H2H_COLS}
            feat_row = feat_row + [h2h[k] for k in H2H_COLS]

        rows.append(feat_row)
        labels.append(LABEL_MAP[m["result"]])
        weights.append(competition_weight(comp))

    col_names = (
        [f"home_{c}" for c in raw_cols] +
        [f"away_{c}" for c in raw_cols] +
        [f"diff_{c}" for c in raw_cols]
    )
    if use_h2h:
        col_names = col_names + H2H_COLS

    X = np.array(rows,    dtype=np.float64)
    y = np.array(labels,  dtype=np.int32)
    w = np.array(weights, dtype=np.float64)
    return X, y, w, col_names, skipped


# ─── STEP 2: WEIGHTED CROSS-VALIDATION ────────────────────────────────────────

def make_pipeline() -> Pipeline:
    """
    LEARNING NOTE — Same architecture across every stage:
    StandardScaler + XGBoost, identical hyper-parameters to the previously
    deployed model (wc2026_player_chain.retrain_model).  Keeping the
    architecture fixed isolates the FEATURES as the only variable — so any
    accuracy change we measure is attributable to the new feature families,
    not to a different model.
    """
    return Pipeline([
        ("scaler", StandardScaler()),
        ("model",  XGBClassifier(
            n_estimators=400, max_depth=5, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            use_label_encoder=False, eval_metric="mlogloss",
            random_state=42, verbosity=0,
        )),
    ])


def run_cv_weighted(
    name: str, X: np.ndarray, y: np.ndarray, w: np.ndarray, n_splits: int = 5
) -> dict:
    """
    LEARNING NOTE — Weighted cross-validation:
    Identical to ordinary StratifiedKFold CV, except each fold's `.fit()`
    call also receives `model__sample_weight=w[train_idx]`.  XGBoost then
    multiplies each training example's gradient contribution by its weight
    — a World Cup final misclassification "hurts" the loss ~6x more than a
    misclassified friendly, so the model is nudged to get the BIG matches
    right even if that costs it a little accuracy on throwaway friendlies.
    """
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    accs, f1s = [], []

    for tr_idx, te_idx in cv.split(X, y):
        pipeline = make_pipeline()
        pipeline.fit(X[tr_idx], y[tr_idx], model__sample_weight=w[tr_idx])
        pred = pipeline.predict(X[te_idx])

        accs.append(accuracy_score(y[te_idx], pred))
        f1s.append(f1_score(y[te_idx], pred, average="macro", zero_division=0))

    return {
        "name":           name,
        "mean_accuracy":  round(float(np.mean(accs)), 4),
        "std_accuracy":   round(float(np.std(accs)),  4),
        "mean_f1":        round(float(np.mean(f1s)),  4),
    }


# ─── STEP 3: FEATURE IMPORTANCE + PRUNING ────────────────────────────────────

def compute_raw_col_importance(pipeline: Pipeline, col_names: list, raw_cols: list) -> dict:
    """
    LEARNING NOTE — Pruning at the RAW-COLUMN level, not the expanded level:
    The simulator (wc2026_simulator.py) rebuilds its feature vector as
    `home_X + away_X + diff_X` for every X in `feature_names_raw` — it has
    no concept of "keep home_win_rate but drop away_win_rate".  If we pruned
    individual expanded columns we'd break that contract and the simulator
    would silently feed the model a misaligned vector.

    So we sum the importance of a raw column's three expanded siblings
    (home_X + away_X + diff_X) and prune/keep the WHOLE TRIPLE together.
    This keeps `feature_names_raw` a clean list the simulator can trust.
    """
    importances = pipeline.named_steps["model"].feature_importances_
    imp = dict(zip(col_names, importances))

    raw_importance = {}
    for c in raw_cols:
        raw_importance[c] = float(
            imp.get(f"home_{c}", 0.0) + imp.get(f"away_{c}", 0.0) + imp.get(f"diff_{c}", 0.0)
        )
    return raw_importance, imp


# ─── STAGE PRINTERS ───────────────────────────────────────────────────────────

def print_stage_header(stage_no: int, title: str, n_features: int):
    print(f"\n   {'─'*64}")
    print(f"   STAGE {stage_no} — {title}   ({n_features} features)")
    print(f"   {'─'*64}")


def print_stage_result(scores: dict, baseline_acc: float | None = None):
    arrow = ""
    if baseline_acc is not None:
        delta = scores["mean_accuracy"] - baseline_acc
        sign  = "+" if delta >= 0 else ""
        arrow = f"   ({sign}{delta:+.4f} vs baseline)"
    print(f"   Mean accuracy : {scores['mean_accuracy']:.4f}  "
          f"(±{scores['std_accuracy']:.4f}){arrow}")
    print(f"   Mean F1 (macro): {scores['mean_f1']:.4f}")


def print_stage_summary_table(stage_results: list):
    print("\n" + "=" * 78)
    print("STAGE-BY-STAGE ACCURACY SUMMARY")
    print("=" * 78)
    print(f"\n  {'Stage':<28} {'#Features':>10} {'Accuracy':>10} {'Δ vs base':>10} {'F1':>8}")
    print(f"  {'─'*68}")
    base_acc = stage_results[0]["accuracy"]
    for s in stage_results:
        delta = s["accuracy"] - base_acc
        sign  = "+" if delta >= 0 else ""
        print(f"  {s['label']:<28} {s['n_features']:>10} {s['accuracy']:>10.4f} "
              f"{sign}{delta:>9.4f} {s['f1']:>8.4f}")
    print(f"  {'─'*68}")
    print(f"\n  Best stage: {max(stage_results, key=lambda s: s['accuracy'])['label']}")


def print_feature_importance(raw_importance: dict, h2h_importance: dict, top_n: int = 15):
    combined = {**raw_importance, **h2h_importance}
    ranked = sorted(combined.items(), key=lambda kv: kv[1], reverse=True)

    print("\n" + "=" * 78)
    print(f"FEATURE IMPORTANCE — TOP {top_n} (raw columns; H2H shown standalone)")
    print("=" * 78)
    print(f"\n  {'#':<4} {'Feature':<36} {'Importance':>12} {'Family':>14}")
    print(f"  {'─'*68}")
    for i, (name, val) in enumerate(ranked[:top_n], 1):
        family = (
            "H2H"        if name in H2H_COLS else
            "Elo"        if name in ELO_COLS else
            "Weighted"   if name in WEIGHTED_COLS else
            "Baseline"
        )
        print(f"  {i:<4} {name:<36} {val:>12.5f} {family:>14}")

    print(f"\n  {'─'*68}")
    print(f"  BOTTOM features (candidates for pruning, importance < {PRUNE_THRESHOLD}):")
    bottom = [kv for kv in ranked if kv[1] < PRUNE_THRESHOLD]
    if not bottom:
        print("   (none — every feature cleared the threshold)")
    else:
        for name, val in bottom:
            family = (
                "H2H"        if name in H2H_COLS else
                "Elo"        if name in ELO_COLS else
                "Weighted"   if name in WEIGHTED_COLS else
                "Baseline"
            )
            print(f"   {name:<36} {val:>12.5f} {family:>14}")


# ─── STEP 4: SAVE FINAL MODEL ─────────────────────────────────────────────────

def save_final_model(
    pipeline, model_name: str, scores: dict,
    raw_cols: list, h2h_cols: list, avg_row: dict,
):
    """
    LEARNING NOTE — Extending the payload contract:
    The existing payload (model_name, feature_cols, label_map, label_names,
    cv_scores, trained_at, avg_row, feature_names_raw) is preserved so older
    consumers keep working.  We ADD two new keys:
      'h2h_feature_names' — the (possibly pruned) list of H2H feature names,
                            in the exact order the model expects them
      'uses_h2h'          — boolean flag the simulator checks before doing
                            the extra pairwise DB lookups
    This keeps the contract backward compatible: a simulator that doesn't
    know about H2H simply ignores the new keys (payload.get(..., default)).
    """
    col_names = (
        [f"home_{c}" for c in raw_cols] +
        [f"away_{c}" for c in raw_cols] +
        [f"diff_{c}" for c in raw_cols] +
        list(h2h_cols)
    )

    payload = {
        "pipeline":          pipeline,
        "model_name":        model_name,
        "feature_cols":      col_names,
        "label_map":         LABEL_MAP,
        "label_names":       LABEL_NAMES,
        "cv_scores":         scores,
        "trained_at":        datetime.now().isoformat(),
        "avg_row":           avg_row,
        "feature_names_raw": list(raw_cols),
        "h2h_feature_names": list(h2h_cols),
        "uses_h2h":          len(h2h_cols) > 0,
    }
    joblib.dump(payload, MODEL_PATH)
    size_kb = Path(MODEL_PATH).stat().st_size // 1024
    print(f"\n   Saved -> {MODEL_PATH}  ({size_kb} KB)")
    print(f"   Total features      : {len(col_names)}  "
          f"({len(raw_cols)} raw x 3 + {len(h2h_cols)} H2H)")
    print(f"   feature_names_raw   : {raw_cols}")
    print(f"   h2h_feature_names   : {h2h_cols}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def run_build4():
    print("World Cup 2026 Predictor - Build 4: Model Retraining")
    print("=" * 78)
    print("  Adding: H2H (6) + time-decay weighted (13) + Elo (6) features")
    print("  Sample weighting: every match weighted by competition_weight()")
    print("=" * 78)

    print("\n[1/6] Loading matches and team stats ...")
    matches_df       = load_matches()
    stats, avg_row   = load_team_stats_lookup(ALL_RAW_COLS)
    print(f"   Teams in stats   : {len(stats)}")
    print(f"   Raw feature pool : {len(ALL_RAW_COLS)} "
          f"(baseline {len(BASELINE_COLS)} + weighted {len(WEIGHTED_COLS)} + elo {len(ELO_COLS)})")

    print("\n[2/6] Building H2H pairwise cache (Build 1 head_to_head table) ...")
    h2h_cache = build_h2h_cache(matches_df)

    # ── 5-stage progressive comparison ───────────────────────────────────────
    print("\n[3/6] Running 5-stage feature comparison (XGBoost, weighted CV) ...")

    stage_results  = []
    stage_pipelines = {}

    # Stage 1 — baseline only
    print_stage_header(1, "Baseline (current production feature set)", len(BASELINE_COLS) * 3)
    X1, y1, w1, c1, skipped1 = build_feature_matrix(matches_df, BASELINE_COLS, stats, h2h_cache=None)
    print(f"   Matches used : {len(X1):,}  (skipped {skipped1:,})")
    s1 = run_cv_weighted("Stage 1 - baseline", X1, y1, w1)
    print_stage_result(s1)
    stage_results.append({"label": "1. Baseline",        "n_features": X1.shape[1],
                          "accuracy": s1["mean_accuracy"], "f1": s1["mean_f1"]})
    base_acc = s1["mean_accuracy"]

    # Stage 2 — baseline + H2H
    print_stage_header(2, "+ Head-to-head (Build 1: 6 pairwise features)", len(BASELINE_COLS) * 3 + len(H2H_COLS))
    X2, y2, w2, c2, skipped2 = build_feature_matrix(matches_df, BASELINE_COLS, stats, h2h_cache=h2h_cache)
    print(f"   Matches used : {len(X2):,}  (skipped {skipped2:,})")
    s2 = run_cv_weighted("Stage 2 - +H2H", X2, y2, w2)
    print_stage_result(s2, base_acc)
    stage_results.append({"label": "2. + H2H",           "n_features": X2.shape[1],
                          "accuracy": s2["mean_accuracy"], "f1": s2["mean_f1"]})

    # Stage 3 — + weighted
    raw3 = BASELINE_COLS + WEIGHTED_COLS
    print_stage_header(3, "+ Time-decay weighted (Build 2: 13 per-team features)", len(raw3) * 3 + len(H2H_COLS))
    X3, y3, w3, c3, skipped3 = build_feature_matrix(matches_df, raw3, stats, h2h_cache=h2h_cache)
    print(f"   Matches used : {len(X3):,}  (skipped {skipped3:,})")
    s3 = run_cv_weighted("Stage 3 - +weighted", X3, y3, w3)
    print_stage_result(s3, base_acc)
    stage_results.append({"label": "3. + Weighted",      "n_features": X3.shape[1],
                          "accuracy": s3["mean_accuracy"], "f1": s3["mean_f1"]})

    # Stage 4 — + Elo  (= full 43-raw-col feature set)
    raw4 = BASELINE_COLS + WEIGHTED_COLS + ELO_COLS
    print_stage_header(4, "+ Elo ratings (Build 3: 6 per-team features) -- FULL SET", len(raw4) * 3 + len(H2H_COLS))
    X4, y4, w4, c4, skipped4 = build_feature_matrix(matches_df, raw4, stats, h2h_cache=h2h_cache)
    print(f"   Matches used : {len(X4):,}  (skipped {skipped4:,})")
    s4 = run_cv_weighted("Stage 4 - +Elo (full)", X4, y4, w4)
    print_stage_result(s4, base_acc)
    stage_results.append({"label": "4. + Elo (full set)", "n_features": X4.shape[1],
                          "accuracy": s4["mean_accuracy"], "f1": s4["mean_f1"]})

    # ── Feature importance on the FULL set ───────────────────────────────────
    print("\n[4/6] Feature importance analysis (training on full data, full feature set) ...")
    full_pipeline = make_pipeline()
    full_pipeline.fit(X4, y4, model__sample_weight=w4)
    raw_importance, full_imp = compute_raw_col_importance(full_pipeline, c4, raw4)
    h2h_importance = {k: float(full_imp.get(k, 0.0)) for k in H2H_COLS}
    print_feature_importance(raw_importance, h2h_importance, top_n=15)

    pruned_raw = [c for c in raw4    if raw_importance[c]   >= PRUNE_THRESHOLD]
    dropped_raw = [c for c in raw4   if raw_importance[c]   <  PRUNE_THRESHOLD]
    pruned_h2h  = [c for c in H2H_COLS if h2h_importance[c] >= PRUNE_THRESHOLD]
    dropped_h2h = [c for c in H2H_COLS if h2h_importance[c] <  PRUNE_THRESHOLD]

    print(f"\n   Raw columns   : {len(raw4)} -> kept {len(pruned_raw)}, dropped {len(dropped_raw)}")
    if dropped_raw:
        print(f"     dropped: {dropped_raw}")
    print(f"   H2H columns   : {len(H2H_COLS)} -> kept {len(pruned_h2h)}, dropped {len(dropped_h2h)}")
    if dropped_h2h:
        print(f"     dropped: {dropped_h2h}")

    # Stage 5 — all combined, pruned
    n_pruned_feats = len(pruned_raw) * 3 + len(pruned_h2h)
    print_stage_header(5, "All combined (pruned, importance >= %.3f)" % PRUNE_THRESHOLD, n_pruned_feats)
    if pruned_raw == raw4 and pruned_h2h == H2H_COLS:
        print("   No features pruned -- stage 5 == stage 4.")
        X5, y5, w5, c5, skipped5 = X4, y4, w4, c4, skipped4
        s5 = s4
    else:
        X5, y5, w5, c5, skipped5 = build_feature_matrix(matches_df, pruned_raw, stats, h2h_cache=h2h_cache)
        # If H2H was pruned entirely, drop those 6 trailing columns from X5/c5
        if not pruned_h2h and dropped_h2h:
            keep_idx = [i for i, name in enumerate(c5) if name not in H2H_COLS]
            X5 = X5[:, keep_idx]
            c5 = [c5[i] for i in keep_idx]
        elif pruned_h2h != H2H_COLS:
            # Partial H2H pruning — drop only the dropped H2H columns
            keep_idx = [i for i, name in enumerate(c5) if name not in dropped_h2h]
            X5 = X5[:, keep_idx]
            c5 = [c5[i] for i in keep_idx]
        print(f"   Matches used : {len(X5):,}  (skipped {skipped5:,})")
        s5 = run_cv_weighted("Stage 5 - pruned all-combined", X5, y5, w5)
    print_stage_result(s5, base_acc)
    stage_results.append({"label": "5. All combined (pruned)", "n_features": X5.shape[1],
                          "accuracy": s5["mean_accuracy"], "f1": s5["mean_f1"]})

    print_stage_summary_table(stage_results)

    # ── Compare XGBoost vs Logistic Regression on the FINAL (pruned) feature set ──
    print("\n[5/6] Final model selection (XGBoost vs Logistic Regression on pruned set) ...")
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    lr_accs, lr_f1s = [], []
    xgb_accs, xgb_f1s = [], []
    for tr_idx, te_idx in cv.split(X5, y5):
        lr = Pipeline([("scaler", StandardScaler()),
                       ("model", LogisticRegression(max_iter=2000, C=1.0, solver="lbfgs", random_state=42))])
        lr.fit(X5[tr_idx], y5[tr_idx], model__sample_weight=w5[tr_idx])
        pred = lr.predict(X5[te_idx])
        lr_accs.append(accuracy_score(y5[te_idx], pred))
        lr_f1s.append(f1_score(y5[te_idx], pred, average="macro", zero_division=0))

        xgb = make_pipeline()
        xgb.fit(X5[tr_idx], y5[tr_idx], model__sample_weight=w5[tr_idx])
        pred = xgb.predict(X5[te_idx])
        xgb_accs.append(accuracy_score(y5[te_idx], pred))
        xgb_f1s.append(f1_score(y5[te_idx], pred, average="macro", zero_division=0))

    lr_scores  = {"name": "Logistic Regression", "mean_accuracy": round(float(np.mean(lr_accs)), 4),
                  "mean_f1": round(float(np.mean(lr_f1s)), 4)}
    xgb_scores = {"name": "XGBoost",             "mean_accuracy": round(float(np.mean(xgb_accs)), 4),
                  "mean_f1": round(float(np.mean(xgb_f1s)), 4)}

    print(f"\n   {'Model':<25} {'Accuracy':>10} {'F1':>8}")
    print(f"   {'─'*45}")
    for s in (lr_scores, xgb_scores):
        print(f"   {s['name']:<25} {s['mean_accuracy']:>10.4f} {s['mean_f1']:>8.4f}")

    winner_name   = "XGBoost" if xgb_scores["mean_f1"] >= lr_scores["mean_f1"] else "Logistic Regression"
    winner_scores = xgb_scores if winner_name == "XGBoost" else lr_scores
    print(f"\n   Winner: {winner_name}  "
          f"(accuracy={winner_scores['mean_accuracy']:.4f}, F1={winner_scores['mean_f1']:.4f})")

    print("\n[6/6] Training final model on 100% of data and saving ...")
    final_pipeline = make_pipeline() if winner_name == "XGBoost" else Pipeline([
        ("scaler", StandardScaler()),
        ("model",  LogisticRegression(max_iter=2000, C=1.0, solver="lbfgs", random_state=42))
    ])
    final_pipeline.fit(X5, y5, model__sample_weight=w5)

    final_avg_row = {c: avg_row[c] for c in pruned_raw}
    save_final_model(
        final_pipeline, winner_name, winner_scores,
        raw_cols=pruned_raw, h2h_cols=pruned_h2h, avg_row=final_avg_row,
    )

    print("\n" + "=" * 78)
    print("BUILD 4 RETRAINING COMPLETE")
    print("=" * 78)
    print(f"  Old model accuracy (production baseline) : 0.5766  (from earlier CV run)")
    print(f"  New model accuracy (pruned, all combined): {winner_scores['mean_accuracy']:.4f}")
    delta = winner_scores["mean_accuracy"] - 0.5766
    sign  = "+" if delta >= 0 else ""
    print(f"  Net change                                : {sign}{delta:+.4f}")
    print("=" * 78)
    print("\nNext: re-run wc2026_simulator.py to regenerate tournament probabilities")
    print("      with the enriched model (the simulator has been updated to read")
    print("      h2h_feature_names / uses_h2h from the payload automatically).")


if __name__ == "__main__":
    run_build4()
