"""When is Mia's line "busy"? Groq's free tier limits every model per minute and per day. Pure.

A short limit is waited out (the LLM provider retries for up to 4 s). A long one, where every
model is limited, means callers should hear a friendly busy line instead of repeated apologies.
"""

BUSY_NOTICE = "Mia's line is busy right now. Please try again in a minute."

# Every model limited for at least this long: the line is busy.
BUSY_AFTER_S = 20.0
# Mid-call: rate-limited replies in a row before Mia gives up and says the busy line.
MAX_RATE_LIMITED_REPLIES = 2


def line_is_busy(busy_seconds: float) -> bool:
    return busy_seconds >= BUSY_AFTER_S


def should_hang_up(rate_limited_in_a_row: int, busy_seconds: float) -> bool:
    """End the call with the busy line: the limit is long, or keeps hitting reply after reply."""
    return line_is_busy(busy_seconds) or rate_limited_in_a_row >= MAX_RATE_LIMITED_REPLIES
