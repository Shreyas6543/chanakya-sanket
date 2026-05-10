# Chanakya — Trading Intelligence Engine | Claude Project Context

## IMPORTANT RULE
**Every time a decision is made, a config is changed, a module is added, or an architecture changes — update this file immediately. This file is the single source of truth for the project.**

---

## Product Name
**Chanakya Sanket** — Trading Intelligence Engine
"Chanakya" = ancient Indian master strategist and economist.
"Sanket" = signal/indication in Sanskrit.
Together: *Chanakya's Signal* — the strategic signal.
Tagline: *Edge through knowledge, not luck.*
Bot handle: @ChanakaSanketBot
Repo/code name: chanakya-sanket

## Project Overview
An explainable AI-assisted intraday options trading intelligence backend system.
- Backend only. No frontend in Phase 1.
- No auto-trading. Ever in early phases.
- No ML initially — rule-based strategies first.
- Signals require manual approval for optimization changes.

---

## Business Context
- Personal use first → paper trading validation → small capital live → productize
- Target market: Indian retail intraday options traders
- Focus instruments: NIFTY and BANKNIFTY (NSE F&O)
- Timeframe: 5-minute candles
- SEBI positioning: "trading intelligence & analytics platform" — NOT a signal service
- No paid subscriptions until SEBI Research Analyst compliance is understood

---

## Tech Stack (Decided)
| Layer | Choice | Reason |
|---|---|---|
| Language | Python 3.11+ | Ecosystem for finance/data |
| API Framework | FastAPI | Async, fast, clean |
| Database | PostgreSQL | Reliable, structured signal history |
| Cache | Redis | Real-time data caching |
| Scheduler | APScheduler | Lightweight, in-process |
| Containerization | Docker Compose | Local + VPS portability |
| Market Data | Upstox v2 API | Free API, WebSocket v2, NSE F&O support |
| Alerts | Telegram Bot API | Free, instant |
| News Sentiment | VADER (Python) | Free, no API key, works out of the box |
| Backtesting | tools/backtest.py | Separate script, not a core service |

---

## Broker Decision: Upstox
- Chosen over Zerodha because: Free API (Zerodha charges ₹2000/month for Kite Connect)
- Upstox v2 supports WebSocket for live market feed
- Supports NSE F&O options chain data
- User must have Upstox account with API access enabled
- Credentials: UPSTOX_API_KEY, UPSTOX_API_SECRET, UPSTOX_ACCESS_TOKEN in .env

---

## Project Structure
```
trading-engine/
├── CLAUDE.md                        # This file — always update
├── .env                             # Secrets — never commit
├── .env.example                     # Template — commit this
├── .gitignore
├── docker-compose.yml               # PostgreSQL + Redis
├── requirements.txt
├── app/
│   ├── main.py                      # FastAPI entry point
│   ├── config.py                    # All settings via pydantic-settings
│   ├── db/
│   │   ├── database.py              # SQLAlchemy async engine
│   │   └── models.py                # All DB models
│   ├── market_data/
│   │   ├── websocket_client.py      # Upstox WebSocket feed
│   │   ├── candle_processor.py      # Build 5m candles from ticks
│   │   └── options_chain.py         # Poll OI data from Upstox REST
│   ├── indicators/
│   │   ├── rsi.py                   # RSI calculation
│   │   ├── vwap.py                  # VWAP calculation
│   │   ├── ema.py                   # EMA calculation
│   │   ├── atr.py                   # ATR + regime detection
│   │   └── volume.py                # Volume spike detection
│   ├── strategies/
│   │   ├── base.py                  # Abstract base strategy
│   │   ├── vwap_breakout.py
│   │   ├── rsi_momentum.py
│   │   ├── bullish_engulfing.py
│   │   ├── opening_range.py
│   │   └── oi_buildup.py
│   ├── signals/
│   │   ├── generator.py             # Combine strategies → signal
│   │   ├── strike_selector.py       # Strike + expiry selection
│   │   ├── confidence.py            # Confidence scoring engine
│   │   └── lifecycle.py             # Signal state machine
│   ├── news/
│   │   ├── fetcher.py               # RSS feed fetcher
│   │   └── sentiment.py             # VADER-based classification
│   ├── alerts/
│   │   └── telegram.py              # Telegram bot sender
│   ├── analytics/
│   │   └── engine.py                # Reason-wise accuracy, metrics
│   └── utils/
│       ├── market_hours.py          # NSE hours + holiday calendar
│       ├── regime.py                # Trending vs sideways detection
│       └── health.py                # Health check endpoints
└── tools/
    └── backtest.py                  # Standalone backtesting script
```

---

## Architecture Decisions

### Signal Lifecycle States
```
OPEN → TARGET_HIT
     → SL_HIT
     → EXPIRED (auto at market close 15:30 IST)
```

### Strike Selection Rules (V1)
- Confidence 65–75% → ATM strike
- Confidence 75–85% → 1 strike OTM
- Confidence >85% → optional deeper OTM (config flag)

