import structlog
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
from app.db.models import Signal, SignalOutcome, StrategyResult, SignalState

logger = structlog.get_logger()


async def get_overall_stats(session: AsyncSession, for_date: date | None = None) -> dict:
    """Overall win rate and P&L summary. Pass for_date to scope to a single day."""
    q = (
        select(
            func.count(SignalOutcome.id).label("total"),
            func.sum(
                case((SignalOutcome.result == "TARGET_HIT", 1), else_=0)
            ).label("wins"),
            func.sum(SignalOutcome.pnl).label("total_pnl"),
        )
        .join(Signal, SignalOutcome.signal_id == Signal.id)
    )
    if for_date is not None:
        q = q.where(func.date(Signal.created_at) == for_date)
    result = await session.execute(q)
    row = result.first()
    total = row.total or 0
    wins = row.wins or 0
    return {
        "total_signals": total,
        "wins": wins,
        "losses": total - wins,
        "win_rate": round(wins / total * 100, 2) if total > 0 else 0,
        "total_pnl": round(row.total_pnl or 0, 2),
    }


async def get_reason_accuracy(session: AsyncSession) -> list[dict]:
    """
    For each strategy reason, calculate how often it contributed to a winning signal.
    """
    result = await session.execute(
        select(StrategyResult, SignalOutcome)
        .join(SignalOutcome, StrategyResult.signal_id == SignalOutcome.signal_id)
    )
    rows = result.all()

    reason_stats: dict[str, dict] = {}
    for strategy_result, outcome in rows:
        name = strategy_result.strategy_name
        if name not in reason_stats:
            reason_stats[name] = {"total": 0, "wins": 0}
        reason_stats[name]["total"] += 1
        if outcome.result == "TARGET_HIT":
            reason_stats[name]["wins"] += 1

    return [
        {
            "reason": name,
            "total": s["total"],
            "wins": s["wins"],
            "win_rate": round(s["wins"] / s["total"] * 100, 2) if s["total"] > 0 else 0,
        }
        for name, s in sorted(reason_stats.items(), key=lambda x: -x[1]["wins"])
    ]


async def get_time_of_day_performance(session: AsyncSession) -> list[dict]:
    """Win rate by hour of day — shows which market hours generate best signals."""
    result = await session.execute(
        select(Signal.signal_context, SignalOutcome.result)
        .join(SignalOutcome, Signal.id == SignalOutcome.signal_id)
        .where(Signal.signal_context.isnot(None))
    )
    rows = result.all()

    hour_stats: dict[int, dict] = {}
    for ctx, outcome in rows:
        hour = ctx.get("hour") if ctx else None
        if hour is None:
            continue
        if hour not in hour_stats:
            hour_stats[hour] = {"total": 0, "wins": 0}
        hour_stats[hour]["total"] += 1
        if outcome == "TARGET_HIT":
            hour_stats[hour]["wins"] += 1

    return [
        {
            "hour": f"{h:02d}:00",
            "total": s["total"],
            "wins": s["wins"],
            "win_rate": round(s["wins"] / s["total"] * 100, 2) if s["total"] > 0 else 0,
        }
        for h, s in sorted(hour_stats.items())
    ]


async def get_strategy_combo_performance(session: AsyncSession) -> list[dict]:
    """Win rate by strategy combination — shows which strategy mixes produce best signals."""
    result = await session.execute(
        select(Signal.signal_context, SignalOutcome.result)
        .join(SignalOutcome, Signal.id == SignalOutcome.signal_id)
        .where(Signal.signal_context.isnot(None))
    )
    rows = result.all()

    combo_stats: dict[str, dict] = {}
    for ctx, outcome in rows:
        fired = ctx.get("strategies_fired") if ctx else None
        if not fired:
            continue
        key = "+".join(sorted(fired))
        if key not in combo_stats:
            combo_stats[key] = {"total": 0, "wins": 0}
        combo_stats[key]["total"] += 1
        if outcome == "TARGET_HIT":
            combo_stats[key]["wins"] += 1

    return [
        {
            "combo": k,
            "total": v["total"],
            "wins": v["wins"],
            "win_rate": round(v["wins"] / v["total"] * 100, 2) if v["total"] > 0 else 0,
        }
        for k, v in sorted(combo_stats.items(), key=lambda x: -x[1]["total"])
        if v["total"] >= 5  # only show combos with enough data
    ]


async def get_regime_performance(session: AsyncSession) -> list[dict]:
    """Win rate by market regime."""
    result = await session.execute(
        select(Signal.regime, SignalOutcome.result)
        .join(SignalOutcome, Signal.id == SignalOutcome.signal_id)
    )
    rows = result.all()

    regime_stats: dict[str, dict] = {}
    for regime, result_label in rows:
        key = regime.value
        if key not in regime_stats:
            regime_stats[key] = {"total": 0, "wins": 0}
        regime_stats[key]["total"] += 1
        if result_label == "TARGET_HIT":
            regime_stats[key]["wins"] += 1

    return [
        {
            "regime": k,
            "total": v["total"],
            "wins": v["wins"],
            "win_rate": round(v["wins"] / v["total"] * 100, 2) if v["total"] > 0 else 0,
        }
        for k, v in regime_stats.items()
    ]
