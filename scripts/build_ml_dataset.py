"""
Phase 5b — ML Feature Extractor + Labeler

For each trading day in the OHLCV data:
  1. Replay candles through all indicators (RSI, VWAP, EMA, ATR)
  2. At every bar where ≥1 strategy fires (crossover detected), snapshot 20+ features
  3. Label forward-looking: did 2×ATR target hit before 1×ATR SL by end of day?

Output:
    data/ml/dataset.parquet  — labeled rows ready for XGBoost training
    data/ml/dataset_stats.txt — summary of class balance and coverage

Usage:
    python scripts/build_ml_dataset.py
    python scripts/build_ml_dataset.py --symbols NIFTY
    python scripts/build_ml_dataset.py --min-strategies 2   # default: 1
"""

import argparse
import sys
from pathlib import Path
from datetime import date, timedelta

import numpy as np
import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT      = Path(__file__).resolve().parent.parent
OHLCV_DIR = ROOT / "data" / "ohlcv"
OI_DIR    = ROOT / "data" / "nse_oi"
OUT_DIR   = ROOT / "data" / "ml"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Market hours (UTC) ────────────────────────────────────────────────────────
# IST = UTC + 5:30
# 9:15 IST  = 03:45 UTC  (first signal candle)
# 15:15 IST = 09:45 UTC  (last signal candle — allow signals up to 15:15)
# 15:30 IST = 10:00 UTC  (hard close — all positions expire)
MARKET_OPEN_UTC  = "03:45"
SIGNAL_CLOSE_UTC = "09:45"
MARKET_CLOSE_UTC = "10:00"

SYMBOLS = ["NIFTY", "BANKNIFTY"]

# ── Indicators (inline — avoid importing app which needs DB/config) ───────────

def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta    = close.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs       = avg_gain / avg_loss.replace(0, float("inf"))
    return 100 - (100 / (1 + rs))


def _vwap(df: pd.DataFrame) -> pd.Series:
    tp  = (df["high"] + df["low"] + df["close"]) / 3
    vol = df["volume"].cumsum()
    if float(vol.iloc[-1]) == 0:
        return tp.expanding().mean()
    return (tp * df["volume"]).cumsum() / vol


