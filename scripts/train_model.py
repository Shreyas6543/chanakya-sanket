"""
Phase 5c — XGBoost Model Training

Trains on the dataset built by build_ml_dataset.py.
Time-based 80/20 split — NEVER random shuffle (prevents leakage).

Output:
    data/ml/model.json          — XGBoost model artifact
    data/ml/feature_importance.csv
    data/ml/training_report.txt — full metrics + threshold analysis

Usage:
    python scripts/train_model.py
    python scripts/train_model.py --threshold 0.45   # custom fire threshold
"""

import argparse
from pathlib import Path

import json
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import (
    classification_report, roc_auc_score, confusion_matrix,
)
from sklearn.inspection import permutation_importance

ROOT    = Path(__file__).resolve().parent.parent
ML_DIR  = ROOT / "data" / "ml"
OUT_DIR = ML_DIR

FEATURES = [
    "rsi", "rsi_above_55", "rsi_below_45",
    "vwap_dist_pct",
    "atr_pct",
    "ema_bull_align", "ema_bear_align",
    "strat_rsi", "strat_vwap", "strat_orb",
    "n_strategies",
    "regime_trending",
    "hour", "minute", "day_of_week", "month",
    "is_banknifty",
    "pcr", "oi_change_pct", "has_oi",
    # direction as binary
    "is_call",
]


def load_dataset() -> pd.DataFrame:
    path = ML_DIR / "dataset.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found at {path}. Run build_ml_dataset.py first.")
    df = pd.read_parquet(path)
    df["is_call"] = (df["direction"] == "CALL").astype(int)
    df = df.sort_values("date").reset_index(drop=True)
    return df


def time_split(df: pd.DataFrame, train_pct: float = 0.8):
    """
    Split by date — all training rows come before all test rows.
    Never random shuffle.
    """
    dates     = df["date"].unique()
    cutoff    = dates[int(len(dates) * train_pct)]
    train     = df[df["date"] < cutoff].copy()
    test      = df[df["date"] >= cutoff].copy()
    return train, test, cutoff


