from app.call.busy import BUSY_AFTER_S, line_is_busy, should_hang_up


def test_a_short_limit_is_not_busy() -> None:
    assert not line_is_busy(0)
    assert not line_is_busy(BUSY_AFTER_S - 1)
    assert line_is_busy(BUSY_AFTER_S)


def test_mia_hangs_up_on_a_long_limit_or_repeated_ones() -> None:
    assert not should_hang_up(1, 5)  # one hiccup: apologize and carry on
    assert should_hang_up(2, 5)  # it keeps happening
    assert should_hang_up(1, 120)  # every model is out for minutes
