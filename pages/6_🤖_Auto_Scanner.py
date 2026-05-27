"""
Auto Scanner Page
─────────────────
يفحص السوق تلقائياً ويعرض أفضل فرص التداول.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

from app.auto_scanner import auto_scanner
from app.config       import SUPPORTED_PAIRS, TIMEFRAME_WEIGHTS
from app.database     import save_trade, save_rejected, init_db
from app.risk_manager import calculate_risk

st.set_page_config(
    page_title="Auto Scanner",
    page_icon="🤖",
    layout="wide",
)
init_db()

st.title("🤖 Auto Market Scanner")
st.markdown("النظام يفحص السوق لوحده ويحدد أفضل فرص الدخول تلقائياً")
st.markdown("---")

# ══════════════════════════════════════════
# Sidebar Settings
# ══════════════════════════════════════════
with st.sidebar:
    st.subheader("⚙️ إعدادات المسح")

    selected_pairs = st.multiselect(
        "الأزواج",
        list(SUPPORTED_PAIRS.keys()),
        default=["EUR/USD", "GBP/USD", "XAU/USD"],
        format_func=lambda s:
            f"{SUPPORTED_PAIRS[s]['emoji']} {s}",
    )

    selected_tfs = st.multiselect(
        "الإطارات الزمنية",
        list(TIMEFRAME_WEIGHTS.keys()),
        default=["15m", "1h", "4h"],
    )

    use_ai = st.toggle(
        "🤖 تفعيل Gemini AI",
        value=False,
        help="أبطأ لكن أدق - يستهلك API credits",
    )

    min_rr = st.slider(
        "الحد الأدنى R:R",
        1.0, 4.0, 1.5, 0.5,
    )

    min_conf = st.slider(
        "الحد الأدنى للثقة %",
        30, 90, 55, 5,
    )

    auto_refresh = st.toggle("🔄 تحديث تلقائي (15 دقيقة)", value=False)

    if auto_refresh:
        st_autorefresh(interval=15 * 60 * 1000, key="scanner_refresh")

    account = st.number_input("💰 الرصيد ($)", 100.0, 1_000_000.0, 10_000.0)

# ══════════════════════════════════════════
# Scan Button
# ══════════════════════════════════════════
col_btn, col_status = st.columns([1, 3])

scan_clicked = col_btn.button(
    "🔍 ابدأ المسح الآن",
    type="primary",
    use_container_width=True,
)

if col_status and auto_scanner.last_scan:
    col_status.info(
        f"🕐 آخر مسح: {auto_scanner.last_scan.strftime('%H:%M:%S UTC')}"
    )

# ══════════════════════════════════════════
# Run Scan
# ══════════════════════════════════════════
if scan_clicked or (auto_refresh and not auto_scanner.last_results):

    if not selected_pairs:
        st.warning("اختر زوجاً واحداً على الأقل")
        st.stop()

    progress = st.progress(0, text="جاري فحص السوق...")

    total = len(selected_pairs) * len(selected_tfs)
    step  = 0

    with st.spinner(
        f"🔍 فحص {len(selected_pairs)} زوج × "
        f"{len(selected_tfs)} إطار = {total} فحص..."
    ):
        results = auto_scanner.scan_all(
            timeframes  = selected_tfs,
            pairs       = selected_pairs,
            use_ai      = use_ai,
            max_workers = 3,
        )

        # Filter by user settings
        results = [
            r for r in results
            if r.get("rr_ratio",    0) >= min_rr and
               r.get("confidence",  0) >= min_conf
        ]

    progress.progress(100, text="✅ اكتمل المسح!")

    if not results:
        st.warning(
            "⚠️ لم يجد النظام فرص تداول تستوفي المعايير الآن.\n\n"
            "جرب: تخفيض الحد الأدنى للـ R:R أو الثقة، "
            "أو اختر إطارات زمنية أخرى."
        )
        st.stop()

    st.session_state["scan_results"] = results
    st.success(
        f"✅ وجد النظام **{len(results)} فرصة** تلبي معاييرك!"
    )

# ══════════════════════════════════════════
# Display Results
# ══════════════════════════════════════════
results = st.session_state.get("scan_results", [])

if not results:
    st.info("👆 اضغط **ابدأ المسح** لفحص السوق")
    st.stop()

st.markdown("---")
st.subheader(f"📊 نتائج المسح — {len(results)} فرصة")

# ── Summary KPIs ─────────────────────────
buys  = sum(1 for r in results if r["side"] == "BUY")
sells = sum(1 for r in results if r["side"] == "SELL")
avg_rr    = sum(r["rr_ratio"]   for r in results) / len(results)
avg_score = sum(r["final_score"] for r in results) / len(results)
best      = results[0]

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("🔢 الفرص",      len(results))
k2.metric("🟢 BUY",        buys)
k3.metric("🔴 SELL",       sells)
k4.metric("📐 متوسط R:R", f"1:{avg_rr:.2f}")
k5.metric("⭐ متوسط Score", f"{avg_score:.1f}")

st.markdown("---")

# ══════════════════════════════════════════
# Best Opportunity (Hero Card)
# ══════════════════════════════════════════
st.subheader("🏆 أفضل فرصة الآن")

dir_color = "#22c55e" if best["side"] == "BUY" else "#ef4444"
dir_label = "📈 LONG" if best["side"] == "BUY" else "📉 SHORT"
entry_badge = (
    "🟢 دخول فوري (Market)"  if best["entry_type"] == "MARKET" else
    "🔵 أمر معلق (Limit)"
)

st.markdown(
    f"""
    <div style="
        background: linear-gradient(135deg, #0f172a, #1e293b);
        border: 2px solid {dir_color};
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 16px;
    ">
        <div style="display:flex; justify-content:space-between; align-items:center">
            <div>
                <h2 style="color:{dir_color}; margin:0">
                    {best['emoji']} {best['symbol']}
                    &nbsp; {dir_label}
                </h2>
                <p style="color:#94a3b8; margin:4px 0">
                    {best['pair_name']} &nbsp;|&nbsp;
                    ⏰ {best['timeframe']} &nbsp;|&nbsp;
                    {entry_badge}
                </p>
                <p style="color:#64748b; font-size:13px; margin:4px 0">
                    {best['entry_reason']}
                </p>
            </div>
            <div style="text-align:right">
                <div style="font-size:42px; color:{dir_color};
                            font-weight:900; line-height:1">
                    {best['grade']}
                </div>
                <div style="color:#94a3b8; font-size:14px">
                    {best['final_score']}/10
                </div>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Entry Levels ─────────────────────────
st.subheader("🎯 مستويات الدخول")
lc = st.columns(5)
labels_vals = [
    ("الدخول",   best["entry_price"],   None),
    ("Stop Loss",best["stop_loss"],      best["stop_loss"]   - best["entry_price"]),
    ("هدف 1",   best["take_profit_1"],  best["take_profit_1"] - best["entry_price"]),
    ("هدف 2",   best["take_profit_2"],  best["take_profit_2"] - best["entry_price"]),
    ("هدف 3",   best["take_profit_3"],  best["take_profit_3"] - best["entry_price"]),
]
for col, (lbl, val, diff) in zip(lc, labels_vals):
    delta = (
        f"{diff/best['entry_price']*100:+.3f}%"
        if diff is not None else None
    )
    col.metric(lbl, f"{val:.5f}", delta=delta,
               delta_color="inverse" if lbl == "Stop Loss" else "normal")

# ── Risk ────────────────────────────────
risk = calculate_risk(
    data={"symbol": best["symbol"], "side": best["side"],
          "price": str(best["entry_price"]),
          "timeframe": best["timeframe"],
          "atr": str(best.get("atr", 0))},
    ai_score=best["final_score"],
    account_balance=account,
)

rc = st.columns(4)
rc[0].metric("المخاطرة",     f"{risk['risk_percent']}%")
rc[1].metric("R:R",          f"1:{best['rr_ratio']}")
rc[2].metric("خسارة محتملة", f"-${risk['potential_loss']:.2f}")
rc[3].metric("ربح محتملة",  f"+${risk['potential_gain']:.2f}")

# ── Score Chart ──────────────────────────
st.subheader("📊 تفاصيل النقاط")
bd     = best["breakdown"]
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
    height=260,
    margin=dict(t=5, b=5, l=5, r=5),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font_color="white",
)
st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# ══════════════════════════════════════════
# All Results Table
# ══════════════════════════════════════════
st.subheader("📋 كل الفرص المكتشفة")

