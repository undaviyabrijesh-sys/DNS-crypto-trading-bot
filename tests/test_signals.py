import pandas as pd
from dns_bot.signals import confirmation_signal
from dns_bot.zones import Zone


def test_demand_touch_then_close_confirmation_enters_next_open():
    candles = pd.DataFrame([
        {"open": 100, "high": 102, "low": 99, "close": 101},
        {"open": 98, "high": 101, "low": 95, "close": 97},
        {"open": 97, "high": 103, "low": 96, "close": 102},
        {"open": 103, "high": 105, "low": 102, "close": 104},
    ])
    zone = Zone("demand", "fvg", 100, 90, "t0", 0, 0, 1.0, "FVG")
    signal = confirmation_signal(candles, zone)
    assert signal is not None
    assert signal.side == "long"
    assert signal.entry == 103
    assert signal.stop == 95


def test_supply_touch_then_close_confirmation_enters_next_open():
    candles = pd.DataFrame([
        {"open": 100, "high": 102, "low": 99, "close": 101},
        {"open": 102, "high": 111, "low": 99, "close": 108},
        {"open": 108, "high": 109, "low": 95, "close": 98},
        {"open": 97, "high": 98, "low": 94, "close": 95},
    ])
    zone = Zone("supply", "fvg", 100, 110, "t0", 0, 0, 1.0, "FVG")
    signal = confirmation_signal(candles, zone)
    assert signal is not None
    assert signal.side == "short"
    assert signal.entry == 97
    assert signal.stop == 111
