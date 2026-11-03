from __future__ import annotations

import streamlit as st
import plotly.graph_objects as go

from dns_bot.data import fetch_ohlcv
from dns_bot.delta_data import fetch_delta_history
from dns_bot.zones import detect_fvg_zones, detect_base_leg_zones
from dns_bot.journal import load_trades, learning_report


st.set_page_config(
    page_title="SALTY TRADES | DNS Terminal",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)


def tf_minutes(value: str) -> int:
    if value.endswith("m"):
        return int(value[:-1])
    if value.endswith("h"):
        return int(value[:-1]) * 60
    if value.endswith("d"):
        return int(value[:-1]) * 1440
    raise ValueError(f"Unsupported timeframe: {value}")


def inject_theme() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Orbitron:wght@500;600;700;800&display=swap');
        :root {
          --bg:#070b14; --panel:#0d1422; --panel2:#101b2d; --line:#1d2c43;
          --cyan:#00e5ff; --blue:#477bff; --green:#00e6a0; --red:#ff5277;
          --text:#e7f1ff; --muted:#8295b2;
        }
        html, body, [data-testid="stAppViewContainer"] {
          background: radial-gradient(ellipse at 50% -20%, #142746 0%, #090f1d 42%, #060912 100%);
          color:var(--text);
        }
        [data-testid="stHeader"] {background:rgba(5,9,18,.75);}
        [data-testid="stSidebar"] {
          background:linear-gradient(180deg,#0c1525 0%,#080e19 100%);
          border-right:1px solid var(--line);
        }
        [data-testid="stSidebar"] * {color:var(--text);}
        .block-container {padding-top:1.15rem;padding-bottom:2rem;max-width:1800px;}
        h1,h2,h3 {font-family:'Orbitron',sans-serif!important;letter-spacing:.04em;}
        h1 {font-size:1.55rem!important;color:#f2f8ff!important;}
        h2,h3 {color:#d9eaff!important;}
        p, label, .stMarkdown {color:var(--text);}
        [data-testid="stMetric"] {
          background:linear-gradient(145deg,rgba(16,29,49,.96),rgba(9,17,30,.96));
          border:1px solid #203653;border-radius:12px;padding:13px 16px;
          box-shadow:0 0 22px rgba(0,229,255,.045), inset 0 1px rgba(255,255,255,.025);
        }
        [data-testid="stMetricLabel"] {color:#8da4c3!important;font-size:.75rem;}
        [data-testid="stMetricValue"] {color:#f1f8ff!important;font-family:'Orbitron',sans-serif;}
        .terminal-brand {
          display:flex;align-items:center;gap:14px;padding:7px 0 17px 0;
          border-bottom:1px solid #1c2b42;margin-bottom:16px;
        }
        .brand-mark {
          width:42px;height:42px;border:1px solid var(--cyan);border-radius:11px;
          display:flex;align-items:center;justify-content:center;color:var(--cyan);
          font-size:24px;box-shadow:0 0 18px rgba(0,229,255,.18),inset 0 0 15px rgba(0,229,255,.08);
        }
        .brand-title {font-family:'Orbitron',sans-serif;font-size:19px;font-weight:800;letter-spacing:2px;color:#f2f8ff;}
        .brand-sub {font-size:10px;letter-spacing:2px;color:#7790b2;margin-top:3px;}
        .status-pill {
          display:inline-flex;align-items:center;gap:7px;padding:6px 11px;border-radius:30px;
          border:1px solid rgba(0,230,160,.35);background:rgba(0,230,160,.07);
          color:#6dffd0;font-size:11px;letter-spacing:1.2px;font-weight:700;
        }
        .status-dot {width:7px;height:7px;border-radius:50%;background:#00e6a0;box-shadow:0 0 9px #00e6a0;}
        .section-kicker {font-size:10px;letter-spacing:2px;color:#6f88aa;font-weight:700;margin:2px 0 9px;}
        div[data-testid="stTabs"] button {color:#8da4c3!important;font-weight:700;}
        div[data-testid="stTabs"] button[aria-selected="true"] {
          color:#00e5ff!important;border-bottom:2px solid #00e5ff!important;
        }
        .stButton>button, .stDownloadButton>button {
          border:1px solid #087f9a!important;color:#dffaff!important;
          background:linear-gradient(110deg,#0c3347,#10213b)!important;
          border-radius:8px!important;font-weight:700!important;
          box-shadow:0 0 15px rgba(0,229,255,.08);
        }
        .stButton>button:hover,.stDownloadButton>button:hover {
          border-color:#00e5ff!important;box-shadow:0 0 20px rgba(0,229,255,.2);
        }
        [data-testid="stDataFrame"], [data-testid="stFileUploader"] {
          border:1px solid #1d2c43;border-radius:10px;overflow:hidden;
        }
        hr {border-color:#1d2c43!important;}
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_theme()

st.markdown(
    """
    <div class="terminal-brand">
      <div class="brand-mark">◈</div>
      <div>
        <div class="brand-title">SALTY TRADES</div>
        <div class="brand-sub">DEMAND & SUPPLY INTELLIGENCE TERMINAL</div>
      </div>
      <div style="margin-left:auto" class="status-pill"><span class="status-dot"></span> RESEARCH MODE · PAPER ONLY</div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### ◈ TERMINAL CONTROLS")
    exchange_id = st.selectbox("VENUE", ["Delta India", "okx", "bybit", "binance"], index=0)
    symbol = st.selectbox(
        "INSTRUMENT",
        ["BTCUSD", "ETHUSD"] if exchange_id == "Delta India" else ["BTC/USDT", "ETH/USDT"],
        index=0,
    )
    timeframe = st.selectbox("TIMEFRAME", ["1m", "3m", "5m", "15m", "1h", "4h"], index=3)
    candle_limit = st.slider("VISIBLE CANDLES", 100, 1000, 500, 50)
    detector = st.selectbox("ZONE ENGINE", ["Both", "FVG", "Base / Leg"])
    st.markdown("---")
    refresh = st.button("⟳  SYNC MARKET DATA", use_container_width=True, type="primary")
    st.caption("Public exchange candles · No order execution")
    st.markdown("---")
    st.markdown("**SYSTEM STATUS**")
    st.markdown('<span class="status-pill"><span class="status-dot"></span> LIVE DATA CONNECTION ON DEMAND</span>', unsafe_allow_html=True)

market_tab, journal_tab, about_tab = st.tabs(["◈  MARKET TERMINAL", "▤  TRADE JOURNAL", "⌘  SYSTEM"])

with market_tab:
    should_load = "candles" not in st.session_state or refresh
    if should_load:
        try:
            with st.spinner("Connecting to exchange market data…"):
                if exchange_id == "Delta India":
                    days = max(1, int((candle_limit * tf_minutes(timeframe) + 1439) / 1440))
                    market_df = fetch_delta_history(symbol=symbol, timeframe=timeframe, days=days)
                else:
                    market_df = fetch_ohlcv(exchange_id, symbol, timeframe, candle_limit)
                market_df = market_df.tail(candle_limit).reset_index(drop=True)
                st.session_state["candles"] = market_df
                st.session_state["market_key"] = (exchange_id, symbol, timeframe)
                st.session_state["load_error"] = None
        except Exception as exc:
            st.session_state["load_error"] = str(exc)

    if st.session_state.get("load_error"):
        st.error(f"Market data unavailable: {st.session_state['load_error']}")
    elif "candles" in st.session_state:
        df = st.session_state["candles"]
        current_key = (exchange_id, symbol, timeframe)
        if st.session_state.get("market_key") != current_key:
            st.info("Change detected in market controls. Press SYNC MARKET DATA to load the selected instrument.")
        zones = []
        try:
            if detector in ("Both", "FVG"):
                zones.extend(detect_fvg_zones(df))
            if detector in ("Both", "Base / Leg"):
                zones.extend(detect_base_leg_zones(df))
        except Exception as exc:
            st.warning(f"Zone engine warning: {exc}")

        last = float(df["close"].iloc[-1])
        previous = float(df["close"].iloc[-2]) if len(df) > 1 else last
        delta = last - previous
        pct = (delta / previous * 100) if previous else 0.0
        demand_count = sum(z.kind == "demand" for z in zones)
        supply_count = sum(z.kind == "supply" for z in zones)

        a,b,c,d,e = st.columns(5)
        a.metric("LAST TRADED PRICE", f"{last:,.2f}", f"{delta:+,.2f} ({pct:+.2f}%)")
        b.metric("CANDLES", f"{len(df):,}")
        c.metric("ACTIVE DEMAND ZONES", f"{demand_count:,}")
        d.metric("ACTIVE SUPPLY ZONES", f"{supply_count:,}")
        e.metric("ZONE COUNT", f"{len(zones):,}")

        st.markdown('<div class="section-kicker">PRICE ACTION · SUPPLY / DEMAND MAP</div>', unsafe_allow_html=True)
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=df["timestamp"], open=df["open"], high=df["high"], low=df["low"], close=df["close"],
            name=symbol, increasing_line_color="#00d9a0", decreasing_line_color="#ff5277",
            increasing_fillcolor="#00b889", decreasing_fillcolor="#e74770",
        ))

        for index, zone in enumerate(zones[-40:]):
            demand = zone.kind == "demand"
            fill = "rgba(0,230,160,0.10)" if demand else "rgba(255,82,119,0.10)"
            line = "rgba(0,230,160,0.62)" if demand else "rgba(255,82,119,0.62)"
            y0, y1 = sorted([float(zone.distal), float(zone.proximal)])
            fig.add_shape(
                type="rect", xref="paper", x0=0, x1=1, y0=y0, y1=y1,
                fillcolor=fill, line=dict(color=line, width=1), layer="below",
            )
            fig.add_annotation(
                xref="paper", x=0.012, y=(y0+y1)/2, yref="y", showarrow=False,
                text=f"{'DEMAND' if demand else 'SUPPLY'} · {zone.pattern} · {zone.method.upper()}",
                font=dict(size=9, color="#8fffe0" if demand else "#ff9bb1"),
                bgcolor="rgba(5,10,20,.72)", borderpad=3, xanchor="left",
            )

        fig.update_layout(
            height=690, template="plotly_dark", paper_bgcolor="#080e19", plot_bgcolor="#080e19",
            margin=dict(l=12,r=18,t=18,b=12), xaxis_rangeslider_visible=False,
            font=dict(family="Inter, sans-serif", color="#a9bdd8", size=11),
            legend=dict(orientation="h", y=1.02, x=0),
            xaxis=dict(showgrid=True, gridcolor="rgba(80,110,150,.13)", zeroline=False,
                       showspikes=True, spikemode="across", spikesnap="cursor"),
            yaxis=dict(side="right", showgrid=True, gridcolor="rgba(80,110,150,.13)",
                       zeroline=False, showspikes=True, spikesnap="cursor"),
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True, config={
            "displaylogo": False,
            "scrollZoom": True,
            "modeBarButtonsToRemove": ["select2d", "lasso2d"],
        })

        st.markdown('<div class="section-kicker">ZONE WATCHLIST</div>', unsafe_allow_html=True)
        if zones:
            zone_rows = []
            for z in sorted(zones, key=lambda item: item.created_at, reverse=True):
                zone_rows.append({
                    "SIDE": z.kind.upper(),
                    "PATTERN": z.pattern,
                    "ENGINE": z.method.upper(),
                    "PROXIMAL": round(float(z.proximal), 2),
                    "DISTAL": round(float(z.distal), 2),
                    "STRENGTH": round(float(z.strength), 3),
                    "STATUS": z.status.upper(),
                    "CREATED": z.created_at,
                })
            st.dataframe(zone_rows, use_container_width=True, hide_index=True)
        else:
            st.info("No zones detected in the selected candle window.")
    else:
        st.info("Press SYNC MARKET DATA to load the selected instrument.")

with journal_tab:
    st.markdown("### TRADE PERFORMANCE & LEARNING")
    st.caption("Import completed backtest trades to review expectancy, drawdown and setup quality.")
    uploaded = st.file_uploader("UPLOAD TRADE HISTORY CSV", type=["csv"])
    if uploaded is not None:
        try:
            trades = load_trades(uploaded)
            report = learning_report(trades)
            metrics = report["summary"]
            p,q,r,s = st.columns(4)
            p.metric("COMPLETED TRADES", metrics["trades"])
            q.metric("WIN RATE", f'{metrics["win_rate_pct"]:.1f}%')
            r.metric("EXPECTANCY", f'{metrics["expectancy_r"]:.3f} R')
            s.metric("PROFIT FACTOR", metrics["profit_factor"] if metrics["profit_factor"] is not None else "—")
            st.write(
                f'**Net result:** {metrics["net_r"]:.2f} R  ·  '
                f'**Max drawdown (1% risk):** {metrics["max_drawdown_pct_at_1pct_risk"]:.2f}%  ·  '
                f'**Longest losing streak:** {metrics["max_consecutive_losses"]}'
            )
            st.info(report["training_note"])
            for title, key in [
                ("ZONE PATTERN", "zone_pattern"), ("DETECTOR", "zone_method"),
                ("TREND ALIGNMENT", "trend_alignment"), ("ZONE SCORE BAND", "zone_score_band"),
                ("LONG VS SHORT", "side"), ("RETEST NUMBER", "touch_number"),
            ]:
                st.markdown(f"#### {title}")
                frame = report["groups"][key]
                if frame.empty:
                    st.caption("Not enough data for this breakdown.")
                else:
                    st.dataframe(frame, use_container_width=True, hide_index=True)
            st.download_button(
                "DOWNLOAD JOURNAL CSV", trades.to_csv(index=False),
                file_name="dns_trade_journal.csv", mime="text/csv",
            )
        except Exception as exc:
            st.error(f"Could not analyse this file: {exc}")
    else:
        st.info("No trade file loaded yet. Upload a backtest CSV to populate the performance desk.")

with about_tab:
    st.markdown("### SYSTEM CONFIGURATION")
    st.write("**Venue focus:** Delta Exchange India")
    st.write("**Primary instrument:** BTCUSD perpetual")
    st.write("**Analysis:** FVG and base/leg supply-demand zones")
    st.write("**Execution:** Disabled — research and paper mode only")
    st.warning(
        "This terminal currently visualizes public market data and detected zones. "
        "It does not send orders. Validate historical data, fees, slippage, funding, "
        "contract sizing and paper execution before considering live deployment."
    )

st.markdown(
    '<div style="text-align:center;color:#526985;font-size:10px;letter-spacing:1.6px;'
    'padding:18px 0 4px;border-top:1px solid #1b2a40;margin-top:24px;">'
    'SALTY TRADES · DNS INTELLIGENCE CORE · BUILT FOR RESEARCH, NOT ORDER EXECUTION</div>',
    unsafe_allow_html=True,
)
