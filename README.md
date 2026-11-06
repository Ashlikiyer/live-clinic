# Live Clinic Desk

A browser-based AI voice receptionist for a fictional clinic, Bayview Family Clinic. You
click **Call the clinic** and talk naturally. On screen, you watch the agent book an
appointment on a live calendar and fill in a patient intake form as you speak. The public
`/stats` page shows how many milliseconds replies take and which stage the time goes to.

The full spec is in [docs/LIVE_CLINIC_DESK_SPEC.md](docs/LIVE_CLINIC_DESK_SPEC.md), and the
rules for AI coding assistants are in [CLAUDE.md](CLAUDE.md).

> Demo only. All data is fake. Don't share real medical information.

## Status

- **Phase 0 (skeleton):** done, except deployment.
- **Phase 1 (real voice loop):** done. The browser's Silero VAD records the caller and sends
  16 kHz WAV over the WebSocket. Groq Whisper transcribes it, then the emergency keyword
  check runs before the LLM. The Groq LLM streams the reply, which is split into sentences
  and spoken by Kokoro in the browser. Barge-in, per-turn latency metrics, a typed-message
  fallback, and one automatic reconnect are all working.
- **Phase 2 (booking tools and live calendar):** done. Mia books, reschedules and cancels on
  the caller's own sandbox calendar, fills the intake form (with "corrected" tags), answers
  clinic questions from the knowledge file, transfers to staff, and ends the call. The rules
  that matter are enforced in code, not only in the prompt:
  - A booking change is refused unless it was read back in an earlier turn and the caller's
    latest reply is a clear yes (rule list first, then a one-word LLM check).
  - Booking needs name, date of birth, phone and reason on the form.
  - Holds expire after 5 minutes, and every change locks the session row, so two fast tool
    calls can't double-book.
  - At most 3 tools per round and 4 LLM rounds per caller turn.
  - A reply stops at its first question, so the model can't answer for the caller.
  - `end_call` is refused until the caller signals they're done (emergencies excepted). A
    transfer needs the caller to have asked for a person, or to have said yes to Mia's offer
    (`TRANSFER_NOT_REQUESTED` otherwise).

  The calendar and doctors load from `GET /api/calendar` and `GET /api/clinic`. A cached
  "Let me check that." plays if a tool runs for 700 ms with nothing said yet. After 8 s of
  silence Mia asks "Are you still there?", and after another 8 s she ends the call.

- **Phase 3 (Latency X-ray, summary card and stats):** done.
  - **Latency X-ray:** every reply is a stacked bar of its pipeline stages. Tool time is drawn
    hatched inside the LLM stage, interruptions carry ⚡, and there's a 1.5 s target line. A
    hover or focus tooltip shows exact milliseconds, and a table view lists every value. The
    stage colors are a validated colorblind-safe palette, in both light and dark mode.
  - **Summary card:** shows Mia's own call summary, the appointment, the form snapshot, call
    length, replies, median and slowest reply, and interruptions. Live calls download the
    stored transcript from the server.
  - **Barge-in timing:** the browser measures how long Mia takes to go quiet once the caller
    starts talking, and it's stored with the interrupted turn.
  - **`/stats`** (public, no transcripts): the last 7 days of median and p95 reply time, the
    median of each stage, a reply-time histogram, a daily trend, which stage made slow
    replies slow, and interruptions.
  - **Daily cleanup:** `POST /api/internal/cleanup` (header `X-Cron-Secret`) rolls expired
    sessions into `daily_stats`, then deletes them. The rollup keeps 50 ms histograms, so
    weekly medians and p95 stay accurate after per-turn data is gone.
    `.github/workflows/cleanup.yml` calls it daily at 02:00 Manila time once the `API_URL`
    and `CRON_SECRET` repository secrets are set.

