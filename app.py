from __future__ import annotations

import streamlit as st
import plotly.graph_objects as go

from dns_bot.data import fetch_ohlcv
from dns_bot.zones import detect_fvg_zones, detect_base_leg_zones
from dns_bot.journal import load_trades, learning_report

st.set_page_config(page_title="DNS Trader", layout="wide")
st.title("DNS Trader")
st.caption("BTC / ETH • Supply & Demand research desk • Public market data • Paper-only")

market_tab, journal_tab = st.tabs(["Market desk", "Trade journal & learning"])

with market_tab:
    with st.sidebar:
        st.header("Market")
        exchange_id = st.selectbox("Exchange", ["binance", "bybit", "okx"], index=0)
        symbol = st.selectbox("Pair", ["BTC/USDT", "ETH/USDT"])
        timeframe = st.selectbox("Timeframe", ["1m", "3m", "5m", "15m", "1h", "4h"], index=3)
        limit = st.slider("Candles", 100, 1000, 500, 50)
        detector = st.selectbox("Zone detector", ["Both", "FVG", "Base / Leg"])
        refresh = st.button("Fetch latest candles", type="primary")

    if "candles" not in st.session_state or refresh:
        try:
            st.session_state.candles = fetch_ohlcv(exchange_id, symbol, timeframe, limit)
            st.session_state.load_error = None
        except Exception as exc:
            st.session_state.load_error = str(exc)

    if st.session_state.get("load_error"):
        st.error(f"Market data unavailable: {st.session_state.load_error}")
    elif "candles" in st.session_state:
        df = st.session_state.candles
        zones = []
        if detector in ("Both", "FVG"):
            zones.extend(detect_fvg_zones(df))
        if detector in ("Both", "Base / Leg"):
            zones.extend(detect_base_leg_zones(df))

        left, mid, right = st.columns(3)
        left.metric("Last price", f"{df.close.iloc[-1]:,.2f}")
        mid.metric("Candles loaded", f"{len(df):,}")
        right.metric("Zones detected", f"{len(zones):,}")

        fig = go.Figure(data=[go.Candlestick(
            x=df.timestamp, open=df.open, high=df.high, low=df.low, close=df.close,
            name=symbol
        )])
        for zone in zones[-30:]:
            color = "rgba(0,170,100,0.18)" if zone.kind == "demand" else "rgba(220,60,60,0.18)"
            fig.add_hrect(y0=min(zone.distal, zone.proximal), y1=max(zone.distal, zone.proximal),
                          fillcolor=color, line_width=1,
                          annotation_text=f"{zone.kind.upper()} · {zone.method} · {zone.pattern}",
                          annotation_position="top left")
        fig.update_layout(height=680, xaxis_rangeslider_visible=False,
                          template="plotly_dark", margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, use_container_width=True)
        st.subheader("Detected zones")
        if zones:
            st.dataframe([z.to_dict() for z in sorted(zones, key=lambda z: z.created_at, reverse=True)],
                         use_container_width=True, hide_index=True)
        else:
            st.info("No zones detected with the current mechanical definitions.")

with journal_tab:
    st.subheader("Learn from completed trades")
    st.write("Upload a backtest trade CSV. The journal compares setup types and context using net R after fees/slippage.")
    uploaded = st.file_uploader("Trade history CSV", type=["csv"])
    if uploaded is not None:
        try:
            trades = load_trades(uploaded)
            report = learning_report(trades)
            metrics = report["summary"]
            cols = st.columns(4)
            cols[0].metric("Completed trades", metrics["trades"])
            cols[1].metric("Win rate", f'{metrics["win_rate_pct"]:.1f}%')
            cols[2].metric("Expectancy", f'{metrics["expectancy_r"]:.3f} R')
            cols[3].metric("Profit factor", metrics["profit_factor"] if metrics["profit_factor"] is not None else "—")
            st.write(f'Net result: **{metrics["net_r"]:.2f} R** · Max drawdown at 1% risk: **{metrics["max_drawdown_pct_at_1pct_risk"]:.2f}%** · Max losing streak: **{metrics["max_consecutive_losses"]}**')
            st.info(report["training_note"])
            for title, key in [
                ("By zone pattern", "zone_pattern"),
                ("By detector", "zone_method"),
                ("Trend alignment", "trend_alignment"),
                ("Zone score band", "zone_score_band"),
                ("Long vs short", "side"),
                ("Retest number", "touch_number"),
            ]:
                st.markdown(f"#### {title}")
                frame = report["groups"][key]
                if frame.empty:
                    st.caption("Not enough data for this breakdown.")
                else:
                    st.dataframe(frame, use_container_width=True, hide_index=True)
            st.download_button("Download validated journal CSV", trades.to_csv(index=False),
                               file_name="dns_trade_journal.csv", mime="text/csv")
        except Exception as exc:
            st.error(f"Could not analyse this file: {exc}")

st.warning("Research/paper mode only. This version does not place orders. Validate zone definitions, fees, slippage, funding and exchange contract sizing before any live deployment.")
