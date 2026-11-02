"""Conversation history and barge-in trimming. Pure, no I/O.

After an interruption the assistant turn keeps only the words the caller actually heard,
so the agent never "remembers" saying something that was cut off.
"""

from dataclasses import dataclass, field

from app.providers.base import ChatMessage

MAX_HISTORY_TURNS = 12


@dataclass
class HistoryEntry:
    turn_id: int
    role: str  # "user" | "assistant"
    text: str
    interrupted: bool = False


@dataclass
class History:
    entries: list[HistoryEntry] = field(default_factory=list)

    def add_user(self, turn_id: int, text: str) -> None:
        self.entries.append(HistoryEntry(turn_id, "user", text))

    def add_assistant(self, turn_id: int, text: str) -> HistoryEntry:
        entry = HistoryEntry(turn_id, "assistant", text)
        self.entries.append(entry)
        return entry

    def assistant_for(self, turn_id: int) -> HistoryEntry | None:
        return next(
            (e for e in reversed(self.entries) if e.role == "assistant" and e.turn_id == turn_id),
            None,
        )

    def apply_interrupt(self, turn_id: int, played_text: str) -> HistoryEntry | None:
        """Trim the assistant reply for `turn_id` to what was played. Returns the entry."""
        entry = self.assistant_for(turn_id)
        if entry is None:
            return None
        entry.text = trim_to_played(entry.text, played_text)
        entry.interrupted = True
        return entry

    def to_messages(self, system_prompt: str) -> list[ChatMessage]:
        """System prompt plus the last MAX_HISTORY_TURNS caller turns and their replies."""
        user_turns = [e.turn_id for e in self.entries if e.role == "user"]
        cutoff = user_turns[-MAX_HISTORY_TURNS] if len(user_turns) > MAX_HISTORY_TURNS else None
        recent = [e for e in self.entries if cutoff is None or e.turn_id >= cutoff]
        messages = [ChatMessage("system", system_prompt)]
        for e in recent:
            if e.role == "assistant" and not e.text:
                continue
            text = f"{e.text} [interrupted by caller]" if e.interrupted else e.text
            messages.append(ChatMessage("user" if e.role == "user" else "assistant", text))
        return messages


def trim_to_played(full_text: str, played_text: str) -> str:
    """The part of `full_text` that was played, never longer than what was generated.

    The client reports the played text; it should be a prefix of the generated text, but
    TTS normalization can change spacing, so trust the word count rather than the characters.
    """
    played_words = played_text.split()
    if not played_words:
        return ""
    full_words = full_text.split()
    return " ".join(full_words[: len(played_words)])
