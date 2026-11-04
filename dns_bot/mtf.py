from __future__ import annotations

from collections.abc import Iterable, Mapping


def latest_structure_bias(events: Iterable[object]) -> str:
    """Return bullish/bearish from the latest confirmed BOS/CHoCH, else neutral."""
    breaks = [
        event for event in events
        if getattr(event, "event", None) in {"BOS", "CHOCH"}
        and getattr(event, "direction", None) in {"bullish", "bearish"}
    ]
    if not breaks:
        return "neutral"
    latest = max(breaks, key=lambda event: int(getattr(event, "index", -1)))
    return str(latest.direction)


def align_setups_to_bias(
    setups: Iterable[Mapping], bias: str
) -> tuple[list[dict], list[dict]]:
    """Keep only setups aligned with confirmed higher-timeframe structure.

    Neutral structure intentionally blocks both directions; callers can display
    the rejected candidates for transparency. This is a directional filter,
    not a claim that a setup has positive expectancy.
    """
    if bias not in {"bullish", "bearish", "neutral"}:
        raise ValueError("bias must be bullish, bearish, or neutral")
    allowed_side = {"bullish": "LONG", "bearish": "SHORT"}.get(bias)
    accepted, filtered = [], []
    for setup in setups:
        item = dict(setup)
        if allowed_side and str(item.get("side", "")).upper() == allowed_side:
            accepted.append(item)
        else:
            filtered.append(item)
    return accepted, filtered
