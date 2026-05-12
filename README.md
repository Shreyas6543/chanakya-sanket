# Chanakya Sanket — Trading Intelligence Engine

> *Edge through knowledge, not luck.*

Rule-based intraday options signal engine for NIFTY & BANKNIFTY. Streams live Upstox prices → builds 5-min candles → runs strategies → sends Telegram alerts. No auto-trading. No ML. Backend only.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.12 | `python3 --version` |
| Docker Desktop | Must be running before `make dev` |
| Upstox account | Free API — no monthly charge |
| Telegram bot | Create via @BotFather, get chat ID |

---

## First-Time Setup

```bash
# 1. Clone and enter project
cd /Users/shrego-persnol/Documents/fintech/trading-engine

# 2. Create virtual environment
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3. Copy env template and fill in your credentials
cp .env.example .env
# Edit .env — add Upstox keys, Telegram token, leave UPSTOX_ACCESS_TOKEN blank for now

# 4. Start everything
make dev
```

---

## Daily Workflow

### Before 9:15 AM
```bash
make dev                          # Start Docker infra + API server on :8000
```
Then open `http://localhost:8000/auth/login` in your browser → log in to Upstox.
This saves your access token and starts the live WebSocket feed.

### During Market Hours (9:15 AM – 3:30 PM)
- Watch Telegram for signal alerts
- Paper trade manually based on alerts
- ⚠️ **Do NOT restart the server mid-session** — you'll lose the partial current candle

### After Market Close
```bash
make report                       # Today's signals + outcomes
make analytics                    # Cumulative win rate + P&L
Ctrl+C                            # Stop the server
```

---

## Make Commands

| Command | What it does |
|---|---|
| `make dev` | Start PostgreSQL + Redis + API server on :8000 |
| `make stop` | Kill server + stop Docker containers |
| `make status` | Health check + count of open signals |
| `make trigger` | Force-generate signals using mock trending data |
| `make evaluate` | Fast-forward 60 price ticks → resolves open signals |
| `make debug` | Show all strategy evaluations for NIFTY |
| `make analytics` | Win rate + P&L + breakdown by hour/strategy/regime |
| `make report` | Today's live signal report |
| `make report DATE=2026-05-11` | Report for a specific date |
| `make simulate DATE=2026-05-11` | Replay one real trading day (Upstox historical data) |
| `make simulate DATE=2026-05-11 COUNT=5` | Same, limit to 5 signals |
| `make backfill` | Replay last 6 weeks of trading days |
| `make backfill WEEKS=4` | Replay last 4 weeks |

---

## API Endpoints

### Health & Auth
| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Server status, mode (live/mock) |
| GET | `/auth/login` | Upstox OAuth login page |
| GET | `/auth/callback` | OAuth callback — saves token, starts WebSocket |

### Signals
| Method | Endpoint | Description |
|---|---|---|
| GET | `/signals` | Recent signals (add `?limit=50&state=OPEN`) |
| GET | `/signals/open` | All currently open signals |
| GET | `/signals/daily-report` | Today's report (add `?date=2026-05-11` for specific date) |
| POST | `/signals/{id}/mark-sold` | Mark an open signal as USER_CLOSED (manually squared off) |

### Analytics
| Method | Endpoint | Description |
|---|---|---|
| GET | `/analytics` | Overall WR + P&L + by_hour + by_strategy_combo + by_regime |

### Admin (OI Toggle)
| Method | Endpoint | Description |
|---|---|---|
| GET | `/admin/oi` | OI strategy status, NSE data coverage, snapshots stored |
| POST | `/admin/oi/enable` | Turn OI strategy ON (uses NSE Bhavcopy in backfill, Upstox in live) |
| POST | `/admin/oi/disable` | Turn OI strategy OFF (price action only — default) |

### Manual Triggers
| Method | Endpoint | Description |
|---|---|---|
| POST | `/trigger/signal-engine` | Run signal engine now (add `?force=true` for mock) |
| POST | `/trigger/evaluate-signals` | Evaluate open signals (add `?ticks=60` to fast-forward) |
| POST | `/trigger/simulate` | Simulate one day (add `?date=YYYY-MM-DD&count=10`) |
| POST | `/trigger/backfill` | Full backfill (add `?weeks=6` or `?start_date=...&end_date=...`) |

