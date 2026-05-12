# Chanakya Sanket — Trading Intelligence Engine | Claude Project Context

## RULES FOR CLAUDE (READ FIRST)
1. **Update this file immediately** after every decision, config change, module addition, or architecture change. This is the single source of truth.
2. **Read this entire file before touching any code.** Never make assumptions — check here first.
3. **Before changing ANY strategy logic, indicator, confidence scoring, or signal rule** — read `LOGIC_CHANGELOG.md` first. If the change was already tried and reverted, do NOT make it again without explicit user approval. After making a logic change, add an entry to `LOGIC_CHANGELOG.md` immediately.
4. **Never commit `.env`**. It contains live secrets.
5. **Never add auto-trading logic.** The system only generates signals. Humans execute.
6. **Never add ML** until Phase 5 is explicitly started.
7. **Always run in the project venv**: `.venv/bin/python3` and `.venv/bin/uvicorn`. Never use system Python.
8. **Always use `make` commands** for dev workflow. See the Makefile section below.
9. **After every code change**, commit and push to GitHub using conventional commit messages.
10. **Before suggesting architecture changes**, check if a simpler fix exists first.
11. **The DB already has real data**. Never drop tables or run destructive migrations without explicit user approval.

---

## Product Identity
- **Name**: Chanakya Sanket — Trading Intelligence Engine
- **Tagline**: *Edge through knowledge, not luck.*
- **Meaning**: "Chanakya" = ancient Indian master strategist. "Sanket" = signal in Sanskrit.
- **Telegram Bot**: @ChanakaSanketBot
- **GitHub**: https://github.com/Shreyas6543/chanakya-sanket (private)
- **GitHub User**: Shreyas6543

---

## What This System Does
An explainable, rule-based intraday options trading intelligence engine for Indian markets.

- Connects to Upstox live WebSocket feed → streams NIFTY & BANKNIFTY prices
- Builds 5-minute candles from live ticks
- Runs 5 strategies every 5 minutes during market hours
- Generates buy/sell signals with confidence scores and explainable reasons
- Sends Telegram alerts instantly
- Tracks every signal lifecycle: OPEN → TARGET_HIT / SL_HIT / EXPIRED
- Stores everything in PostgreSQL for analytics
- Tags every signal as `live` or `mock` for clean data separation

**No auto-trading. No ML. No frontend. Backend only.**

---

## Business Context
- Personal use first → paper trading validation → small capital live → productize
- Target market: Indian retail intraday options traders
- Focus instruments: NIFTY and BANKNIFTY (NSE F&O)
- Timeframe: 5-minute candles only
- SEBI positioning: "trading intelligence & analytics platform" — NOT a signal service
- No paid subscriptions until SEBI Research Analyst compliance is understood

---

## Tech Stack
| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.12 | venv at `.venv/` |
| API Framework | FastAPI 0.111 | Async, lifespan pattern |
| Database | PostgreSQL 15 | Docker container `trading_postgres` |
| Cache | Redis 7 | Docker container `trading_redis` |
| Scheduler | APScheduler 3.10 | In-process, AsyncIOScheduler |
| Market Data | Upstox v3 WebSocket | `wss://api.upstox.com/v3/feed/market-data-feed` |
| Protobuf | upstox-python-sdk 2.26 + google-protobuf 7.34 | Decode binary WebSocket frames |
| SSL | certifi | Required on macOS — system certs don't work |
| Alerts | python-telegram-bot 21.2 | Instant push notifications |
| News Sentiment | VADER (vaderSentiment) | No API key needed |
| ORM | SQLAlchemy 2.0 async | asyncpg driver |

---

## Broker: Upstox
- Free API — no monthly charge (Zerodha charges ₹2000/month for Kite Connect)
- WebSocket v3 for live prices (binary protobuf frames, not JSON)
- REST API for options chain OI data
- **Token expires daily at midnight** — must re-authenticate every morning
- **Auth flow**: `GET /auth/login` in browser → Upstox OAuth → token auto-saved to `.env`
- Credentials needed in `.env`: `UPSTOX_API_KEY`, `UPSTOX_API_SECRET`, `UPSTOX_ACCESS_TOKEN`

---

## Original Specification Documents
All original design docs are at `/Users/shrego-persnol/Documents/fintech/docs/`. Read these for full product vision, business context, and roadmap intent before making any major architectural decisions.

