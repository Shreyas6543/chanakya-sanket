"""
AI signal filter using Claude Code CLI via claude-agent-sdk.
No API billing — uses your existing Claude subscription (logged-in session).
Falls back to rule-based filter if Claude CLI is unavailable.
"""
import json
import structlog
from dataclasses import dataclass

logger = structlog.get_logger()


@dataclass
class FilterResult:
    verdict: str    # "GO", "NO_GO", "WATCH"
    score: int      # 0-100
    reason: str


# Statistical patterns from 1,409-signal backtest (May 2025–May 2026)
_HOUR_WR = {9: 46.0, 10: 55.7, 11: 61.2, 12: 45.9, 13: 37.5, 14: 36.1, 15: 2.4}
_COMBO_WR = {
    frozenset(["opening_range_breakout", "rsi_momentum"]):                  48.2,
    frozenset(["opening_range_breakout", "vwap_breakout"]):                 34.6,
    frozenset(["rsi_momentum", "vwap_breakout"]):                           21.7,
    frozenset(["opening_range_breakout", "rsi_momentum", "vwap_breakout"]): 33.3,
}
_BREAKEVEN = 33.3

_PROMPT_TEMPLATE = """You are an intraday options signal evaluator for Indian markets.

Statistical patterns from our 1,409-signal backtest (May 2025–May 2026, 5-min candles):

HOURLY WIN RATES (IST):
- 09:xx → 46% WR | 10:xx → 56% WR | 11:xx → 61% WR (BEST)
- 12:xx → 46% WR | 13:xx → 38% WR | 14:xx → 36% WR | 15:xx → 2% WR (AVOID)

STRATEGY COMBO WIN RATES:
- ORB + RSI → 48% WR (primary, most reliable)
- ORB + VWAP → 35% WR (weaker)
- RSI + VWAP → 22% WR (poor)
- All 3 → 33% WR (adds noise)

CONTEXT CLUES:
- RSI > 60 for CALL or < 40 for PUT = momentum aligned (good)
- VWAP distance > 0.3% in signal direction = confirms breakout (good)
- Price hugging VWAP (dist < 0.1%) = choppy, avoid
- Break-even WR for our 2:1 R:R = 33.3%

SIGNAL TO EVALUATE:
Symbol: {symbol} | Direction: {direction} | Engine confidence: {confidence}/100
Time: {hour}:{minute:02d} IST
Strategies fired: {combo}
RSI: {rsi} | VWAP distance: {vwap_dist}% | ATR: {atr} | PCR: {pcr}

Respond with ONLY a JSON object, nothing else:
{{"verdict": "GO" or "NO_GO" or "WATCH", "score": <0-100>, "reason": "<one sentence>"}}"""


async def _claude_filter(symbol, direction, confidence, signal_context) -> FilterResult | None:
    """Call Claude Code CLI via agent SDK. Returns None if CLI unavailable."""
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage
        import anyio

        hour = signal_context.get("hour", 0)
        minute = signal_context.get("minute", 0)
        strategies = signal_context.get("strategies_fired", [])
        combo = " + ".join(sorted(strategies)) if strategies else "none"

        prompt = _PROMPT_TEMPLATE.format(
            symbol=symbol,
            direction=direction,
            confidence=confidence,
            hour=hour,
            minute=minute or 0,
            combo=combo,
            rsi=signal_context.get("rsi", "N/A"),
            vwap_dist=signal_context.get("vwap_distance_pct", 0),
            atr=signal_context.get("atr", "N/A"),
            pcr=signal_context.get("pcr", "N/A"),
        )

        result_text = None

        async def _run():
            nonlocal result_text
            async for msg in query(
                prompt=prompt,
                options=ClaudeAgentOptions(
                    max_turns=1,
                    allowed_tools=[],   # no tools needed, pure reasoning
                ),
            ):
                if isinstance(msg, ResultMessage):
                    result_text = msg.result

        await anyio.from_thread.run_sync(lambda: anyio.run(_run)) if False else await _run()

        if not result_text:
            return None

        # Parse JSON
        clean = result_text.strip()
        if "```" in clean:
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        # Extract first JSON object
        start = clean.find("{")
        end = clean.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        parsed = json.loads(clean[start:end])

        verdict = parsed.get("verdict", "GO").upper()
        if verdict not in ("GO", "NO_GO", "WATCH"):
            verdict = "GO"

        return FilterResult(
            verdict=verdict,
            score=int(parsed.get("score", confidence)),
            reason=parsed.get("reason", ""),
        )

    except Exception as e:
        logger.warning("Claude CLI filter failed, falling back to rules", error=str(e))
        return None


