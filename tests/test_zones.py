import pandas as pd
from dns_bot.zones import detect_fvg_zones


def test_bullish_fvg_uses_first_candle_range():
    df = pd.DataFrame([
        {"open": 10, "high": 12, "low": 9, "close": 11},
        {"open": 12, "high": 15, "low": 11, "close": 14},
        {"open": 16, "high": 18, "low": 13, "close": 17},
    ])
    zones = detect_fvg_zones(df)
    assert len(zones) == 1
    assert zones[0].kind == "demand"
    assert zones[0].proximal == 12
    assert zones[0].distal == 9