```
docs/
├── AI_Trading_Intelligence_System_Roadmap.docx   # Full 6-phase roadmap + business model
├── Trading_AI_Execution_Blueprint.docx           # Technical execution plan
├── Trading_AI_Pitch_Deck.docx                    # Product pitch + market positioning
├── Trading_AI_Starter_Logics.docx                # Initial strategy logic ideas
├── iteration-1/
│   ├── UPDATED_Claude_Build_Instructions.docx    # Phase 1 build instructions (implemented)
│   └── UPDATED_Master_Trading_Roadmap.docx       # Updated roadmap after iteration 1
└── iteration-2/
    ├── FINAL_Claude_Build_Spec.docx              # Final build spec (current codebase basis)
    └── FINAL_Updated_Execution_Roadmap.docx      # Most current roadmap — read this first
```

**Priority reading order for a new agent:**
1. `iteration-2/FINAL_Updated_Execution_Roadmap.docx` — current roadmap, what's next
2. `iteration-2/FINAL_Claude_Build_Spec.docx` — full technical spec this codebase is built from
3. `iteration-1/UPDATED_Master_Trading_Roadmap.docx` — context on earlier decisions
4. `AI_Trading_Intelligence_System_Roadmap.docx` — original vision (some superseded by iteration-2)
5. **Chat history + decisions log (Google Doc)**: https://docs.google.com/document/d/12-VHaGOsw_-GqPD6uNQ74OhMLdKvmhdoZhdDDnKvz3o/edit?usp=sharing — contains pasted chat sessions with key decisions, reasoning, and context not captured elsewhere. Read with WebFetch tool.

---

## Local Setup & Prerequisites
- macOS (Darwin 25.4.0)
- Python 3.12 at `/usr/local/bin/python3`
- Docker Desktop must be running before `make dev`
- Project path: `/Users/shrego-persnol/Documents/fintech/trading-engine`
- Docs path: `/Users/shrego-persnol/Documents/fintech/docs` (original spec .docx files)
- venv: `.venv/` inside project root

---

## Project Structure
```
trading-engine/
├── CLAUDE.md                        # This file — always update
├── Makefile                         # All dev commands — use these
├── .env                             # Secrets — NEVER commit
├── .env.example                     # Template — commit this
├── .gitignore
├── docker-compose.yml               # PostgreSQL + Redis
├── requirements.txt
├── app/
│   ├── main.py                      # FastAPI app, all endpoints, lifespan
│   ├── config.py                    # All settings via pydantic-settings + lru_cache
│   ├── scheduler.py                 # APScheduler jobs — signal engine, evaluator, EOD
│   ├── auth/
│   │   └── upstox.py                # OAuth flow + token save + cache_clear
│   ├── db/
│   │   ├── database.py              # Async engine, create_tables (with ALTER migrations)
│   │   └── models.py                # All SQLAlchemy models
│   ├── market_data/
│   │   ├── websocket_client.py      # Upstox v3 WebSocket, protobuf decode, LIVE_PRICES store
│   │   ├── candle_processor.py      # Aggregate ticks into 5m candles (_candle_buffer)
│   │   ├── mock.py                  # Mock candle generator + tick simulator
│   │   └── options_chain.py         # Fetch OI data from Upstox REST
│   ├── indicators/
│   │   ├── rsi.py                   # RSI + rsi_crossed_above()
│   │   ├── vwap.py                  # VWAP + vwap_breakout()
│   │   ├── ema.py                   # EMA + ema_bullish_alignment()
│   │   ├── atr.py                   # ATR + current_atr()
│   │   └── volume.py                # volume_spike()
│   ├── strategies/
│   │   ├── base.py                  # BaseStrategy ABC + StrategySignal dataclass
│   │   ├── vwap_breakout.py         # VWAP cross + volume spike → +20 pts
│   │   ├── rsi_momentum.py          # RSI cross 55 + EMA alignment → +15 pts
│   │   ├── bullish_engulfing.py     # Engulfing candle near VWAP → +15 pts
│   │   ├── opening_range.py         # First 15m breakout + OI → +15 pts
│   │   └── oi_buildup.py            # Call OI buildup + put unwind → +25 pts
│   ├── signals/
│   │   ├── generator.py             # Pipeline: strategies → confidence → Signal DB row
│   │   ├── confidence.py            # Scoring engine → ConfidenceResult
│   │   ├── strike_selector.py       # Strike + expiry selection
│   │   └── lifecycle.py             # evaluate_signal_tick, expire_eod_signals
│   ├── news/
│   │   ├── fetcher.py               # RSS feed fetcher (Moneycontrol, ET, NSE)
│   │   └── sentiment.py             # VADER classification → BULLISH/BEARISH/NEUTRAL
│   ├── alerts/
│   │   └── telegram.py              # send_signal_alert, send_text_alert
│   ├── analytics/
│   │   └── engine.py                # get_overall_stats, get_reason_accuracy, get_regime_performance
│   └── utils/
│       ├── market_hours.py          # is_market_open, can_generate_signals, is_eod, now_ist
│       └── regime.py                # detect_regime (TRENDING / SIDEWAYS)
└── tools/
    └── backtest.py                  # Standalone backtesting script (not a service)
```

