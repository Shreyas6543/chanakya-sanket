.PHONY: help dev infra stop logs status trigger debug analytics report simulate backfill backfill-full ui

PYTHON := .venv/bin/python3
UVICORN := .venv/bin/uvicorn
API := http://localhost:8000

help:
	@echo ""
	@echo "Chanakya Sanket — Trading Intelligence Engine"
	@echo "---------------------------------------------"
	@echo "  make dev          Start infra + API server"
	@echo "  make infra        Start PostgreSQL + Redis only"
	@echo "  make stop         Stop everything"
	@echo "  make logs         Tail API server logs"
	@echo "  make status       Health check + open signals"
	@echo "  make trigger      Force-generate signals (mock)"
	@echo "  make evaluate     Fast-forward 60 ticks (resolve signals)"
	@echo "  make debug        Debug all strategies for NIFTY"
	@echo "  make analytics    Show win rate + P&L"
	@echo "  make simulate     Replay a date using real Upstox historical candles"
	@echo "  make backfill     Replay past N weeks to build signal history (default 6 weeks)"
	@echo "  make ui           Start analytics dashboard UI on :5173"
	@echo ""

infra:
	docker compose up -d postgres redis
	@echo "Waiting for postgres..."
	@until docker exec trading_postgres pg_isready -U trading -q; do sleep 1; done
	@echo "Infra ready."

dev: infra
	@pkill -f "uvicorn app.main:app" 2>/dev/null || true
	$(UVICORN) app.main:app --port 8000 --reload

stop:
	@pkill -f "uvicorn app.main:app" 2>/dev/null || true
	docker compose stop postgres redis
	@echo "Stopped."

status:
	@curl -s $(API)/health | $(PYTHON) -m json.tool
	@echo ""
	@curl -s $(API)/signals/open | $(PYTHON) -m json.tool

trigger:
	@curl -s -X POST "$(API)/trigger/signal-engine?force=true" | $(PYTHON) -m json.tool

evaluate:
	@curl -s -X POST "$(API)/trigger/evaluate-signals?ticks=60" | $(PYTHON) -m json.tool

debug:
	@curl -s "$(API)/debug/strategies/NIFTY" | $(PYTHON) -m json.tool

analytics:
	@curl -s $(API)/analytics | $(PYTHON) -m json.tool

# Daily report: make report          → today
#               make report DATE=2026-05-11  → specific date
report:
	@curl -s "$(API)/signals/daily-report$(if $(DATE),?date=$(DATE),)" | $(PYTHON) -m json.tool

# Simulate a real trading day using Upstox historical candles
# make simulate                           → today, 10 signals
# make simulate DATE=2026-05-11          → specific date, 10 signals
# make simulate DATE=2026-05-11 COUNT=5  → specific date, 5 signals
simulate:
	@curl -s -X POST "$(API)/trigger/simulate$(if $(DATE),?date=$(DATE)$(if $(COUNT),\&count=$(COUNT),),$(if $(COUNT),?count=$(COUNT),))" | $(PYTHON) -m json.tool

# Backfill past N weeks of real trading days
# make backfill              → 6 weeks back, 5 signals/day
# make backfill WEEKS=4      → 4 weeks back
backfill:
	@echo "Starting backfill — this may take a few minutes..."
	@curl -s -X POST "$(API)/trigger/backfill$(if $(WEEKS),?weeks=$(WEEKS),)" --max-time 600 | $(PYTHON) -m json.tool

ui:
	cd frontend && npm run dev

# Walk-forward backfill — 2-year clean run with adaptive hour filter
# 1. Clears all historical + mock signals (live signals untouched)
# 2. Backfills from oldest OHLCV data (2024-05-13) to today
# 3. Hour filter self-bootstraps: no-op for first ~4 months, then kicks in
# Server must be running: make dev
backfill-full:
	@echo "Step 1/2 — Clearing all historical + mock signals (live signals safe)..."
	@curl -s -X POST "$(API)/admin/clear-historical" | $(PYTHON) -m json.tool
	@echo ""
	@echo "Step 2/2 — Starting walk-forward backfill (2024-05-13 → today, ~500 trading days)..."
	@echo "This will take 20-40 minutes. Go get a coffee."
	@curl -s -X POST "$(API)/trigger/backfill?start_date=2024-05-13&signals_per_day=10" \
		--max-time 3600 | $(PYTHON) -m json.tool
