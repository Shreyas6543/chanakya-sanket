# Chanakya Sanket — Trading Intelligence Engine | Claude Project Context

## RULES FOR CLAUDE (READ FIRST)
1. **Update this file immediately** after every decision, config change, module addition, or architecture change. This is the single source of truth.
2. **Read this entire file before touching any code.** Never make assumptions — check here first.
3. **Never commit `.env`**. It contains live secrets.
4. **Never add auto-trading logic.** The system only generates signals. Humans execute.
5. **Never add ML** until Phase 5 is explicitly started.
6. **Always run in the project venv**: `.venv/bin/python3` and `.venv/bin/uvicorn`. Never use system Python.
7. **Always use `make` commands** for dev workflow. See the Makefile section below.
8. **After every code change**, commit and push to GitHub using conventional commit messages.
9. **Before suggesting architecture changes**, check if a simpler fix exists first.
10. **The DB already has real data**. Never drop tables or run destructive migrations without explicit user approval.

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
POST /trigger/signal-engine           Manual trigger (force=true bypasses market hours)
POST /trigger/evaluate-signals        Evaluate open signals (ticks=60 fast-forward)
POST /trigger/test-signal             Send test Telegram alert
GET  /debug/strategies/{symbol}       Debug all strategies on current candle data
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

---

## Scheduler Jobs
| Job | Trigger | What it does |
|---|---|---|
| signal_engine | Every 5min, Mon-Fri 9:15-15:15 IST | Fetch candles → run strategies → generate signal → Telegram |
| signal_evaluator | Every 1min (mock: always, live: market hours) | Check SL/target hit for open signals |
| news_fetcher | Every 15min | Fetch RSS feeds, cache in `_latest_news` |
| morning_startup | 9:15 IST Mon-Fri | Clear buffers, seed candles, send "Market Open" alert |
| eod_expire | 15:30 IST Mon-Fri | Expire all OPEN signals, clear buffers, send EOD P&L summary |

---

## Database Schema
```
signals
  id, symbol, direction (CALL/PUT), strike, expiry, entry, stop_loss, target,
  confidence (int), reasons (JSON), regime (TRENDING/SIDEWAYS),
  capital_required, suggested_lots, source ("live"/"mock"),
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

**DB migrations**: handled in `database.py → create_tables()` using `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. No Alembic. Always use this pattern for schema changes on existing tables.

---

## Confidence Scoring Formula
| Strategy | Points | Condition |
|---|---|---|
| OI Buildup | +25 | Call OI up >5%, Put OI down >5% |
| VWAP Breakout | +20 | Price crosses above VWAP + volume spike >1.5x |
| RSI Momentum | +15 | RSI crosses above 55 + EMA9 > EMA21 > EMA50 |
| Bullish Engulfing | +15 | Engulfing candle within 0.2% of VWAP |
| Opening Range Breakout | +15 | Price breaks first-15m high with volume |
| Positive Sentiment | +10 | VADER compound > 0.05 on relevant news |
| **Minimum to fire** | **65** | Configurable via `MIN_CONFIDENCE_SCORE` in .env |

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
OPEN → TARGET_HIT  (price >= target)
     → SL_HIT      (price <= stop_loss)
     → EXPIRED     (auto at 15:30 IST if still OPEN)
```
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

During market hours:
  Watch Telegram for signal alerts.
  Paper trade manually.

After market close:
  make report                   # today's live signals + outcomes
  make analytics                # cumulative win rate
  Ctrl+C to stop server

Note: Upstox token expires daily at midnight.
Re-authenticate every morning: open http://localhost:8000/auth/login in browser.
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
- [ ] Historical candle seeding on startup (currently empty buffer on fresh start)
- [ ] Daily token auto-refresh (token expires at midnight, manual re-login required)
- [ ] Accumulate 50–100 real live signals over 4–6 weeks
- [ ] Review by_reason analytics to identify strongest strategies

### Phase 3 — Analytics Dashboard (not started)
### Phase 4 — Strategy Optimization (not started)
### Phase 5 — ML Layer (not started)
### Phase 6 — Productization + SEBI Compliance (not started)

---

## Known Issues / Next Up
1. **Historical candle seeding** — On startup in live mode, candle buffer is empty. Strategies need 50+ candles. Upstox historical API is free and available — seed on startup.
2. **Daily token refresh** — Upstox access tokens expire at midnight. Current flow: open browser → `/auth/login` → re-authenticate manually. Should be simplified.

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
