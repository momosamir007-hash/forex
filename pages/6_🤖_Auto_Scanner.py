"""
Auto Scanner Page - النسخة الكاملة
تستخدم ScannerScheduler للمسح في الخلفية
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

from app.auto_scanner       import auto_scanner
from app.scanner_scheduler  import scheduler, alert_system
from app.config             import SUPPORTED_PAIRS, TIMEFRAME_WEIGHTS
from app.database           import save_trade, init_db
from app.risk_manager       import calculate_risk

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
# Sidebar
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

    interval = st.select_slider(
        "فترة المسح التلقائي",
        options=[5, 10, 15, 30, 60],
        value=15,
        format_func=lambda x: f"{x} دقيقة",
    )

    use_ai = st.toggle(
        "🤖 Gemini AI",
        value=False,
        help="أدق لكن أبطأ",
    )

    min_rr   = st.slider("الحد الأدنى R:R",    1.0, 4.0, 1.5, 0.5)
    min_conf = st.slider("الحد الأدنى الثقة %", 30,  90,  55,  5)
    account  = st.number_input("💰 الرصيد ($)", 100.0, 1_000_000.0, 10_000.0)

    st.markdown("---")

    # ── Scheduler Controls ────────────────
    st.subheader("🔄 التشغيل التلقائي")

    status = scheduler.get_status()

    if status["running"]:
        st.success(
            f"🟢 يعمل\n\n"
            f"المسح القادم: **{status['next_scan_in_min']} دقيقة**\n\n"
            f"إجمالي عمليات المسح: {status['total_scans']}"
        )
        if st.button("⏹️ إيقاف التلقائي", use_container_width=True):
            scheduler.stop()
            st.rerun()
    else:
        st.info("⚪ متوقف")
        if st.button("▶️ تشغيل تلقائي", type="primary",
                     use_container_width=True):
            scheduler.update_config(
                interval_minutes = interval,
                pairs            = selected_pairs,
                timeframes       = selected_tfs,
                use_ai           = use_ai,
            )
            scheduler.start()
            st.success("✅ بدأ التشغيل التلقائي!")
            st.rerun()

# ══════════════════════════════════════════
# Auto-refresh إذا كان الـ Scheduler يعمل
# ══════════════════════════════════════════
if scheduler.is_running:
    refresh_ms = interval * 60 * 1000
    st_autorefresh(interval=refresh_ms, key="sched_refresh")

# ══════════════════════════════════════════
# Manual Scan Button
# ══════════════════════════════════════════
col1, col2, col3 = st.columns([2, 2, 4])

scan_now = col1.button(
    "🔍 مسح فوري",
    type="primary",
    use_container_width=True,
)
clear_btn = col2.button(
    "🗑️ مسح النتائج",
    use_container_width=True,
)

if clear_btn:
    st.session_state.pop("scan_results", None)
    st.rerun()

if scheduler.is_running:
    col3.info(
        f"🔄 مسح تلقائي كل {interval} دقيقة | "
        f"القادم: {scheduler.next_scan_in} دقيقة"
    )

# ══════════════════════════════════════════
# Run Manual Scan
# ══════════════════════════════════════════
if scan_now:
    if not selected_pairs or not selected_tfs:
        st.warning("اختر أزواج وإطارات زمنية")
        st.stop()

    total = len(selected_pairs) * len(selected_tfs)
    prog  = st.progress(0, f"🔍 فحص {total} إعداد...")

    with st.spinner("جاري الفحص..."):
        results = auto_scanner.scan_all(
            timeframes  = selected_tfs,
            pairs       = selected_pairs,
            use_ai      = use_ai,
            max_workers = 3,
        )
        results = [
            r for r in results
            if r.get("rr_ratio",   0) >= min_rr and
               r.get("confidence", 0) >= min_conf
        ]

    prog.progress(100, "✅ اكتمل!")

    st.session_state["scan_results"] = results
    st.session_state["scan_time"]    = (
        datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    )

    if results:
        st.success(f"✅ وجد **{len(results)} فرصة**!")
    else:
        st.warning("⚠️ لا توجد فرص تستوفي المعايير الآن")

# ── استخدام نتائج الـ Scheduler إذا توفرت ──
elif scheduler.is_running and scheduler.last_results:
    results_raw = [
        r for r in scheduler.last_results
        if r.get("rr_ratio",   0) >= min_rr and
           r.get("confidence", 0) >= min_conf
    ]
    if results_raw:
        st.session_state["scan_results"] = results_raw
        st.session_state["scan_time"]    = (
            scheduler.last_scan_at.strftime("%H:%M:%S UTC")
            if scheduler.last_scan_at else "—"
        )

# ══════════════════════════════════════════
# Display
# ══════════════════════════════════════════
results  = st.session_state.get("scan_results", [])
scan_time = st.session_state.get("scan_time", "—")

if not results:
    # ── Empty State ──────────────────────
    st.markdown(
        """
        <div style="text-align:center; padding:60px;
                    background:#1e293b; border-radius:16px;
                    margin:20px 0">
            <div style="font-size:64px">🔍</div>
            <h3 style="color:#94a3b8">
                لا توجد نتائج بعد
            </h3>
            <p style="color:#64748b">
                اضغط <b>مسح فوري</b> أو فعّل <b>التشغيل التلقائي</b>
                من القائمة الجانبية
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

