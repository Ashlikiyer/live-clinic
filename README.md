# Live Clinic Desk

A browser-based AI voice receptionist for a fictional clinic, Bayview Family Clinic. You
click **Call the clinic** and talk naturally. On screen, you watch the agent book an
appointment on a live calendar and fill in a patient intake form as you speak. A Latency
X-ray shows how many milliseconds each reply took and which stage the time went to.

The full spec is in [docs/LIVE_CLINIC_DESK_SPEC.md](docs/LIVE_CLINIC_DESK_SPEC.md), and the
rules for AI coding assistants are in [CLAUDE.md](CLAUDE.md).

> Demo only. All data is fake. Don't share real medical information.

## Status

**Phase 0 (skeleton)**, done except the deployment step:

- `backend/`: FastAPI with `/api/health` and a WebSocket echo route at `/ws/call`, the
  spec's error format, Alembic migrations for all tables, and a seed script.
- `frontend/`: Next.js with the Call Desk layout (call panel, calendar, intake form, Latency
  X-ray, summary card). For now it's driven by a scripted demo call that sends the same
  typed events the real backend will send.
- CI: GitHub Actions runs the lint, type check and test steps for both apps.

Next is **Phase 1**: browser VAD → WAV → WebSocket → Groq Whisper → Groq LLM → sentences →
Kokoro, plus latency metrics.

## Repository layout

```text
backend/    FastAPI app (uv): app/, alembic/, seed/, tests/
frontend/   Next.js app (npm): src/app, src/components, src/store, src/realtime, tests/
docs/       Project spec
```

## Local setup

You need Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js 20+ (24 recommended), npm,
Docker and Chrome.

### Backend

```bash
cd backend
uv sync
docker run -d --name clinic-db -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=clinic -p 5432:5432 postgres:16
cp .env.example .env              # then edit it
uv run alembic upgrade head
uv run python -m seed             # doctors, clinic info, fake patients and appointments
uv run uvicorn app.main:app --reload --port 8000   # http://localhost:8000
```

If something else already uses port 5432 (for example a local PostgreSQL install), map the
container to another port (`-p 5433:5432`) and change `DATABASE_URL` in `.env` to match.

Seeded appointments cover the past week and the next three weeks from the day you run the
seed. Run `uv run python -m seed` again to refresh them. Doing so replaces all seed rows.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev                       # http://localhost:3000
```

The microphone only works on `localhost` or HTTPS, so test at `http://localhost:3000`, not
at a LAN IP address.

## Checks

```bash
# Backend
cd backend
uv run ruff check . && uv run ruff format --check .
uv run mypy app tests seed alembic/env.py
uv run pytest                     # the DB test is skipped if Postgres isn't reachable

# Frontend
cd frontend
npm run lint && npm run typecheck && npm test && npm run build
```

## What a real deployment would need

This project is a demo. A real clinic deployment would also need patient consent,
compliance with health-data rules (for example HIPAA in the US or the Data Privacy Act in
the Philippines), a call-recording notice, audit logs, and access controls.
