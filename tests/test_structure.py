import pandas as pd

from dns_bot.structure import detect_market_structure


def test_structure_events_are_confirmed_after_right_bars():
    df = pd.DataFrame({
        "high":  [10, 12, 15, 11, 10, 11, 16, 17, 18],
        "low":   [8, 9, 10, 7, 6, 8, 9, 10, 11],
        "close": [9, 11, 14, 9, 8, 10, 15, 16, 17],
    })
    events = detect_market_structure(df, left=1, right=1)
    pivot_event = next(e for e in events if e.event == "SWING_HIGH")
    assert pivot_event.pivot_index == 2
    assert pivot_event.index == 3


def test_invalid_structure_parameters_raise():
    df = pd.DataFrame({"high":[2,3,2,3], "low":[1,2,1,2], "close":[2,2,2,2]})
    try:
        detect_market_structure(df, left=0, right=1)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError")
