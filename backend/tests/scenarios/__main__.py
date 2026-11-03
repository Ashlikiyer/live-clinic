"""Run the conversation scenarios against the real providers (Groq) and the database.

    uv run python -m tests.scenarios                     # all of them
    uv run python -m tests.scenarios chest_pain medical_advice
    uv run python -m tests.scenarios --list

Each scenario: a simulated caller talks to Mia in text mode, the database is checked, then an
LLM judge scores the call. Results are appended to tests/scenarios/results.csv and each
transcript is saved in tests/scenarios/transcripts/.
"""

import argparse
import asyncio
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from anyio.from_thread import start_blocking_portal
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.call.session import ToolDeps
from app.core.config import get_settings
from app.db.models import Doctor
from app.main import create_app
from app.providers.groq_llm import GroqLLM
from app.repositories.booking import BookingRepository
from app.repositories.calls import SqlCallStore
from app.repositories.clinic import ClinicInfoRepository

from .judge import style_stats
from .results import RESULTS_CSV, append_rows, result_row
from .runner import ScenarioResult, ScenarioRunner, scenario_settings
from .scenarios import BY_NAME, SCENARIOS

TRANSCRIPTS = Path(__file__).parent / "transcripts"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m tests.scenarios", description=__doc__)
    parser.add_argument("names", nargs="*", help="scenarios to run (default: all)")
    parser.add_argument("--list", action="store_true", help="list the scenarios and exit")
    parser.add_argument(
        "--pace",
        type=float,
        default=float(os.environ.get("SCENARIO_PACE_S", "20")),
        help="minimum seconds between caller lines, to stay under Groq's free-tier limits",
    )
    parser.add_argument(
        "--cooldown",
        type=float,
        default=float(os.environ.get("SCENARIO_COOLDOWN_S", "45")),
        help="seconds to pause between scenarios, so the per-minute token budget refills",
    )
    parser.add_argument("--no-judge", action="store_true", help="skip the LLM judge")
    parser.add_argument("--no-csv", action="store_true", help="don't append to results.csv")
    parser.add_argument("--label", default="", help="a note for this run in results.csv")
    parser.add_argument(
        "--caller-model",
        default=os.environ.get("SCENARIO_CALLER_MODEL", "openai/gpt-oss-20b:low"),
        help="model:reasoning_effort for the simulated caller",
    )
    parser.add_argument(
        "--judge-model",
        default=os.environ.get("SCENARIO_JUDGE_MODEL", "openai/gpt-oss-120b:low"),
        help="model:reasoning_effort for the judge",
    )
    parser.add_argument(
        "--mia-fallbacks",
        default=os.environ.get("SCENARIO_MIA_FALLBACKS"),
        help="override Mia's fallback models for the run (default: LLM_FALLBACK_MODELS)",
    )
    return parser.parse_args(argv)


def _model(spec: str) -> tuple[str, str]:
    name, _, effort = spec.partition(":")
    return name, effort


async def _prepare_database(url: str) -> None:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            doctors = await conn.scalar(select(func.count()).select_from(Doctor))
    except OSError as exc:
        raise SystemExit(f"Postgres isn't reachable at DATABASE_URL: {exc}") from exc
    finally:
        await engine.dispose()
    if not doctors:
        raise SystemExit("The database has no clinic data; run `uv run python -m seed` first.")


def save_transcript(result: ScenarioResult) -> None:
    TRANSCRIPTS.mkdir(exist_ok=True)
    lines = [f"# {result.scenario.name}: {result.scenario.title}", ""]
    lines += [
        f"{'Mia' if ln.speaker == 'mia' else 'Caller'}: {ln.text}"
        for ln in result.record.transcript
    ]
    lines += ["", f"Outcome: {result.record.outcome}  (ended by {result.record.ended_by})"]
    lines += [f"Failure: {f}" for f in result.failures]
    (TRANSCRIPTS / f"{result.scenario.name}.txt").write_text("\n".join(lines) + "\n", "utf-8")


def report(result: ScenarioResult) -> str:
    status = "PASS" if result.passed else "FAIL"
    parts = [f"{status} {result.scenario.name} ({result.seconds:.0f} s)"]
    if result.judgement is not None:
        j = result.judgement
        scores = " ".join(f"{k}={v}" for k, v in j.scores.items()) or j.error
        parts.append(f"judge: {scores}")
        if j.checks:
            parts.append(f"checks {j.checks_passed}/{len(j.checks)}")
    stats = style_stats(result.record.transcript)
    parts.append(f"max {stats.max_sentences} sentences")
    text = " | ".join(parts)
    for failure in result.failures:
        text += f"\n    - {failure}"
    if result.judgement is not None:
        text += "".join(f"\n    - judge: {c}" for c, ok in result.judgement.checks if not ok)
    return text


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    args = parse_args(argv)
    if args.list:
        for s in SCENARIOS:
            print(f"{s.name:28} {s.title}")
        return 0
    unknown = [n for n in args.names if n not in BY_NAME]
    if unknown:
        print(f"Unknown scenarios: {', '.join(unknown)}. Use --list.")
        return 2
    chosen = [BY_NAME[n] for n in args.names] or SCENARIOS

    # get_settings() is cached, so the PROVIDER override must come before anything reads it.
    settings = get_settings()
    if settings.provider != "groq" or not settings.groq_api_key or not settings.llm_model:
        print("Scenarios need PROVIDER=groq, GROQ_API_KEY and LLM_MODEL (see .env.example).")
        return 2
    asyncio.run(_prepare_database(settings.database_url))

    tz = ZoneInfo(settings.clinic_timezone)
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    results: list[ScenarioResult] = []
    run_at = datetime.now(tz)
    with (
        scenario_settings(settings, args.mia_fallbacks),
        start_blocking_portal() as portal,
        portal.wrap_async_context_manager(httpx.AsyncClient()) as http,
    ):
        caller_name, caller_effort = _model(args.caller_model)
        caller = GroqLLM(
            http,
            settings.groq_api_key,
            caller_name,
            temperature=0.7,
            max_tokens=500,
            reasoning_effort=caller_effort,
        )
        judge = None
        if not args.no_judge:
            judge_name, judge_effort = _model(args.judge_model)
            judge = GroqLLM(
                http,
                settings.groq_api_key,
                judge_name,
                temperature=0.0,
                max_tokens=1500,
                reasoning_effort=judge_effort,
            )
        app = create_app(
            store=SqlCallStore(sessionmaker),
            tools=ToolDeps(BookingRepository(sessionmaker, tz), ClinicInfoRepository(sessionmaker)),
        )
        with TestClient(app) as client:
            runner = ScenarioRunner(
                client, portal, sessionmaker, settings, caller, judge, pace_s=args.pace
            )
            for i, scenario in enumerate(chosen):
                if i:
                    time.sleep(args.cooldown)
                print(f"\n== {scenario.name}: {scenario.title}")
                result = runner.run(scenario)
                save_transcript(result)
                results.append(result)
                print(report(result))

    if not args.no_csv:
        rows = [
            result_row(r, run_at=run_at, label=args.label, model=settings.llm_model)
            for r in results
        ]
        append_rows(rows)
        print(f"\nAppended {len(rows)} rows to {RESULTS_CSV}")
    passed = sum(r.passed for r in results)
    print(f"{passed}/{len(results)} scenarios passed their database checks.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
