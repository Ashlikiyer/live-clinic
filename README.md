# Live Clinic Desk

A browser-based AI voice receptionist for a fictional clinic, Bayview Family Clinic. You
click **Call the clinic** and talk naturally. On screen, you watch the agent book an
appointment on a live calendar and fill in a patient intake form as you speak. A Latency
X-ray shows how many milliseconds each reply took and which stage the time went to.

The full spec is in [docs/LIVE_CLINIC_DESK_SPEC.md](docs/LIVE_CLINIC_DESK_SPEC.md), and the
rules for AI coding assistants are in [CLAUDE.md](CLAUDE.md).

> Demo only. All data is fake. Don't share real medical information.

## Status

- **Phase 0 (skeleton):** done, except deployment.
- **Phase 1 (real voice loop):** done. The browser's Silero VAD records the caller and sends
  16 kHz WAV over the WebSocket. Groq Whisper transcribes it, then the emergency keyword
  check runs before the LLM. The Groq LLM streams the reply, which is split into sentences
  and spoken by Kokoro in the browser. Barge-in, per-turn latency metrics, a typed-message
  fallback, and one automatic reconnect are all working. The calendar and intake form tools
  come in Phase 2. Until then Mia offers a staff callback for bookings, and the calendar
  shows mock data.

Next is **Phase 2**: availability, booking and the agent tools.

## Measured latency (Phase 1)

These are real calls on a Windows laptop with an AMD integrated GPU (RDNA 2), Microsoft
Edge, Groq free tier and a local backend. Each value is the time from the end of the
caller's speech to Mia's first audio, measured in the browser.

| Stage | Reply with a cached opener | Reply without a cached opener |
| --- | --- | --- |
| End-of-speech wait (VAD) | 600 ms | 600 ms |
| Upload | ~20 ms | ~20 ms |
| Speech-to-text (Groq `whisper-large-v3-turbo`) | 620 ms | 620 ms |
| LLM first token (Groq `qwen/qwen3.8-27b`, reasoning off) | 259 ms | 241 ms |
| First sentence ready | 4 ms | 4 ms |
| Voice start (Kokoro, WebGPU fp16) | 5 ms | 1,123 ms |
| **Total** | **1,508 ms** | **2,618 ms** |

Measured Kokoro speed: WebGPU fp16 synthesizes at 0.5–0.6× real time after warm-up. WASM
q8, used when there's no WebGPU, runs at about 2.7× real time, which is too slow to keep up
with speech. Four tricks keep the first audio fast:

- Mia is prompted to start every reply with a short opener ("Sure.", "Of course."...).
  Those openers are generated ahead of time while the landing page is open, so they play
  instantly while the rest of the reply synthesizes.
- The greeting and recovery lines are pre-generated the same way.
- Live speech always goes ahead of background pre-generation in the worker queue.
- A device that synthesizes slower than real time starts with the browser's built-in "lite"
  voice. A device that gets two slow replies in a row switches to it mid-call.

The first visit downloads the voice model once (163 MB on WebGPU, 92 MB on WASM). After
that the browser serves it from cache.

### Notes on the spec

- **LLM:** `llama-3.3-70b-versatile` isn't available to this Groq key. `qwen/qwen3.8-27b`
  with `LLM_REASONING_EFFORT=none` replied fastest (about 370 ms vs about 700 ms for the
  `gpt-oss` models) and followed Mia's rules best.
- **Extra event fields:** three optional fields extend the spec's protocol so the browser
  can report the stages it measures. `vad_wait_ms` is on the audio header, `tts_ms` is on
  `tts.first_audio`, and `resume_call_id` on `call.start` rejoins a call after a dropped
  connection.
- **Cross-origin isolation:** the frontend sends `Cross-Origin-Opener-Policy` and
  `Cross-Origin-Embedder-Policy: credentialless` headers, which let the Kokoro worker use
  multi-threaded WebAssembly.

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
