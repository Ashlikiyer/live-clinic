from app.stats.latency import (
    BUCKET_MS,
    Rollup,
    TurnSample,
    mean,
    percentile,
    rollup,
    slowest_stage,
    summarize,
)

STAGES = {
    "vad_wait_ms": 600,
    "upload_ms": 20,
    "stt_ms": 600,
    "llm_ttft_ms": 250,
    "first_sentence_ms": 5,
    "tts_ms": 10,
}


def sample(total: int, **overrides: object) -> TurnSample:
    params: dict[str, object] = {"stages": STAGES, "total_ms": total}
    params.update(overrides)
    return TurnSample(**params)  # type: ignore[arg-type]


def test_percentiles_from_histograms_are_accurate_to_a_bucket() -> None:
    r = rollup(sample(t) for t in [1000, 1200, 1400, 1600, 3000])
    totals = r.histograms["total_ms"]
    assert percentile(totals, 50) == 1400 + BUCKET_MS // 2
    assert percentile(totals, 95) == 3000 + BUCKET_MS // 2
    assert percentile({}, 50) is None


def test_days_merge_to_the_same_numbers_as_one_big_rollup() -> None:
    monday = [sample(t) for t in (1500, 1600, 2600)]
    tuesday = [sample(t, interrupted=True, stop_ms=450) for t in (1400, 1900)]
    merged = rollup(monday)
    merged.merge(rollup(tuesday))
    assert merged == rollup(monday + tuesday)


def test_slow_turns_record_their_slowest_stage() -> None:
    slow = {**STAGES, "tts_ms": 1300}
    r = rollup([sample(1500), sample(2600, stages=slow), sample(2400)])
    assert r.slow_causes == {"tts_ms": 1, "vad_wait_ms": 1}
    assert slowest_stage(slow) == "tts_ms"
    assert slowest_stage({"vad_wait_ms": None}) is None


def test_summary_numbers() -> None:
    r = Rollup()
    for s in [
        sample(1500),
        sample(1800),
        sample(2500, interrupted=True, stop_ms=420),
        sample(1600, interrupted=True, stop_ms=480),
    ]:
        r.add(s)
    summary = summarize(r)
    assert summary["replies"] == 4
    assert summary["slow_turn_share"] == 0.25
    assert summary["interruptions"] == 2
    assert summary["avg_stop_ms"] == mean({"400": 1, "450": 1}) == 450
    assert summary["stage_medians"]["stt_ms"] == 625
    assert list(summary["total_ms_histogram"]) == ["1500", "1600", "1800", "2500"]


def test_empty_window() -> None:
    summary = summarize(Rollup())
    assert summary["replies"] == 0
    assert summary["median_total_ms"] is None
    assert summary["slow_turn_share"] is None
    assert summary["avg_stop_ms"] is None
