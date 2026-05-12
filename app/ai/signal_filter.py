"""
Claude AI signal filter.
Evaluates each live signal's context before Telegram alert fires.
Returns GO / NO_GO / WATCH with reasoning.

Skip for backfill/historical signals — only for live source.
"""
import json
import structlog
from dataclasses import dataclass

import anthropic

logger = structlog.get_logger()

# Statistical patterns from 1,409-signal backtest (May 2025–May 2026)
# Embedded as system prompt context — cached on first call.
_SYSTEM_PROMPT = """You are an intraday options trading signal evaluator for Indian markets (NIFTY and BANKNIFTY).

You will receive signal context from a rule-based engine and must decide whether to trade it.

## Statistical patterns from 1,409 historical signals (May 2025–May 2026, 5-min candles):

### Win rate by time of day (IST):
- 09:00–09:59: 46% WR (606 signals)
- 10:00–10:59: 56% WR (212 signals) ← good window
- 11:00–11:59: 61% WR (152 signals) ← BEST window
- 12:00–12:59: 46% WR (157 signals)
- 13:00–13:59: 38% WR (144 signals) ← weakening
- 14:00–14:59: 36% WR (97 signals)  ← weak
- 15:00–15:30: 2%  WR (41 signals)  ← AVOID — near EOD, liquidity dries up

### Win rate by strategy combination:
- opening_range_breakout + rsi_momentum: 48% WR (1,222 signals) ← primary combo
- opening_range_breakout + vwap_breakout: 35% WR (153 signals) ← weaker
- All three strategies: 33% WR (27 signals) ← adds noise

### Key observations:
- VWAP breakout as the sole or primary reason correlates with lower WR
- RSI momentum + ORB together is the most reliable combo
- 15:00+ signals are almost worthless (EOD chop, wide spreads)
- 10:00–11:00 window has best edge — fresh trend established, full liquidity
- High ATR (trending day) improves outcomes vs low ATR (choppy)
- RSI above 60 for CALL or below 40 for PUT suggests momentum alignment
- VWAP distance > 0.5% in signal direction = confirms breakout
- Break-even WR for this R:R ratio (2×ATR target / 1×ATR SL) = 33.3%

## Your task:
Evaluate the signal and return a JSON object with exactly these fields:
{
  "verdict": "GO" | "NO_GO" | "WATCH",
  "score": <integer 0-100, your confidence in the trade>,
  "reason": "<one concise sentence explaining the decision>"
}

GO = trade it (high confidence, good context)
WATCH = marginal, worth monitoring but not ideal
NO_GO = skip this signal (bad time, weak combo, unfavourable context)

Be concise. Think step by step about: time of day, strategy combo, RSI level, VWAP distance, ATR context."""


@dataclass
class FilterResult:
    verdict: str        # "GO", "NO_GO", "WATCH"
    score: int          # 0-100
    reason: str
    raw_response: str   # full Claude response for logging


_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic | None:
    global _client
    if _client is not None:
        return _client
    from app.config import get_settings
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None
    _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


async def evaluate_signal(
    symbol: str,
    direction: str,
    confidence: int,
    signal_context: dict,
) -> FilterResult:
    """
    Ask Claude to evaluate a signal before it fires.
    Falls back to GO if API key not set or call fails — never blocks a signal due to API issues.
    """
    client = _get_client()
    if client is None:
        return FilterResult(verdict="GO", score=confidence, reason="AI filter disabled (no API key)", raw_response="")

    # Build the user message
    hour = signal_context.get("hour")
    strategies = signal_context.get("strategies_fired", [])
    combo = "+".join(sorted(strategies))

    user_msg = f"""Signal to evaluate:
- Symbol: {symbol}
- Direction: {direction}
- Engine confidence: {confidence}/100
- Time (IST hour): {hour}:{"0" + str(signal_context.get("minute", 0)) if signal_context.get("minute", 0) < 10 else signal_context.get("minute", 0)}
- Strategies fired: {combo}
- RSI: {signal_context.get("rsi")}
- VWAP distance: {signal_context.get("vwap_distance_pct")}%
- ATR: {signal_context.get("atr")}
- PCR (EOD): {signal_context.get("pcr")}

Evaluate this signal. Return only the JSON object."""

    try:
        response = await client.messages.create(
            model="claude-opus-4-6",
            max_tokens=256,
            thinking={"type": "adaptive"},
            system=[{
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},  # cache system prompt across calls
            }],
            messages=[{"role": "user", "content": user_msg}],
        )

        raw = next((b.text for b in response.content if b.type == "text"), "")

        # Parse JSON from response
        # Strip markdown code fences if present
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        parsed = json.loads(clean.strip())

        verdict = parsed.get("verdict", "GO").upper()
        if verdict not in ("GO", "NO_GO", "WATCH"):
            verdict = "GO"

        result = FilterResult(
            verdict=verdict,
            score=int(parsed.get("score", confidence)),
            reason=parsed.get("reason", ""),
            raw_response=raw,
        )

        logger.info(
            "AI signal filter",
            symbol=symbol,
            direction=direction,
            verdict=result.verdict,
            score=result.score,
            reason=result.reason,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        return result

    except Exception as e:
        logger.warning("AI signal filter failed — defaulting to GO", error=str(e))
        return FilterResult(verdict="GO", score=confidence, reason=f"Filter error: {e}", raw_response="")