---

## Makefile Commands (Always Use These)
```
make dev          Start Docker infra + uvicorn on :8000 (with --reload)
make stop         Kill uvicorn + stop Docker containers
make status       Health check + open signals count
make trigger      Force-generate signals using trending mock data (for testing)
make evaluate     Fast-forward 60 ticks → resolves open signals (for testing)
make debug        Show all strategy evaluations for NIFTY with real data
make analytics    Overall win rate + P&L + by_reason + by_regime
make report       Today's daily report (live signals only)
make report DATE=YYYY-MM-DD   Specific date report
```

---

## All API Endpoints
```
GET  /health                          Mode (live/mock), env
GET  /auth/login                      Upstox OAuth login page
GET  /auth/callback                   OAuth callback — saves token, starts WebSocket
GET  /signals                         List recent signals (limit, state filters)
GET  /signals/open                    All currently OPEN signals
GET  /signals/daily-report            Daily report (date, include_mock params)
GET  /analytics                       Overall + by_reason + by_regime stats
POST /trigger/signal-engine           Manual trigger (force=true bypasses market hours, uses mock data)
POST /trigger/evaluate-signals        Evaluate open signals (ticks=60 fast-forward)
POST /trigger/test-signal             Send test Telegram alert
GET  /debug/strategies/{symbol}       ⚠️ OVERWRITES buffer with mock candles — do NOT call in live session
GET  /debug/real-strategies/{symbol}  Evaluate strategies on real candle buffer (safe to call anytime)
GET  /debug/live-prices               Show current LIVE_PRICES dict from WebSocket
```

---

## Mode: Live vs Mock
The system automatically detects mode on startup:
- `UPSTOX_ACCESS_TOKEN` is set in `.env` → **Live mode**: WebSocket starts, real prices flow
- `UPSTOX_ACCESS_TOKEN` is empty → **Mock mode**: fake candles seeded, scheduler uses simulated ticks

`USE_MOCK = not bool(settings.upstox_access_token)` — evaluated once at startup in `scheduler.py`.

**Important**: Changing from mock → live requires a server restart. Set the token in `.env` first, then `make stop && make dev`.

---

## Signal Source Tagging
Every signal in the DB has a `source` column:
- `"live"` — generated from real Upstox WebSocket data (default)
- `"mock"` — generated via `POST /trigger/signal-engine?force=true`

`make report` filters to `source="live"` by default. Pass `include_mock=true` to see all.

---

## WebSocket Architecture
- URL: `wss://api.upstox.com/v3/feed/market-data-feed` (v3, NOT v2)
- Auth: `Authorization: Bearer <token>` header
- Subscription: binary frame (JSON encoded as UTF-8 bytes), mode `"ltpc"`
- Messages: binary protobuf frames decoded via `MarketDataFeedV3_pb2.FeedResponse.FromString(raw)`
- SSL: must use `ssl.create_default_context(cafile=certifi.where())` on macOS
- Instruments: `["NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank"]`
- Symbol mapping: `"NSE_INDEX|Nifty 50"` → `"NIFTY"`, `"NSE_INDEX|Nifty Bank"` → `"BANKNIFTY"`
- LTP path for indices (ltpc mode): `feed_data["ltpc"]["ltp"]`
- LTP path for indices (full mode): `feed_data["fullFeed"]["indexFF"]["ltpc"]["ltp"]`
- Live prices stored in `LIVE_PRICES` dict in `websocket_client.py`, read via `get_live_price(symbol)`
- Auto-reconnects every 5 seconds on disconnect
- Started as `asyncio.create_task(ws_client.connect())` in FastAPI lifespan
- **Candle persistence**: `process_tick` returns finalized candle dict when a 5-min window closes; `_save_candle_to_db` immediately persists it to `candles` table via `INSERT ... ON CONFLICT DO NOTHING`

