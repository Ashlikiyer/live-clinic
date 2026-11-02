from app.call.interrupt import MAX_HISTORY_TURNS, MAX_TOOL_TURNS, History, trim_to_played
from app.providers.base import ToolCallRequest


def test_trim_keeps_only_played_words() -> None:
    full = "I'm holding Wednesday at 9:30 AM with Dr. Reyes. Shall I confirm?"
    assert trim_to_played(full, "I'm holding Wednesday ") == "I'm holding Wednesday"
    assert trim_to_played(full, "") == ""


def test_trim_never_exceeds_generated_text() -> None:
    assert trim_to_played("Short reply.", "Short reply. plus words never generated") == (
        "Short reply."
    )


def test_interrupted_reply_is_trimmed_and_marked_in_llm_messages() -> None:
    history = History()
    history.add_assistant(0, "Hi, how can I help?")
    history.add_user(1, "Book me for Wednesday.")
    history.add_assistant(1, "I'm holding Wednesday at 9:30 AM. Shall I confirm?")
    history.add_user(2, "Actually, the afternoon.")

    entry = history.apply_interrupt(1, "I'm holding Wednesday")
    assert entry is not None and entry.interrupted

    messages = history.to_messages("SYSTEM")
    assert [m.role for m in messages] == ["system", "assistant", "user", "assistant", "user"]
    assert messages[3].content == "I'm holding Wednesday [interrupted by caller]"


def test_interrupt_for_unknown_turn_is_ignored() -> None:
    assert History().apply_interrupt(5, "anything") is None


def test_reply_cut_before_any_audio_is_left_out() -> None:
    history = History()
    history.add_user(1, "Hello")
    history.add_assistant(1, "Hi there, welcome.")
    history.apply_interrupt(1, "")
    assert [m.role for m in history.to_messages("S")] == ["system", "user"]


def test_history_is_trimmed_to_recent_turns() -> None:
    history = History()
    for turn in range(1, MAX_HISTORY_TURNS + 6):
        history.add_user(turn, f"user {turn}")
        history.add_assistant(turn, f"reply {turn}")
    messages = history.to_messages("S")
    user_messages = [m.content for m in messages if m.role == "user"]
    assert len(user_messages) == MAX_HISTORY_TURNS
    assert user_messages[-1] == f"user {MAX_HISTORY_TURNS + 5}"


def test_old_tool_exchanges_are_dropped_but_their_spoken_text_stays() -> None:
    history = History()
    for turn in range(1, MAX_TOOL_TURNS + 3):
        history.add_user(turn, f"user {turn}")
        reply = history.add_assistant(turn, f"reply {turn}")
        call = ToolCallRequest(f"c{turn}", "get_clinic_info", "{}")
        history.add_tool_exchange(reply, (call,), [(f"c{turn}", "{}")])
    messages = history.to_messages("S")
    tool_ids = [m.tool_call_id for m in messages if m.role == "tool"]
    assert len(tool_ids) == MAX_TOOL_TURNS
    assert tool_ids[0] == f"c{3}"
    assert sum(m.content.startswith("reply") for m in messages) == MAX_TOOL_TURNS + 2
