.PHONY: help dev infra stop logs status trigger debug analytics report

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
