# DARKPOOL

**AI trading intelligence desk.** Real-time market data → deterministic quant/SMC engine →
a panel of mandate-differentiated AI analysts that disagree by design → Claude as CIO
issuing one fully-reasoned, risk-managed trade plan. Advisory only in v1.

> Single source of truth: [`docs/MASTER_PLAN.md`](docs/MASTER_PLAN.md) ·
> Standing orders: [`CLAUDE.md`](CLAUDE.md) · Build state: [`docs/STATUS.md`](docs/STATUS.md)

## Layout
```
backend/   FastAPI · adapters · quant engine · consensus engine · MCP server
frontend/  Next.js · DARKPOOL design language
docs/      master plan · ADRs · status
```

## Run locally (dev)
```bash
# backend
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt -r requirements-dev.txt
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000

# frontend
cd frontend
npm install && npm run dev   # http://localhost:3000
```

No API keys are needed for Phase 0/1 market data — Binance public endpoints are keyless.
Copy `backend/.env.example` → `backend/.env` to configure optional services.
