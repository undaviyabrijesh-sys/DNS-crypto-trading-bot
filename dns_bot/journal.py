from __future__ import annotations

from pathlib import Path
import pandas as pd

REQUIRED = {
    "symbol", "side", "zone_method", "zone_pattern", "net_result_r",
    "exit_reason", "zone_score", "trend_aligned", "touch_number",
}


def load_trades(source) -> pd.DataFrame:
    """Load a backtest/journal CSV and validate the minimum learning fields."""
    df = pd.read_csv(source) if not isinstance(source, pd.DataFrame) else source.copy()
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f"Trade journal missing columns: {sorted(missing)}")
    df["net_result_r"] = pd.to_numeric(df["net_result_r"], errors="coerce")
    df = df.dropna(subset=["net_result_r"]).copy()
    df["trend_aligned"] = df["trend_aligned"].astype(str).str.lower().isin(["true", "1", "yes"])
    df["zone_score"] = pd.to_numeric(df["zone_score"], errors="coerce")
    df["touch_number"] = pd.to_numeric(df["touch_number"], errors="coerce")
    return df


def performance_summary(trades: pd.DataFrame) -> dict:
    """Return realised trade stats after costs, expressed in R multiples."""
    if trades.empty:
        return {"trades": 0, "message": "No completed trades to analyse."}
    r = trades["net_result_r"].astype(float)
    wins, losses = r[r > 0], r[r <= 0]
    equity = (1 + r * 0.01).cumprod()
    dd = equity / equity.cummax() - 1
    gross_loss = abs(float(losses.sum()))
    return {
        "trades": int(len(r)),
        "win_rate_pct": round(float((r > 0).mean() * 100), 2),
        "expectancy_r": round(float(r.mean()), 4),
        "profit_factor": round(float(wins.sum() / gross_loss), 3) if gross_loss else None,
        "net_r": round(float(r.sum()), 2),
        "average_win_r": round(float(wins.mean()), 3) if len(wins) else 0.0,
        "average_loss_r": round(float(losses.mean()), 3) if len(losses) else 0.0,
        "max_drawdown_pct_at_1pct_risk": round(float(dd.min() * 100), 2),
        "max_consecutive_losses": _max_streak((r <= 0).tolist()),
        "max_consecutive_wins": _max_streak((r > 0).tolist()),
    }


def _max_streak(values: list[bool]) -> int:
    best = current = 0
    for value in values:
        current = current + 1 if value else 0
        best = max(best, current)
    return best


def breakdown(trades: pd.DataFrame, dimensions: list[str]) -> pd.DataFrame:
    """Group outcomes by setup context; small samples are explicitly flagged."""
    usable = [column for column in dimensions if column in trades.columns]
    if not usable or trades.empty:
        return pd.DataFrame()
    rows = []
    for keys, group in trades.groupby(usable, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        r = group["net_result_r"].astype(float)
        wins, losses = r[r > 0], r[r <= 0]
        gross_loss = abs(float(losses.sum()))
        item = dict(zip(usable, keys))
        item.update({
            "trades": len(group),
            "win_rate_pct": round(float((r > 0).mean() * 100), 2),
            "expectancy_r": round(float(r.mean()), 4),
            "profit_factor": round(float(wins.sum() / gross_loss), 3) if gross_loss else None,
            "net_r": round(float(r.sum()), 2),
            "sample_quality": "low" if len(group) < 30 else "developing" if len(group) < 100 else "usable",
        })
        rows.append(item)
    return pd.DataFrame(rows).sort_values(["expectancy_r", "trades"], ascending=[False, False])


def learning_report(trades: pd.DataFrame) -> dict:
    """Produce evidence-based observations; never fit a model on tiny samples."""
    summary = performance_summary(trades)
    groups = {
        "zone_pattern": breakdown(trades, ["zone_pattern"]),
        "zone_method": breakdown(trades, ["zone_method"]),
        "trend_alignment": breakdown(trades, ["trend_aligned"]),
        "zone_score_band": breakdown(
            trades.assign(score_band=pd.cut(
                trades["zone_score"], bins=[-1, 49, 69, 84, 101],
                labels=["below_50", "50_69", "70_84", "85_plus"]
            )), ["score_band"]
        ) if not trades.empty else pd.DataFrame(),
        "side": breakdown(trades, ["side"]),
        "touch_number": breakdown(trades, ["touch_number"]),
    }
    enough = len(trades) >= 200
    return {
        "summary": summary,
        "groups": groups,
        "model_training_ready": enough,
        "training_note": (
            "At least 200 completed trades are available for an initial time-ordered "
            "walk-forward experiment; keep a separate untouched test period."
            if enough else
            f"Only {len(trades)} completed trades. Keep this as descriptive analysis; "
            "do not train or tune a predictive model yet. Aim for 200+ trades across "
            "different market regimes, then use chronological train/validation/test splits."
        ),
    }


def save_report(trades: pd.DataFrame, output_dir: str | Path) -> dict:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    trades.to_csv(out / "journal_trades.csv", index=False)
    report = learning_report(trades)
    for name, frame in report["groups"].items():
        frame.to_csv(out / f"journal_{name}.csv", index=False)
    return report