---

## Scheduler Jobs
| Job | Trigger | What it does |
|---|---|---|
| signal_engine | Every 5min, Mon-Fri 9:15-15:15 IST | Fetch candles → run strategies → generate signal → Telegram |
| signal_evaluator | Every 1min (mock: always, live: market hours) | Check SL/target hit for open signals |
| news_fetcher | Every 15min | Fetch RSS feeds, cache in `_latest_news` |
| morning_startup | 9:15 IST Mon-Fri | Clear buffers, seed candles, send "Market Open" alert |
| eod_expire | 15:30 IST Mon-Fri | Expire all OPEN signals, clear buffers, send EOD P&L summary |
| squareoff_warning_1 | 3:10 PM Mon-Fri | Warn about OPEN signals — live P&L + "Mark as Sold" button |
| squareoff_warning_2 | 3:20 PM Mon-Fri | Final square-off warning (10 min to close) |
| telegram_polling | Every 10s | Polls Telegram for inline button taps → marks signal USER_CLOSED |

---

## Database Schema
```
signals
  id, symbol, direction (CALL/PUT), strike, expiry, entry, stop_loss, target,
  confidence (int), reasons (JSON), regime (TRENDING/SIDEWAYS),
  capital_required, suggested_lots, source ("live"/"mock"),
  signal_context (JSONB) — snapshot at signal time: signal_time, hour, minute, rsi,
    vwap_distance_pct, atr, pcr (real NSE EOD), strategies_fired
  state (OPEN/TARGET_HIT/SL_HIT/EXPIRED),
  created_at, evaluated_at

signal_outcomes
  id, signal_id (FK), mfe, mae, result, pnl, evaluated_at

strategy_results
  id, signal_id (FK), strategy_name, contributed_points, fired (bool), timestamp

news_events
  id, headline, source, sentiment, score, symbol, url, published_at, fetched_at

market_snapshots
  id, symbol, price, call_oi, put_oi, iv_percentile, regime, timestamp

candles
  id, symbol, timeframe, open, high, low, close, volume, timestamp
```

**DB migrations**: handled in `database.py → create_tables()` using `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` and `CREATE UNIQUE INDEX IF NOT EXISTS`. No Alembic. Always use this pattern for schema changes on existing tables.

**Candle persistence**: Live 5-minute candles are written to the `candles` table as they close. Unique index `uq_candles_symbol_timeframe_ts` on `(symbol, timeframe, timestamp)` prevents duplicates. On server restart, today's candles are loaded from DB first (no network call), then previous days are fetched from Upstox API.

---

## Confidence Scoring Formula
| Strategy | Points | Condition |
|---|---|---|
| OI Buildup | +25 | Call or put OI change >1% with price confirmation (live: intraday Upstox; backfill: skipped) |
| VWAP Breakout | +20 | Price crosses above VWAP + volume spike >1.5x (volume check skipped for zero-volume indices) |
| RSI Momentum | +15 | RSI crosses above 55 within last 5 candles (lookback=5) + EMA9 > EMA21 > EMA50 |
| Opening Range Breakout | +15 | Price breaks first-15m high/low (volume check skipped for zero-volume indices) |
| Positive Sentiment | +10 | VADER compound > 0.05 on relevant news |
| **Minimum to fire** | **60** | Score is normalized to 0-100 — 60 means same quality bar in all modes |

**Note:** BullishEngulfing strategy removed — backtested at 14.3% WR vs 33.3% break-even.

**Confidence normalization (confidence.py):**
Score is normalized to 0-100 as `raw_score / max_possible × 100`. Max possible is computed from only the strategies actually evaluated (in `strategy_signals`) and sentiment only when `sentiment_label is not None`. At least 2 strategies must agree or signal is blocked. This keeps the 60-point threshold meaningful regardless of mode:
- Backfill (VWAP+RSI+ORB evaluated, max=50): RSI+ORB (30pts) = 60% → fires; VWAP+RSI (35pts) = 70% → fires
- Live (all 4 + possible sentiment, max=75): needs 45pts = 3 price-action strategies
- SIDEWAYS (only RSI available, no OI): RSI alone = 1 strategy → blocked (min 2 required)

