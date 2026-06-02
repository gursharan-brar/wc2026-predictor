"""
World Cup 2026 Predictor — Phase 3: Match Prediction Model
Author: Gursharan Singh Brar

WHAT THIS FILE DOES:
  Builds a machine-learning model that predicts the outcome of any international
  football match as one of three classes: home_win, draw, or away_win.

  Two models are trained and compared:
    1. Logistic Regression  — fast, interpretable, good baseline
    2. XGBoost              — gradient-boosted trees, usually more accurate

  The better model is saved to wc2026_model.pkl for use by the simulator.

HOW TO RUN:
  python wc2026_model.py

REQUIREMENTS:
  Phase 1 + Phase 2 must have been run first.
  pip install scikit-learn xgboost joblib pandas numpy
"""

import sqlite3
import warnings
import numpy as np
import pandas as pd
import joblib
from datetime import datetime
from pathlib import Path

from sklearn.linear_model    import LogisticRegression
from sklearn.preprocessing   import LabelEncoder, StandardScaler
from sklearn.model_selection import StratifiedKFold, cross_validate
from sklearn.pipeline        import Pipeline
from sklearn.metrics         import (accuracy_score, precision_score,
                                      recall_score, f1_score,
                                      classification_report, confusion_matrix)
from xgboost import XGBClassifier

warnings.filterwarnings("ignore")   # suppress convergence warnings on small folds

DB_PATH    = "wc2026.db"
MODEL_PATH = "wc2026_model.pkl"

# ─── FEATURE COLUMNS ──────────────────────────────────────────────────────────
# These 8 columns exist in team_stats after Phase 2.
# For each match we build: 8 home cols + 8 away cols + 8 diff cols = 24 features.

FEATURE_COLS = [
    "win_rate",
    "avg_goals_scored",
    "avg_goals_conceded",
    "big_game_win_rate",
    "defensive_strength",
    "offensive_strength",
    "tournament_experience_score",
    "form_momentum",
]

# Label encoding:  0 = away_win  |  1 = draw  |  2 = home_win
LABEL_MAP     = {"away_win": 0, "draw": 1, "home_win": 2}
LABEL_NAMES   = ["away_win", "draw", "home_win"]


# ─── STEP 1: BUILD TRAINING DATA ──────────────────────────────────────────────

def load_team_stats_lookup() -> dict:
    """
    LEARNING NOTE — Feature lookup table:
    Instead of doing a SQL JOIN for every single match (slow for 32k rows),
    we load all team stats once into a Python dictionary keyed by team name.
    Dictionary lookup is O(1) — it takes the same time whether we have 10
    teams or 10,000.  This is a common performance pattern in ML pipelines.
    """
    conn = sqlite3.connect(DB_PATH)
    df   = pd.read_sql_query(
        f"SELECT team_name, {', '.join(FEATURE_COLS)} FROM team_stats",
        conn
    )
    conn.close()

    # Fill any NULLs with 0 so no NaN leaks into the model
    df = df.fillna(0)
    return df.set_index("team_name")[FEATURE_COLS].to_dict("index")


