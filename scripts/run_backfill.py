"""
Standalone full backfill script.
Runs _simulate_one_day for every trading day in the range directly — no HTTP overhead.
Usage: .venv/bin/python3 scripts/run_backfill.py
"""
import asyncio
import sys
import os
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import AsyncSessionLocal, create_tables
from app.main import _simulate_one_day

START_DATE = date(2025, 5, 1)
END_DATE   = date(2026, 5, 11)
SIGNALS_PER_DAY = 10     # per call (2 symbols, so up to 10 total)
MIN_CONFIDENCE  = 25     # low enough to capture 1-2 strategy combos


def trading_days(start: date, end: date):
    d = start
    while d < end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


async def main():
    await create_tables()

    all_days = list(trading_days(START_DATE, END_DATE))
    print(f"Backfilling {len(all_days)} trading days ({START_DATE} → {END_DATE})")
    print(f"min_confidence={MIN_CONFIDENCE}, signals_per_day={SIGNALS_PER_DAY}\n")

    total_signals = total_wins = total_losses = total_expired = 0

    for i, sim_date in enumerate(all_days, 1):
        async with AsyncSessionLocal() as session:
            results = await _simulate_one_day(
                sim_date, session,
                count=SIGNALS_PER_DAY,
                notify=False,
                min_confidence=MIN_CONFIDENCE,
            )

        wins    = sum(1 for r in results if r["outcome"] == "TARGET_HIT")
        losses  = sum(1 for r in results if r["outcome"] == "SL_HIT")
        expired = sum(1 for r in results if r["outcome"] == "EXPIRED")
        total_signals += len(results)
        total_wins    += wins
        total_losses  += losses
        total_expired += expired

        wr = round(total_wins / total_signals * 100, 1) if total_signals else 0
        status = f"[{i}/{len(all_days)}] {sim_date}  signals={len(results)} W={wins} L={losses} E={expired}  |  cumulative: {total_signals} signals, {wr}% WR"
        print(status, flush=True)

    print(f"\nDone. {total_signals} signals | {total_wins}W {total_losses}L {total_expired}E | WR={round(total_wins/total_signals*100,1) if total_signals else 0}%")


if __name__ == "__main__":
    asyncio.run(main())