**OI strategy behaviour by mode:**
- **Backfill/historical**: `oi_data=None` — OI strategy skipped entirely. EOD day-over-day OI has wrong granularity for intraday signals and was found to hurt WR (31.9% vs 36.5% without it).
- **Live trading**: Upstox options chain gives real-time intraday OI — strategy fires normally. True OI signal quality unknown until live data accumulates.
- **signal_context**: always captures real NSE EOD PCR (from `data/nse_oi/`) for post-hoc analysis regardless of mode.

**Real market calibration notes:**
- NSE index instruments (NIFTY/BANKNIFTY) have zero volume in Upstox — volume checks are bypassed
- `rsi_crossed_above` uses lookback=5 (25 min window) so RSI cross aligns with later VWAP breakout
- On a sell-off day (market opens high, falls) ORB fires PUT; on breakout days all 3 CALL strategies align
- **Strategies fire on crossover moment only** — `vwap_breakout/breakdown` and `rsi_crossed_above/below` detect the single candle where the cross happens. If price is already below VWAP at server start, no PUT signal fires until a fresh cross. On days with a gap-down open or early breakdown, signals may fire at 9:20–9:30 AM only; no further signals until a new crossover.

---

## Backtesting Research Findings (6-month dataset, Nov 2025 – May 2026)

### OI Discovery (May 2026) — critical finding
**Fake OI was inflating all previous backtest results by ~8% WR.**

| Config | Signals | WR | Notes |
|---|---|---|---|
| Fake OI (old baseline) | 562 | 44.8% | OI always aligned with price — circular, not real |
| Real NSE EOD OI | 150 | 31.9% | EOD day-over-day OI disagrees with price → adds noise |
| No OI (old normalization bug) | 97 | 36.5% | max_possible included unavailable sentiment+strategies → fewer signals |
| **No OI (corrected normalization)** | **364** | **44.8%** | **Honest baseline — min 2 strategies, correct max_possible** |

**Conclusion:** Real NSE EOD OI data has wrong granularity for intraday signals. The old 97-signal baseline had a normalization bug where sentiment (10pts) and un-evaluated strategies inflated max_possible, blocking signals. With correct normalization: 364 signals at **44.8% honest WR** (wins / (wins+losses+expired)) — strong edge above 33.3% break-even.

True OI value will only be known once live Upstox intraday options chain data accumulates.

### Real OI data (data/nse_oi/)
- **253 days downloaded**: May 2025 – May 11 2026 (NSE F&O UDiFF Bhavcopy)
- **Script**: `scripts/download_nse_oi.py` — re-runnable to extend coverage
- **Module**: `app/market_data/real_oi.py` — loads day-over-day OI for signal_context PCR
- **Not used for strategy evaluation** — only for signal_context enrichment (PCR column)

### Honest backtest baseline (price action only, no OI, correct normalization)
**364 signals, 44.8% WR, Nov 2025 – May 2026**
163 wins, 156 losses, 45 expired. Config: VWAP=20, RSI=15, ORB=15, OI=skipped, min_confidence=60 (normalized, min 2 strategies)

### Monthly WR breakdown (price action only)
| Month | WR | Notes |
|---|---|---|
| Dec 2025 | ~20% | **Danger zone — year-end thin liquidity, FII rebalancing** |
| Feb–Mar 2026 | ~55–60% | Strong trending period |
| Nov, Jan, Apr | ~35–45% | Normal — marginal edge |

### R:R ratio analysis
Current 2×ATR target has highest edge above break-even. Do not change without re-backtesting.

### CALL vs PUT direction bias (Nov 2025–May 2026, bearish market)
- CALL: ~37% WR | PUT: ~48% WR — regime dependent, not structural.

### Circuit breaker (scheduler.py)
- `_consecutive_losses`: per-symbol gate — skip symbol after 2 consecutive SL_HITs
- `_daily_losses_total`: global gate — stop ALL signals after 3 SL_HITs in a day
- Both reset at 9:15 AM morning_startup_job
- Wipeout days capped at 3 losses instead of 5 (saves ~2 bad trades per bad day)

