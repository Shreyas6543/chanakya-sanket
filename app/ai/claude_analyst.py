"""
Chanakya Sanket — Claude AI Analyst
Streams signal analysis responses using claude-opus-4-6 with adaptive thinking.
"""
import anthropic
from typing import AsyncIterator
from app.config import get_settings

SYSTEM_PROMPT = """You are Chanakya — an expert intraday options trading analyst embedded in the Chanakya Sanket signal intelligence engine.

You have real access to the user's signal history, win rates, P&L data, and strategy performance. You speak like a sharp, concise trading mentor — direct, honest, and specific. You do not give generic advice.

Rules:
- Always reference the actual numbers from the data provided. Do not make up figures.
- Be honest. If the data shows a weakness, say so directly.
- Keep responses concise — 3 to 6 sentences unless a detailed breakdown is genuinely needed.
- Never recommend specific trades or tell the user to buy or sell anything.
- This is paper trading data for research and learning purposes.
- Break-even win rate for this system is 33.3% (2× ATR target, 1× ATR stop-loss).
- Win rate calculation: wins / (wins + losses + expired). Expired signals count as losses due to theta decay.
- The system trades NIFTY and BANKNIFTY weekly options, 5-minute candles, intraday only.
"""


async def stream_analysis(question: str, context: dict) -> AsyncIterator[str]:
    settings = get_settings()
    if not settings.anthropic_api_key:
        yield "ANTHROPIC_API_KEY is not set in .env — cannot call Claude."
        return

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    ov = context.get("overview", {})
    filters = context.get("filters", {})
    signals = context.get("signals", [])

    # Summarise signals — avoid sending hundreds of raw rows to the model
    recent = signals[:20]
    signal_lines = "\n".join(
        f"  {s.get('signal_time', '?')[:16]} | {s.get('symbol')} {s.get('direction')} "
        f"| conf={s.get('confidence')}% | outcome={s.get('outcome')} "
        f"| strategies={','.join(s.get('strategies_fired') or [])}"
        for s in recent
    )

    by_symbol_lines = "\n".join(
        f"  {s['symbol']}: {s['total']} signals, {s['win_rate']}% WR, ₹{s['pnl']:,.0f} P&L"
        for s in context.get("by_symbol", [])
    )
    by_direction_lines = "\n".join(
        f"  {d['direction']}: {d['total']} signals, {d['win_rate']}% WR"
        for d in context.get("by_direction", [])
    )

    context_block = f"""
## Dashboard Data (current filters)

Filters: {filters.get('start_date')} to {filters.get('end_date')} | strategies={filters.get('strategies', 'all')}

Overview:
  Total signals : {ov.get('total_signals', 0)}
  Win rate      : {ov.get('win_rate', 0)}%  (break-even = 33.3%)
  Wins          : {ov.get('wins', 0)}
  Losses        : {ov.get('losses', 0)}
  Expired/Sold  : {ov.get('expired', 0)}
  Open          : {ov.get('open', 0)}
  Total P&L     : ₹{ov.get('total_pnl', 0):,.0f}

By symbol:
{by_symbol_lines or '  (no data)'}

By direction:
{by_direction_lines or '  (no data)'}

Most recent {len(recent)} signals:
{signal_lines or '  (no signals)'}
"""

    async with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=1024,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"{context_block}\n\nQuestion: {question}"
        }],
    ) as stream:
        async for text in stream.text_stream:
            yield text