# ── Filters ──
fc1, fc2, fc3 = st.columns(3)
side_f = fc1.multiselect("الاتجاه", ["BUY","SELL"], default=["BUY","SELL"])
tf_f   = fc2.multiselect("الإطار", selected_tfs, default=selected_tfs)
min_sc = fc3.slider("حد أدنى للنقاط", 0.0, 10.0, 0.0, 0.5)

filtered = [
    r for r in results
    if r["side"] in side_f
    and r["timeframe"] in tf_f
    and r["final_score"] >= min_sc
]

# ── Cards Grid ───────────────────────────
for i in range(0, len(filtered), 3):
    cols = st.columns(3)
    for j, col in enumerate(cols):
        if i + j >= len(filtered):
            break
        r = filtered[i + j]

        dc = "#22c55e" if r["side"] == "BUY" else "#ef4444"
        dl = "📈 BUY" if r["side"] == "BUY" else "📉 SELL"
        et = "Market 🟢" if r["entry_type"] == "MARKET" else "Limit 🔵"

        # Patterns
        pats = ", ".join(r.get("patterns", [])[:2]) or "—"

        with col:
            st.markdown(
                f"""
                <div style="
                    background:#1e293b;
                    border-left: 4px solid {dc};
                    border-radius:12px;
                    padding:16px;
                    margin-bottom:12px;
                    height:100%;
                ">
                    <div style="display:flex;
                                justify-content:space-between">
                        <b style="color:{dc}; font-size:16px">
                            {r['emoji']} {r['symbol']}
                        </b>
                        <span style="color:{dc}; font-weight:700">
                            {r['grade']} · {r['final_score']}/10
                        </span>
                    </div>
                    <div style="color:#94a3b8; font-size:12px;
                                margin:4px 0">
                        {dl} &nbsp;|&nbsp; ⏰ {r['timeframe']}
                        &nbsp;|&nbsp; {et}
                    </div>
                    <hr style="border-color:#334155; margin:8px 0">
                    <div style="font-size:12px; color:#e2e8f0">
                        🎯 Entry:&nbsp;&nbsp;
                        <b>{r['entry_price']:.5f}</b><br>
                        🛑 SL:&nbsp;&nbsp;&nbsp;&nbsp;
                        <b>{r['stop_loss']:.5f}</b><br>
                        ✅ TP1:&nbsp;&nbsp;&nbsp;
                        <b>{r['take_profit_1']:.5f}</b><br>
                        ✅ TP2:&nbsp;&nbsp;&nbsp;
                        <b>{r['take_profit_2']:.5f}</b>
                    </div>
                    <hr style="border-color:#334155; margin:8px 0">
                    <div style="font-size:11px; color:#64748b">
                        📐 R:R 1:{r['rr_ratio']} &nbsp;|&nbsp;
                        🎯 {r['confidence']:.0f}% confidence<br>
                        📊 MTF {r['mtf_aligned']:.0f}% aligned<br>
                        🕯 {pats}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Save button
            if st.button(f"💾 حفظ #{i+j+1}", key=f"save_{r['symbol']}_{r['timeframe']}_{i+j}"):
                save_data = {
                    "symbol":    r["symbol"],
                    "side":      r["side"],
                    "price":     str(r["entry_price"]),
                    "timeframe": r["timeframe"],
                }
                score_result = {
                    "final_score": r["final_score"],
                    "grade":       r["grade"],
                    "breakdown":   r["breakdown"],
                    "approved":    True,
                }
                risk_data = calculate_risk(
                    save_data, r["final_score"], account
                )
                ai_mock = {
                    "final_score":       r["final_score"],
                    "analysis_summary":  r["entry_reason"],
                    "market_condition":  r["structure"],
                    "confidence":        "HIGH" if r["confidence"] > 70 else "MEDIUM",
                }
                trade_id = save_trade(
                    save_data, score_result, risk_data, ai_mock
                )
                st.success(f"✅ محفوظ — Trade #{trade_id}")

# ══════════════════════════════════════════
# Market Overview Chart
# ══════════════════════════════════════════
st.markdown("---")
st.subheader("🌍 نظرة عامة على السوق")

if results:
    overview_data = []
    for r in results:
        overview_data.append({
            "Symbol":    r["symbol"],
            "Side":      r["side"],
            "Score":     r["final_score"],
            "R:R":       r["rr_ratio"],
            "Timeframe": r["timeframe"],
            "Confidence":r["confidence"],
        })

    ov_df = pd.DataFrame(overview_data)

    fig2 = go.Figure()

    for side, color in [("BUY", "#22c55e"), ("SELL", "#ef4444")]:
        mask = ov_df["Side"] == side
        if mask.any():
            sub = ov_df[mask]
            fig2.add_trace(go.Scatter(
                x=sub["R:R"],
                y=sub["Score"],
                mode="markers+text",
                name=side,
                marker=dict(
                    color=color, size=sub["Confidence"] / 5,
                    line=dict(width=1, color="white"),
                ),
                text=sub["Symbol"],
                textposition="top center",
                textfont=dict(color="white", size=10),
                hovertemplate=(
                    "<b>%{text}</b><br>"
                    "Score: %{y:.1f}<br>"
                    "R:R: 1:%{x:.2f}<br>"
                    "<extra></extra>"
                ),
            ))

    fig2.add_hline(y=7.5, line_dash="dash", line_color="#f59e0b",
                   annotation_text="Target Score 7.5")
    fig2.add_vline(x=2.0, line_dash="dash", line_color="#6366f1",
                   annotation_text="Target R:R 2.0")

    fig2.update_layout(
        xaxis_title="R:R Ratio",
        yaxis_title="Signal Score",
        height=400,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="white",
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    st.plotly_chart(fig2, use_container_width=True)
    st.caption(
        "حجم الدائرة = درجة الثقة · "
        "الأفضل: نقطة في الزاوية اليمنى العليا ↗️"
    )
