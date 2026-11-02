"""Per-turn latency stages for the Latency X-ray. Pure, no I/O.

All server times are epoch ms on the server clock; client times are epoch ms on the browser
clock. `total_ms` only ever subtracts browser times from browser times, so clock skew never
affects it. `upload_ms` mixes clocks and is approximate, corrected by `clock_offset_ms`.
"""

import statistics
from dataclasses import dataclass
from typing import Any

STAGE_KEYS = (
    "vad_wait_ms",
    "upload_ms",
    "stt_ms",
    "llm_ttft_ms",
    "first_sentence_ms",
    "tts_ms",
)


@dataclass
class TurnTiming:
    turn_id: int
    # Browser time the caller stopped speaking (audio) or pressed send (typed).
    client_start_ts: int | None = None
    vad_wait_ms: int | None = None
    received_at: int | None = None
    # server clock - client clock, estimated at call start.
    clock_offset_ms: int = 0
    stt_ms: int | None = None
    llm_started_at: int | None = None
    first_token_at: int | None = None
    first_sentence_at: int | None = None
    tts_ms: int | None = None
    first_audio_client_ts: int | None = None
    interrupted: bool = False

    def upload_ms(self) -> int | None:
        if self.client_start_ts is None or self.received_at is None or self.vad_wait_ms is None:
            return None
        sent_at_server_clock = self.client_start_ts + self.vad_wait_ms + self.clock_offset_ms
        return max(0, self.received_at - sent_at_server_clock)

    def stages(self) -> dict[str, int | None]:
        def diff(end: int | None, start: int | None) -> int | None:
            return None if end is None or start is None else max(0, end - start)

        return {
            "vad_wait_ms": self.vad_wait_ms,
            "upload_ms": self.upload_ms(),
            "stt_ms": self.stt_ms,
            "llm_ttft_ms": diff(self.first_token_at, self.llm_started_at),
            "first_sentence_ms": diff(self.first_sentence_at, self.first_token_at),
            "tts_ms": self.tts_ms,
        }

    def total_ms(self) -> int | None:
        if self.first_audio_client_ts is None or self.client_start_ts is None:
            return None
        return max(0, self.first_audio_client_ts - self.client_start_ts)

    def event_payload(self) -> dict[str, Any]:
        total = self.total_ms()
        if total is None:
            # No audio played (e.g. interrupted first): fall back to the stage sum.
            total = sum(v for v in self.stages().values() if v is not None)
        return {
            "turn_id": self.turn_id,
            "stages": self.stages(),
            "total_ms": total,
            "interrupted": self.interrupted,
        }


def call_stats(totals: list[int], duration_s: float) -> dict[str, Any]:
    return {
        "duration_s": round(duration_s),
        "turn_count": len(totals),
        "median_reply_ms": round(statistics.median(totals)) if totals else None,
        "slowest_reply_ms": max(totals) if totals else None,
    }
