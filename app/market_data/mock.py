"""
Mock market data generator for testing without live Upstox connection.
Generates realistic NIFTY/BANKNIFTY candle data and simulates ticks.
"""
import random
import pandas as pd
from datetime import datetime, timedelta
from app.market_data.candle_processor import _candle_buffer

MOCK_PRICES = {
    "NIFTY": 24500.0,
    "BANKNIFTY": 52000.0,
}

MOCK_VOLATILITY = {
    "NIFTY": 0.003,
    "BANKNIFTY": 0.005,
}


def generate_mock_candles(symbol: str, n: int = 80, trending: bool = False) -> pd.DataFrame:
    """
    Generate n 5-minute candles.
    trending=True produces a bullish trending scenario that reliably triggers strategies.
    trending=False produces neutral random walk (default, realistic).
    """
    price = MOCK_PRICES.get(symbol, 24500.0)
    vol = MOCK_VOLATILITY.get(symbol, 0.003)

    now = datetime.now().replace(second=0, microsecond=0)
    now = now - timedelta(minutes=now.minute % 5)

    candles = []
    avg_volume = 150_000
    anchor_price = price  # used for mean reversion in trending mode

    for i in range(n, 0, -1):
        ts = now - timedelta(minutes=i * 5)

        open_ = price

        if trending:
            if i == 2:
                # Setup candle: clearly bearish — drops below VWAP, RSI dips under 55.
                # Sets up the bullish engulfing on the final candle.
                close = round(open_ * 0.997, 2)
                vol_mult = random.uniform(0.8, 1.1)
            elif i == 1:
                # Trigger candle: big +2.5% bullish move.
                # - Mean reversion kept VWAP ≈ anchor_price; prev close is below it → breakout
                # - RSI from ~45 (flat) + bearish dip → jumps to ~70+ on this candle
                # - Engulfs candle n-1 (open == prev close, close >> prev open)
                # - EMA9 responds fastest → EMA9 > EMA21 > EMA50
                # - Volume 4-5x average → volume_spike fires
                close = round(open_ * 1.025, 2)
                vol_mult = random.uniform(4.0, 5.0)
            else:
                # Mean-reverting flat phase: pull 30% toward anchor each step with half-vol noise.
                # Keeps VWAP anchored near starting price so the trigger candle truly crosses it.
                mean_rev_drift = (anchor_price - price) / price * 0.3
                ret = random.gauss(mean_rev_drift, vol * 0.5)
                close = round(open_ * (1 + ret), 2)
                vol_mult = random.uniform(0.7, 1.3)
        else:
            drift = random.gauss(0.0001, 0.0002)
            ret = random.gauss(drift, vol)
            close = round(open_ * (1 + ret), 2)
            vol_mult = random.uniform(0.7, 1.3)

        high = round(max(open_, close) * (1 + abs(random.gauss(0, vol / 3))), 2)
        low = round(min(open_, close) * (1 - abs(random.gauss(0, vol / 3))), 2)
        volume = round(avg_volume * vol_mult, 0)

        candles.append({
            "timestamp": ts,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        })
        price = close

    df = pd.DataFrame(candles)
    _candle_buffer[symbol].clear()
    _candle_buffer[symbol].extend(candles)
    MOCK_PRICES[symbol] = price

    return df


def get_mock_spot_price(symbol: str, bullish_bias: bool = True) -> float:
    """
    Simulate a single 1-minute price tick.
    bullish_bias=True gives a slight upward drift so CALL signals resolve
    toward target within a reasonable number of ticks during testing.
    """
    price = MOCK_PRICES.get(symbol, 24500.0)
    vol = MOCK_VOLATILITY.get(symbol, 0.003)
    # Drift: ~0.05% upward per tick ≈ realistic 1-min move on a trending day
    drift = 0.0005 if bullish_bias else 0.0
    new_price = round(price * (1 + random.gauss(drift, vol / 3)), 2)
    MOCK_PRICES[symbol] = new_price
    return new_price


def get_mock_oi_data(symbol: str, bullish: bool = False, bearish: bool = False) -> dict:
    """
    Generate OI data aligned with market direction.
    bullish=True: call buildup + put unwind → CALL signal
    bearish=True: put buildup + call unwind → PUT signal
    Neither: neutral random OI (no clear signal)
    """
    base_call_oi = 5_000_000 if symbol == "NIFTY" else 3_000_000
    base_put_oi = 4_500_000 if symbol == "NIFTY" else 2_800_000

    if bullish:
        return {
            "call_oi": base_call_oi * random.uniform(1.07, 1.15),  # 7-15% buildup
            "put_oi": base_put_oi * random.uniform(0.83, 0.93),    # 7-17% unwind
            "prev_call_oi": base_call_oi,
            "prev_put_oi": base_put_oi,
        }

    if bearish:
        return {
            "call_oi": base_call_oi * random.uniform(0.83, 0.93),  # 7-17% unwind
            "put_oi": base_put_oi * random.uniform(1.07, 1.15),    # 7-15% buildup
            "prev_call_oi": base_call_oi,
            "prev_put_oi": base_put_oi,
        }

    return {
        "call_oi": base_call_oi * random.uniform(0.95, 1.10),
        "put_oi": base_put_oi * random.uniform(0.90, 1.05),
        "prev_call_oi": base_call_oi,
        "prev_put_oi": base_put_oi,
    }
