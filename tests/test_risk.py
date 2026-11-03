import pytest
from dns_bot.risk import position_size, reward_risk


def test_position_size():
    assert position_size(10_000, 0.01, 100, 90) == 10


def test_reward_risk():
    assert reward_risk(100, 90, 120, "long") == 2


def test_rejects_zero_stop_distance():
    with pytest.raises(ValueError):
        position_size(10_000, 0.01, 100, 100)