# ── Header ───────────────────────────────
st.markdown("---")
hc1, hc2, hc3, hc4, hc5 = st.columns(5)
hc1.metric("🔢 الفرص",        len(results))
hc2.metric("🟢 BUY",          sum(1 for r in results if r["side"]=="BUY"))
hc3.metric("🔴 SELL",         sum(1 for r in results if r["side"]=="SELL"))
hc4.metric("📐 متوسط R:R",   f"1:{sum(r['rr_ratio'] for r in results)/len(results):.2f}")
hc5.metric("🕐 آخر مسح",     scan_time)

st.markdown("---")

# ══════════════════════════════════════════
# Alerts Section
# ══════════════════════════════════════════
recent_alerts = alert_system.get_recent(5)
if recent_alerts:
    st.subheader("🚨 تنبيهات عالية الجودة")
    for al in reversed(recent_alerts):
        dc = "#22c55e" if al["side"] == "BUY" else "#ef4444"
        st.markdown(
            f"""
            <div style="background:#1e293b;
                        border-left:4px solid {dc};
                        border-radius:8px;
                        padding:12px 16px;
                        margin:6px 0;
                        display:flex;
                        justify-content:space-between">
                <span style="color:#e2e8f0">
                    🚨 <b style="color:{dc}">
                        {al['symbol']} {al['side']}
                    </b>
                    &nbsp;·&nbsp; {al['tf']}
                    &nbsp;·&nbsp; {al['type']}
                    &nbsp;·&nbsp; Score: <b>{al['score']}</b>
                    &nbsp;·&nbsp; R:R 1:{al['rr']}
                </span>
                <span style="color:#64748b; font-size:12px">
                    {al['time']}
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("---")

# ══════════════════════════════════════════
# Best Opportunity
# ══════════════════════════════════════════
best = results[0]
st.subheader("🏆 أفضل فرصة الآن")

dc  = "#22c55e" if best["side"] == "BUY" else "#ef4444"
dl  = "📈 LONG"  if best["side"] == "BUY" else "📉 SHORT"
et  = "🟢 Market (دخول فوري)" if best["entry_type"] == "MARKET" \
      else "🔵 Limit (أمر معلق)"

st.markdown(
    f"""
    <div style="background:linear-gradient(135deg,#0f172a,#1e293b);
                border:2px solid {dc}; border-radius:16px;
                padding:24px; margin-bottom:16px">
        <div style="display:flex;
                    justify-content:space-between;
                    align-items:center">
            <div>
                <h2 style="color:{dc}; margin:0">
                    {best['emoji']} {best['symbol']} &nbsp; {dl}
                </h2>
                <p style="color:#94a3b8; margin:6px 0">
                    {best['pair_name']} &nbsp;|&nbsp;
                    ⏰ {best['timeframe']} &nbsp;|&nbsp;
                    {et}
                </p>
                <p style="color:#64748b; font-size:13px">
                    📌 {best['entry_reason']}
                </p>
            </div>
            <div style="text-align:center">
                <div style="font-size:52px; color:{dc};
                            font-weight:900; line-height:1">
                    {best['grade']}
                </div>
                <div style="color:#94a3b8">
                    {best['final_score']}/10
                </div>
                <div style="color:#64748b; font-size:12px">
                    {best['confidence']:.0f}% confidence
                </div>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Levels ───────────────────────────────
lc = st.columns(5)
for col, (lbl, val, diff) in zip(lc, [
    ("الدخول",   best["entry_price"],   None),
    ("Stop Loss",best["stop_loss"],     best["stop_loss"]    - best["entry_price"]),
    ("هدف 1",   best["take_profit_1"], best["take_profit_1"] - best["entry_price"]),
    ("هدف 2",   best["take_profit_2"], best["take_profit_2"] - best["entry_price"]),
    ("هدف 3",   best["take_profit_3"], best["take_profit_3"] - best["entry_price"]),
]):
    delta = f"{diff/best['entry_price']*100:+.3f}%" if diff is not None else None
    col.metric(lbl, f"{val:.5f}", delta=delta,
               delta_color="inverse" if lbl == "Stop Loss" else "normal")

# ── Risk ────────────────────────────────
risk_r = calculate_risk(
    {"symbol": best["symbol"], "side": best["side"],
     "price": str(best["entry_price"]),
     "timeframe": best["timeframe"],
     "atr": str(best.get("atr", 0))},
    best["final_score"], account,
)
rc = st.columns(4)
rc[0].metric("المخاطرة",      f"{risk_r['risk_percent']}%")
rc[1].metric("R:R",           f"1:{best['rr_ratio']}")
rc[2].metric("خسارة محتملة", f"-${risk_r['potential_loss']:.2f}")
rc[3].metric("ربح محتمل",    f"+${risk_r['potential_gain']:.2f}")

st.markdown("---")

# ══════════════════════════════════════════
# All Results Cards
# ══════════════════════════════════════════
st.subheader(f"📋 كل الفرص ({len(results)})")

fc1, fc2 = st.columns(2)
side_f = fc1.multiselect(
    "الاتجاه", ["BUY","SELL"], default=["BUY","SELL"]
)
tf_f = fc2.multiselect(
    "الإطار", selected_tfs or ["15m","1h","4h"],
    default=selected_tfs or ["15m","1h","4h"],
)

filtered = [
    r for r in results
    if r["side"] in side_f and r["timeframe"] in tf_f
]

for i in range(0, len(filtered), 3):
    cols = st.columns(3)
    for j, col in enumerate(cols):
        if i + j >= len(filtered):
            break
        r  = filtered[i + j]
        dc = "#22c55e" if r["side"] == "BUY" else "#ef4444"
        et = "Market 🟢" if r["entry_type"] == "MARKET" else "Limit 🔵"
        pats = ", ".join(r.get("patterns", [])[:2]) or "—"

        with col:
            st.markdown(
                f"""
                <div style="background:#1e293b;
                            border-left:4px solid {dc};
                            border-radius:12px;
                            padding:16px;
                            margin-bottom:12px">
                    <div style="display:flex;
                                justify-content:space-between">
                        <b style="color:{dc}; font-size:15px">
                            {r['emoji']} {r['symbol']}
                        </b>
                        <span style="color:{dc}; font-weight:700">
                            {r['grade']} · {r['final_score']}/10
                        </span>
                    </div>
                    <div style="color:#94a3b8; font-size:12px;
                                margin:4px 0">
                        {'📈' if r['side']=='BUY' else '📉'}
                        {r['side']} · ⏰ {r['timeframe']} · {et}
                    </div>
                    <hr style="border-color:#334155; margin:8px 0">
                    <div style="font-size:12px; color:#e2e8f0;
                                line-height:1.8">
                        🎯 Entry: <b>{r['entry_price']:.5f}</b><br>
                        🛑 SL: &nbsp;&nbsp;<b>{r['stop_loss']:.5f}</b><br>
                        ✅ TP1: &nbsp;<b>{r['take_profit_1']:.5f}</b><br>
                        ✅ TP2: &nbsp;<b>{r['take_profit_2']:.5f}</b><br>
                        ✅ TP3: &nbsp;<b>{r['take_profit_3']:.5f}</b>
                    </div>
                    <hr style="border-color:#334155; margin:8px 0">
                    <div style="font-size:11px; color:#64748b;
                                line-height:1.6">
                        📐 R:R 1:{r['rr_ratio']} &nbsp;|&nbsp;
                        🎯 {r['confidence']:.0f}%<br>
                        📊 MTF {r['mtf_aligned']:.0f}%<br>
                        🕯 {pats}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if st.button(
                "💾 حفظ",
                key=f"sv_{r['symbol']}_{r['timeframe']}_{i+j}",
                use_container_width=True,
            ):
                t_id = save_trade(
                    {"symbol": r["symbol"], "side": r["side"],
                     "price": str(r["entry_price"]),
                     "timeframe": r["timeframe"]},
                    {"final_score": r["final_score"],
                     "grade": r["grade"],
                     "breakdown": r["breakdown"],
                     "approved": True},
                    calculate_risk(
                        {"symbol": r["symbol"], "side": r["side"],
                         "price": str(r["entry_price"]),
                         "timeframe": r["timeframe"],
                         "atr": str(r.get("atr", 0))},
                        r["final_score"], account,
                    ),
                    {"final_score": r["final_score"],
                     "analysis_summary": r["entry_reason"],
                     "market_condition": r["structure"],
                     "confidence": "HIGH" if r["confidence"] > 70 else "MEDIUM"},
                )
                st.success(f"✅ Trade #{t_id}")

# ══════════════════════════════════════════
# Scan History
# ══════════════════════════════════════════
if scheduler.scan_history:
    st.markdown("---")
    st.subheader("📜 سجل عمليات المسح")
    hist_df = pd.DataFrame(scheduler.scan_history)
    st.dataframe(
        hist_df[[
            "scan_number", "timestamp", "opportunities",
            "elapsed_sec", "top_signal", "top_score",
        ]].rename(columns={
            "scan_number":   "#",
            "timestamp":     "الوقت",
            "opportunities": "الفرص",
            "elapsed_sec":   "المدة (ث)",
            "top_signal":    "أفضل زوج",
            "top_score":     "أعلى نقطة",
        }),
        use_container_width=True,
    )
