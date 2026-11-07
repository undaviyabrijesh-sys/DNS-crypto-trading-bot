import pandas as pd
from dns_bot.zones import Zone, detect_fvg_zones, detect_base_leg_zones, track_zone_lifecycle


def test_bullish_fvg_returns_gap_bounds():
    df = pd.DataFrame([
        {"open": 10, "high": 12, "low": 9, "close": 11},
        {"open": 12, "high": 15, "low": 11, "close": 14},
        {"open": 16, "high": 18, "low": 13, "close": 17},
    ])
    zones = detect_fvg_zones(df)
    assert len(zones) == 1
    assert zones[0].kind == "demand"
    assert zones[0].proximal == 13
    assert zones[0].distal == 12


def test_bearish_fvg_returns_gap_bounds():
    df = pd.DataFrame([
        {"open": 14, "high": 16, "low": 12, "close": 13},
        {"open": 12, "high": 14, "low": 10, "close": 11},
        {"open": 9, "high": 11, "low": 7, "close": 8},
    ])
    zones = detect_fvg_zones(df)
    assert len(zones) == 1
    assert zones[0].kind == "supply"
    assert zones[0].proximal == 11
    assert zones[0].distal == 12


def test_demand_counts_defended_retests_not_taps():
    df = pd.DataFrame([
        {"open": 105, "high": 106, "low": 104, "close": 105},
        {"open": 104, "high": 105, "low": 103, "close": 104},
        {"open": 104, "high": 105, "low": 103, "close": 104},
        {"open": 103, "high": 106, "low": 102, "close": 105},
        {"open": 105, "high": 107, "low": 105, "close": 106},
    ])
    zone = Zone("demand", "test", 104, 102, "0", 0, 0, 0.6, "DBR", created_index=0)
    result = track_zone_lifecycle(df, [zone])[0]
    assert result.touches == 1
    assert result.defended_retests == 1
    assert result.status == "tested"
    assert result.score > 0
    assert result.score <= result.strength


def test_demand_break_creates_sbr_flip():
    df = pd.DataFrame([
        {"open": 105, "high": 106, "low": 104, "close": 105},
        {"open": 103, "high": 104, "low": 100, "close": 101},
        {"open": 99, "high": 101, "low": 98, "close": 99},
        {"open": 100, "high": 103, "low": 99, "close": 102},
    ])
    zone = Zone("demand", "test", 104, 102, "0", 0, 0, 0.8, "DBR", created_index=0)
    result = track_zone_lifecycle(df, [zone])
    assert result[0].status == "broken"
    assert result[1].kind == "supply"
    assert result[1].pattern == "SBR"


def test_supply_break_creates_rbs_flip():
    df = pd.DataFrame([
        {"open": 95, "high": 96, "low": 94, "close": 95},
        {"open": 101, "high": 104, "low": 100, "close": 103},
        {"open": 105, "high": 108, "low": 104, "close": 107},
        {"open": 103, "high": 105, "low": 102, "close": 104},
    ])
    zone = Zone("supply", "test", 102, 104, "0", 0, 0, 0.8, "RBD", created_index=0)
    result = track_zone_lifecycle(df, [zone])
    assert result[0].status == "broken"
    assert result[1].kind == "demand"
    assert result[1].pattern == "RBS"


def test_swing_high_uses_full_origin_candle_and_confirmation_time():
    rows = []
    for i in range(20):
        price = 100.0 + (0.15 if i % 2 else -0.15)
        rows.append({
            "timestamp": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(minutes=15 * i),
            "open": price,
            "high": price + 1.0,
            "low": price - 1.0,
            "close": price + (0.1 if i % 2 else -0.1),
        })
    # A clear swing high followed by a three-candle displacement.
    rows[10] = {"timestamp": rows[10]["timestamp"], "open": 119.0,
                "high": 121.0, "low": 118.0, "close": 120.0}
    for i, close in zip((11, 12, 13), (116.0, 113.0, 110.0)):
        rows[i] = {"timestamp": rows[i]["timestamp"], "open": close + 1.0,
                   "high": close + 2.0, "low": close - 1.0, "close": close}
    zones = detect_base_leg_zones(pd.DataFrame(rows))
    swing = [z for z in zones if z.pattern == "SWING_HIGH"]
    assert swing
    assert swing[0].proximal == 118.0
    assert swing[0].distal == 121.0
    assert swing[0].created_index == 13
    assert swing[0].created_at == str(rows[13]["timestamp"])


def test_latest_only_zone_scan_matches_full_scan_for_current_confirmation():
    rows = []
    for i in range(20):
        price = 100.0 + (0.15 if i % 2 else -0.15)
        rows.append({
            "timestamp": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(minutes=15 * i),
            "open": price,
            "high": price + 1.0,
            "low": price - 1.0,
            "close": price + (0.1 if i % 2 else -0.1),
        })
    rows[10] = {"timestamp": rows[10]["timestamp"], "open": 119.0,
                "high": 121.0, "low": 118.0, "close": 120.0}
    for i, close in zip((11, 12, 13), (116.0, 113.0, 110.0)):
        rows[i] = {"timestamp": rows[i]["timestamp"], "open": close + 1.0,
                   "high": close + 2.0, "low": close - 1.0, "close": close}

    current_window = pd.DataFrame(rows[:14])
    full_scan = detect_base_leg_zones(current_window)
    expected = [zone.to_dict() for zone in full_scan if zone.created_index == len(current_window) - 1]
    latest_scan = detect_base_leg_zones(current_window, only_latest=True)

    assert [zone.to_dict() for zone in latest_scan] == expected
    assert any(zone.pattern == "SWING_HIGH" for zone in latest_scan)
