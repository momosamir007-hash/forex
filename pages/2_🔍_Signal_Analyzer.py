import streamlit as st
import plotly.graph_objects as go
from app.ai_filter       import analyze_signal
from app.risk_manager    import calculate_risk
from app.market_filters  import data_fetcher, run_all_filters
from app.price_action    import analyze_price_action
from app.smart_money     import analyze_smc
from app.multi_timeframe import analyze_mtf
from app.news_filter     import check_news_risk, get_upcoming_events
from app.signal_scorer   import calculate_score
from app.database        import save_trade, save_rejected, init_db
from app.config          import SUPPORTED_PAIRS, TIMEFRAME_WEIGHTS

st.set_page_config(page_title="Signal Analyzer", page_icon="🔍", layout="wide")
init_db()

st.title("🔍 Signal Analyzer")
st.markdown("7-Layer AI Analysis Engine · Forex & Commodities")
st.markdown("---")

# ─────────────────────────────────────────────────
# Upcoming News Banner
# ─────────────────────────────────────────────────
upcoming = get_upcoming_events(hours_ahead=3)
if upcoming:
    ev = upcoming[0]
    st.warning(
        f"⚠️ **Upcoming High-Impact Event** in "
        f"**{ev['minutes_away']} min**: "
        f"{ev['impact']} {ev['name']} @ {ev['utc_time']} UTC"
    )

# ─────────────────────────────────────────────────
# Input Form
# ─────────────────────────────────────────────────
with st.form("signal_form"):
    st.subheader("📥 Signal Input")

    c1, c2, c3 = st.columns(3)
    with c1:
        symbol    = st.selectbox(
            "Symbol", list(SUPPORTED_PAIRS.keys()),
            format_func=lambda s:
                f"{SUPPORTED_PAIRS[s]['emoji']}  {s}",
        )
        side      = st.selectbox("Direction", ["BUY", "SELL"])
    with c2:
        price     = st.number_input("Entry Price", min_value=0.0,
                                    value=1.0850, format="%.5f")
        timeframe = st.selectbox("Timeframe",
                                 list(TIMEFRAME_WEIGHTS.keys()), index=2)
    with c3:
        account   = st.number_input("Account ($)", min_value=100.0,
                                    value=10_000.0)
        live      = st.toggle("Live Data (TwelveData)", value=True)

    submitted = st.form_submit_button(
        "🚀 Run 7-Layer Analysis", type="primary", use_container_width=True
    )