### Backfill endpoint parameters (for strategy research)
`POST /trigger/backfill` accepts:
- `start_date`, `end_date` — explicit date range (overrides `weeks`)
- `min_confidence` — override confidence threshold
- `points_vwap`, `points_rsi`, `points_oi`, `points_orb` — per-strategy weight overrides
- `target_multiplier`, `sl_multiplier` — R:R ratio overrides (default: target=2.0, sl=1.0)
- `signals_per_day` — max signals per trading day (default 10)

---

## Strike & Expiry Selection
- Confidence 65–75% → ATM strike
- Confidence 75–85% → 1 strike OTM
- Confidence >85% → 2 strikes OTM
- Strike intervals: NIFTY = 50, BANKNIFTY = 100
- Expiry: nearest weekly if >2 days remain, else next weekly
- NIFTY weekly expiry = Thursday | BANKNIFTY weekly expiry = Wednesday

---

## Risk & Position Sizing
- Capital base: `CAPITAL_BASE` (default ₹5,00,000)
- Max per trade: 10% of capital = ₹50,000
- Risk per trade: 1.5% of capital = ₹7,500
- Lot sizes: NIFTY = 25, BANKNIFTY = 15
- Premium estimate: `ATR × 1.2` (until live options chain pricing available)
- Capital = premium × lots × lot_size (NOT notional)
- `suggested_lots = min(lots_by_risk, lots_by_capital)`
- Max 2 concurrent OPEN signals per symbol per direction

---

## Signal Lifecycle
```
OPEN → TARGET_HIT   (price >= target)
     → SL_HIT       (price <= stop_loss)
     → EXPIRED      (auto at 15:30 IST if still OPEN)
     → USER_CLOSED  (user tapped "Mark as Sold" on Telegram inline button)
```
**Win rate denominator**: wins + losses + expired + user_closed. EXPIRED/USER_CLOSED are real trades with theta decay — excluding them overstates WR.
- Evaluator runs every minute in mock mode (always), every minute in live mode during market hours
- P&L recorded in `signal_outcomes` on close: `(exit - entry) × lots` for CALL, reversed for PUT

---

## Market Regime Detection
- ATR >= 70% of its 20-period average → TRENDING → all 5 strategies active
- ATR < 70% → SIDEWAYS → VWAP breakout + opening range strategies suppressed
- Regime tagged on every signal in `regime` column

---

## Mock Mode Details (For Testing)
`generate_mock_candles(symbol, n=80, trending=True)` produces:
- Candles 1–78: mean-reverting flat walk (RSI → ~50, price anchored near VWAP)
- Candle 79 (i=2): forced -0.3% bearish → RSI dips, sets up engulfing
- Candle 80 (i=1): forced +2.5% bullish, 4–5× volume → all 5 strategies fire

`get_mock_spot_price(symbol, bullish_bias=True)` drifts +0.05% per tick for testing lifecycle.

`make trigger` always uses trending mock data regardless of live/mock mode. Signals get `source="mock"`.

---

## Daily Workflow (Production)
```
Before 9:15 IST:
  cd /Users/shrego-persnol/Documents/fintech/trading-engine
  make dev
  Open http://localhost:8000/auth/login in browser → re-authenticate Upstox

During market hours:
  Watch Telegram for signal alerts.
  Paper trade manually.
  ⚠️ DO NOT restart the server mid-session — restarts wipe the in-memory tick buffer
     for the current candle (the one currently building). Completed candles are safe
     in DB, but the partial candle since the last 5-min boundary is lost.

After market close:
  make report                   # today's live signals + outcomes
  make analytics                # cumulative win rate
  Ctrl+C to stop server

Note: Upstox token validity: observed to survive overnight as of May 2026 (may be
longer-lived than advertised). The 8:45 AM token_check_job sends a Telegram alert
if expired. Re-authenticate via http://localhost:8000/auth/login.
```

---

