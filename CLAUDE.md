# Live Clinic Desk – rules for AI coding assistants

Spec: docs/LIVE_CLINIC_DESK_SPEC.md. Follow it exactly; ask if unclear.

## Commands
- Backend: cd backend && uv run pytest | uv run ruff check . | uv run mypy app
- Frontend: cd frontend && npm run lint | npm run typecheck | npm test

## Rules
- Use the exact event names, tool names, table names and error codes from the spec.
- All provider calls (STT, LLM) go through backend/app/providers. Tests use the fake provider.
- The agent changes data only through tools in backend/app/agent/handlers,
  validated with Pydantic and scoped to the caller's session.
- Booking changes require the confirmation check in code (call/confirm.py).
- The emergency keyword check runs before the LLM on every caller transcript.
- Audio models (VAD, TTS) run in the browser only. Never add audio models to the server.
- Keep pure logic (availability, sentence splitting, confirmation rules) free of I/O and unit-tested.
- Frontend: TypeScript strict; events typed in src/realtime/events.ts;
  call state in Zustand; animations respect prefers-reduced-motion.
- Frontend uses npm (not pnpm). Next.js 16 with cacheComponents: read
  frontend/node_modules/next/dist/docs/ before using unfamiliar Next APIs.
- Every change includes tests. Run lint, types and tests before saying you are done.
- Ask before adding dependencies. Everything must stay free.