# ─────────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────────
if submitted:
    base_data = {
        "symbol": symbol, "side": side,
        "price": str(price), "timeframe": timeframe,
    }

    st.markdown("---")
    st.subheader("⚙️ 7-Layer Analysis Pipeline")

    ind    = {}
    df_raw = None

    # ════ Layer 1: Market Data ════════════
    with st.status("Layer 1 · Fetching market data …") as s:
        if live:
            df_raw = data_fetcher.get_ohlcv(symbol, timeframe)
            ind    = data_fetcher.get_indicators(df_raw)
            if ind:
                base_data.update({k: str(v) for k, v in ind.items()})
                s.update(label="Layer 1 · ✅ Live data ready", state="complete")
            else:
                s.update(label="Layer 1 · ⚠️ No live data", state="error")
        else:
            s.update(label="Layer 1 · ℹ️ Manual mode", state="complete")

    # ════ Layer 2: News Filter ════════════
    with st.status("Layer 2 · Checking economic news …") as s:
        news_result = check_news_risk(symbol)
        if news_result["safe"]:
            s.update(label="Layer 2 · ✅ News clear", state="complete")
        else:
            s.update(label=f"Layer 2 · 🚨 {news_result['reason']}", state="error")

    # ════ Layer 3: Market Filters ════════
    with st.status("Layer 3 · Technical filters …") as s:
        filter_result = run_all_filters(base_data, ind)
        if filter_result["passed"]:
            s.update(label="Layer 3 · ✅ All filters passed", state="complete")
        else:
            blocked = ", ".join(filter_result["blocked_by"])
            s.update(label=f"Layer 3 · ❌ {blocked}", state="error")

    # ════ Layer 4: Price Action ══════════
    with st.status("Layer 4 · Price action analysis …") as s:
        pa_result = analyze_price_action(df_raw, side) if df_raw is not None \
                    else {"score": 5.0, "patterns": [], "structure": "N/A",
                          "sr_levels": {}, "ranging": False, "approved": True,
                          "reason": "No live data"}
        icon = "✅" if pa_result["approved"] else "⚠️"
        s.update(
            label=f"Layer 4 · {icon} PA Score: {pa_result['score']}/10 "
                  f"| {', '.join(pa_result['patterns'][:2]) or 'No pattern'}",
            state="complete",
        )

    # ════ Layer 5: Smart Money ═══════════
    with st.status("Layer 5 · Smart Money Concepts …") as s:
        smc_result = analyze_smc(df_raw, side) if df_raw is not None \
                     else {"score": 5.0, "ob": {}, "fvg": {}, "sweep": False,
                           "bos": False, "choch": False, "approved": True,
                           "reason": "No live data"}
        s.update(
            label=f"Layer 5 · ✅ SMC Score: {smc_result['score']}/10 "
                  f"| {smc_result['reason'][:50]}",
            state="complete",
        )

    # ════ Layer 6: MTF Confirmation ══════
    with st.status("Layer 6 · Multi-timeframe alignment …") as s:
        mtf_result = analyze_mtf(symbol, timeframe, side)
        icon = "✅" if mtf_result["aligned"] else "❌"
        s.update(
            label=f"Layer 6 · {icon} MTF: {mtf_result['alignment_pct']}% aligned",
            state="complete" if mtf_result["aligned"] else "error",
        )

    # ════ Layer 7: Gemini AI ═════════════
    with st.status("Layer 7 · Gemini AI analysis …") as s:
        ai_result = analyze_signal(base_data, ind)
        icon = "✅" if ai_result["approved"] else "❌"
        s.update(
            label=f"Layer 7 · {icon} AI Score: {ai_result['final_score']}/10",
            state="complete" if ai_result["approved"] else "error",
        )

    # ════ Final Score ═════════════════════
    sr_levels  = pa_result.get("sr_levels", {})
    score_result = calculate_score(
        ai_result, filter_result,
        pa_result, smc_result, mtf_result, news_result,
    )
    risk = calculate_risk(base_data, score_result["final_score"],
                          account, sr_levels)

    st.markdown("---")

    # ════════════════════════════════════════
    # ── RESULT DISPLAY ──────────────────────
    # ════════════════════════════════════════
    approved = score_result["approved"]

    if approved:
        dir_color = "#22c55e" if side == "BUY" else "#ef4444"
        pair_info = SUPPORTED_PAIRS.get(symbol, {})

        # ── Hero Banner ──
        st.markdown(
            f"""
            <div style="background:linear-gradient(135deg,#0f172a,#1e293b);
                border:2px solid {dir_color}; border-radius:16px;
                padding:24px; margin-bottom:16px;">
                <h2 style="color:{dir_color};margin:0">
                    ✅ Signal Approved — 7/7 Layers
                </h2>
                <p style="color:#94a3b8;margin:6px 0 0">
                    {pair_info.get('emoji','')} {symbol} &nbsp;|&nbsp;
                    {'📈 LONG' if side=='BUY' else '📉 SHORT'} &nbsp;|&nbsp;
                    ⏰ {timeframe} &nbsp;|&nbsp;
                    Grade: <b style="color:{dir_color}">{score_result['grade']}</b>
                    &nbsp;|&nbsp; Score: <b>{score_result['final_score']}/10</b>
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ── Entry Levels ──
        st.subheader("🎯 Entry Levels")
        lc = st.columns(5)
        levels = [
            ("Entry",    risk["entry"],         None),
            ("Stop Loss",risk["stop_loss"],      risk["stop_loss"] - risk["entry"]),
            ("TP 1",     risk["take_profit"],    risk["take_profit"] - risk["entry"]),
            ("TP 2",     risk["take_profit_2"],  risk["take_profit_2"] - risk["entry"]),
            ("TP 3",     risk["take_profit_3"],  risk["take_profit_3"] - risk["entry"]),
        ]
        for col, (label, val, diff) in zip(lc, levels):
            delta = f"{diff/risk['entry']*100:+.3f}%" if diff else None
            inv   = (label == "Stop Loss")
            col.metric(label, f"{val:.5f}", delta=delta,
                       delta_color="inverse" if inv else "normal")

        # ── Risk ──
        st.subheader("💰 Risk Management")
        rc = st.columns(4)
        rc[0].metric("Risk %",         f"{risk['risk_percent']}%")
        rc[1].metric("R:R Ratio",      f"1 : {risk['rr_ratio']}")
        rc[2].metric("Potential Loss", f"-${risk['potential_loss']:.2f}")
        rc[3].metric("Potential Gain", f"+${risk['potential_gain']:.2f}")

        # ── Score Radar / Bar ──
        st.subheader("🧠 Score Breakdown (8 Layers)")
        bd = score_result["breakdown"]
        labels = list(bd.keys())
        values = list(bd.values())
        colors = ["#22c55e" if v >= 7 else "#f59e0b" if v >= 5 else "#ef4444"
                  for v in values]

        fig = go.Figure(go.Bar(
            x=values, y=labels, orientation="h",
            marker_color=colors,
            text=[f"{v:.1f}" for v in values],
            textposition="auto",
        ))
        fig.add_vline(x=7, line_dash="dash", line_color="white",
                      annotation_text="Min 7.0",
                      annotation_font_color="white")
        fig.update_layout(
            xaxis=dict(range=[0, 10]),
            height=300, margin=dict(t=5, b=5, l=5, r=5),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="white",
        )
        st.plotly_chart(fig, use_container_width=True)

        # ── SMC + PA Details ──
        col_pa, col_smc = st.columns(2)

        with col_pa:
            with st.expander("📊 Price Action Details"):
                st.write(f"**Structure:** {pa_result.get('structure','N/A')}")
                st.write(f"**Patterns:** {', '.join(pa_result.get('patterns',[]) or ['None'])}")
                st.write(f"**Breakout:** {'✅' if pa_result.get('breakout') else '❌'}")
                st.write(f"**Ranging:** {'⚠️ Yes' if pa_result.get('ranging') else '✅ No'}")
                sr = pa_result.get("sr_levels", {})
                if sr:
                    st.write(f"**Support:** `{sr.get('support','N/A')}`")
                    st.write(f"**Resistance:** `{sr.get('resistance','N/A')}`")

        with col_smc:
            with st.expander("💎 Smart Money Details"):
                ob = smc_result.get("ob", {})
                if ob.get("found"):
                    st.write(f"**Order Block:** {ob.get('type')} "
                             f"{'(In Zone ✅)' if ob.get('in_zone') else ''}")
                fvg = smc_result.get("fvg", {})
                if fvg.get("found"):
                    st.write(f"**FVGs Found:** {fvg.get('count', 0)}")
                st.write(f"**Liquidity Sweep:** {'✅' if smc_result.get('sweep') else '❌'}")
                st.write(f"**BOS:** {'✅' if smc_result.get('bos') else '❌'}")
                st.write(f"**CHOCH:** {'✅' if smc_result.get('choch') else '❌'}")

        # ── MTF ──
        with st.expander("⏱️ Multi-Timeframe Alignment"):
            st.write(f"**Alignment:** {mtf_result.get('alignment_pct', 0):.0f}%")
            for tf, v in mtf_result.get("details", {}).items():
                icon = "✅" if v.get("aligned") else "❌"
                st.write(f"{icon} **{tf}** → {v.get('trend','N/A')}")

        # ── AI Analysis ──
        with st.expander("🤖 Gemini AI Analysis"):
            st.info(ai_result.get("analysis_summary", "N/A"))
            kl = ai_result.get("key_levels", {})
            if kl:
                st.write(f"**Support:** `{kl.get('support','N/A')}` "
                         f"| **Resistance:** `{kl.get('resistance','N/A')}`")
            st.write(f"**Market Condition:** {ai_result.get('market_condition','N/A')}")
            st.write(f"**Confidence:** {ai_result.get('confidence','N/A')}")

        # ── Save ──
        trade_id = save_trade(base_data, score_result, risk, ai_result)
        st.success(f"💾 Trade saved — ID #{trade_id}")

    # ─────────────────────────────────────
    # REJECTED
    # ─────────────────────────────────────
    else:
        st.error("🚫 Signal Rejected")

        hard = score_result.get("hard_blocks", [])
        if hard:
            for b in hard:
                st.error(f"🔴 Hard Block: {b}")

        reasons = []
        if not news_result["safe"]:
            reasons.append(f"📰 News: {news_result['reason']}")
        if not filter_result["passed"]:
            reasons.append(f"📊 Filters: {', '.join(filter_result['blocked_by'])}")
        if not ai_result["approved"]:
            reasons.append(f"🤖 AI: {ai_result.get('rejection_reason','')}")
        if not score_result["approved"] and not hard:
            reasons.append(
                f"📐 Score {score_result['final_score']}/10 below "
                f"minimum {7.5}"
            )

        for r in reasons:
            st.warning(r)

        with st.expander("🔎 Full Filter Report"):
            for name, res in filter_result["filters"].items():
                icon = "✅" if res["passed"] else "❌"
                st.write(f"{icon} **{name}** — {res.get('reason','')}")

        save_rejected(base_data, " | ".join(reasons),
                      score_result.get("final_score", 0))
