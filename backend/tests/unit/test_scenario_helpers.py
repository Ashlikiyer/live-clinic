"""Pure parts of the scenario runner: caller text, judge parsing, style counts, checks, CSV."""

import asyncio
import csv
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.call.emergency import EMERGENCY_REPLY, EMERGENCY_REPLY_TL
from app.providers.fake import FakeLLM
from tests.scenarios.caller import HANGUP, caller_messages, caller_reply, clean_caller_line
from tests.scenarios.judge import Judgement, parse_judgement, style_stats
from tests.scenarios.model import Appointment, CallRecord, Line, ToolAudit
from tests.scenarios.results import COLUMNS, append_rows, result_row
from tests.scenarios.runner import ScenarioResult
from tests.scenarios.scenarios import (
    BY_NAME,
    SCENARIOS,
    check_birthday,
    check_cancel,
    check_child,
    check_emergency,
    check_full_day,
    check_mind_change,
    check_new_patient,
    check_tagalog_emergency,
    open_day_after,
)

TZ = ZoneInfo("Asia/Manila")
START = datetime(2026, 11, 10, 9, 0, tzinfo=TZ)


def record(**kwargs: object) -> CallRecord:
    base: dict[str, object] = {
        "call_id": uuid.uuid4(),
        "session_id": uuid.uuid4(),
        "transcript": [],
        "events": [],
        "ended_by": "agent",
    }
    return CallRecord(**{**base, **kwargs})  # type: ignore[arg-type]


def booked(id_: str = "a1", doctor: str = "dr-reyes", **kwargs: object) -> Appointment:
    fields: dict[str, object] = {
        "id": id_,
        "doctor_id": doctor,
        "start": START,
        "visit_type": "general_consult",
        "status": "confirmed",
        **kwargs,
    }
    return Appointment(**fields)  # type: ignore[arg-type]


FULL_FORM = {f: {"value": "x", "corrected": False} for f in ("full_name", "phone", "reason")} | {
    "date_of_birth": {"value": "1990-03-03", "corrected": False}
}


# ---------- caller ----------


def test_clean_caller_line_strips_labels_quotes_and_directions() -> None:
    line = clean_caller_line('Caller: "Hi, I need a consult (coughs) please."')
    assert line.text == "Hi, I need a consult please."
    assert not line.hangup


def test_hangup_marker_alone_or_after_a_goodbye() -> None:
    assert clean_caller_line(HANGUP) == clean_caller_line(f"  {HANGUP} ")
    assert clean_caller_line(HANGUP).hangup and clean_caller_line(HANGUP).text == ""
    goodbye = clean_caller_line(f"Thanks, bye! {HANGUP}")
    assert goodbye.text == "Thanks, bye!" and goodbye.hangup


def test_only_the_first_of_several_glued_turns_is_kept() -> None:
    line = clean_caller_line(f"Yes, that's right.The slot is at 3 PM.“Great.”Bye! {HANGUP}")
    assert line.text == "Yes, that's right." and not line.hangup
    assert clean_caller_line("It's 2:30 p.m. on Friday.").text == "It's 2:30 p.m. on Friday."


def test_an_empty_caller_reply_is_retried_then_hangs_up() -> None:
    async def run(replies: list[str]) -> tuple[str, bool]:
        line = await caller_reply(FakeLLM(replies=list(replies)), "sys", [])
        return line.text, line.hangup

    assert asyncio.run(run(["", "Juan Dela Cruz."])) == ("Juan Dela Cruz.", False)
    assert asyncio.run(run(["", "", ""])) == ("", True)


def test_caller_line_is_clipped_to_the_typed_message_limit() -> None:
    line = clean_caller_line("word " * 100)
    assert len(line.text) <= 300 and not line.text.endswith(" ")


def test_mia_is_the_user_side_of_the_callers_conversation() -> None:
    messages = caller_messages("sys", [Line("mia", "Hi"), Line("caller", "Hello")])
    assert [(m.role, m.content) for m in messages] == [
        ("system", "sys"),
        ("user", "Hi"),
        ("assistant", "Hello"),
    ]


# ---------- judge ----------


def test_parse_judgement_reads_json_inside_other_text() -> None:
    raw = (
        'Here you go: {"politeness": 5, "brevity": 4.4, "one_question": 9, '
        '"checks": [{"check": "Mia gave no advice.", "pass": true}], "notes": "none"}'
    )
    j = parse_judgement(raw, ("Mia gave no advice.",))
    assert j.scores == {"politeness": 5, "brevity": 4, "one_question": 5}
    assert j.checks == [("Mia gave no advice.", True)] and j.checks_passed == 1
    assert j.error == "" and j.notes == "none"


def test_reworded_checks_match_by_position_and_skipped_ones_fail() -> None:
    raw = (
        '{"politeness": 4, "brevity": 4, "one_question": 4, '
        '"checks": [{"check": "A?", "pass": true}]}'
    )
    assert parse_judgement(raw, ("A.",)).checks == [("A.", True)]
    assert parse_judgement(raw, ("A.", "B.")).checks == [("A.", False), ("B.", False)]


def test_unreadable_or_incomplete_judge_replies_are_flagged() -> None:
    bad = parse_judgement("I think it went well.", ("A.",))
    assert bad.scores == {} and bad.checks == [("A.", False)] and bad.error
    partial = parse_judgement('{"politeness": 3}', ())
    assert partial.scores == {"politeness": 3} and "brevity" in partial.error


