from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from dns_bot.zones import Zone


@dataclass
class TradeScenario:
    side: str
    zone_pattern: str
    zone_low: float
    zone_high: float
    entry_low: float
    entry_high: float
    stop: float
    targets: list[float]
    risk_reward: list[float]
    trigger: str
    invalidation: str
    status: str = "CONDITIONAL"


def _bounds(zone: Zone) -> tuple[float, float]:
    return tuple(sorted((float(zone.proximal), float(zone.distal))))


def _rr(entry: float, stop: float, target: float, side: str) -> float:
    risk = entry - stop if side == "LONG" else stop - entry
    reward = target - entry if side == "LONG" else entry - target
    return round(reward / risk, 2) if risk > 0 and reward > 0 else 0.0


def generate_trade_scenarios(
    current_price: float,
    zones: Iterable[Zone],
    max_scenarios: int = 2,
) -> list[TradeScenario]:
    """Build conditional pullback/rejection plans from active opposing zones.

    No market order is implied. Entry is the zone band; targets are opposing
    zones beyond the entry. Invalid, broken, or already-crossed zones are ignored.
    """
    if current_price <= 0:
        raise ValueError("current_price must be positive")
    if max_scenarios < 1:
        raise ValueError("max_scenarios must be at least 1")

    active = [z for z in zones if z.status not in ("broken", "invalidated")]
    demands = [(z, *_bounds(z)) for z in active if z.kind == "demand"]
    supplies = [(z, *_bounds(z)) for z in active if z.kind == "supply"]
    scenarios: list[TradeScenario] = []

    below = sorted(
        [(z, lo, hi) for z, lo, hi in demands if hi < current_price],
        key=lambda item: current_price - item[2],
    )
    above = sorted(
        [(z, lo, hi) for z, lo, hi in supplies if lo > current_price],
        key=lambda item: item[1] - current_price,
    )

    if below:
        zone, low, high = below[0]
        entry = (low + high) / 2
        stop = low - max((high - low) * 0.25, current_price * 0.0005)
        targets = [lo for _, lo, _ in above if lo > entry][:3]
        rr = [_rr(entry, stop, target, "LONG") for target in targets]
        long_zone_label = "RBS support" if str(zone.pattern).upper() == "RBS" else "demand"
        scenarios.append(TradeScenario(
            "LONG", zone.pattern, low, high, low, high, round(stop, 8),
            targets, rr,
            f"Wait for price to retest {long_zone_label} and a completed-candle bullish rejection/confirmation.",
            f"Invalidate on a completed candle close below the {long_zone_label} distal edge.",
        ))

    if above:
        zone, low, high = above[0]
        entry = (low + high) / 2
        stop = high + max((high - low) * 0.25, current_price * 0.0005)
        targets = [hi for _, _, hi in below if hi < entry][:3]
        rr = [_rr(entry, stop, target, "SHORT") for target in targets]
        short_zone_label = "SBR resistance" if str(zone.pattern).upper() == "SBR" else "supply"
        scenarios.append(TradeScenario(
            "SHORT", zone.pattern, low, high, low, high, round(stop, 8),
            targets, rr,
            f"Wait for price to retest {short_zone_label} and a completed-candle bearish rejection/confirmation.",
            f"Invalidate on a completed candle close above the {short_zone_label} distal edge.",
        ))

    scenarios.sort(key=lambda s: min(
        abs(current_price - s.zone_low), abs(current_price - s.zone_high)
    ))
    return scenarios[:max_scenarios]


def scenarios_frame(scenarios: list[TradeScenario]) -> list[dict]:
    return [asdict(scenario) for scenario in scenarios]
