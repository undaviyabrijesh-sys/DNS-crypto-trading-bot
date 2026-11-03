from __future__ import annotations

# Streamlit Cloud can launch the entrypoint from a working directory that does
# not reliably expose the repository root as an import path. Add it explicitly
# before importing the local dns_bot package.
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from dns_bot.delta_data import fetch_delta_history
from dns_bot.delta_market import fetch_ticker, fetch_orderbook, fetch_recent_trades
from dns_bot.zones import detect_fvg_zones, detect_base_leg_zones, track_zone_lifecycle
from dns_bot.journal import load_trades, learning_report


st.set_page_config(page_title="SALTY TRADES | Delta Terminal", page_icon="◈", layout="wide")

st.markdown("""
<style>
:root{--bg:#0b0e11;--panel:#131722;--line:#242a35;--muted:#848e9c;--cyan:#00c2ff;--green:#0ecb81;--red:#f6465d;}
html,body,[data-testid="stAppViewContainer"]{background:var(--bg);color:#eaecef;font-family:Inter,Arial,sans-serif;}
[data-testid="stHeader"]{background:#0b0e11;}
[data-testid="stSidebar"]{background:#11151d;border-right:1px solid #252b36;}
.block-container{max-width:1900px;padding-top:.7rem;padding-bottom:1.5rem;}
h1,h2,h3{font-family:Orbitron,Arial,sans-serif!important;color:#f0f3f7!important;}
h1{font-size:1.3rem!important;}
div[data-testid="stMetric"]{background:#131722;border:1px solid #252b36;border-radius:7px;padding:9px 12px;}
[data-testid="stMetricLabel"]{color:#848e9c!important;font-size:.72rem;}
[data-testid="stMetricValue"]{font-family:Orbitron,sans-serif;color:#eaecef!important;font-size:1.25rem;}
div[data-testid="stTabs"] button{color:#929aa5!important;font-weight:650;}
div[data-testid="stTabs"] button[aria-selected="true"]{color:#00c2ff!important;border-bottom:2px solid #00c2ff!important;}
.stButton>button{background:#17202d;color:#dce3eb;border:1px solid #303a49;border-radius:5px;}
.stButton>button:hover{border-color:#00c2ff;color:#00c2ff;}
[data-testid="stDataFrame"]{border:1px solid #252b36;border-radius:6px;}
hr{border-color:#252b36!important;}
.small-label{font-size:10px;letter-spacing:1.4px;color:#848e9c;font-weight:700;margin:4px 0 9px;}
.market-head{display:flex;align-items:center;gap:10px;padding:4px 0 10px;border-bottom:1px solid #252b36;margin-bottom:12px;}
.market-symbol{font-family:Orbitron,sans-serif;font-size:20px;font-weight:700;color:#f0f3f7;}
.market-tag{font-size:10px;color:#00c2ff;border:1px solid #13516a;padding:3px 7px;border-radius:4px;}
.muted{color:#848e9c;font-size:11px;}
.price-up{color:#0ecb81;font-weight:700}.price-down{color:#f6465d;font-weight:700}
.panel{background:#131722;border:1px solid #252b36;border-radius:6px;padding:10px;margin-bottom:10px;}
div[data-testid="stAlert"]{border-radius:6px;}
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=10, show_spinner=False)
def get_ticker(symbol: str):
    return fetch_ticker(symbol)


@st.cache_data(ttl=8, show_spinner=False)
def get_book(symbol: str):
    return fetch_orderbook(symbol, 20)


@st.cache_data(ttl=3, show_spinner=False)
def get_trades(symbol: str):
    return fetch_recent_trades(symbol)


def timeframe_minutes(tf: str) -> int:
    if tf.endswith("m"):
        return int(tf[:-1])
    if tf.endswith("h"):
        return int(tf[:-1]) * 60
    return 1440


@st.cache_data(ttl=300, show_spinner=False)
def get_zones(df: pd.DataFrame, engine: str):
    """Cache expensive zone scans; Streamlit reruns should not rescan unchanged candles."""
    found = []
    if engine in ("Both", "FVG"):
        found.extend(detect_fvg_zones(df))
    if engine in ("Both", "Base / Leg"):
        found.extend(detect_base_leg_zones(df))
    return track_zone_lifecycle(df, found)


def build_chart(df: pd.DataFrame, zones: list, show_volume: bool = True,
                chart_style: str = "Candles", indicators: list[str] | None = None,
                show_zones: bool = True):
    """TradingView-inspired interactive chart with editable drawing tools."""
    rows = 2 if show_volume else 1
    heights = [0.80, 0.20] if show_volume else [1]
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=.025,
                        row_heights=heights)

    if chart_style == "Candles":
        fig.add_trace(go.Candlestick(
            x=df.timestamp, open=df.open, high=df.high, low=df.low, close=df.close,
            name="BTCUSD", increasing_line_color="#0ecb81", decreasing_line_color="#f6465d",
            increasing_fillcolor="#0ecb81", decreasing_fillcolor="#f6465d",
        ), row=1, col=1)
    elif chart_style == "Line":
        fig.add_trace(go.Scatter(x=df.timestamp, y=df.close, mode="lines", name="Close",
                                 line=dict(color="#d8dee9", width=1.6)), row=1, col=1)
    else:
        fig.add_trace(go.Scatter(x=df.timestamp, y=df.close, mode="lines", name="Close",
                                 line=dict(color="#00c2ff", width=1.6),
                                 fill="tozeroy", fillcolor="rgba(0,194,255,.08)"), row=1, col=1)

    ema_colors = {"EMA 9": "#f0b90b", "EMA 20": "#00c2ff",
                  "EMA 50": "#b084f5", "EMA 200": "#ff8a65"}
    for label in indicators or []:
        period = int(label.split()[-1])
        if len(df) >= period:
            ema = df.close.ewm(span=period, adjust=False).mean()
            fig.add_trace(go.Scatter(x=df.timestamp, y=ema, mode="lines", name=label,
                                     line=dict(color=ema_colors.get(label, "#ffffff"), width=1.25)),
                          row=1, col=1)

    if show_volume and "volume" in df:
        volume_colors = ["#0ecb8180" if c >= o else "#f6465d80"
                         for o, c in zip(df.open, df.close)]
        fig.add_trace(go.Bar(x=df.timestamp, y=df.volume, marker_color=volume_colors,
                             name="Volume", showlegend=False), row=2, col=1)

    if show_zones:
        for zone in zones:
            if zone.status == "broken":
                continue
            demand = zone.kind == "demand"
            color = "rgba(14,203,129,.10)" if demand else "rgba(246,70,93,.10)"
            edge = "rgba(14,203,129,.62)" if demand else "rgba(246,70,93,.62)"
            low, high = sorted((float(zone.distal), float(zone.proximal)))
            fig.add_hrect(y0=low, y1=high, fillcolor=color, line_color=edge,
                          line_width=1, layer="below", row=1, col=1)

    last = float(df.close.iloc[-1])
    fig.add_hline(y=last, line_dash="dot", line_color="#00c2ff", line_width=1,
                  annotation_text=f"{last:,.1f}", annotation_position="right",
                  row=1, col=1)
    fig.update_layout(
        height=820, template="plotly_dark", paper_bgcolor="#0b0e11", plot_bgcolor="#0b0e11",
        margin=dict(l=5, r=5, t=8, b=5),
        font=dict(family="Inter", color="#aeb7c2", size=10),
        hovermode="x unified", showlegend=bool(indicators),
        legend=dict(orientation="h", y=1.02, x=0, bgcolor="rgba(0,0,0,0)"),
        dragmode="pan", uirevision="salty-trades-chart",
        xaxis=dict(showgrid=True, gridcolor="#1d232d", rangeslider_visible=False,
                   showspikes=True, spikemode="across", spikesnap="cursor",
                   rangeselector=dict(bgcolor="#131722", activecolor="#263747",
                       font=dict(color="#aeb7c2", size=9),
                       buttons=[
                           dict(count=1, label="1H", step="hour", stepmode="backward"),
                           dict(count=4, label="4H", step="hour", stepmode="backward"),
                           dict(count=1, label="1D", step="day", stepmode="backward"),
                           dict(count=7, label="1W", step="day", stepmode="backward"),
                           dict(count=1, label="1M", step="month", stepmode="backward"),
                           dict(step="all", label="ALL"),
                       ])),
        yaxis=dict(side="right", showgrid=True, gridcolor="#1d232d",
                   fixedrange=False, showspikes=True),
        xaxis2=dict(showgrid=True, gridcolor="#1d232d", showspikes=True),
        yaxis2=dict(side="right", showgrid=True, gridcolor="#1d232d"),
    )
    return fig

with st.sidebar:
    st.markdown("## ◈ SALTY TRADES")
    st.caption("DELTA EXCHANGE INDIA · MARKET TERMINAL")
    symbol = st.selectbox("CONTRACT", ["BTCUSD", "ETHUSD"], index=0)
    timeframe = st.selectbox("TIMEFRAME", ["1m", "3m", "5m", "15m", "30m", "1h", "4h"], index=3)
    candle_count = st.select_slider("CHART HISTORY", options=[250, 500, 750, 1000, 1500, 1999], value=1500)
    st.caption("15m chart: 1,500 candles ≈ 15.6 days")
    zone_engine = st.selectbox("SUPPLY / DEMAND OVERLAY", ["Both", "FVG", "Base / Leg", "Off"])
    show_volume = st.toggle("Show volume", value=True)
    refresh = st.button("↻  REFRESH MARKET", use_container_width=True, type="primary")
    st.markdown("---")
    st.caption("Public market data · Read-only · No orders sent")


# Instrument header and top-of-screen market statistics
st.markdown(
    f'<div class="market-head"><span class="market-symbol">{symbol}</span>'
    f'<span class="market-tag">PERPETUAL</span><span class="market-tag">DELTA INDIA</span>'
    f'<span class="muted">USD quoted · public market feed</span></div>',
    unsafe_allow_html=True,
)

# A changed contract/timeframe always reloads the matching candle series.
market_key = (symbol, timeframe, candle_count)
if refresh or st.session_state.get("market_key") != market_key:
    st.session_state.pop("market_error", None)
    try:
        days = max(1, int((candle_count * timeframe_minutes(timeframe) + 1439) / 1440))
        with st.spinner(f"Loading {symbol} {timeframe} candles from Delta…"):
            candles = fetch_delta_history(symbol=symbol, timeframe=timeframe, days=days)
        candles = candles.tail(candle_count).reset_index(drop=True)
        if candles.empty or len(candles) < 3:
            raise RuntimeError("Delta returned fewer than 3 completed candles.")
        st.session_state["market_candles"] = candles
        st.session_state["market_key"] = market_key
    except Exception as exc:
        st.session_state["market_error"] = str(exc)

ticker = book = trades = None
market_errors = []
try:
    ticker = get_ticker(symbol)
except Exception as exc:
    market_errors.append(f"Ticker: {exc}")
try:
    book = get_book(symbol)
except Exception as exc:
    market_errors.append(f"Order book: {exc}")
try:
    trades = get_trades(symbol)
except Exception as exc:
    market_errors.append(f"Recent trades: {exc}")

df = st.session_state.get("market_candles")
if df is not None and not df.empty:
    last_price = float(ticker.get("close", df.close.iloc[-1])) if ticker else float(df.close.iloc[-1])
    change = float(ticker.get("ltp_change_24h", 0) or 0) if ticker else 0.0
    day_high = ticker.get("high", "—") if ticker else "—"
    day_low = ticker.get("low", "—") if ticker else "—"
    volume_24h = ticker.get("volume", "—") if ticker else "—"
    mark = ticker.get("mark_price", "—") if ticker else "—"
    c1,c2,c3,c4,c5,c6 = st.columns(6)
    c1.metric("LAST PRICE", f"{last_price:,.2f}", f"{change:+.2f}% 24h")
    c2.metric("MARK PRICE", f"{float(mark):,.2f}" if mark not in (None, "—") else "—")
    c3.metric("24H HIGH", f"{float(day_high):,.2f}" if day_high != "—" else "—")
    c4.metric("24H LOW", f"{float(day_low):,.2f}" if day_low != "—" else "—")
    c5.metric("24H VOLUME", f"{float(volume_24h):,.2f}" if volume_24h != "—" else "—")
    c6.metric("CANDLES", f"{len(df):,}")

    zones = []
    try:
        zones = get_zones(df, zone_engine)
    except Exception as exc:
        st.warning(f"Zone detection issue: {exc}")

    with st.container():
        st.markdown('<div class="small-label">PRICE CHART · TRADINGVIEW-STYLE WORKSPACE</div>',
                    unsafe_allow_html=True)
        tool1, tool2, tool3 = st.columns([1.0, 1.5, 1.0])
        with tool1:
            chart_style = st.selectbox("CHART TYPE", ["Candles", "Line", "Area"],
                                       index=0, key="chart-style")
        with tool2:
            indicators = st.multiselect("INDICATORS", ["EMA 9", "EMA 20", "EMA 50", "EMA 200"],
                                        default=["EMA 20", "EMA 50"], key="chart-indicators")
        with tool3:
            show_chart_zones = st.toggle("Show zones", value=True, key="chart-zones")
        # Keep every detected zone in the watchlist. On the chart, show only
        # the three strongest individual demand zones and three strongest supply
        # zones. Do not merge zones: selection only reduces visual clutter.
        chart_zones = []
        for side in ("demand", "supply"):
            side_zones = [z for z in zones if str(z.kind).lower() == side]
            chart_zones.extend(sorted(
                [z for z in side_zones if z.status != "broken"],
                key=lambda z: (float(z.score), float(z.strength), str(z.created_at)),
                reverse=True
            )[:3])
        st.plotly_chart(
            build_chart(df, chart_zones, show_volume, chart_style, indicators, show_chart_zones),
            use_container_width=True,
            config={
                "displaylogo": False, "scrollZoom": True, "doubleClick": "reset",
                "editable": False,
                "modeBarButtonsToAdd": [
                    "drawline", "drawrect", "drawcircle", "eraseshape"
                ],
                "modeBarButtonsToRemove": ["select2d", "lasso2d"],
                "toImageButtonOptions": {"format": "png", "filename": "salty-trades-chart"}
            },
            key=f"chart-{symbol}-{timeframe}-{zone_engine}-{show_volume}-{chart_style}-{','.join(indicators)}-{show_chart_zones}"
        )
    depth_col, tape_col = st.columns(2, gap="small")
    with depth_col:
        st.markdown('<div class="small-label">ORDER BOOK · L2</div>', unsafe_allow_html=True)
        if book:
            asks = sorted(book.get("sell", []), key=lambda x: float(x.get("price", 0)))[:10]
            bids = sorted(book.get("buy", []), key=lambda x: float(x.get("price", 0)), reverse=True)[:10]
            ask_rows = [{"SIDE":"ASK", "PRICE":f'{float(x["price"]):,.1f}',
                         "SIZE":f'{float(x.get("size",0)):,.0f}'} for x in reversed(asks)]
            bid_rows = [{"SIDE":"BID", "PRICE":f'{float(x["price"]):,.1f}',
                         "SIZE":f'{float(x.get("size",0)):,.0f}'} for x in bids]
            st.dataframe(ask_rows + bid_rows, hide_index=True, height=390,
                         use_container_width=True)
            if asks and bids:
                spread = float(asks[0]["price"]) - float(bids[0]["price"])
                st.metric("BID / ASK SPREAD", f"{spread:,.2f}")
        else:
            st.info("Order book temporarily unavailable.")
    with tape_col:
        st.markdown('<div class="small-label">RECENT TRADES</div>', unsafe_allow_html=True)
        if trades:
            rows = []
            for trade in trades[:12]:
                side = str(trade.get("side", "")).upper()
                rows.append({"SIDE":side,
                             "PRICE":f'{float(trade.get("price",0)):,.1f}',
                             "SIZE":f'{float(trade.get("size",0)):,.0f}'})
            st.dataframe(rows, hide_index=True, height=260, use_container_width=True)
        else:
            st.caption("No recent trade prints returned.")

    lower_tabs = st.tabs(["ZONE WATCHLIST", "TRADE TICKET", "MARKET DATA", "TRADE JOURNAL", "SYSTEM"])
    with lower_tabs[0]:
        st.markdown("**Detected supply and demand areas**")
        if zones:
            rows = [{
                "SIDE": z.kind.upper(), "PATTERN": z.pattern, "SOURCE": z.method.upper(),
                "PROXIMAL": round(float(z.proximal), 2), "DISTAL": round(float(z.distal), 2),
                "STRENGTH": round(float(z.strength), 3),
                "SCORE": round(float(z.score), 3),
                "DEFENDED RETESTS": int(z.defended_retests),
                "TOUCHES": int(z.touches), "STATUS": z.status.upper(),
                "FORMED": z.created_at,
            } for z in sorted(zones, key=lambda x: x.created_at, reverse=True)]
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.info("No zones found in this chart window. Try 'Both' or a higher timeframe.")
    with lower_tabs[1]:
        st.markdown("**Manual trade ticket · paper planning only**")
        st.caption("Build and track a trade plan here. This version does not send orders to Delta Exchange.")
        if "paper_trade_plans" not in st.session_state:
            st.session_state["paper_trade_plans"] = []

        zone_labels = ["Manual / no zone"] + [
            f"{z.kind.upper()} | {z.method.upper()} | {z.pattern} | "
            f"{min(float(z.proximal), float(z.distal)):.2f}–"
            f"{max(float(z.proximal), float(z.distal)):.2f} | {z.created_at}"
            for z in zones
        ]
        with st.form("paper_trade_ticket", clear_on_submit=False):
            a,b,c1 = st.columns(3)
            with a:
                ticket_side = st.selectbox("DIRECTION", ["LONG", "SHORT"])
                ticket_entry = st.number_input("PLANNED ENTRY", min_value=0.0,
                    value=float(last_price), format="%.2f")
                ticket_stop = st.number_input("STOP LOSS", min_value=0.0,
                    value=round(float(last_price) * (0.995 if ticket_side == "LONG" else 1.005), 2),
                    format="%.2f")
            with b:
                ticket_target = st.number_input("TAKE PROFIT", min_value=0.0,
                    value=round(float(last_price) * (1.01 if ticket_side == "LONG" else 0.99), 2),
                    format="%.2f")
                ticket_qty = st.number_input("CONTRACTS / QTY (manual)", min_value=0.0,
                    value=0.0, step=1.0, format="%.4f")
                ticket_risk_pct = st.number_input("PLANNED RISK %", min_value=0.0,
                    max_value=5.0, value=1.0, step=0.25)
            with c1:
                ticket_zone = st.selectbox("SETUP / ZONE", zone_labels)
                ticket_note = st.text_input("SETUP NOTE", placeholder="e.g. 15m demand retest + bullish close")
                ticket_status = st.selectbox("PLAN STATUS", ["WATCHING", "READY", "ENTERED MANUALLY"])
            if ticket_side == "LONG":
                valid_levels = ticket_stop < ticket_entry < ticket_target
                risk_distance = ticket_entry - ticket_stop
                reward_distance = ticket_target - ticket_entry
            else:
                valid_levels = ticket_target < ticket_entry < ticket_stop
                risk_distance = ticket_stop - ticket_entry
                reward_distance = ticket_entry - ticket_target
            rr = reward_distance / risk_distance if risk_distance > 0 else 0.0
            st.caption(f"Risk distance: {risk_distance:,.2f} · Reward distance: {reward_distance:,.2f} · R:R: {rr:.2f}:1")
            if not valid_levels:
                st.error("Invalid levels: LONG requires SL < Entry < TP; SHORT requires TP < Entry < SL.")
            submitted = st.form_submit_button("＋  SAVE TRADE PLAN", type="primary",
                                               disabled=not valid_levels or ticket_entry <= 0)
        if submitted:
            import datetime as dt
            st.session_state["paper_trade_plans"].append({
                "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "symbol": symbol, "timeframe": timeframe, "side": ticket_side,
                "entry": float(ticket_entry), "stop": float(ticket_stop),
                "target": float(ticket_target), "rr": round(rr, 3),
                "quantity_manual": float(ticket_qty), "risk_pct_planned": float(ticket_risk_pct),
                "zone": ticket_zone, "status": ticket_status, "note": ticket_note,
            })
            st.success("Trade plan saved in this session. No exchange order was placed.")

        plans = st.session_state["paper_trade_plans"]
        if plans:
            plan_df = pd.DataFrame(plans)
            st.markdown("**Saved trade plans (session only)**")
            st.dataframe(plan_df, use_container_width=True, hide_index=True)
            st.download_button("Download trade plans CSV", plan_df.to_csv(index=False),
                file_name="salty_trades_paper_plans.csv", mime="text/csv")
            if st.button("Clear saved plans", key="clear-paper-plans"):
                st.session_state["paper_trade_plans"] = []
                st.rerun()
        else:
            st.info("No trade plans saved in this session yet.")

    with lower_tabs[1]:
        st.markdown("**Latest completed candles**")
        st.dataframe(df.tail(30).sort_values("timestamp", ascending=False),
                     use_container_width=True, hide_index=True)
    with lower_tabs[2]:
        st.markdown("**Trade performance & learning**")
        uploaded = st.file_uploader("Upload backtest trade CSV", type=["csv"], key="journal-upload")
        if uploaded is not None:
            try:
                journal = learning_report(load_trades(uploaded))
                metrics = journal["summary"]
                m1,m2,m3,m4 = st.columns(4)
                m1.metric("TRADES", metrics["trades"])
                m2.metric("WIN RATE", f'{metrics["win_rate_pct"]:.1f}%')
                m3.metric("EXPECTANCY", f'{metrics["expectancy_r"]:.3f} R')
                m4.metric("PROFIT FACTOR", metrics["profit_factor"] if metrics["profit_factor"] is not None else "—")
                st.write(journal["training_note"])
                for label,key in [("Zone pattern","zone_pattern"),("Zone engine","zone_method"),
                                  ("Trend alignment","trend_alignment"),("Side","side")]:
                    st.markdown(f"##### {label}")
                    st.dataframe(journal["groups"][key], use_container_width=True, hide_index=True)
            except Exception as exc:
                st.error(f"Journal error: {exc}")
        else:
            st.caption("Upload the backtest trade CSV to inspect the strategy's measured performance.")
    with lower_tabs[3]:
        st.warning("Read-only research terminal. No order entry, account balance, positions or private account data are connected.")
        st.write("Data sources: Delta public OHLC candles, ticker, L2 order book and public trades.")
        if market_errors:
            for error in market_errors:
                st.caption(error)
else:
    st.error(f"Chart data could not be loaded: {st.session_state.get('market_error', 'No candle data available.')}")
    st.info("Use Refresh Market after checking the Delta API connection. This terminal will not draw synthetic or placeholder candles.")

st.markdown('<div style="border-top:1px solid #252b36;padding-top:10px;color:#687382;font-size:10px;letter-spacing:1px;">SALTY TRADES · DELTA EXCHANGE INDIA · READ-ONLY RESEARCH TERMINAL</div>',
            unsafe_allow_html=True)
