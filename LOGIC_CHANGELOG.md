# Logic Changelog — Chanakya Sanket

## RULES FOR CLAUDE (READ BEFORE ANY LOGIC CHANGE)
1. **Read this entire file before changing any strategy, indicator, confidence scoring, or signal rule.**
2. **After every logic change, add an entry here immediately** — before committing.
3. **If a change you are about to make already appears here and was reverted**, do NOT make it again without explicit user approval.
4. This file is the anti-loop guardrail. Its purpose is to prevent re-introducing changes that were tried and rejected.

---

### [2026-05-13] Branching strategy introduced — main=v1, develop=v2

- **What changed**: Created `develop` branch from `main` at commit `07af1eb` (post Supertrend+PDH/PDL+new formula). Reverted `main` to 4-strategy stable engine (pre `0e2e9d9`).
- **v1 (main)**: VWAP+RSI+ORB+OI, max_possible normalization, min_confidence=60. Honest baseline: 364 signals, 44.8% WR.
- **v2 (develop)**: Supertrend+PDH/PDL added, penalty-based fixed-denominator formula, ML Phase 5 in progress.
- **Merge rule**: develop → main only when v2 backtest WR ≥ 44.8% AND explicit user approval.
- **Status**: ACTIVE — respect branch discipline at all times.

---

## Format
```
### [YYYY-MM-DD] Short title
- **What changed**: exact config/code change
- **Why**: reason it was made
- **Result**: what happened (improved / hurt / reverted)
- **Status**: KEPT / REVERTED / SUPERSEDED
```

---

## Changelog

### [2026-05-11] OI buildup threshold lowered 5% → 1%
- **What changed**: `oi_buildup_threshold` in config.py: `0.05` → `0.01`
- **Why**: Real NSE EOD day-over-day OI changes are ~0.5–1%, never reached 5% threshold so strategy never fired
- **Result**: Strategy started firing on real NSE data
- **Status**: KEPT

---

### [2026-05-11] OI strategy logic relaxed — single-leg condition
- **What changed**: `oi_buildup.py` CALL signal: fires if `call_oi_buildup OR put_oi_unwind` (was AND). Same for PUT: `put_oi_buildup OR call_oi_unwind`. Added guard `not put_oi_buildup` for CALL and `not call_oi_buildup` for PUT to prevent conflicting signals.
- **Why**: EOD data rarely shows both legs moving simultaneously; single-leg is sufficient for daily data
- **Result**: More signals fired on real NSE EOD data
- **Status**: KEPT

---

### [2026-05-11] OI disabled in backfill — oi_data=None
- **What changed**: `_simulate_one_day()` in main.py passes `oi_data=None` instead of `get_mock_oi_data()`
- **Why**: Real NSE EOD OI data has wrong granularity for intraday signals. Real OI in backfill hurt WR (31.9% vs 36.5% without it). Fake OI was inflating WR by ~8% by always agreeing with price direction.
- **Result**: Honest baseline established — 97 signals, 36.5% WR (price action only)
- **Status**: KEPT — do NOT re-enable OI in backfill without a proper intraday OI dataset

---

