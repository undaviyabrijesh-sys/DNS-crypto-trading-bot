import pandas as pd

from dns_bot.structure_zones import detect_structure_zones


def _base_frame(direction="up"):
    rows = [
        {"open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0, "volume": 10}
        for _ in range(15)
    ]
    if direction == "up":
        rows.append({"open": 99.0, "high": 101.0, "low": 98.5, "close": 100.0, "volume": 10})
        rows.append({"open": 100.0, "high": 122.0, "low": 99.0, "close": 121.0, "volume": 30})
    else:
        rows.append({"open": 100.0, "high": 101.5, "low": 99.0, "close": 100.0, "volume": 10})
        rows.append({"open": 100.0, "high": 101.0, "low": 78.0, "close": 79.0, "volume": 30})
    return pd.DataFrame(rows)


def test_structure_detector_finds_bullish_base_displacement():
    zones = detect_structure_zones(_base_frame("up"))
    assert zones
    demand = [z for z in zones if z.kind == "demand"]
    assert demand
    assert demand[0].method == "structure"
    assert demand[0].pattern in ("DBR", "RBR")
    assert demand[0].distal < demand[0].proximal
    assert demand[0].strength > 0.5


def test_structure_detector_finds_bearish_base_displacement():
    zones = detect_structure_zones(_base_frame("down"))
    supply = [z for z in zones if z.kind == "supply"]
    assert supply
    assert supply[0].method == "structure"
    assert supply[0].pattern in ("RBD", "DBD")
    assert supply[0].proximal < supply[0].distal


def test_structure_detector_rejects_small_non_displacement():
    frame = _base_frame("up")
    frame.loc[16, ["open", "high", "low", "close"]] = [100.0, 103.0, 99.0, 102.0]
    zones = detect_structure_zones(frame)
    assert not zones
