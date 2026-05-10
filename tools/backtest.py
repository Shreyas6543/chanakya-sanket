"""
Standalone backtesting script.

Usage:
    python tools/backtest.py --symbol NIFTY --start 2024-01-01 --end 2024-12-31

NOTE: OI-based strategies cannot be backtested until a proprietary historical
OI dataset has been built by recording live OI data daily.
Candle + indicator strategies can be backtested using Upstox historical API.
"""

import argparse
import asyncio
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.strategies.vwap_breakout import VWAPBreakoutStrategy
from app.strategies.rsi_momentum import RSIMomentumStrategy
from app.strategies.bullish_engulfing import BullishEngulfingStrategy
from app.strategies.opening_range import OpeningRangeBreakoutStrategy
from app.signals.confidence import calculate_confidence
from app.utils.regime import detect_regime


STRATEGIES = [
    VWAPBreakoutStrategy(),
    RSIMomentumStrategy(),
    BullishEngulfingStrategy(),
    OpeningRangeBreakoutStrategy(),
    # OIBuildupStrategy excluded — no historical OI data yet
]


def run_backtest(candles: pd.DataFrame, symbol: str, min_confidence: int = 65):
    results = []
    window = 60  # Minimum candles needed

    for i in range(window, len(candles)):
        window_candles = candles.iloc[:i]
        regime = detect_regime(window_candles)

        strategy_results = [s.evaluate(window_candles) for s in STRATEGIES]
        confidence = calculate_confidence(strategy_results)

        if confidence.score < min_confidence or confidence.direction is None:
            continue

        entry_candle = candles.iloc[i]
        entry = float(entry_candle["close"])

        # Simple 1 ATR SL, 2 ATR target
        from app.indicators.atr import current_atr
        atr = current_atr(window_candles)
        if atr == 0:
            continue

        sl = entry - atr if confidence.direction == "CALL" else entry + atr
        target = entry + (2 * atr) if confidence.direction == "CALL" else entry - (2 * atr)

        # Evaluate next 6 candles (30 minutes)
        future = candles.iloc[i + 1: i + 7]
        result = "EXPIRED"
        for _, future_candle in future.iterrows():
            if confidence.direction == "CALL":
                if float(future_candle["high"]) >= target:
                    result = "TARGET_HIT"
                    break
                if float(future_candle["low"]) <= sl:
                    result = "SL_HIT"
                    break
            else:
                if float(future_candle["low"]) <= target:
                    result = "TARGET_HIT"
                    break
                if float(future_candle["high"]) >= sl:
                    result = "SL_HIT"
                    break

        results.append({
            "timestamp": entry_candle["timestamp"],
            "direction": confidence.direction,
            "confidence": confidence.score,
            "regime": regime,
            "reasons": list(confidence.reasons.keys()),
            "entry": entry,
            "sl": sl,
            "target": target,
            "result": result,
        })

    return pd.DataFrame(results)


def print_summary(df: pd.DataFrame):
    if df.empty:
        print("No signals generated.")
        return

    total = len(df)
    wins = len(df[df["result"] == "TARGET_HIT"])
    losses = len(df[df["result"] == "SL_HIT"])
    expired = len(df[df["result"] == "EXPIRED"])

    print(f"\n{'='*40}")
    print(f"BACKTEST SUMMARY")
    print(f"{'='*40}")
    print(f"Total signals : {total}")
    print(f"Target hit    : {wins} ({wins/total*100:.1f}%)")
    print(f"SL hit        : {losses} ({losses/total*100:.1f}%)")
    print(f"Expired       : {expired} ({expired/total*100:.1f}%)")
    print(f"\nBy Regime:")
    print(df.groupby("regime")["result"].value_counts().to_string())
    print(f"\nBy Confidence bucket:")
    df["conf_bucket"] = pd.cut(df["confidence"], bins=[64, 75, 85, 100], labels=["65-75", "75-85", "85+"])
    print(df.groupby("conf_bucket")["result"].value_counts().to_string())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument("--csv", help="Path to candle CSV file (timestamp,open,high,low,close,volume)")
    args = parser.parse_args()

    if not args.csv:
        print("Provide --csv path to candle data. Upstox historical API integration coming next.")
        sys.exit(1)

    candles = pd.read_csv(args.csv, parse_dates=["timestamp"])
    results_df = run_backtest(candles, args.symbol)
    print_summary(results_df)
    output_path = f"backtest_{args.symbol}.csv"
    results_df.to_csv(output_path, index=False)
    print(f"\nDetailed results saved to {output_path}")
