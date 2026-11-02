import json
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.agent.handlers.get_clinic_info import rank_answers
from app.agent.spoken import clinic_iso, spoken_time
from app.agent.tools import ARG_MODELS, CheckAvailabilityArgs, UpdateIntakeFormArgs, tool_specs
from app.call.interrupt import History
from app.providers.base import ChatMessage, ToolCallRequest
from app.providers.groq_llm import StreamParser, message_payload
from app.repositories.clinic import InfoEntry

TZ = ZoneInfo("Asia/Manila")

SPEC_TOOLS = {
    "update_intake_form",
    "find_patient",
    "check_availability",
    "hold_slot",
    "confirm_booking",
    "release_hold",
    "reschedule_appointment",
    "cancel_appointment",
    "get_clinic_info",
    "end_call",
}


def test_exactly_the_ten_spec_tools_are_offered() -> None:
    specs = tool_specs()
    assert {s["function"]["name"] for s in specs} == SPEC_TOOLS == set(ARG_MODELS)
    for spec in specs:
        params = spec["function"]["parameters"]
        assert params["type"] == "object"
        assert "title" not in json.dumps(params)
        assert spec["function"]["description"]


def test_optional_fields_are_plain_types_for_the_llm() -> None:
    form = next(s for s in tool_specs() if s["function"]["name"] == "update_intake_form")
    props = form["function"]["parameters"]["properties"]
    assert props["full_name"]["type"] == "string"
    assert props["date_of_birth"]["format"] == "date"


def test_argument_validation() -> None:
    assert CheckAvailabilityArgs.model_validate({"date_from": "2026-11-03"}).part_of_day == "any"
    for bad in (
        {"date_from": "2026-11-05", "date_to": "2026-11-03"},
        {"date_from": "2026-11-01", "date_to": "2026-12-01"},
        {"date_from": "tomorrow"},
        {"date_from": "2026-11-03", "part_of_day": "night"},
        {"date_from": "2026-11-03", "surprise": True},
    ):
        try:
            CheckAvailabilityArgs.model_validate(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad}")
    try:
        UpdateIntakeFormArgs.model_validate({})
    except ValueError:
        pass
    else:
        raise AssertionError("empty form update accepted")


def test_stream_parser_merges_fragmented_tool_calls() -> None:
    parser = StreamParser()
    lines = [
        'data: {"choices":[{"delta":{"content":"Sure."}}]}',
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1","function":'
        '{"name":"hold_slot","arguments":"{\\"doctor"}}]}}]}',
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":'
        '{"arguments":"_id\\": \\"dr-reyes\\"}"}}]}}]}',
        'data: {"choices":[{"delta":{"tool_calls":[{"index":1,"id":"c2","function":'
        '{"name":"release_hold","arguments":"{}"}}]}}]}',
        "data: [DONE]",
    ]
    text = [chunk for line in lines for chunk in parser.feed(line)]
    assert text == ["Sure."]
    calls = parser.finish()
    assert [(c.id, c.name, json.loads(c.arguments)) for c in calls] == [
        ("c1", "hold_slot", {"doctor_id": "dr-reyes"}),
        ("c2", "release_hold", {}),
    ]


def test_message_payload_for_tool_rounds() -> None:
    call = ToolCallRequest("c1", "find_patient", '{"full_name": "A"}')
    assistant = message_payload(ChatMessage("assistant", "", tool_calls=(call,)))
    assert assistant["content"] is None
    assert assistant["tool_calls"][0]["function"]["name"] == "find_patient"
    tool = message_payload(ChatMessage("tool", '{"found": false}', tool_call_id="c1"))
    assert tool == {"role": "tool", "content": '{"found": false}', "tool_call_id": "c1"}


def test_history_keeps_tool_exchanges_before_the_spoken_reply() -> None:
    history = History()
    history.add_user(1, "Can I come Tuesday?")
    reply = history.add_assistant(1, "")
    call = ToolCallRequest("c1", "check_availability", "{}")
    history.add_tool_exchange(reply, (call,), [("c1", '{"slots": []}')])
    reply.text = "Sure. Tuesday is full. How about Wednesday?"
    history.apply_interrupt(1, "Sure. Tuesday is full.")

    messages = history.to_messages("SYSTEM")
    assert [m.role for m in messages] == ["system", "user", "assistant", "tool", "assistant"]
    assert messages[2].tool_calls == (call,)
    assert messages[3].tool_call_id == "c1"
    assert messages[4].content == "Sure. Tuesday is full. [interrupted by caller]"


def test_spoken_times_are_in_clinic_time() -> None:
    moment = datetime(2026, 11, 3, 6, 30, tzinfo=UTC)  # 14:30 in Manila
    assert spoken_time(moment, TZ) == "Tuesday, November 3, at 2:30 PM"
    assert (
        spoken_time(datetime(2026, 11, 3, 9, 0, tzinfo=TZ), TZ) == "Tuesday, November 3, at 9:00 AM"
    )
    assert clinic_iso(moment, TZ) == "2026-11-03T14:30:00+08:00"


def test_clinic_info_ranking() -> None:
    entries = [
        InfoEntry("prices", "How much is a consultation?", "A general consult is 600 pesos."),
        InfoEntry("prices", "Do you accept HMO?", "We accept most major HMO cards."),
        InfoEntry("hours", "What are your hours?", "Monday to Saturday, 9 to 5."),
    ]
    best = rank_answers(entries, "prices", "Do you take my HMO card?")
    assert best[0].answer.startswith("We accept most major HMO")
    assert rank_answers(entries, "other", "Do you have parking for bicycles?") == []
    assert rank_answers(entries, "other", "When are your hours on Saturday?")[0].topic == "hours"