def threshold_analysis(y_true, y_prob) -> pd.DataFrame:
    """WR and trade count at each probability threshold."""
    rows = []
    for t in np.arange(0.30, 0.75, 0.02):
        mask   = y_prob >= t
        n      = mask.sum()
        if n == 0:
            continue
        wins   = y_true[mask].sum()
        wr     = round(wins / n * 100, 1)
        rows.append({"threshold": round(t, 2), "trades": int(n), "wins": int(wins), "win_rate_pct": wr})
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=0.45,
                        help="Probability threshold to call a signal (default 0.45)")
    args = parser.parse_args()

    print("Loading dataset...")
    df = load_dataset()
    print(f"  {len(df):,} rows | {df['date'].min()} → {df['date'].max()}")
    print(f"  Positive rate: {df['label'].mean():.1%}\n")

    train, test, cutoff = time_split(df)
    print(f"Train: {len(train):,} rows ({train['date'].min()} → {train['date'].max()})")
    print(f"Test:  {len(test):,}  rows ({test['date'].min()} → {test['date'].max()})\n")

    X_train = train[FEATURES]
    y_train = train["label"]
    X_test  = test[FEATURES]
    y_test  = test["label"]

    # Class imbalance: ~31% positive — use scale_pos_weight
    neg     = int((y_train == 0).sum())
    pos     = int((y_train == 1).sum())
    spw     = round(neg / pos, 2)
    print(f"Class balance — neg: {neg:,} pos: {pos:,} → scale_pos_weight: {spw}\n")

    # HistGradientBoostingClassifier: sklearn's native GBDT
    # - No OpenMP / no libomp needed on macOS
    # - Handles NaN natively (no imputation needed for pcr/oi_change_pct)
    # - class_weight corrects imbalance (equivalent to scale_pos_weight)
    model = HistGradientBoostingClassifier(
        max_iter            = 500,
        max_depth           = 4,
        learning_rate       = 0.05,
        class_weight        = "balanced",
        early_stopping      = True,
        validation_fraction = 0.1,
        n_iter_no_change    = 30,
        random_state        = 42,
        verbose             = 1,
    )

    print("Training HistGradientBoosting (sklearn)...")
    model.fit(X_train, y_train)
    print()

    # ── Evaluation ────────────────────────────────────────────────────────────
    y_prob = model.predict_proba(X_test)[:, 1]
    y_pred = (y_prob >= args.threshold).astype(int)

    auc    = roc_auc_score(y_test, y_prob)
    cm     = confusion_matrix(y_test, y_pred)
    report = classification_report(y_test, y_pred, target_names=["Loss", "Win"])

    thresh_df = threshold_analysis(y_test.values, y_prob)

    # Feature importance via permutation (HistGBT doesn't expose split-based importance)
    print("Computing feature importance (permutation)...")
    perm = permutation_importance(model, X_test, y_test, n_repeats=5,
                                  random_state=42, scoring="roc_auc")
    fi = pd.DataFrame({
        "feature":    FEATURES,
        "importance": perm.importances_mean,
    }).sort_values("importance", ascending=False).reset_index(drop=True)

    # ── Print summary ─────────────────────────────────────────────────────────
    print("=" * 55)
    print(f"ROC-AUC: {auc:.4f}")
    print(f"\nClassification report (threshold={args.threshold}):")
    print(report)
    print("Confusion matrix (rows=actual, cols=predicted):")
    print(pd.DataFrame(cm, index=["Actual Loss","Actual Win"], columns=["Pred Loss","Pred Win"]))
    print("\nTop 10 features:")
    print(fi.head(10).to_string(index=False))
    print("\nThreshold analysis (test set):")
    print(thresh_df.to_string(index=False))
    print("=" * 55)

    # Baseline WR on test set
    baseline_wr = round(y_test.mean() * 100, 1)
    selected    = thresh_df[thresh_df["threshold"] == args.threshold]
    model_wr    = float(selected["win_rate_pct"].iloc[0]) if not selected.empty else None
    model_n     = int(selected["trades"].iloc[0]) if not selected.empty else 0
    print(f"\nBaseline WR (all test signals): {baseline_wr}%")
    if model_wr:
        print(f"Model WR  (threshold={args.threshold}): {model_wr}% on {model_n} trades")
        print(f"Improvement: +{round(model_wr - baseline_wr, 1)}pp")

    # ── Save artifacts ────────────────────────────────────────────────────────
    import pickle
    model_path = OUT_DIR / "model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(model, f)
    fi.to_csv(OUT_DIR / "feature_importance.csv", index=False)

    full_report = f"""Chanakya Sanket — XGBoost Training Report
==========================================
Dataset   : {len(df):,} rows | {df['date'].min()} → {df['date'].max()}
Train     : {len(train):,} rows → {cutoff}
Test      : {len(test):,} rows ← {cutoff}
Split     : time-based 80/20 (NO random shuffle — prevents leakage)

Model params:
  n_iter={model.n_iter_}  max_depth=4  lr=0.05
  class_weight=balanced  (corrects 31% positive class imbalance)

ROC-AUC: {auc:.4f}

Classification report (threshold={args.threshold}):
{report}

Confusion matrix:
{pd.DataFrame(cm, index=["Actual Loss","Actual Win"], columns=["Pred Loss","Pred Win"]).to_string()}

Top features:
{fi.to_string(index=False)}

Threshold analysis:
{thresh_df.to_string(index=False)}

Baseline WR (raw, no filter): {baseline_wr}%
Model WR (threshold={args.threshold}): {model_wr}% on {model_n} trades
"""
    (OUT_DIR / "training_report.txt").write_text(full_report)
    print(f"\nSaved: {model_path}")
    print(f"Saved: {OUT_DIR / 'feature_importance.csv'}")
    print(f"Saved: {OUT_DIR / 'training_report.txt'}")


if __name__ == "__main__":
    main()