### Expiry Selection Rules (V1)
- Use nearest weekly expiry if more than 2 days remain
- Use next weekly expiry if expiry is within 2 days
- NIFTY weekly expiry = Thursday | BANKNIFTY weekly expiry = Wednesday

### Confidence Scoring Formula (V1)
| Reason | Points |
|---|---|
| VWAP breakout | +20 |
| OI buildup | +25 |
| Bullish engulfing | +15 |
| Volume spike | +15 |
| EMA alignment | +15 |
| Positive sentiment | +10 |
| **Minimum to generate signal** | **65** |

### Market Regime Detection
- ATR < 70% of its 20-period average → SIDEWAYS → suppress breakout strategies
- ATR >= 70% → TRENDING → all strategies active

### Risk & Position Rules
- Capital base: configurable via CAPITAL_BASE in .env (default: 500000)
- Max capital deployed per trade: 10% of capital base (MAX_CAPITAL_PER_TRADE_PCT)
- Risk per trade (SL distance): 1.5% of capital base
- Lot sizing: min(lots_by_risk, lots_by_capital_cap) — respects BOTH limits
- Lot sizes: NIFTY = 25, BANKNIFTY = 15
- Capital required = option PREMIUM × lots × lot_size (NOT notional/spot × lots × lot_size)
- Premium estimated as ATR × 1.2 until live options chain data is available
- Max concurrent open signals per symbol: 2
- Max daily loss: 5% of capital base
- If same symbol already has OPEN signal in same direction → suppress new signal

### Signal Evaluator Architecture
- Uses the SAME WebSocket feed as market data engine (no separate polling)
- Continuously evaluates SL/target conditions on every tick
- Tracks MFE (Max Favorable Excursion) and MAE (Max Adverse Excursion)
- Auto-expires all OPEN signals at 15:30 IST

### News Sentiment (V1)
- Sources: Moneycontrol RSS, Economic Times Markets RSS, NSE circular feed
- Library: VADER (vaderSentiment)
- Classification: compound score > 0.05 = BULLISH, < -0.05 = BEARISH, else NEUTRAL
- Mapped to relevant symbol before contributing to signal confidence

### Historical Data Strategy
- Candle data: Upstox historical API (free, available)
- OI data: No free historical source — build proprietary dataset by recording live OI daily from day 1
- OI-based backtesting will be possible only after accumulating live data

---

## Database Schema (Core Tables)
- **candles**: symbol, timeframe, open, high, low, close, volume, timestamp
- **signals**: symbol, direction, strike, expiry, entry, sl, target, confidence, reasons, regime, state, created_at, evaluated_at
- **signal_outcomes**: signal_id, mfe, mae, result, pnl, evaluated_at
- **news_events**: headline, source, sentiment, score, symbol, timestamp
- **market_snapshots**: symbol, price, oi, iv_percentile, regime, timestamp
- **strategy_results**: strategy_name, signal_id, contributed_points, timestamp

---

## API Keys Needed (User Must Configure)
1. **Upstox**: Create app at upstox.com/developer → get API key + secret
2. **Telegram**: Message @BotFather → /newbot → get bot token + your chat ID

---

## Market Hours
- Market open: 09:15 IST
- Market close: 15:30 IST
- Pre-market (avoid signals): 09:00–09:15
- No signals generated outside market hours
- NSE holidays: integrated via holiday calendar utility

---

## Current Build Phase
**Phase 1 — Core Signal Engine**
- [ ] Docker Compose (PostgreSQL + Redis)
- [ ] FastAPI skeleton
- [ ] DB models + migrations
- [ ] Upstox WebSocket client
- [ ] 5m candle processor
- [ ] Indicator calculations (RSI, VWAP, EMA, ATR, Volume)
- [ ] Strategy implementations
- [ ] Signal generator + confidence scoring
- [ ] Strike + expiry selector
- [ ] Telegram alert sender
- [ ] Signal lifecycle tracker
- [ ] Outcome evaluator
- [ ] Basic analytics engine
- [ ] Health check endpoints

**Phase 2 — Paper Trading Validation** (not started)
**Phase 3 — Analytics Dashboard** (not started)
**Phase 4 — Strategy Optimization** (not started)
**Phase 5 — ML Layer** (not started)
**Phase 6 — Productization + SEBI Compliance** (not started)

---

## Future Features (Not Building Now)
- IV-aware strategies
- Greeks (Delta, Theta, Gamma, Vega)
- PCR and Max Pain analysis
- Advanced OI analytics
- Machine learning confidence scoring
- Frontend dashboard
- Backtesting engine (proper, with historical OI)
- SEBI RA registration + monetization

---

## Key Constraints (Never Violate)
1. No auto-trading
2. No self-modifying strategies
3. No ML until Phase 5
4. All optimization changes require manual approval
5. Never commit .env file
6. Signals only generated during market hours (09:15–15:30 IST)
7. Max 2 open signals per symbol at any time
