"""WebSocket event schemas. Client events are validated; server events are built here.

Names follow the spec. Two optional fields extend the spec so the browser can report its own
stage timings: `vad_wait_ms` on the audio header and `tts_ms` on `tts.first_audio`.
`call.start` may carry `resume_call_id` to rejoin a call after a dropped connection.
"""

import json
import struct
import time
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

MAX_TYPED_CHARS = 300
MAX_UTTERANCE_SECONDS = 30
# 16 kHz * 16-bit mono * 30 s, plus a little room for the WAV header.
MAX_UTTERANCE_BYTES = 16_000 * 2 * MAX_UTTERANCE_SECONDS + 1024
MAX_AUDIO_HEADER_BYTES = 4096


def now_ms() -> int:
    return int(time.time() * 1000)


class _ClientEvent(BaseModel):
    ts: int | None = None


class CallStart(_ClientEvent):
    type: Literal["call.start"]
    voice: Literal["kokoro", "lite"] = "kokoro"
    captions: bool = False
    resume_call_id: str | None = None


class TextMessage(_ClientEvent):
    type: Literal["text.message"]
    text: Annotated[str, Field(min_length=1, max_length=MAX_TYPED_CHARS)]


class UserInterrupt(_ClientEvent):
    type: Literal["user.interrupt"]
    turn_id: int
    played_text: Annotated[str, Field(max_length=4000)] = ""
    played_ms: int = 0


class TtsFirstAudio(_ClientEvent):
    type: Literal["tts.first_audio"]
    turn_id: int
    tts_ms: int | None = None


class CallEnd(_ClientEvent):
    type: Literal["call.end"]
    # "silence": the caller didn't answer "Are you still there?" (an addition to the spec).
    reason: Literal["user", "silence"] = "user"


class Ping(_ClientEvent):
    type: Literal["ping"]


ClientEvent = Annotated[
    CallStart | TextMessage | UserInterrupt | TtsFirstAudio | CallEnd | Ping,
    Field(discriminator="type"),
]
_client_event_adapter: TypeAdapter[ClientEvent] = TypeAdapter(ClientEvent)


def parse_client_event(raw: str) -> ClientEvent | None:
    """A validated client event, or None if the frame is not one."""
    try:
        return _client_event_adapter.validate_json(raw)
    except ValidationError:
        return None


class AudioHeader(BaseModel):
    type: Literal["audio.utterance"]
    turn_id: int
    speech_end_ts: int
    vad_wait_ms: int | None = None


class AudioFrameError(ValueError):
    pass


def parse_audio_frame(frame: bytes) -> tuple[AudioHeader, bytes]:
    """Split a binary frame: 4-byte big-endian header length + JSON header + WAV bytes."""
    if len(frame) < 4:
        raise AudioFrameError("Frame too short.")
    (header_len,) = struct.unpack(">I", frame[:4])
    if header_len == 0 or header_len > MAX_AUDIO_HEADER_BYTES or 4 + header_len > len(frame):
        raise AudioFrameError("Bad header length.")
    try:
        header = AudioHeader.model_validate(json.loads(frame[4 : 4 + header_len]))
    except (ValueError, ValidationError) as exc:
        raise AudioFrameError("Bad header.") from exc
    wav = frame[4 + header_len :]
    if not wav:
        raise AudioFrameError("No audio.")
    if len(wav) > MAX_UTTERANCE_BYTES:
        raise AudioFrameError("Utterance longer than 30 seconds.")
    return header, wav


def build_audio_frame(header: dict[str, Any], wav: bytes) -> bytes:
    """Inverse of parse_audio_frame (used by tests and scripts)."""
    encoded = json.dumps(header).encode()
    return struct.pack(">I", len(encoded)) + encoded + wav


def server_event(type_: str, **payload: Any) -> dict[str, Any]:
    return {"type": type_, "ts": now_ms(), **payload}
