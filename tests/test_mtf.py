from types import SimpleNamespace

import pytest

from dns_bot.mtf import align_setups_to_bias, latest_structure_bias


def test_latest_confirmed_break_sets_bias():
    events = [
        SimpleNamespace(event="BOS", direction="bullish", index=10),
        SimpleNamespace(event="SWING_HIGH", direction="bearish", index=12),
        SimpleNamespace(event="CHOCH", direction="bearish", index=15),
    ]
    assert latest_structure_bias(events) == "bearish"


def test_no_break_means_neutral():
    assert latest_structure_bias([]) == "neutral"


@pytest.mark.parametrize(
    "bias, expected",
    [("bullish", ["LONG"]), ("bearish", ["SHORT"]), ("neutral", [])],
)
def test_only_aligned_setups_are_kept(bias, expected):
    setups = [{"side": "LONG", "id": 1}, {"side": "SHORT", "id": 2}]
    accepted, rejected = align_setups_to_bias(setups, bias)
    assert [x["side"] for x in accepted] == expected
    assert len(accepted) + len(rejected) == 2


def test_invalid_bias_is_rejected():
    with pytest.raises(ValueError):
        align_setups_to_bias([], "sideways")