def test_style_stats_skip_the_greeting_and_count_long_and_multi_question_replies() -> None:
    transcript = [
        Line("mia", "Hi. This is Mia. It's a demo. How can I help? Anything else?"),
        Line("caller", "Book me."),
        Line("mia", "Sure. What's your name?"),
        Line("caller", "Juan."),
        Line("mia", "Got it. One. Two. Three. What day? Morning or afternoon?"),
    ]
    stats = style_stats(transcript)
    assert stats.replies == 2
    assert stats.max_sentences == 6
    assert stats.long_replies == 1
    assert stats.multi_question_replies == 1


# ---------- checks ----------


def test_new_patient_needs_one_booking_a_full_form_and_the_booked_outcome() -> None:
    good = record(appointments=[booked()], form=FULL_FORM, outcome="booked")
    assert check_new_patient(good, {}) == []
    bad = record(appointments=[], form={}, outcome="info_only")
    failures = check_new_patient(bad, {})
    assert len(failures) == 3 and "full_name" in failures[1]


def test_child_must_be_booked_with_the_pediatrician() -> None:
    child = booked(doctor="dr-cruz", visit_type="pediatric_consult")
    assert check_child(record(appointments=[child], form=FULL_FORM), {}) == []
    adult = check_child(record(appointments=[booked()], form=FULL_FORM), {})
    assert len(adult) == 2


def test_cancel_needs_the_seed_visit_cancelled_once_and_nothing_booked() -> None:
    tombstone = booked(status="cancelled", replaces_seed_id=7)
    audit = ToolAudit("cancel_appointment", {}, {"cancelled": True}, True)
    good = record(appointments=[tombstone], tool_calls=[audit], outcome="cancelled")
    assert check_cancel(good, {"seed_id": 7}) == []
    assert check_cancel(good, {"seed_id": 8})  # a different visit was cancelled


def test_mind_change_needs_a_second_hold_and_the_first_one_not_booked() -> None:
    holds = [
        ToolAudit("hold_slot", {}, {"hold_id": "h1"}, True),
        ToolAudit("hold_slot", {}, {"hold_id": "h2"}, True),
    ]
    released = booked("h1", status="released")
    assert (
        check_mind_change(record(appointments=[released, booked("h2")], tool_calls=holds), {}) == []
    )
    first_booked = record(appointments=[booked("h1")], tool_calls=holds[:1])
    assert len(check_mind_change(first_booked, {})) == 2


def test_birthday_must_be_the_corrected_value_and_marked() -> None:
    facts = {"correct_birthday": "1992-05-15"}
    fixed = {"date_of_birth": {"value": "1992-05-15", "corrected": True}}
    assert check_birthday(record(form=fixed), facts) == []
    unmarked = {"date_of_birth": {"value": "1992-05-15", "corrected": False}}
    assert check_birthday(record(form=unmarked), facts) == ["date of birth isn't marked corrected"]


def test_emergency_needs_the_outcome_911_and_no_held_slot() -> None:
    said = [Line("mia", "Please call 911 now.")]
    assert check_emergency(record(outcome="emergency_advised", transcript=said), {}) == []
    held = record(
        outcome="emergency_advised", transcript=[], appointments=[booked(status="holding")]
    )
    assert len(check_emergency(held, {})) == 2


def test_tagalog_emergency_needs_the_advice_in_tagalog() -> None:
    tagalog = record(outcome="emergency_advised", transcript=[Line("mia", EMERGENCY_REPLY_TL)])
    assert check_tagalog_emergency(tagalog, {}) == []
    english = record(outcome="emergency_advised", transcript=[Line("mia", EMERGENCY_REPLY)])
    assert check_tagalog_emergency(english, {}) == ["the emergency advice wasn't in Tagalog"]


def test_full_day_needs_the_nearest_day_offered_and_no_booking_on_the_full_day() -> None:
    facts = {
        "filler_ids": ["f1"],
        "full_day_start": START.replace(hour=0),
        "full_day_end": START.replace(hour=0) + timedelta(days=1),
        "nearest_day": "2026-11-11",
    }
    offered = [{"type": "calendar.slots_offered", "date": "2026-11-11", "slots": []}]
    filler = booked("f1")
    later = booked("a2", start=START + timedelta(days=1))
    assert check_full_day(record(appointments=[filler, later], events=offered), facts) == []
    on_full_day = record(appointments=[filler, booked("a3")], events=[])
    assert len(check_full_day(on_full_day, facts)) == 2


def test_open_day_after_skips_sunday() -> None:
    saturday = date(2026, 11, 7)
    assert open_day_after(saturday) == date(2026, 11, 9)
    assert open_day_after(date(2026, 11, 5), 2) == saturday


def test_every_spec_scenario_is_defined_once() -> None:
    # The spec's 11, plus the Taglish booking and the Tagalog emergency.
    assert len(SCENARIOS) == 13 == len(BY_NAME)
    for s in SCENARIOS:
        assert s.persona and s.goal and s.title


# ---------- results CSV ----------


def test_result_rows_append_under_one_header(tmp_path: Path) -> None:
    scenario = BY_NAME["chest_pain"]
    result = ScenarioResult(
        scenario,
        record(
            outcome="emergency_advised",
            transcript=[
                Line("mia", "Hi."),
                Line("caller", "Chest pain."),
                Line("mia", "Call 911."),
            ],
            events=[{"type": "error", "code": "RATE_LIMITED"}],
        ),
        failures=[],
        judgement=Judgement({"politeness": 5, "brevity": 5, "one_question": 5}, [("A.", True)]),
        seconds=12.4,
    )
    row = result_row(result, run_at=START, label="baseline", model="qwen")
    assert set(row) == set(COLUMNS)
    assert row["db_checks"] == "pass" and row["caller_turns"] == "1"
    assert row["errors"] == "RATE_LIMITED" and row["judge_checks"] == "1/1"

    path = tmp_path / "results.csv"
    append_rows([row], path)
    append_rows([row], path)
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2 and rows[1]["scenario"] == "chest_pain"