def _ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift(1)).abs(),
        (df["low"]  - df["close"].shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


# ── OI loader ─────────────────────────────────────────────────────────────────

def _load_oi_index(symbols: list[str]) -> dict[str, dict[date, dict]]:
    """
    Returns {symbol: {date: {call_oi, put_oi, pcr, oi_change_pct}}}
    Uses the previous day's EOD OI — consistent with signal_context.pcr in live mode.
    """
    index: dict[str, dict[date, dict]] = {s: {} for s in symbols}

    files = sorted(OI_DIR.glob("*.csv"))
    prev: dict[str, dict] = {}

    for f in files:
        try:
            d   = date.fromisoformat(f.stem)
            df  = pd.read_csv(f)
            df["oi"] = pd.to_numeric(df["oi"], errors="coerce").fillna(0)

            for sym in symbols:
                sdf      = df[df["symbol"] == sym]
                call_oi  = int(sdf[sdf["option_type"] == "CE"]["oi"].sum())
                put_oi   = int(sdf[sdf["option_type"] == "PE"]["oi"].sum())
                pcr      = round(put_oi / call_oi, 3) if call_oi > 0 else None

                prev_call = prev.get(sym, {}).get("call_oi", 0)
                oi_chg    = round((call_oi - prev_call) / prev_call * 100, 2) if prev_call > 0 else None

                index[sym][d] = {
                    "call_oi":       call_oi,
                    "put_oi":        put_oi,
                    "pcr":           pcr,
                    "oi_change_pct": oi_chg,
                }
                prev[sym] = {"call_oi": call_oi, "put_oi": put_oi}
        except Exception:
            continue

    return index


# ── Strategy fire detection ────────────────────────────────────────────────────

def _rsi_crossed_above(rsi: pd.Series, level: float = 55, lookback: int = 5) -> bool:
    if len(rsi) < 2:
        return False
    window = rsi.iloc[-(lookback + 1):]
    for i in range(len(window) - 1):
        if float(window.iloc[i]) < level <= float(window.iloc[i + 1]):
            return True
    return False


def _rsi_crossed_below(rsi: pd.Series, level: float = 45, lookback: int = 5) -> bool:
    if len(rsi) < 2:
        return False
    window = rsi.iloc[-(lookback + 1):]
    for i in range(len(window) - 1):
        if float(window.iloc[i]) > level >= float(window.iloc[i + 1]):
            return True
    return False


def _detect_strategies(day_df: pd.DataFrame, idx: int, rsi: pd.Series, vwap: pd.Series,
                        ema9: pd.Series, ema21: pd.Series, ema50: pd.Series,
                        or_high: float, or_low: float) -> tuple[list[str], list[str]]:
    """
    Returns (call_strategies_fired, put_strategies_fired) at candle index `idx`.
    """
    sub_rsi  = rsi.iloc[:idx + 1]
    close    = float(day_df["close"].iloc[idx])
    prev_close = float(day_df["close"].iloc[idx - 1]) if idx > 0 else close
    curr_vwap  = float(vwap.iloc[idx])
    prev_vwap  = float(vwap.iloc[idx - 1]) if idx > 0 else curr_vwap

    calls, puts = [], []

    # RSI momentum
    if _rsi_crossed_above(sub_rsi):
        if float(ema9.iloc[idx]) > float(ema21.iloc[idx]) > float(ema50.iloc[idx]):
            calls.append("rsi_momentum")
    if _rsi_crossed_below(sub_rsi):
        if float(ema9.iloc[idx]) < float(ema21.iloc[idx]) < float(ema50.iloc[idx]):
            puts.append("rsi_momentum")

    # VWAP breakout/breakdown
    if prev_close <= prev_vwap and close > curr_vwap:
        calls.append("vwap_breakout")
    if prev_close >= prev_vwap and close < curr_vwap:
        puts.append("vwap_breakout")

    # Opening range breakout (only after OR is established — candle index >= 3)
    if idx >= 3 and or_high > 0:
        if prev_close <= or_high and close > or_high:
            calls.append("opening_range_breakout")
        if prev_close >= or_low and close < or_low:
            puts.append("opening_range_breakout")

    return calls, puts


# ── Forward labeler ────────────────────────────────────────────────────────────

def _label(day_df: pd.DataFrame, signal_idx: int, direction: str, atr_val: float,
           target_mult: float = 2.0, sl_mult: float = 1.0) -> int:
    """
    Label = 1 if target hit before SL within the remaining day candles.
    Label = 0 if SL hit or expired (EXPIRED counts as loss — consistent with WR formula).
    No lookahead: only uses candles AFTER signal_idx.
    """
    entry  = float(day_df["close"].iloc[signal_idx])
    target = entry + atr_val * target_mult if direction == "CALL" else entry - atr_val * target_mult
    sl     = entry - atr_val * sl_mult     if direction == "CALL" else entry + atr_val * sl_mult

    future = day_df.iloc[signal_idx + 1:]
    for _, row in future.iterrows():
        h, l = float(row["high"]), float(row["low"])
        if direction == "CALL":
            if h >= target: return 1   # target hit first
            if l <= sl:     return 0   # sl hit
        else:
            if l <= target: return 1
            if h >= sl:     return 0

    return 0  # expired = loss


# ── Per-day feature extraction ────────────────────────────────────────────────

def _process_day(symbol: str, day_str: str, day_df: pd.DataFrame,
                 oi_row: dict | None, min_strategies: int) -> list[dict]:
    """
    Replay one trading day's candles and extract labeled feature rows.
    """
    rows = []
    n    = len(day_df)

    if n < 20:   # need enough candles for indicators
        return rows

    # Compute indicators on full day (no leakage — we use iloc[:i+1] slices for crossovers)
    close  = day_df["close"]
    rsi    = _rsi(close)
    vwap   = _vwap(day_df)
    ema9   = _ema(close, 9)
    ema21  = _ema(close, 21)
    ema50  = _ema(close, 50)
    atr_s  = _atr(day_df)
    atr20  = atr_s.rolling(20).mean()   # for regime detection

    # Opening range: first 3 candles (9:15, 9:20, 9:25 IST)
    or_df   = day_df[day_df["time_ist"] < "09:30"]
    or_high = float(or_df["high"].max()) if not or_df.empty else 0.0
    or_low  = float(or_df["low"].min())  if not or_df.empty else 0.0

    # Track last-fired bar per direction+strategy to avoid duplicate crossover rows.
    # RSI lookback=5 means ONE crossover can appear in 5 consecutive bars — we only
    # want the FIRST bar (the actual crossover), not the 4 downstream duplicates.
    last_fired: dict[str, dict[str, int]] = {"CALL": {}, "PUT": {}}

    for i in range(3, n):   # skip first 3 candles — OR not established yet
        row_time = day_df["time_ist"].iloc[i]

        # Only generate signals during 9:15–15:15 IST
        if row_time < "09:15" or row_time > "15:15":
            continue

        atr_val  = float(atr_s.iloc[i])
        if pd.isna(atr_val) or atr_val == 0:
            continue

        calls, puts = _detect_strategies(
            day_df, i, rsi, vwap, ema9, ema21, ema50, or_high, or_low
        )

        for direction, all_strategies in [("CALL", calls), ("PUT", puts)]:
            # Deduplicate: only keep strategies that weren't fired in the last 5 bars
            strategies = [
                s for s in all_strategies
                if i - last_fired[direction].get(s, -99) > 5
            ]
            # Update fired tracking for ALL strategies (even duplicates)
            for s in all_strategies:
                last_fired[direction][s] = i

            if len(strategies) < min_strategies:
                continue

            curr_rsi   = float(rsi.iloc[i])
            curr_vwap  = float(vwap.iloc[i])
            curr_close = float(close.iloc[i])
            atr20_val  = float(atr20.iloc[i]) if not pd.isna(atr20.iloc[i]) else atr_val

            label = _label(day_df, i, direction, atr_val)

            # Momentum / candle quality features
            prev_close_1 = float(close.iloc[i - 1]) if i >= 1 else curr_close
            prev_close_5 = float(close.iloc[i - 5]) if i >= 5 else curr_close
            open_0       = float(close.iloc[0])  # first candle close as day anchor
            ret_1bar     = (curr_close - prev_close_1) / prev_close_1 * 100
            ret_5bar     = (curr_close - prev_close_5) / prev_close_5 * 100
            intraday_ret = (curr_close - open_0) / open_0 * 100
            rsi_slope    = float(rsi.iloc[i]) - float(rsi.iloc[i - 3]) if i >= 3 else 0.0
            candle_range = float(day_df["high"].iloc[i]) - float(day_df["low"].iloc[i])
            candle_body  = abs(curr_close - float(day_df["open"].iloc[i]))
            body_ratio   = candle_body / candle_range if candle_range > 0 else 0.5

            rows.append({
                # Identity
                "symbol":      symbol,
                "date":        day_str,
                "time_ist":    row_time,
                "direction":   direction,
                # Label
                "label":       label,
                # Price features
                "close":           curr_close,
                "atr":             round(atr_val, 2),
                "atr_pct":         round(atr_val / curr_close * 100, 3),
                "vwap_dist_pct":   round((curr_close - curr_vwap) / curr_vwap * 100, 3),
                # RSI features
                "rsi":             round(curr_rsi, 2),
                "rsi_above_55":    int(curr_rsi > 55),
                "rsi_below_45":    int(curr_rsi < 45),
                "rsi_slope":       round(rsi_slope, 2),
                # EMA features
                "ema_bull_align":  int(float(ema9.iloc[i]) > float(ema21.iloc[i]) > float(ema50.iloc[i])),
                "ema_bear_align":  int(float(ema9.iloc[i]) < float(ema21.iloc[i]) < float(ema50.iloc[i])),
                # Strategy flags
                "strat_rsi":       int("rsi_momentum"           in strategies),
                "strat_vwap":      int("vwap_breakout"          in strategies),
                "strat_orb":       int("opening_range_breakout" in strategies),
                "n_strategies":    len(strategies),
                # Regime
                "regime_trending": int(atr_val >= 0.7 * atr20_val),
                # Momentum features
                "ret_1bar":        round(ret_1bar, 3),
                "ret_5bar":        round(ret_5bar, 3),
                "intraday_ret":    round(intraday_ret, 3),
                "body_ratio":      round(body_ratio, 3),
                # Time features
                "hour":            int(row_time[:2]),
                "minute":          int(row_time[3:5]),
                "day_of_week":     pd.Timestamp(day_str).dayofweek,
                "month":           pd.Timestamp(day_str).month,
                # Symbol
                "is_banknifty":    int(symbol == "BANKNIFTY"),
                # OI features (None → NaN — XGBoost handles missing values natively)
                "pcr":             oi_row.get("pcr")           if oi_row else None,
                "oi_change_pct":   oi_row.get("oi_change_pct") if oi_row else None,
                "has_oi":          int(oi_row is not None),
            })

    return rows


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Build ML training dataset")
    parser.add_argument("--symbols",       default="NIFTY,BANKNIFTY")
    parser.add_argument("--min-strategies", type=int, default=1,
                        help="Min strategies that must fire to create a row (default 1)")
    args = parser.parse_args()

    symbols      = [s.strip() for s in args.symbols.split(",")]
    min_strats   = args.min_strategies

    print(f"Building ML dataset | symbols={symbols} | min_strategies={min_strats}")
    print(f"OHLCV: {OHLCV_DIR} | OI: {OI_DIR} | Output: {OUT_DIR}\n")

    # Load OI index once
    print("Loading OI data...", end=" ", flush=True)
    oi_index = _load_oi_index(symbols)
    total_oi_days = sum(len(v) for v in oi_index.values())
    print(f"{total_oi_days} symbol-days loaded\n")

    all_rows = []

    for symbol in symbols:
        parquet = OHLCV_DIR / f"{symbol}_5min.parquet"
        if not parquet.exists():
            print(f"[{symbol}] No OHLCV parquet found at {parquet} — skipping")
            continue

        df = pd.read_parquet(parquet)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

        # Convert to IST for easier time filtering
        df["timestamp_ist"] = df["timestamp"].dt.tz_convert("Asia/Kolkata")
        df["date_ist"]      = df["timestamp_ist"].dt.date.astype(str)
        df["time_ist"]      = df["timestamp_ist"].dt.strftime("%H:%M")

        trading_days = sorted(df["date_ist"].unique())
        print(f"[{symbol}] {len(df):,} bars | {len(trading_days)} trading days")

        sym_rows = 0
        for day_str in trading_days:
            day_df = df[df["date_ist"] == day_str].copy().reset_index(drop=True)

            # Get previous day's OI (consistent with live signal_context.pcr)
            day_date = date.fromisoformat(day_str)
            prev_date = day_date - timedelta(days=1)
            # Look back up to 5 days for OI (handles weekends/holidays)
            oi_row = None
            for delta in range(1, 6):
                candidate = day_date - timedelta(days=delta)
                oi_row = oi_index.get(symbol, {}).get(candidate)
                if oi_row:
                    break

            rows = _process_day(symbol, day_str, day_df, oi_row, min_strats)
            all_rows.extend(rows)
            sym_rows += len(rows)

        print(f"  → {sym_rows} labeled rows generated\n")

    if not all_rows:
        print("No rows generated. Check OHLCV data and strategy thresholds.")
        sys.exit(1)

    dataset = pd.DataFrame(all_rows)
    out_path = OUT_DIR / "dataset.parquet"
    dataset.to_parquet(out_path, index=False)

    # Summary stats
    total     = len(dataset)
    wins      = int(dataset["label"].sum())
    losses    = total - wins
    win_rate  = round(wins / total * 100, 1)

    summary = f"""ML Dataset Summary
==================
Total rows     : {total:,}
Wins (label=1) : {wins:,}  ({win_rate}%)
Losses (label=0): {losses:,}  ({100-win_rate}%)

By symbol:
{dataset.groupby('symbol')['label'].agg(['count','sum','mean']).rename(columns={'count':'total','sum':'wins','mean':'wr'}).to_string()}

By direction:
{dataset.groupby('direction')['label'].agg(['count','sum','mean']).rename(columns={'count':'total','sum':'wins','mean':'wr'}).to_string()}

By month:
{dataset.groupby('month')['label'].agg(['count','sum','mean']).rename(columns={'count':'total','sum':'wins','mean':'wr'}).to_string()}

Date range: {dataset['date'].min()} → {dataset['date'].max()}
Output: {out_path}
"""
    print(summary)
    (OUT_DIR / "dataset_stats.txt").write_text(summary)
    print(f"Saved {total:,} rows → {out_path}")


if __name__ == "__main__":
    main()
