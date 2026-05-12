"""
Rule-based signal filter derived from 1,409-signal backtest (May 2025–May 2026).
No external API — pure Python logic using our own statistical findings.
Returns GO / NO_GO / WATCH with reasoning.
"""
import structlog
from dataclasses import dataclass

logger = structlog.get_logger()


@dataclass
class FilterResult:
    verdict: str    # "GO", "NO_GO", "WATCH"
    score: int      # 0-100
    reason: str


# Win rates from backtest by hour (IST)
_HOUR_WR = {
    9:  46.0,
    10: 55.7,
    11: 61.2,
    12: 45.9,
    13: 37.5,
    14: 36.1,
    15:  2.4,   # already blocked upstream, but kept here as safety
}

# Win rates by strategy combo
_COMBO_WR = {
    frozenset(["opening_range_breakout", "rsi_momentum"]):              48.2,
    frozenset(["opening_range_breakout", "vwap_breakout"]):             34.6,
    frozenset(["rsi_momentum", "vwap_breakout"]):                       21.7,
    frozenset(["opening_range_breakout", "rsi_momentum", "vwap_breakout"]): 33.3,
}
_BREAKEVEN_WR = 33.3


async def evaluate_signal(
    symbol: str,
    direction: str,
    confidence: int,
    signal_context: dict,
) -> FilterResult:
    """
    Evaluate signal context against backtest-derived rules.
    Returns GO / WATCH / NO_GO with a reason string.
    """
    hour = signal_context.get("hour")
    rsi = signal_context.get("rsi") or 50.0
    vwap_dist = signal_context.get("vwap_distance_pct") or 0.0
    strategies = frozenset(signal_context.get("strategies_fired", []))
    combo_wr = _COMBO_WR.get(strategies)
    hour_wr = _HOUR_WR.get(hour, 40.0)

    reasons = []
    score = confidence  # start from engine confidence

    # --- Time of day ---
    if hour == 15:
        return FilterResult(verdict="NO_GO", score=10, reason="15:00 window — 2.4% WR, skip")
    elif hour == 11:
        score += 10
        reasons.append("11:00 window (61% WR, best of day)")
    elif hour == 10:
        score += 5
        reasons.append("10:00 window (56% WR)")
    elif hour in (13, 14):
        score -= 8
        reasons.append(f"{hour}:00 window (WR {hour_wr}%, weakening)")

    # --- Strategy combo ---
    if combo_wr is not None:
        if combo_wr >= 45:
            score += 8
            reasons.append(f"combo WR {combo_wr}%")
        elif combo_wr < _BREAKEVEN_WR:
            score -= 15
            reasons.append(f"combo WR {combo_wr}% (below break-even)")
        else:
            reasons.append(f"combo WR {combo_wr}%")
    elif "vwap_breakout" in strategies and len(strategies) == 1:
        score -= 20
        reasons.append("VWAP-only (weak, no ORB/RSI confirmation)")

    # --- RSI alignment ---
    if direction == "CALL":
        if rsi >= 60:
            score += 5
            reasons.append(f"RSI {rsi} (momentum aligned)")
        elif rsi < 50:
            score -= 10
            reasons.append(f"RSI {rsi} (not yet bullish)")
    else:  # PUT
        if rsi <= 40:
            score += 5
            reasons.append(f"RSI {rsi} (momentum aligned)")
        elif rsi > 50:
            score -= 10
            reasons.append(f"RSI {rsi} (not yet bearish)")

    # --- VWAP distance confirmation ---
    if direction == "CALL" and vwap_dist > 0.3:
        score += 5
        reasons.append(f"above VWAP +{vwap_dist}%")
    elif direction == "PUT" and vwap_dist < -0.3:
        score += 5
        reasons.append(f"below VWAP {vwap_dist}%")
    elif abs(vwap_dist) < 0.1:
        reasons.append("price hugging VWAP (choppy)")

    score = max(0, min(100, score))

    if score >= 65:
        verdict = "GO"
    elif score >= 45:
        verdict = "WATCH"
    else:
        verdict = "NO_GO"

    reason = " | ".join(reasons) if reasons else "no strong edge factors"

    logger.info(
        "Signal filter",
        symbol=symbol,
        direction=direction,
        verdict=verdict,
        score=score,
        reason=reason,
    )
    return FilterResult(verdict=verdict, score=score, reason=reason)