def build_feature_matrix() -> tuple[np.ndarray, np.ndarray, list[str]]:
    """
    LEARNING NOTE — Feature matrix construction:
    A machine-learning model expects a 2-D matrix X where:
      - Each ROW is one training example (one match)
      - Each COLUMN is one feature (a number describing that example)

    For each match we create 24 features:
      home_win_rate, home_avg_goals_scored, ... (8 cols for the home team)
      away_win_rate, away_avg_goals_scored, ... (8 cols for the away team)
      diff_win_rate, diff_avg_goals_scored, ... (8 difference cols)

    The DIFFERENCE features are especially powerful because the model can
    learn "if home team is much stronger than away team, predict home_win"
    purely from the gap in numbers rather than absolute values.

    KNOWN LIMITATION:
    We are using *current* team stats (2024/25 snapshot) to label matches
    going back to 1872.  This is called "data leakage" in the strict sense.
    A fully correct approach would require a time-series of team ratings.
    In practice, for forecasting a 2026 tournament, current form is actually
    what we *want* the model to prioritise — so this is a deliberate tradeoff,
    not a mistake.
    """
    conn       = sqlite3.connect(DB_PATH)
    matches_df = pd.read_sql_query(
        "SELECT home_team, away_team, result FROM match_results "
        "WHERE result IN ('home_win','draw','away_win')",
        conn
    )
    conn.close()

    stats = load_team_stats_lookup()
    known_teams = set(stats.keys())

    rows   = []
    labels = []
    skipped = 0

    for _, match in matches_df.iterrows():
        home = match["home_team"]
        away = match["away_team"]

        # Skip if we have no stats for either team
        if home not in known_teams or away not in known_teams:
            skipped += 1
            continue

        h = stats[home]
        a = stats[away]

        home_feats = [h[c] for c in FEATURE_COLS]
        away_feats = [a[c] for c in FEATURE_COLS]
        diff_feats = [h[c] - a[c] for c in FEATURE_COLS]

        rows.append(home_feats + away_feats + diff_feats)
        labels.append(LABEL_MAP[match["result"]])

    print(f"   Matches used   : {len(rows):,}")
    print(f"   Matches skipped: {skipped:,} (no stats for one/both teams)")

    # Column names for interpretability
    col_names = (
        [f"home_{c}" for c in FEATURE_COLS] +
        [f"away_{c}" for c in FEATURE_COLS] +
        [f"diff_{c}" for c in FEATURE_COLS]
    )

    X = np.array(rows,   dtype=np.float64)
    y = np.array(labels, dtype=np.int32)
    return X, y, col_names


# ─── STEP 2: CROSS-VALIDATION ─────────────────────────────────────────────────

def run_cross_validation(
    name: str,
    pipeline,
    X: np.ndarray,
    y: np.ndarray,
    n_splits: int = 5
) -> dict:
    """
    LEARNING NOTE — Why cross-validation instead of a single train/test split?
    If you split data once (e.g. 80% train, 20% test), your score depends
    heavily on *which* 20% you happened to pick.  You might get lucky or
    unlucky.  Cross-validation splits the data N times, trains on N-1 folds
    and tests on the held-out fold, then averages the scores.  This gives a
    much more reliable estimate of how the model will perform on truly unseen
    matches.

    We use StratifiedKFold which ensures each fold has roughly the same
    proportion of home_win / draw / away_win labels.  Without this, a fold
    might have almost no draws, making evaluation misleading.
    """
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)

    print(f"\n   {'─'*56}")
    print(f"   {name} — {n_splits}-Fold Cross Validation")
    print(f"   {'─'*56}")
    print(f"   {'Fold':<6} {'Accuracy':>9} {'Precision':>10} {'Recall':>8} {'F1':>8}")
    print(f"   {'─'*56}")

    accs = precs = recs = f1s = []
    accs, precs, recs, f1s = [], [], [], []

    for fold, (train_idx, test_idx) in enumerate(cv.split(X, y), 1):
        X_tr, X_te = X[train_idx], X[test_idx]
        y_tr, y_te = y[train_idx], y[test_idx]

        pipeline.fit(X_tr, y_tr)
        y_pred = pipeline.predict(X_te)

        acc  = accuracy_score(y_te, y_pred)
        prec = precision_score(y_te, y_pred, average="macro", zero_division=0)
        rec  = recall_score(y_te, y_pred, average="macro", zero_division=0)
        f1   = f1_score(y_te, y_pred, average="macro", zero_division=0)

        accs.append(acc);  precs.append(prec)
        recs.append(rec);  f1s.append(f1)

        print(f"   {fold:<6} {acc:>9.4f} {prec:>10.4f} {rec:>8.4f} {f1:>8.4f}")

    print(f"   {'─'*56}")
    print(f"   {'Mean':<6} {np.mean(accs):>9.4f} {np.mean(precs):>10.4f} "
          f"{np.mean(recs):>8.4f} {np.mean(f1s):>8.4f}")
    print(f"   {'Std':<6} {np.std(accs):>9.4f} {np.std(precs):>10.4f} "
          f"{np.std(recs):>8.4f} {np.std(f1s):>8.4f}")

    return {
        "name":         name,
        "mean_accuracy":  round(float(np.mean(accs)),  4),
        "mean_precision": round(float(np.mean(precs)), 4),
        "mean_recall":    round(float(np.mean(recs)),  4),
        "mean_f1":        round(float(np.mean(f1s)),   4),
        "pipeline":       pipeline,
    }