### Debug (use with caution)
| Method | Endpoint | Description |
|---|---|---|
| GET | `/debug/real-strategies/{symbol}` | Evaluate strategies on live candle buffer (safe anytime) |
| GET | `/debug/strategies/{symbol}` | ⚠️ Overwrites buffer with mock candles — never call in live session |
| GET | `/debug/live-prices` | Show current WebSocket prices |

---

## Signal Flow

```
Upstox WebSocket → 5-min candle → Strategies → Confidence Score → Signal → Telegram
```

**Strategies (and points):**
| Strategy | Points | What it checks |
|---|---|---|
| OI Buildup | 25 | Call/put OI change >1% with price confirmation |
| VWAP Breakout | 20 | Price crosses VWAP + volume spike |
| RSI Momentum | 15 | RSI crosses 55 (lookback 5 candles) + EMA alignment |
| Opening Range Breakout | 15 | Price breaks first-15min high/low |
| Positive Sentiment | 10 | VADER news sentiment > 0.05 |

**Confidence threshold:** 60 (normalized 0–100). Without OI (max 50pts): all 3 price strategies must fire → score = 83. With OI (max 75pts): 3 strategies needed → score = 67.

**Market regime:**
- CPR width < 0.15% of pivot → SIDEWAYS → VWAP + ORB strategies suppressed
- Falls back to ATR check: ATR < 70% of 20-period average → SIDEWAYS

**Circuit breaker:**
- 2 consecutive SL hits on same symbol → that symbol paused for the day
- 3 total SL hits across all symbols → all signals paused for the day
- Both reset at 9:15 AM

**Signal lifecycle:**
```
OPEN → TARGET_HIT   (price >= target)
     → SL_HIT       (price <= stop_loss)
     → EXPIRED      (auto at 3:30 PM if still open)
     → USER_CLOSED  (user tapped "Mark as Sold" on Telegram)
```
EXPIRED and USER_CLOSED both count as losses in the win rate denominator — they represent real theta decay / forced exits, not neutral events.

**Near-expiry alerts (live mode, 3:10 PM + 3:20 PM):**
Telegram sends a warning for every open signal with current unrealized P&L and a **✅ Mark as Sold** inline button. Tap it → signal moves to USER_CLOSED and alerts stop. If you don't tap, it auto-expires at 3:30 PM.

---

## Strike & Expiry Selection

| Confidence | Strike |
|---|---|
| < 75% | ATM (delta ~0.5, best liquidity) |
| ≥ 75% | 1 OTM (CALL = higher strike, PUT = lower strike) |

Expiry: nearest weekly if >3 days remain, else next weekly.
NIFTY = Thursday expiry | BANKNIFTY = Wednesday expiry

---

## Risk Management

| Parameter | Default | Notes |
|---|---|---|
| Capital base | ₹5,00,000 | Set in `.env` as `CAPITAL_BASE` |
| Max per trade | 10% = ₹50,000 | `MAX_CAPITAL_PER_TRADE_PCT` |
| Risk per trade | 1.5% = ₹7,500 | `MAX_RISK_PER_TRADE_PCT` |
| Stop loss | 1× ATR from entry | |
| Target | 2× ATR from entry | |
| Max open signals | 2 per symbol | `MAX_OPEN_SIGNALS_PER_SYMBOL` |

---

## OI Toggle

By default OI is **OFF** (price action only = 42.6% WR baseline on 267 days).

```bash
# Check status
curl http://localhost:8000/admin/oi

# Turn ON (backfill uses NSE Bhavcopy EOD OI)
curl -X POST http://localhost:8000/admin/oi/enable

# Turn OFF (price action only)
curl -X POST http://localhost:8000/admin/oi/disable
```

While running in live mode, OI snapshots (call_oi, put_oi) are automatically saved to the DB every 5 minutes. Over time this builds a real intraday OI history for future backtesting.

---

## Backtest Results (May 2025 – May 2026)

| Config | Signals | Win Rate | Notes |
|---|---|---|---|
| Fake OI | 562 | 44.8% | Inflated — OI circular, always agreed with price |
| Real NSE EOD OI | 150 | 31.9% | EOD granularity wrong for intraday |
| Price action only (baseline) | 97 | 36.5% | Honest, above 33.3% break-even |
| + Zerodha improvements | 564 | **42.6%** | CPR regime + RSI continuation + strike fix |

