import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.models import Signal, SignalOutcome, StrategyResult, SignalState

logger = structlog.get_logger()


async def get_overall_stats(session: AsyncSession) -> dict:
    """Overall win rate and P&L summary."""
    result = await session.execute(
        select(
            func.count(SignalOutcome.id).label("total"),
            func.sum(
                func.cast(SignalOutcome.result == "TARGET_HIT", int)
            ).label("wins"),
            func.sum(SignalOutcome.pnl).label("total_pnl"),
        )
    )
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