# ─── STEP 3: FULL TRAIN ON ALL DATA ───────────────────────────────────────────

def train_final_model(pipeline, X: np.ndarray, y: np.ndarray) -> object:
    """
    LEARNING NOTE — Final training on full dataset:
    Cross-validation only EVALUATES a model — it doesn't produce the model
    you deploy.  After CV tells us which model architecture is better, we
    retrain on 100% of the data (not just 80%) so the final model has seen
    every example.  More data almost always means a better model.
    """
    pipeline.fit(X, y)
    return pipeline


# ─── STEP 4: FEATURE IMPORTANCE ───────────────────────────────────────────────

def print_feature_importance(pipeline, col_names: list[str], model_name: str):
    """
    LEARNING NOTE — Feature importance:
    After training, we can ask the model "which features did you rely on most?"
    For XGBoost this is called 'feature_importances_' — a score per feature
    showing how much it reduced prediction error.  High importance = the model
    found this feature very useful.  Low importance = consider dropping it in
    future to simplify the model.
    """
    try:
        if "xgb" in model_name.lower():
            importances = pipeline.named_steps["model"].feature_importances_
        else:
            # Logistic regression: use mean absolute coefficient across classes
            importances = np.abs(pipeline.named_steps["model"].coef_).mean(axis=0)

        pairs = sorted(zip(col_names, importances), key=lambda x: x[1], reverse=True)

        print(f"\n   Top 10 features ({model_name}):")
        for feat, imp in pairs[:10]:
            bar = "█" * int(imp * 40 / pairs[0][1])
            print(f"   {feat:<42} {imp:.4f}  {bar}")
    except Exception as e:
        print(f"   (Feature importance not available: {e})")


# ─── STEP 5: CONFUSION MATRIX ─────────────────────────────────────────────────

def print_confusion_matrix(pipeline, X: np.ndarray, y: np.ndarray, name: str):
    """
    LEARNING NOTE — Confusion matrix:
    A confusion matrix shows where the model gets confused.  Rows = actual
    labels, columns = predicted labels.  Diagonal = correct predictions.
    Off-diagonal = mistakes.  For football, models almost always under-predict
    draws because draws are the least common outcome and hardest to distinguish.
    """
    y_pred = pipeline.predict(X)
    cm     = confusion_matrix(y, y_pred)

    print(f"\n   Confusion Matrix ({name}) — trained on full dataset:")
    print(f"   {'':15} {'pred away':>10} {'pred draw':>10} {'pred home':>10}")
    for i, row_label in enumerate(LABEL_NAMES):
        print(f"   {'actual ' + row_label:<15} {cm[i][0]:>10} {cm[i][1]:>10} {cm[i][2]:>10}")

    print(f"\n   Full classification report:\n")
    print(classification_report(y, y_pred, target_names=LABEL_NAMES, zero_division=0))


# ─── STEP 6: SAVE MODEL ───────────────────────────────────────────────────────

def save_model(pipeline, model_name: str, scores: dict, col_names: list[str]):
    """
    LEARNING NOTE — Model serialisation with joblib:
    'Serialisation' means converting a Python object (the trained model) into
    bytes that can be written to disk and loaded back later.  joblib is
    preferred over Python's built-in pickle for sklearn/XGBoost models because
    it handles large numpy arrays more efficiently.

    We save not just the pipeline but also metadata (which features to use,
    when it was trained, its CV scores) so the simulator doesn't need to
    re-derive this information.
    """
    payload = {
        "pipeline":    pipeline,
        "model_name":  model_name,
        "feature_cols": col_names,
        "label_map":   LABEL_MAP,
        "label_names": LABEL_NAMES,
        "cv_scores":   scores,
        "trained_at":  datetime.now().isoformat(),
    }
    joblib.dump(payload, MODEL_PATH)
    size_kb = Path(MODEL_PATH).stat().st_size // 1024
    print(f"\n   Saved: {MODEL_PATH}  ({size_kb} KB)")
    print(f"   Model: {model_name}")
    print(f"   CV Accuracy: {scores['mean_accuracy']:.4f}  |  F1: {scores['mean_f1']:.4f}")