> **Note on win rate calculation:** EXPIRED and USER_CLOSED signals count as losses in the denominator (`resolved = wins + losses + expired`). Options held to EOD always incur theta decay — they are not neutral events.

**Monthly pattern:** Dec historically ~20% WR (thin liquidity). Feb–Mar best at 55–60%.

---

## Environment Variables (`.env`)

```bash
# Upstox
UPSTOX_API_KEY=...
UPSTOX_API_SECRET=...
UPSTOX_ACCESS_TOKEN=         # Leave blank — filled automatically after /auth/login

# Telegram
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...

# PostgreSQL (defaults work with docker-compose)
POSTGRES_USER=trading
POSTGRES_PASSWORD=trading_secret
POSTGRES_DB=trading_engine
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Trading
CAPITAL_BASE=500000
MIN_CONFIDENCE_SCORE=60      # 0-100 normalized score
```

Full template: `.env.example`

---

## Database Tables

| Table | Contents |
|---|---|
| `signals` | Every signal — direction, strike, expiry, confidence, entry/SL/target, state, signal_context JSON |
| `signal_outcomes` | Closed signal results — MFE, MAE, P&L, outcome |
| `strategy_results` | Which strategies fired per signal and points contributed |
| `candles` | 5-min candles (live candles persisted as they close) |
| `market_snapshots` | Intraday OI snapshots every 5 min (live mode only) |
| `news_events` | RSS headlines with VADER sentiment scores |

---

## Project Structure

```
trading-engine/
├── Makefile                    # All dev commands
├── .env                        # Secrets — NEVER commit
├── .env.example                # Template
├── docker-compose.yml          # PostgreSQL + Redis
├── requirements.txt
├── scripts/
│   ├── run_backfill.py         # Standalone full backfill (runs directly, no HTTP timeout)
│   └── download_nse_oi.py      # Downloads NSE F&O Bhavcopy OI data
├── data/nse_oi/                # 253 days of NSE EOD OI (May 2025 – May 2026)
└── app/
    ├── main.py                 # FastAPI app + all endpoints + _simulate_one_day
    ├── config.py               # All settings via pydantic-settings
    ├── scheduler.py            # APScheduler jobs
    ├── indicators/             # RSI, VWAP, EMA, ATR, Volume, CPR
    ├── strategies/             # VWAP breakout, RSI momentum, Opening range, OI buildup
    ├── signals/                # Generator, confidence scoring, strike selector, lifecycle
    ├── market_data/            # WebSocket client, candle processor, options chain, real OI
    ├── analytics/              # Win rate, P&L, by_hour, by_strategy_combo, by_regime
    ├── ai/                     # Signal filter (claude-agent-sdk, live mode only)
    ├── alerts/                 # Telegram
    └── utils/                  # Market hours, regime detection, OI toggle
```

---

## Common Issues

| Problem | Fix |
|---|---|
| No signals in backfill | Lower `min_confidence` — try 25. Default 60 needs 3+ strategies to fire simultaneously |
| WebSocket not connecting | Token expired — go to `http://localhost:8000/auth/login` |
| `make dev` fails | Docker Desktop not running — start it first |
| Backfill script import error | Starlette version mismatch — run `.venv/bin/pip install "starlette==0.37.2"` |
| Signal only after 1 PM in backfill | Previous-day seed missing — fixed in `_simulate_one_day` (3 prev weekdays seeded) |
| 15:00–15:30 signals blocked | Intentional — 2.4% WR in backtest, hardcoded block |

---

## Key Files for Strategy Changes

Before changing any strategy, indicator, or confidence threshold:
1. Read `LOGIC_CHANGELOG.md` — if a change was tried and reverted, don't repeat it
2. Make the change
3. Add an entry to `LOGIC_CHANGELOG.md`
4. Re-run backfill to measure WR impact
5. Commit

---

## Roadmap

| Phase | Status |
|---|---|
| Phase 1 — Core signal engine | ✅ Done |
| Phase 2 — Paper trading validation | 🔄 In Progress |
| Phase 3 — Analytics dashboard | Not started |
| Phase 4 — Strategy optimization | Not started |
| Phase 5 — ML layer | Not started |
| Phase 6 — SEBI compliance + productization | Not started |
