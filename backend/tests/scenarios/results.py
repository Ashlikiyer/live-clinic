"""Scenario results: one CSV row per scenario run, so prompt changes can be compared."""

import csv
from datetime import datetime
from pathlib import Path

from .judge import SCORES, style_stats
from .runner import ScenarioResult

RESULTS_CSV = Path(__file__).parent / "results.csv"

COLUMNS = [
    "run_at",
    "run_label",
    "llm_model",
    "scenario",
    "db_checks",
    "failures",
    "outcome",
    "ended_by",
    "caller_turns",
    "errors",
    *SCORES,
    "judge_checks",
    "max_sentences",
    "long_replies",
    "multi_question_replies",
    "seconds",
    "judge_notes",
]


def result_row(
    result: ScenarioResult, *, run_at: datetime, label: str, model: str
) -> dict[str, str]:
    record, judgement = result.record, result.judgement
    stats = style_stats(record.transcript)
    row = {
        "run_at": run_at.isoformat(timespec="seconds"),
        "run_label": label,
        "llm_model": model,
        "scenario": result.scenario.name,
        "db_checks": "pass" if result.passed else "fail",
        "failures": "; ".join(result.failures),
        "outcome": record.outcome or "",
        "ended_by": record.ended_by,
        "caller_turns": str(sum(1 for line in record.transcript if line.speaker == "caller")),
        "errors": " ".join(record.error_codes()),
        "judge_checks": "",
        "max_sentences": str(stats.max_sentences),
        "long_replies": str(stats.long_replies),
        "multi_question_replies": str(stats.multi_question_replies),
        "seconds": f"{result.seconds:.0f}",
        "judge_notes": "",
    }
    for name in SCORES:
        row[name] = str(judgement.scores.get(name, "")) if judgement else ""
    if judgement is not None:
        if judgement.checks:
            row["judge_checks"] = f"{judgement.checks_passed}/{len(judgement.checks)}"
        row["judge_notes"] = judgement.error or judgement.notes
    return row


def append_rows(rows: list[dict[str, str]], path: Path = RESULTS_CSV) -> None:
    """Append to the CSV, writing the header first for a new file."""
    new = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        if new:
            writer.writeheader()
        writer.writerows(rows)