- **Phase 4 (conversation scenarios):** done. A simulated caller talks to Mia through the
  real Groq models, each call ends with database checks, and an LLM judge scores it. See
  [Conversation scenarios](#conversation-scenarios).
- **Mia's voice (after Phase 4):** Mia now speaks with Groq's Orpheus voice (`hannah`) by
  default. See [Mia's voice](#mias-voice).
- **Design v2 (after Phase 4):** the landing page, call desk and summary follow the "Live
  Clinic Desk v2" design: a light, monochrome look with Geist type, soft status colours on the
  calendar, and a full landing page (hero, doctors, how it works, safety, FAQ). "Type
  instead" starts a call without the microphone. The Latency X-ray strip was taken off the
  call desk to keep it simple for callers; the same timings are still collected and shown on
  `/stats`. The app is light-only now.
- **Tagalog and Taglish (the spec's stretch goal):** Mia understands English, Tagalog and
  Taglish and replies in the caller's language. See [Tagalog and Taglish](#tagalog-and-taglish).

## Tagalog and Taglish

Callers can speak English, Tagalog or a mix of both, and Mia answers the same way.

- **Hearing:** Whisper now detects the language per utterance instead of being forced to
  English (`STT_LANGUAGE` empty; set `en` to force English again). A short Taglish hint
  prompt with the doctors' names helps it expect code-switching and spell "Ana Reyes" right.
- **Replies:** the prompt tells Mia to answer in the caller's language. She uses "po" and
  "opo" in Tagalog and keeps doctor names, dates and times in English words.
- **Safety:** the emergency check runs before the LLM in Tagalog too. It covers chest pain
  ("masakit ang dibdib"), breathing ("hindi makahinga"), heavy bleeding, stroke signs,
  fainting or seizures ("nahimatay", "nangingisay") and self-harm. A caller who speaks
  Tagalog gets the 911 advice in Tagalog. Ordinary requests like "masakit ang ulo ko"
  (headache) are not flagged.
- **Booking rules:** the confirmation check also understands Tagalog. "Opo, sige po" and
  "Tama" are a yes. "Teka lang" (wait) and "Sige, pero sa hapon na lang" (yes, but the
  afternoon) are not. "Yun lang po, salamat" counts as a goodbye, and "Pwede ko pong
  kausapin ang staff?" as a request for a person.
- **Voice:** Orpheus is an English voice, so Tagalog words have a slight accent.
- **Scenarios:** `taglish_booking` and `tagalog_chest_pain` join the spec's 11. The Tagalog
  emergency passed on Groq. The Taglish booking was cut short by a Groq outage on its first
  run and still needs a full run.

## Mia's voice

The landing page has a voice switch. The caller's choice is remembered in their browser:

| Choice | Engine | Where it runs | Limits |
| --- | --- | --- | --- |
| **Natural** (default) | Groq Orpheus `canopylabs/orpheus-v1-english`, voice `hannah` | Groq's servers, through our backend | 100 requests a day, 1,200 characters a minute (free tier) |
| **In-browser** | Kokoro `af_nova` | The caller's GPU (WebGPU) | Downloads ~160 MB once; needs a GPU that runs it correctly |
| **Built-in** | The browser's `speechSynthesis` | The caller's device | None; quality depends on the browser |

- **Why Orpheus is the default:** Kokoro made silent or garbled audio on the developer's
  laptop and on a recent phone, and the official kokoro-js WebGPU demo sounded the same, so
  it's a device problem we can't fix from code. Orpheus runs on Groq, so it sounds the same
  everywhere.
- **How it works:**
  - The browser waits for Mia's whole reply, then sends one `tts.request` over the call
    socket. One request per reply keeps a call to about 10 of the 100 daily requests.
  - The backend checks the text is something Mia said in this call, or one of her fixed lines.
    Otherwise the socket would be a free text-to-speech service.
  - The backend streams Groq's audio back as binary `tts.audio` frames (16-bit PCM), then
    `tts.done`. Playback starts at the first chunk, about 0.4-0.7 s after the request.
- **Saved lines:** the greeting, recovery lines and the "Let me check that." filler are kept
  in the backend's memory after their first request, so they cost nothing afterwards (until
  the backend restarts).
- **When Orpheus can't speak:** if the daily limit runs out or Groq fails, the backend sends
  `tts.failed`, and Mia switches to the built-in voice for the rest of the call. She's never
  silent. The badge next to her name shows the voice in use.
- **Kokoro, when chosen:** it now checks its own output. If WebGPU produces silence or noise
  in half precision, it tries full precision on the GPU, then the CPU. If those are too slow
  or broken too, the built-in voice takes over. Its download only starts when "In-browser" is
  picked.

## Conversation scenarios

`backend/tests/scenarios/` holds the 11 scenarios from the spec, from "new patient books a
consult for a cough" to "requested day fully booked", plus two in Tagalog and Taglish.

- **How a run works:** the backend runs in-process with the real Groq provider and your
  database. Each scenario gets a fresh session and talks over the real WebSocket in text mode
  (`text.message`), so everything except audio is exercised.
- **The caller** is `qwen/qwen3.8-27b` with a persona and a goal. Some scenarios prepare the
  session first: a seeded patient to reschedule or cancel, or a day filled for every doctor.
- **Database checks** decide pass or fail: appointments, the intake form (and its "corrected"
  tag), the call outcome and the tool audit rows.
- **The judge** (also Qwen) then scores politeness, brevity and one question per
  turn from 1 to 5, and answers scenario checks such as "Mia gave no medical advice". Simple
  counts done in code (most sentences in a reply, replies with two questions) sit beside the
  scores. During a run Mia falls back only to `gpt-oss-20b`, so she never competes with the
  caller and the judge for Qwen's budget.
- **Results** are appended to `backend/tests/scenarios/results.csv`, one row per scenario, so
  runs before and after a prompt change can be compared. Transcripts go to
  `backend/tests/scenarios/transcripts/` (not committed).

```bash
cd backend
uv run python -m tests.scenarios --list
uv run python -m tests.scenarios                         # all 13, about 30 minutes
uv run python -m tests.scenarios chest_pain medical_advice --label "shorter prompt"
```

They need `PROVIDER=groq` and the Groq key in `.env`. One Mia reply costs about 2,500 tokens
per LLM round, and the free tier allows 8,000 tokens per minute per model, so caller lines are
at least 20 s apart (`--pace`), with a 45 s pause between scenarios (`--cooldown`). If a model
stays rate limited, that scenario is marked "stopped" and the run moves on.

**Mind the daily limit.** The free tier also caps each model at 200,000 tokens per day, and
the live demo uses the same budget. All 11 scenarios use roughly 300,000 tokens or more, so
run a few at a time (for example the ones a prompt change affects), not the whole set daily.
That's also why the GitHub workflow is manual only.

### What the scenarios found

The first runs turned up real bugs, all fixed with tests:

- **Silent replies.** When Qwen was rate limited, the `gpt-oss` fallback spent its 160-token
  reply on hidden reasoning and said nothing. Reasoning models now get 1,024 extra tokens,
  and an empty reply becomes "Sorry, I had a little trouble there. Could you repeat that?"
- **A made-up transfer.** A fallback model asked for a phone number and transferred the
  caller in the same reply. Transfers now need the caller's say-so (see Phase 2 above).
- **Repeated goodbyes.** When Mia wrapped up before the caller was done, the refused
  `end_call` led to a second LLM round that repeated her closing lines. She now asks "Is
  there anything else I can help you with?" instead, which also saves a round.
- **Lost audit rows.** If the LLM failed after a tool had run in that turn (a cancel, a
  booking), the tool's `tool_calls` row was never saved.
- **Tools skipped by the main model.** Qwen (with reasoning off) often talked instead of
  acting: "Let me check" with no availability check, "Your appointment is set" with nothing
  booked, and every form detail saved only at the end, so a corrected birthday was never
  marked "corrected". A probe of the same moments called the right tool 1 time in 4 with
  Qwen and 4 times in 4 with `gpt-oss-120b`, so Mia's main model is now `gpt-oss-120b`
  (see the LLM note below).
- **A call closed as "booked" with no booking.** `end_call` now refuses booked,
  rescheduled or cancelled unless that change really succeeded in the call
  (`OUTCOME_NOT_DONE`).

The runner itself is tested with fake providers in normal CI. The real run is in
`.github/workflows/scenarios.yml`, started by hand from the Actions tab once a `GROQ_API_KEY`
repository secret is set. Its CSV and transcripts are uploaded as a build artifact.

## Groq free tier: what it allows

Every chat model on the free tier is limited to **8,000 tokens per minute and 200,000
tokens per day, per model**. An
LLM call with Mia's prompt, the 10 tool schemas and a few turns of history is about
2,000–2,800 tokens. To fit a real call into that:

- **Smaller requests.** The prompt and tool schemas are trimmed, tool results use compact
  JSON, and history keeps 8 turns (tool details for the last 3 only).
- **No wasted rounds.** Once Mia has asked her question, no second LLM round is made after
  the tools.
- **Model fallback.** When the main model (`LLM_MODEL`) is rate limited, the same request
  goes to `LLM_FALLBACK_MODELS` (`gpt-oss-20b`, then Qwen, each with its own budget). If all
  of them free up within 4 s, Mia waits instead of failing.

Measured: one call at a natural pace (a turn about every 10 s) fits, including a full
booking, reschedule and cancel. Quick back-to-back turns, or several calls at once, can
still hit the limit. Mia then says "Sorry, I had a little trouble there. Could you repeat
that?" and recovers on the next turn. Removing the limit would need Groq's paid tier.

**When the limit lasts (the busy line):**

- **The landing page:** `GET /api/health` reports `"llm": "busy"` (and `busy_seconds`) once
  every model has been rate limited for 20 s or more. The landing page then shows "Mia's line
  is busy right now. Please try again in a minute." and checks again every 30 s.
- **New calls:** refused with a `RATE_LIMITED` error and that message. No call is created,
  so it doesn't use up the caller's 10 calls a day.
- **During a call:** a single rate-limited reply still gets the apology. A second one in a
  row, or a limit that will last 20 s or more (for example the daily token limit), makes Mia
  say a friendly busy line instead ("Sorry, our line is very busy right now. Please call back
  in a few minutes."), in Tagalog for a Tagalog caller. She then hangs up with outcome
  `abandoned`, and the summary says "Mia's line is busy."

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

- **Extra client values:** `call.end` may carry `reason: "silence"` (the 8-second rule), so
  the call record says why it ended. `user.interrupt` may carry `stop_ms`: the time from the
  caller's first word to Mia going quiet, which includes the 400 ms barge-in threshold.
- **Clock sync:** the spec's three-message clock-sync handshake isn't implemented. The
  approximate upload stage uses a single offset taken at call start. Total reply time is
  measured entirely in the browser, so it doesn't depend on this.
- **LLM:** `llama-3.3-70b-versatile` isn't available to this Groq key. Phase 1 used
  `qwen/qwen3.8-27b` with reasoning off, the fastest to reply. Once Mia had tools, the
  scenarios showed Qwen often skipping them, so the main model is now `openai/gpt-oss-120b`
  with `LLM_REASONING_EFFORT=low`. It called the right tool every time in a probe, for
  about 0.1-0.3 s more per reply. The Phase 1 latency table above was measured with Qwen.
- **Extra event fields:** three optional fields extend the spec's protocol so the browser
  can report the stages it measures. `vad_wait_ms` is on the audio header, `tts_ms` is on
  `tts.first_audio`, and `resume_call_id` on `call.start` rejoins a call after a dropped
  connection.
- **Server speech (an addition to the spec):** the spec runs all speech in the browser. Mia's
  default voice is now Groq Orpheus, asked for by the browser with `tts.request {id, text}`
  and answered with binary `tts.audio` frames, then `tts.done {id, chunks}` or
  `tts.failed {id, code, message}`. The server runs no audio model; Groq does, the same way
  it does for Whisper. Also added: `call.start` accepts `voice: "orpheus"` (migration `0004`
  allows it in `calls.voice_mode`), and a `TTS_FAILED` error code.
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
