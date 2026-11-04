from dns_bot.scenarios import generate_trade_scenarios
from dns_bot.zones import Zone


def zone(kind, proximal, distal, pattern):
    return Zone(kind, "base_leg", proximal, distal, "2026-01-01", 1, 2,
                0.8, pattern, status="fresh", created_index=3)


def test_scenarios_use_nearest_demand_and_supply_and_are_conditional():
    zones = [
        zone("demand", 99, 95, "DBR"),
        zone("demand", 89, 85, "SWING_LOW"),
        zone("supply", 110, 115, "RBD"),
        zone("supply", 120, 125, "SWING_HIGH"),
    ]
    result = generate_trade_scenarios(105, zones)
    assert {item.side for item in result} == {"LONG", "SHORT"}
    long = next(item for item in result if item.side == "LONG")
    short = next(item for item in result if item.side == "SHORT")
    assert (long.zone_low, long.zone_high) == (95, 99)
    assert (short.zone_low, short.zone_high) == (110, 115)
    assert long.status == short.status == "CONDITIONAL"
    assert long.targets[0] == 110
    assert short.targets[0] == 99


def test_broken_zones_are_ignored():
    demand = zone("demand", 99, 95, "DBR")
    demand.status = "broken"
    assert generate_trade_scenarios(105, [demand]) == []


def test_rbs_and_sbr_flip_zones_keep_both_trade_sides_eligible():
    rbs = zone("demand", 99, 95, "RBS")
    sbr = zone("supply", 110, 115, "SBR")

    result = generate_trade_scenarios(105, [rbs, sbr])

    assert {item.side for item in result} == {"LONG", "SHORT"}
    long = next(item for item in result if item.side == "LONG")
    short = next(item for item in result if item.side == "SHORT")
    assert long.zone_pattern == "RBS"
    assert short.zone_pattern == "SBR"
    assert "RBS support" in long.trigger
    assert "SBR resistance" in short.trigger
