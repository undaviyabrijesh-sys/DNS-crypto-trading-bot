from __future__ import annotations


def position_size(equity: float, risk_fraction: float, entry: float, stop: float) -> float:
    """Base-asset quantity for linear spot-like contracts; fees/slippage excluded."""
    if equity <= 0 or not 0 < risk_fraction <= 0.05:
        raise ValueError("equity must be positive and risk_fraction in (0, 0.05]")
    distance = abs(entry - stop)
    if distance <= 0:
        raise ValueError("entry and stop must differ")
    return equity * risk_fraction / distance


def reward_risk(entry: float, stop: float, target: float, side: str) -> float:
    risk = abs(entry - stop)
    if risk == 0:
        raise ValueError("entry and stop must differ")
    reward = target - entry if side == "long" else entry - target
    return reward / risk