# ─── PUBLIC API: predict_match ─────────────────────────────────────────────────

def predict_match(
    home_team: str,
    away_team: str,
    model_path: str = MODEL_PATH
) -> dict:
    """
    LEARNING NOTE — Inference (using a trained model):
    'Training' teaches the model from historical data.  'Inference' is using
    that trained model to make a prediction on new, unseen inputs.  Here we:
      1. Load the saved model from disk
      2. Look up the two teams' current stats
      3. Build the same 24-feature vector we used during training
      4. Call model.predict_proba() — this returns probabilities for each class
         rather than just the winning class, which is what the simulator needs

    Returns a dict like:
      {"home_win": 0.52, "draw": 0.24, "away_win": 0.24, "predicted": "home_win"}
    """
    payload    = joblib.load(model_path)
    pipeline   = payload["pipeline"]
    feat_cols  = payload["feature_cols"]
    label_names = payload["label_names"]

    stats = load_team_stats_lookup()

    # Graceful fallback for unknown teams — use league average
    avg_row = {c: np.mean([s[c] for s in stats.values()]) for c in FEATURE_COLS}
    h = stats.get(home_team, avg_row)
    a = stats.get(away_team, avg_row)

    home_feats = [h[c] for c in FEATURE_COLS]
    away_feats = [a[c] for c in FEATURE_COLS]
    diff_feats = [h[c] - a[c] for c in FEATURE_COLS]

    X_pred = np.array([home_feats + away_feats + diff_feats])
    probs  = pipeline.predict_proba(X_pred)[0]

    result = {label_names[i]: round(float(probs[i]), 4) for i in range(3)}
    result["predicted"] = label_names[int(np.argmax(probs))]

    # Warn if either team used the fallback
    if home_team not in stats:
        result["home_team_warning"] = f"'{home_team}' not in stats — used league average"
    if away_team not in stats:
        result["away_team_warning"] = f"'{away_team}' not in stats — used league average"

    return result


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def run_phase3():
    """
    LEARNING NOTE — The full ML workflow:
    Every ML project follows the same skeleton:
      1. Prepare data       → build_feature_matrix()
      2. Choose models      → LogisticRegression, XGBClassifier
      3. Evaluate fairly    → cross_validate() — never evaluate on training data!
      4. Pick winner        → compare mean F1 scores
      5. Train final model  → on 100% of data
      6. Save               → joblib.dump()
      7. Verify             → predict_match() spot-checks

    The separation between evaluation (CV) and final training is critical.
    If you evaluate on training data you get inflated scores that don't
    reflect real-world performance — this mistake is called "overfitting".
    """
    print("World Cup 2026 Predictor — Phase 3: Match Prediction Model")
    print("=" * 65)

    # ── 1. Build feature matrix ────────────────────────────────────────────
    print("\n[1/6] Building feature matrix from match_results + team_stats ...")
    X, y, col_names = build_feature_matrix()
    print(f"   Feature matrix shape: {X.shape}  "
          f"({X.shape[0]:,} matches x {X.shape[1]} features)")
    label_counts = {name: int((y == i).sum()) for i, name in enumerate(LABEL_NAMES)}
    print(f"   Label distribution : {label_counts}")

    # ── 2. Define model pipelines ──────────────────────────────────────────
    # LEARNING NOTE — Pipeline:
    # A Pipeline chains preprocessing + model into one object.  This prevents
    # a subtle bug called "data leakage" where the scaler learns statistics
    # from the test set.  With a Pipeline the scaler only sees training data
    # during each CV fold, exactly as it would in production.
    print("\n[2/6] Defining model pipelines ...")

    lr_pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("model",  LogisticRegression(
            max_iter    = 2000,
            C           = 1.0,
            solver      = "lbfgs",   # lbfgs handles multi-class natively in sklearn 1.5+
            random_state= 42,
        ))
    ])

    xgb_pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("model",  XGBClassifier(
            n_estimators      = 400,
            max_depth         = 5,
            learning_rate     = 0.05,
            subsample         = 0.8,
            colsample_bytree  = 0.8,
            use_label_encoder = False,
            eval_metric       = "mlogloss",
            random_state      = 42,
            verbosity         = 0,
        ))
    ])

    print("   LogisticRegression  : multinomial, lbfgs, C=1.0, max_iter=2000")
    print("   XGBClassifier       : 400 trees, depth=5, lr=0.05, subsample=0.8")

    # ── 3. Cross-validation ────────────────────────────────────────────────
    print("\n[3/6] Running 5-fold cross-validation (this may take ~60s) ...")

    lr_scores  = run_cross_validation("Logistic Regression", lr_pipeline,  X, y)
    xgb_scores = run_cross_validation("XGBoost",             xgb_pipeline, X, y)

    # ── 4. Compare models ──────────────────────────────────────────────────
    print("\n[4/6] Model comparison:")
    print(f"\n   {'Model':<25} {'Accuracy':>9} {'Precision':>10} {'Recall':>8} {'F1':>8}")
    print(f"   {'─'*62}")
    for s in [lr_scores, xgb_scores]:
        print(f"   {s['name']:<25} {s['mean_accuracy']:>9.4f} "
              f"{s['mean_precision']:>10.4f} {s['mean_recall']:>8.4f} "
              f"{s['mean_f1']:>8.4f}")

    # Pick winner by macro F1 (more informative than accuracy on imbalanced labels)
    if xgb_scores["mean_f1"] >= lr_scores["mean_f1"]:
        winner_scores   = xgb_scores
        winner_pipeline = xgb_pipeline
        winner_name     = "XGBoost"
    else:
        winner_scores   = lr_scores
        winner_pipeline = lr_pipeline
        winner_name     = "Logistic Regression"

    print(f"\n   Winner: {winner_name}  "
          f"(F1 = {winner_scores['mean_f1']:.4f})")

    # ── 5. Train final model on 100% of data ──────────────────────────────
    print(f"\n[5/6] Training final {winner_name} on full dataset ...")
    final_pipeline = train_final_model(winner_pipeline, X, y)
    print("   Done.")

    print_confusion_matrix(final_pipeline, X, y, winner_name)
    print_feature_importance(final_pipeline, col_names, winner_name)

    # ── 6. Save ────────────────────────────────────────────────────────────
    print(f"\n[6/6] Saving model ...")
    save_model(final_pipeline, winner_name, winner_scores, col_names)

    # ── 7. Spot-check with predict_match ──────────────────────────────────
    print("\n" + "=" * 65)
    print("SPOT-CHECK: predict_match() on 6 well-known fixtures")
    print("=" * 65)

    fixtures = [
        ("France",    "Argentina"),
        ("Brazil",    "Germany"),
        ("Spain",     "England"),
        ("Morocco",   "USA"),
        ("Japan",     "South Korea"),
        ("Canada",    "Mexico"),
    ]

    print(f"\n   {'Home':<14} {'Away':<14} {'home_win':>9} {'draw':>6} {'away_win':>9} {'predicted'}")
    print(f"   {'─'*70}")
    for home, away in fixtures:
        p = predict_match(home, away, MODEL_PATH)
        print(f"   {home:<14} {away:<14} "
              f"{p['home_win']:>9.3f} {p['draw']:>6.3f} {p['away_win']:>9.3f}  "
              f"{p['predicted']}")

    print("\n" + "=" * 65)
    print("Phase 3 complete.")
    print(f"  Model file : {MODEL_PATH}")
    print(f"  Winner     : {winner_name}")
    print(f"  CV Accuracy: {winner_scores['mean_accuracy']:.4f}")
    print(f"  CV F1      : {winner_scores['mean_f1']:.4f}")
    print("=" * 65)
    print("\nNext command: python wc2026_model.py")
    print("Say 'next' when ready for Phase 4 — Monte Carlo Simulator")


if __name__ == "__main__":
    run_phase3()
