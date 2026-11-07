from types import SimpleNamespace

import pandas as pd
import pytest

from dns_bot.entries import find_entry_setups


def candles(start="2026-11-07T10:00:00Z", count=24):
    times = pd.date_range(start, periods=count, freq="3min", tz="UTC")
    return [
        {"timestamp": stamp, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}
        for stamp in times
    ]


def zone(kind="demand", created_at="2026-11-07T10:00:00Z"):
    if kind == "demand":
        return SimpleNamespace(
            kind=kind, proximal=100.0, distal=95.0,
            created_at=created_at, status="fresh", pattern="DBR",
        )
    return SimpleNamespace(
        kind=kind, proximal=100.0, distal=105.0,
        created_at=created_at, status="fresh", pattern="RBD",
    )


def test_demand_requires_later_close_above_lowest_low_touch_candle_high():
    rows = candles()
    rows[14].update(open=100.0, high=102.0, low=97.0, close=99.0)
    rows[15].update(open=99.0, high=101.0, low=95.5, close=99.5)
    rows[16].update(open=99.5, high=103.0, low=99.0, close=102.0)
    rows[17].update(open=102.5, high=104.0, low=102.0, close=103.0)

    result = find_entry_setups(pd.DataFrame(rows), [zone()])

    assert len(result) == 1
    assert result[0]["side"] == "LONG"
    assert result[0]["touch_candle_index"] == 15
    assert result[0]["tap_time"] == str(rows[15]["timestamp"])
    assert result[0]["confirmation_time"] == str(rows[16]["timestamp"])
    assert result[0]["entry"] == 102.5
    assert result[0]["stop"] < 95.0


def test_supply_requires_later_close_below_highest_high_touch_candle_low():
    rows = candles()
    rows[14].update(open=103.0, high=104.0, low=99.0, close=102.0)
    rows[15].update(open=104.0, high=106.0, low=100.0, close=104.0)
    rows[16].update(open=104.0, high=101.0, low=98.0, close=99.0)
    rows[17].update(open=98.5, high=99.0, low=97.0, close=98.0)

    result = find_entry_setups(pd.DataFrame(rows), [zone("supply")])

    assert len(result) == 1
    assert result[0]["side"] == "SHORT"
    assert result[0]["touch_candle_index"] == 15
    assert result[0]["confirmation_time"] == str(rows[16]["timestamp"])
    assert result[0]["entry"] == 98.5
    assert result[0]["stop"] > 105.0


def test_zone_is_not_usable_until_its_15m_confirmation_candle_closes():
    rows = candles()
    # The zone's 10:36 15m candle is only known at 10:51 (index 17).
    rows[14].update(open=100.0, high=102.0, low=97.0, close=101.5)
    rows[15].update(open=101.5, high=104.0, low=101.0, close=103.0)

    result = find_entry_setups(
        pd.DataFrame(rows), [zone(created_at="2026-11-07T10:36:00Z")]
    )

    assert result == []


def test_close_through_distal_boundary_invalidates_touch_sequence():
    rows = candles()
    rows[14].update(open=100.0, high=102.0, low=97.0, close=99.0)
    rows[15].update(open=98.0, high=99.0, low=94.0, close=94.5)
    rows[16].update(open=94.5, high=105.0, low=94.0, close=104.0)

    assert find_entry_setups(pd.DataFrame(rows), [zone()]) == []


def test_invalid_buffer_is_rejected():
    with pytest.raises(ValueError, match="buffer_atr"):
        find_entry_setups(pd.DataFrame(candles()), [zone()], buffer_atr=-0.1)


def test_touch_candle_cannot_confirm_itself_above_zone_edge():
    rows = candles()
    rows[14].update(open=100.0, high=102.0, low=97.0, close=101.5)

    assert find_entry_setups(pd.DataFrame(rows), [zone()]) == []


def test_missing_3m_candle_resets_touch_confirmation_sequence():
    rows = candles()
    rows[14].update(open=100.0, high=102.0, low=97.0, close=99.0)
    for index in range(15, len(rows)):
        rows[index]["timestamp"] += pd.Timedelta(minutes=3)
    rows[15].update(open=99.0, high=103.0, low=101.0, close=102.5)

    assert find_entry_setups(pd.DataFrame(rows), [zone()]) == []


def test_missing_next_entry_candle_prevents_signal():
    rows = candles()
    rows[14].update(open=100.0, high=102.0, low=97.0, close=99.0)
    rows[15].update(open=99.0, high=103.0, low=101.0, close=102.5)
    for index in range(16, len(rows)):
        rows[index]["timestamp"] += pd.Timedelta(minutes=3)

    assert find_entry_setups(pd.DataFrame(rows), [zone()]) == []