## Current Phase Status
### Phase 1 — Core Signal Engine — COMPLETE ✓
- [x] Docker Compose (PostgreSQL + Redis)
- [x] FastAPI + DB models
- [x] Upstox v3 WebSocket client with protobuf decoding
- [x] 5-minute candle processor
- [x] All 5 indicators (RSI, VWAP, EMA, ATR, Volume)
- [x] All 5 strategies
- [x] Signal generator + confidence scoring
- [x] Strike + expiry selector
- [x] Telegram alerts
- [x] Signal lifecycle (OPEN → TARGET_HIT / SL_HIT / EXPIRED)
- [x] Analytics engine (overall, by_reason, by_regime)
- [x] Mock data mode for testing
- [x] source column (live/mock) on all signals
- [x] Daily report endpoint + `make report` command
- [x] GitHub repo (private, all changes pushed)
- [x] Makefile for single-command workflow

### Phase 2 — Paper Trading Validation — IN PROGRESS
- [x] Strategy calibration for real index market data (volume=0 fixes, RSI lookback)
- [x] Historical simulation (`make simulate DATE=YYYY-MM-DD`) — verified working
- [x] 6-month backtest — honest baseline: **97 signals, 36.5% WR** (price action only, no OI)
- [x] OI discovery: fake OI was inflating results — switched to real NSE data then disabled for backfill
- [x] 253 days of real NSE EOD OI downloaded (`data/nse_oi/`, `scripts/download_nse_oi.py`)
- [x] signal_context JSONB on every signal — captures RSI, VWAP dist%, ATR, PCR, strategies_fired, hour
- [x] Analytics: by_hour + by_strategy_combo endpoints for accuracy improvement
- [x] Circuit breaker (3 SL_HITs/day stops all signals) + per-symbol consecutive loss gate
- [x] PUT/CALL support across all strategies (direction-aware SL/target/evaluation)
- [x] Backfill endpoint with full grid-search parameter overrides
- [x] Upstox token active — system running in live mode
- [x] Candle seeding fixed — seeds 3 previous weekdays + today on startup (80+ candles ready from minute 1)
- [x] Live candle persistence — every finalized 5m candle saved to DB; restart recovers today's candles from DB instantly
- [x] Confidence normalized to 0-100 based on available strategies — threshold stays at 60 in all modes
- [ ] Accumulate 50–100 real live signals (with real intraday OI from Upstox)
- [ ] Analyse by_hour + by_strategy_combo once 50+ live signals collected

### Phase 3 — Analytics Dashboard (not started)
### Phase 4 — Strategy Optimization (not started)
### Phase 5 — ML Layer (not started)
### Phase 6 — Productization + SEBI Compliance (not started)

---

## Known Issues / Next Up
1. **Token expiry unclear** — Token has NOT expired at midnight (May 12 2026). Upstox may have changed to longer-lived tokens. The 8:45 AM `token_check_job` will alert on Telegram if it ever expires.
2. **December seasonal pattern** — Dec historically shows ~20% WR (well below break-even). Year-end thin liquidity, FII rebalancing. Consider skipping December or halving position size.
3. **OI signal quality unknown** — Backfill uses no OI. First real test of OI strategy quality is live trading with Upstox intraday options chain. Watch `by_strategy_combo` analytics once 50+ live signals accumulate.
4. **signal_context hour/minute null in backfill** — Historical candles use RangeIndex; timestamp extracted from column. Works correctly for live WebSocket candles (DatetimeIndex).
5. **`/debug/strategies/{symbol}` overwrites live candle buffer** — This endpoint calls `generate_mock_candles()` which replaces real data. Never call it during market hours. Use `/debug/real-strategies/{symbol}` instead.
6. **Partial candle lost on restart** — The candle currently being built from live ticks (not yet closed) is lost on server restart. Completed candles are safe in DB. Impact: ≤5 minutes of tick data lost.

---

## Key Constraints (Never Violate)
1. No auto-trading — ever in early phases
2. No self-modifying strategies
3. No ML until Phase 5 is explicitly started
4. All strategy threshold changes require manual approval
5. Never commit `.env`
6. Signals only generated during market hours (09:15–15:30 IST)
7. Max 2 open signals per symbol at any time
8. `make report` must always default to live signals only
9. EXPIRED and USER_CLOSED both count as losses in win rate denominator — never exclude them

---

## Future Features (Not Building Now)
- IV-aware strategies
- Greeks (Delta, Theta, Gamma, Vega)
- PCR and Max Pain analysis
- Advanced OI analytics
- Machine learning confidence scoring
- Frontend analytics dashboard
- Backtesting engine (proper, with historical OI)
- SEBI RA registration + monetization
