import pandas as pd
import pytest

from dns_bot.delta_data import history_quality


def candle_frame(times):
    return pd.DataFrame({"timestamp": pd.to_datetime(times, utc=True)})


def test_contiguous_history_is_usable():
    frame = candle_frame([
        "2026-11-07T00:00:00Z",
        "2026-11-07T00:15:00Z",
        "2026-11-07T00:30:00Z",
    ])
    quality = history_quality(frame, "15m", now="2026-11-07T00:45:00Z")

    assert quality["is_usable"] is True
    assert quality["has_gaps"] is False
    assert quality["missing_candles"] == 0
    assert quality["age_minutes"] == 0


def test_history_counts_missing_complete_candles():
    frame = candle_frame([
        "2026-11-07T00:00:00Z",
        "2026-11-07T00:15:00Z",
        "2026-11-07T00:45:00Z",
    ])
    quality = history_quality(frame, "15m", now="2026-11-07T01:00:00Z")

    assert quality["has_gaps"] is True
    assert quality["gap_intervals"] == 1
    assert quality["missing_candles"] == 1
    assert quality["irregular_intervals"] == 0
    assert quality["is_usable"] is False


def test_history_flags_irregular_timestamp_spacing():
    frame = candle_frame([
        "2026-11-07T00:00:00Z",
        "2026-11-07T00:17:00Z",
        "2026-11-07T00:32:00Z",
    ])
    quality = history_quality(frame, "15m", now="2026-11-07T00:47:00Z")

    assert quality["has_gaps"] is True
    assert quality["gap_intervals"] == 1
    assert quality["irregular_intervals"] == 1
    assert quality["missing_candles"] == 0


def test_history_flags_stale_latest_completed_candle():
    frame = candle_frame([
        "2026-11-07T00:00:00Z",
        "2026-11-07T00:15:00Z",
    ])
    quality = history_quality(frame, "15m", now="2026-11-07T02:00:00Z")

    assert quality["is_stale"] is True
    assert quality["age_minutes"] == 90
    assert quality["is_usable"] is False


def test_history_quality_rejects_empty_or_unsupported_input():
    with pytest.raises(ValueError, match="empty"):
        history_quality(pd.DataFrame(), "15m")
    with pytest.raises(ValueError, match="Unsupported"):
        history_quality(candle_frame(["2026-11-07T00:00:00Z"]), "2m")
