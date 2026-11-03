import pandas as pd

from dns_bot.journal import load_trades, performance_summary, breakdown, learning_report


def sample_trades(n=4):
    return pd.DataFrame({
        "symbol": ["BTC/USDT"] * n,
        "side": ["long", "short", "long", "short"][:n],
        "zone_method": ["fvg", "base_leg", "fvg", "base_leg"][:n],
        "zone_pattern": ["FVG", "DBR", "FVG", "RBD"][:n],
        "net_result_r": [2.0, -1.0, 1.5, -0.5][:n],
        "exit_reason": ["target", "stop", "target", "stop"][:n],
        "zone_score": [80, 60, 75, 55][:n],
        "trend_aligned": [True, False, True, False][:n],
        "touch_number": [1, 1, 1, 1][:n],
    })


def test_summary_uses_net_r_and_counts_loss_streak():
    summary = performance_summary(sample_trades())
    assert summary["trades"] == 4
    assert summary["net_r"] == 2.0
    assert summary["max_consecutive_losses"] == 1


def test_breakdown_flags_small_samples():
    result = breakdown(sample_trades(), ["zone_pattern"])
    assert set(result["sample_quality"]) == {"low"}


def test_learning_report_does_not_train_on_small_sample():
    report = learning_report(sample_trades())
    assert report["model_training_ready"] is False
    assert "do not train" in report["training_note"]


def test_load_trades_rejects_missing_fields():
    try:
        load_trades(pd.DataFrame({"net_result_r": [1]}))
    except ValueError as exc:
        assert "missing" in str(exc).lower()
    else:
        raise AssertionError("Expected missing-field validation")
