# Logic Changelog — Chanakya Sanket

## RULES FOR CLAUDE (READ BEFORE ANY LOGIC CHANGE)
1. **Read this entire file before changing any strategy, indicator, confidence scoring, or signal rule.**
2. **After every logic change, add an entry here immediately** — before committing.
3. **If a change you are about to make already appears here and was reverted**, do NOT make it again without explicit user approval.
4. This file is the anti-loop guardrail. Its purpose is to prevent re-introducing changes that were tried and rejected.

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

### [2026-05-12] Starlette downgrade to 0.37.2 (infra fix)
- **What changed**: `starlette` downgraded from 1.0.0 (claude-agent-sdk bumped it) back to 0.37.2 (FastAPI 0.111 requires ~0.37)
- **Why**: claude-agent-sdk install silently upgraded Starlette, breaking FastAPI's Router init
- **Result**: FastAPI works again; backfill script imports correctly
- **Status**: KEPT