### [2026-05-11] Confidence scoring normalized to 0-100
- **What changed**: `confidence.py` — score is now `raw_score / max_possible × 100`. `max_possible` excludes OI points when `oi_data=None`. Previously raw points were compared directly to `min_confidence_score`.
- **Why**: User correctly identified that lowering `min_confidence` to 35 was the wrong fix. Normalizing keeps the 60-point threshold meaningful in all modes (backfill, live, with/without OI).
- **Result**: Backfill (no OI, max=55pts): 3 strategies → 83%, 2 strategies → 58% (doesn't fire). Live (with OI, max=75pts): 3 strategies → 67%, fires correctly.
- **Status**: KEPT — do NOT revert to raw point comparison

---

### [2026-05-11] min_confidence restored to 60
- **What changed**: `config.py` and `.env`: `min_confidence_score` restored from 35 → 60
- **Why**: Was wrongly lowered to 35 to compensate for missing OI points. Normalization fix made this unnecessary.
- **Result**: Threshold now meaningful again — 60% of max possible strategies must agree
- **Status**: KEPT

---

### [2026-05-11] BullishEngulfing strategy removed from confidence scoring
- **What changed**: `bullish_engulfing` strategy no longer contributes to confidence score max_possible
- **Why**: Backtested at 14.3% WR — well below 33.3% break-even. Negative edge.
- **Result**: Cleaner scoring without a losing strategy inflating noise
- **Status**: KEPT — do NOT re-add to scoring without a fresh backtest showing positive edge

---

### [2026-05-11] Candle seeding extended to 3 previous weekdays + today
- **What changed**: `main.py` lifespan — seeds `days_back` in `[3, 2, 1, 0]`, skipping weekends
- **Why**: Server was only seeding today's candles (4 at 9:35 AM). Signal engine needs 20+ candles minimum, 50+ for RSI. With only today's candles, first signal couldn't fire until ~10:35 AM.
- **Result**: 80+ candles available from minute 1 on startup
- **Status**: KEPT

---

### [2026-05-11] RSI momentum lookback extended to 5 candles
- **What changed**: `rsi_crossed_above()` lookback parameter: 1 → 5 (checks if RSI crossed above level within last 5 candles)
- **Why**: RSI cross and VWAP breakout don't happen on the exact same candle in real data. Lookback=5 (25 min window) aligns the two signals so they can contribute to the same confidence score.
- **Result**: More realistic signal alignment with real market behaviour
- **Status**: KEPT

---

### [2026-05-12] Live candles persisted to DB
- **What changed**: `candle_processor.py` — `process_tick()` now returns finalized candle dict. `websocket_client.py` — `_save_candle_to_db()` saves each closed candle via `INSERT ON CONFLICT DO NOTHING`. `main.py` startup — loads today's candles from DB first, falls back to Upstox API.
- **Why**: Server restart mid-session wiped in-memory candle buffer. Today's intraday candles were being re-fetched from Upstox API (network call, possible delay). DB is always fresher and faster.
- **Result**: Restart recovery is now instant from DB. No missed candle history after a reload.
- **Status**: KEPT

---

### [2026-05-12] CPR added to regime detection
- **What changed**: `app/indicators/cpr.py` added. `regime.py` now checks CPR width first — narrow CPR (<0.15% of pivot) = SIDEWAYS, suppresses breakout strategies. Falls back to ATR check if CPR unavailable.
- **Why**: Zerodha Varsity CPR chapter — narrow CPR means prior day was range-bound, expect same today. More reliable than ATR alone for intraday regime.
- **Result**: Pending backtest
- **Status**: KEPT

---

### [2026-05-12] Strike selector — direction-aware OTM, capped at 1 OTM
- **What changed**: `strike_selector.py` `select_strike()` now takes `direction` param. CALL OTM = ATM + interval (higher strike). PUT OTM = ATM - interval (lower strike). 2 OTM removed — intraday delta too low (<0.3), poor liquidity.
- **Why**: Bug — was always adding interval regardless of direction (PUT OTM should go DOWN). Also Zerodha delta chapter: 2 OTM delta <0.3, too unresponsive for intraday directional trades.
- **Result**: Fixes PUT strike selection bug
- **Status**: KEPT

---

### [2026-05-12] Expiry min days bumped from 2 → 3
- **What changed**: `config.py` `expiry_min_days`: 2 → 3
- **Why**: Zerodha Theta chapter — decay accelerates exponentially in final days. Buying options within 2 days of expiry puts theta heavily against the buyer.
- **Result**: Will switch to next week's expiry earlier
- **Status**: KEPT

---

### [2026-05-12] RSI stuck overbought/oversold = continuation signal
- **What changed**: `rsi_momentum.py` — if RSI has been above 70 for 5+ consecutive candles (stuck overbought), fire CALL signal even without a fresh crossover. Same logic for stuck oversold (<30) → PUT.
- **Why**: Zerodha Varsity RSI chapter — "stuck overbought means excess positive momentum sustaining the trend, look for buying not selling". Previously only crossover above 55 triggered signal.
- **Result**: Pending backtest
- **Status**: KEPT

---

### [2026-05-12] OI strategy — differentiated points by scenario strength
- **What changed**: `oi_buildup.py` — long buildup and short buildup (new money entering) keep full 25 pts. Short covering and long unwinding (exits only, no new money) reduced to 12 pts (max_points // 2).
- **Why**: Verified across Zerodha Varsity, StockEdge, TradeJini, Quora — all confirm long/short buildup are structurally stronger than covering/unwinding. Short covering = "pain-driven buying, not conviction". Previously all 4 scenarios awarded equal points.
- **Result**: Pending backtest
- **Status**: KEPT

---

### [2026-05-12] signal_context JSONB added to every signal
- **What changed**: `Signal` model — added `signal_context` JSON column. `generator.py` — captures RSI, VWAP distance%, ATR, PCR (real NSE EOD), strategies_fired, hour, minute at signal time.
- **Why**: Needed to analyse which market conditions produce winning vs losing signals for future accuracy improvement.
- **Result**: Every signal now has a market snapshot for post-hoc analysis
- **Status**: KEPT

---

### [2026-05-12] Circuit breaker added
- **What changed**: `scheduler.py` — `_consecutive_losses` per-symbol (skip after 2 SL_HITs in a row). `_daily_losses_total` global (stop all signals after 3 SL_HITs/day). Both reset at 9:15 AM.
- **Why**: Backtest showed wipeout days with 5 consecutive losses. Capping at 3 saves ~2 bad trades on the worst days.
- **Result**: Wipeout days capped. Marginal WR improvement (34.4% → 37.7% in backtested 6-week window).
- **Status**: KEPT

---

### [2026-05-12] Zerodha Varsity batch improvements — cumulative backtest result
- **What changed**: CPR regime detection + direction-aware OTM strike fix + expiry_min_days 2→3 + RSI stuck overbought/oversold (all in one commit)
- **Why**: Applied from reading Zerodha Varsity modules (Technical Analysis, Options Theory, Risk Management)
- **Result**: Full re-backtest on 267 trading days (May 2025 – May 2026), min_confidence=25: **564 signals, 42.6% WR** (was 36.5% price-action baseline). +6.1pp improvement.
- **Status**: KEPT

---

### [2026-05-12] OI toggle + intraday snapshot persistence
- **What changed**: `app/utils/oi_toggle.py` — Redis key `oi_strategy_enabled` (default OFF). `scheduler.py` — `save_oi_snapshot_job` saves Upstox options chain OI to `market_snapshots` every 5 min during live market hours. `main.py _simulate_one_day` — when OI toggle ON, uses NSE Bhavcopy OI (`real_oi.py`). Admin endpoints: `GET /admin/oi`, `POST /admin/oi/enable`, `POST /admin/oi/disable`.
- **Why**: OI data was never being persisted to DB. Now every live 5-min cycle stores call_oi + put_oi. Admin toggle lets you switch OI on/off without a restart to test its impact.
- **Result**: OI default kept OFF (price action baseline = 42.6% WR). Toggle ON to test EOD OI impact or accumulate intraday OI history.
- **Status**: KEPT

---

### [2026-05-12] Near-expiry alerts + USER_CLOSED state + honest win rate

- **What changed**:
  - `SignalState` enum: added `USER_CLOSED` — signals user manually squared off before EOD
  - `database.py`: `ALTER TYPE signalstate ADD VALUE IF NOT EXISTS 'USER_CLOSED'` (runs in AUTOCOMMIT outside transaction)
  - `telegram.py`: `send_squareoff_alert()` — per-signal warning with live unrealized P&L estimate + inline "✅ Mark as Sold" button
  - `scheduler.py`: two new jobs — `squareoff_warning_job(20)` at 3:10 PM, `squareoff_warning_job(10)` at 3:20 PM (live mode only). `telegram_polling_job` every 10s polls Telegram callback queries, marks signal `USER_CLOSED` when button tapped.
  - `main.py`: `POST /signals/{id}/mark-sold` endpoint. Analytics: `resolved = wins + losses + expired` — EXPIRED and USER_CLOSED now included in WR denominator.
- **Why**: In reality EXPIRED signals = theta decay = real loss. Excluding them from WR was overstating performance. "Mark as Sold" button lets user ack each signal before EOD so system tracks that they actually exited.
- **Result**: WR denominator is now honest. Near-expiry alerts give 20-min and 10-min warnings so user never misses a square-off.
- **Status**: KEPT — do NOT revert to `resolved = wins + losses` (that was the overstated baseline)

---

### [2026-05-13] Hard signal cutoff at 13:30 IST
- **What changed**: `generator.py` — blocks signal generation when `hour >= 14 OR (hour == 13 AND minute >= 30)`. Previously only `hour == 15` was blocked.
- **Why**: 2-year ML analysis (6,864 deduplicated crossovers): 14:xx WR=25.7%, 15:xx WR=11.8% — both below 33.3% break-even. 13:xx WR=33.3% (break-even, marginal). Signal P&L deteriorates sharply after 13:30.
- **Result**: Eliminates clearly losing time window. Expected WR improvement.
- **Status**: KEPT — do NOT re-enable 14:xx signals without strong evidence of edge

---

### [2026-05-13] Signal filter stats corrected — removed inflated backtest numbers
- **What changed**: `signal_filter.py` — `_HOUR_WR` and `_COMBO_WR` updated from old 1,409-signal fake-OI backtest to corrected 2-year analysis (May 2024 – May 2026, honest WR). Old numbers were 10–25pp too high (e.g. 11:xx was 61% WR → corrected to 33%). Old combo ORB+RSI was 48% → corrected to 38.5%.
- **Why**: Fake OI backtest inflated WR by always agreeing with price direction. Inflated stats caused Claude AI filter to be too permissive.
- **Result**: AI filter now uses honest baselines. NO_GO threshold adjusted accordingly.
- **Status**: KEPT

---

### [2026-05-13] signal_time always stored as IST with +05:30 offset
- **What changed**: `generator.py` — `_sig_ts` converted to IST via `.astimezone(IST)` before extracting hour/minute and before storing `signal_time` in signal_context. Existing 948 naive-UTC timestamps in DB backfilled with correct IST hour/minute and `+05:30` suffix.
- **Why**: Parquet/historical candle timestamps are UTC. `_sig_ts.hour` was reading UTC hour (e.g. 3am) instead of IST hour (e.g. 9am). Dashboard by_hour chart showed phantom hours 3–8 (UTC) alongside correct hours 9–15 (IST) for newer signals.
- **Result**: All signal_times consistently stored as IST `+05:30`. By-hour chart now correctly shows only 9–15 IST.
- **Status**: KEPT — always use IST for all signal_context timestamps

---

### [2026-05-13] Full 2-year backfill completed (May 2024 – May 2026)
- **What changed**: Ran `POST /trigger/backfill?start_date=2024-05-13&end_date=2025-11-02` to fill gap before Nov 2025. Total historical signals: 1,629 spanning May 2024 – May 2026.
- **Why**: Oldest signal was Nov 2025. OHLCV parquet data goes back to May 2024. Needed full 2-year dataset for ML training.
- **Result**: 1,629 historical signals, 41.7% WR (680W/821L/128E). 2-year ML training dataset ready.
- **Status**: KEPT — do NOT delete historical signals; they are the ML training set

---

### [2026-05-12] Starlette downgrade to 0.37.2 (infra fix)
- **What changed**: `starlette` downgraded from 1.0.0 (claude-agent-sdk bumped it) back to 0.37.2 (FastAPI 0.111 requires ~0.37)
- **Why**: claude-agent-sdk install silently upgraded Starlette, breaking FastAPI's Router init
- **Result**: FastAPI works again; backfill script imports correctly
- **Status**: KEPT

---

### [2026-05-13] Adaptive hour-based shadow filter
- **What changed**: New `app/utils/hour_filter.py`. `generator.py` — removed 13:30 IST hard cutoff. Added `should_shadow(hour, session)` call for `source IN ('live','historical')`. When rolling WR for the hour < 40% AND ≥ 15 samples, signal.source set to 'shadow'. Shadow signals are saved to DB + evaluated, Telegram skipped. `scheduler.py` — Telegram send conditioned on `signal.source != 'shadow'`. Dashboard aggregation: shadow signals excluded from overview/by_symbol/by_direction stats but included in table. Source badge: purple.
- **Why**: Hard cutoff at 13:30 was explore-vs-exploit failure: bad hours would never recover because no signals → no data → filter never lifts. Shadow source lets the filter self-correct as outcomes accumulate.
- **Result**: After walk-forward backfill (May 2024–May 2026), WR improved from 41.7% → 51.4% when filtering to non-shadow signals.
- **Status**: KEPT — do NOT re-introduce hard time cutoffs

---

### [2026-05-13] Confidence scoring formula replaced — penalty-based fixed denominator

- **What changed**: `app/signals/confidence.py` — replaced dynamic `max_possible` normalization with:
  `score = max(0, min(100, round((fired_pts - unfired_pts/10) / 60 * 100)))`
  - `fired_pts`: sum of points from all strategies that fired
  - `unfired_pts/10`: small penalty for each evaluated-but-not-fired strategy
  - `60`: fixed calibration constant (old raw threshold)
  - Score floored at 0, capped at 100
- **Why**: Adding Supertrend+PDH/PDL inflated `max_possible` from 50→85, causing the old reliable VWAP+RSI+ORB combo to score 59% (just under the 60% threshold) — producing zero signals. The old dynamic normalization was fragile: adding any new strategy changed the scoring of all existing combos.
- **Key scores with new formula**:
  - VWAP+RSI+ORB (2 unfired): 77% → fires ✓
  - RSI+ORB only (3 unfired): 41% → no fire ✓
  - VWAP+RSI+ORB+ST: 100% → fires ✓
  - SIDEWAYS (RSI+ST max=35): 58% → no fire ✓ (sideways still silent)
  - Single strategy: 0% → no fire ✓ (min-2 rule + low score)
- **Result**: Pending backfill re-run
- **Status**: KEPT — do NOT revert to max_possible normalization

---

### [2026-05-13] Supertrend + PDH/PDL strategies added
- **What changed**: `app/indicators/supertrend.py` (new) — ATR-based trailing stop, period=10, multiplier=3.0. `app/strategies/supertrend.py` (new) — fires on direction crossover; bearish→bullish=CALL, bullish→bearish=PUT. +20 pts. `app/strategies/pdh_pdl.py` (new) — fires when today's close breaks above previous day's high (CALL) or below previous day's low (PUT) for the first time. +15 pts. PDH/PDL added to BREAKOUT_STRATEGIES (suppressed in SIDEWAYS). Both added to STRATEGIES list in generator.py and all_strategy_pts in confidence.py.
- **Why**: Price action strategies with strong intraday breakout evidence. Supertrend adds trend-following confirmation. PDH/PDL captures widely-watched breakout levels used by large participants.
- **Result**: Pending backfill re-run
- **Status**: KEPT
