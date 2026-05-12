"""
Chanakya Sanket — Claude AI Analyst
Shells out to the `claude` CLI (Claude Code) in non-interactive mode.
No API key needed — uses the existing Claude Pro/Max subscription.
"""
import asyncio
import shutil
from typing import AsyncIterator

SYSTEM_PROMPT = """You are Chanakya — an expert intraday options trading analyst embedded in the Chanakya Sanket signal intelligence engine.

You have real access to the user's signal history, win rates, P&L data, and strategy performance. Speak like a sharp, concise trading mentor — direct, honest, specific. No generic advice.

Key facts about this system:
- Instruments: NIFTY and BANKNIFTY weekly options, intraday only, 5-minute candles
- Break-even win rate: 33.3% (2x ATR target, 1x ATR stop-loss, so you need >33% to be profitable)
- Win rate formula: wins / (wins + losses + expired). Expired signals count as losses — theta decay makes them real costs.
- Strategies: VWAP Breakout (20pts), RSI Momentum (15pts), Opening Range Breakout (15pts), OI Buildup (25pts)
- Min confidence: 60% (normalized — needs at least 3 price-action strategies to fire simultaneously)
- Circuit breaker: 2 consecutive SL hits on a symbol pauses it; 3 total SL hits stops all signals for the day

Rules:
- Reference the actual numbers from the data. Do not make up figures.
- Be honest. If the data shows a weakness, say so directly.
- Keep responses concise — 3 to 6 sentences unless a detailed breakdown is needed.
- Never recommend specific trades or tell the user to buy or sell.
- This is paper trading data for research and learning.
"""


def _build_prompt(question: str, context: dict) -> str:
    ov = context.get("overview", {})
    filters = context.get("filters", {})
    signals = context.get("signals", [])

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

    return f"""{SYSTEM_PROMPT}

---

## Dashboard Data (current filters)

Filters: {filters.get('start_date')} to {filters.get('end_date')} | strategies: {filters.get('strategies', 'all')}

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

---

Question: {question}
"""


async def stream_analysis(question: str, context: dict) -> AsyncIterator[str]:
    claude_bin = shutil.which("claude")
    if not claude_bin:
        yield "Error: `claude` CLI not found in PATH. Make sure Claude Code is installed."
        return

    prompt = _build_prompt(question, context)

    proc = await asyncio.create_subprocess_exec(
        claude_bin, "-p",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        proc.stdin.write(prompt.encode("utf-8"))
        proc.stdin.close()

        while True:
            chunk = await proc.stdout.read(256)
            if not chunk:
                break
            yield chunk.decode("utf-8", errors="replace")

        await proc.wait()

        # Surface stderr if the process failed
        if proc.returncode != 0:
            stderr = await proc.stderr.read()
            if stderr:
                yield f"\n\n[CLI error: {stderr.decode('utf-8', errors='replace').strip()}]"

    except Exception as e:
        try:
            proc.kill()
        except Exception:
            pass
        yield f"\n\n[Error: {e}]"
