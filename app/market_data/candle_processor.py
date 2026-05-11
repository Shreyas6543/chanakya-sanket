from collections import defaultdict
from datetime import datetime
import pandas as pd
import structlog

logger = structlog.get_logger()

# In-memory candle buffer: {symbol: [candle_dict, ...]}
_candle_buffer: dict[str, list[dict]] = defaultdict(list)
_current_candle: dict[str, dict] = {}


def process_tick(symbol: str, price: float, volume: float, timestamp: datetime):
    """
    Aggregate ticks into 5-minute candles.
    Completes a candle when the 5-minute window rolls over.
    """
    candle_minute = timestamp.replace(second=0, microsecond=0)
    # Round down to 5-minute boundary
    minute_floor = candle_minute.minute - (candle_minute.minute % 5)
    candle_start = candle_minute.replace(minute=minute_floor)

    if symbol not in _current_candle:
        _current_candle[symbol] = _new_candle(candle_start, price, volume)
        return

    curr = _current_candle[symbol]

    if candle_start > curr["timestamp"]:
        # New candle window — finalize the old one
        _candle_buffer[symbol].append(curr)
        logger.debug("Candle closed", symbol=symbol, candle=curr)
        _current_candle[symbol] = _new_candle(candle_start, price, volume)
    else:
        # Update current candle
        curr["high"] = max(curr["high"], price)
        curr["low"] = min(curr["low"], price)
        curr["close"] = price
        curr["volume"] += volume


def _new_candle(timestamp: datetime, price: float, volume: float) -> dict:
    return {
        "timestamp": timestamp,
        "open": price,
        "high": price,
        "low": price,
        "close": price,
        "volume": volume,
    }


def get_candles(symbol: str, limit: int = 100) -> pd.DataFrame:
    """Return last `limit` completed candles as a DataFrame."""
    candles = _candle_buffer[symbol][-limit:]
    if not candles:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    return pd.DataFrame(candles)


def clear_candles(symbol: str):
    """Clear candle buffer — called at EOD."""
    _candle_buffer[symbol].clear()
    _current_candle.pop(symbol, None)


def seed_candles(symbol: str, df: pd.DataFrame):
    """
    Pre-load historical 5m candles into the buffer on startup.
    Called in live mode so strategies have 50+ candles immediately at 9:15 AM
    instead of waiting ~4 hours for the buffer to fill from live ticks.
    """
    if df.empty:
        return
    _candle_buffer[symbol].clear()
    for row in df.itertuples(index=False):
        ts = row.timestamp
        if hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()
        _candle_buffer[symbol].append({
            "timestamp": ts,
            "open":      float(row.open),
            "high":      float(row.high),
            "low":       float(row.low),
            "close":     float(row.close),
            "volume":    float(row.volume),
        })
    logger.info("Candle buffer seeded", symbol=symbol, candles=len(_candle_buffer[symbol]))