def _rule_filter(symbol, direction, confidence, signal_context) -> FilterResult:
    """
    Pure rule-based fallback using backtest-derived patterns.
    Used when Claude CLI is unavailable.
    """
    hour = signal_context.get("hour")
    rsi = signal_context.get("rsi") or 50.0
    vwap_dist = signal_context.get("vwap_distance_pct") or 0.0
    strategies = frozenset(signal_context.get("strategies_fired", []))
    combo_wr = _COMBO_WR.get(strategies)
    hour_wr = _HOUR_WR.get(hour, 40.0)

    reasons = []
    score = confidence

    if hour == 15:
        return FilterResult(verdict="NO_GO", score=10, reason="15:00 window — 2.4% WR")
    elif hour == 11:
        score += 10; reasons.append("11:00 (61% WR)")
    elif hour == 10:
        score += 5; reasons.append("10:00 (56% WR)")
    elif hour in (13, 14):
        score -= 8; reasons.append(f"{hour}:00 ({hour_wr}% WR, weak)")

    if combo_wr is not None:
        if combo_wr >= 45:
            score += 8; reasons.append(f"combo {combo_wr}% WR")
        elif combo_wr < _BREAKEVEN:
            score -= 15; reasons.append(f"combo {combo_wr}% WR (below break-even)")
        else:
            reasons.append(f"combo {combo_wr}% WR")
    elif "vwap_breakout" in strategies and len(strategies) == 1:
        score -= 20; reasons.append("VWAP-only (weak)")

    if direction == "CALL":
        if rsi >= 60:   score += 5;  reasons.append(f"RSI {rsi} aligned")
        elif rsi < 50:  score -= 10; reasons.append(f"RSI {rsi} not bullish")
    else:
        if rsi <= 40:   score += 5;  reasons.append(f"RSI {rsi} aligned")
        elif rsi > 50:  score -= 10; reasons.append(f"RSI {rsi} not bearish")

    if direction == "CALL" and vwap_dist > 0.3:
        score += 5; reasons.append(f"above VWAP +{vwap_dist}%")
    elif direction == "PUT" and vwap_dist < -0.3:
        score += 5; reasons.append(f"below VWAP {vwap_dist}%")

    score = max(0, min(100, score))
    verdict = "GO" if score >= 65 else "WATCH" if score >= 45 else "NO_GO"
    return FilterResult(verdict=verdict, score=score, reason=" | ".join(reasons) or "rule-based")


async def evaluate_signal(
    symbol: str,
    direction: str,
    confidence: int,
    signal_context: dict,
) -> FilterResult:
    """
    Evaluate a signal. Tries Claude CLI first, falls back to rule-based filter.
    Always returns a result — never blocks due to filter failure.
    """
    # Try Claude CLI (requires `claude` logged in on this machine)
    result = await _claude_filter(symbol, direction, confidence, signal_context)
    if result is not None:
        source = "claude-cli"
    else:
        result = _rule_filter(symbol, direction, confidence, signal_context)
        source = "rules"

    logger.info(
        "Signal filter",
        symbol=symbol,
        direction=direction,
        verdict=result.verdict,
        score=result.score,
        reason=result.reason,
        source=source,
    )
    return result
