"""
Auto Scanner Page - واجهة محدَّثة
تدعم 3 أوضاع مسح مختلفة
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

from app.auto_scanner      import auto_scanner
from app.scanner_scheduler import scheduler, alert_system
from app.config            import SUPPORTED_PAIRS, TIMEFRAME_WEIGHTS
from app.database          import save_trade, init_db
from app.risk_manager      import calculate_risk

st.set_page_config(
    page_title="Auto Scanner",
    page_icon="🤖",
    layout="wide",
)
init_db()

st.title("🤖 Auto Market Scanner")
st.markdown("النظام يفحص السوق لوحده ويحدد أفضل فرص الدخول")
st.markdown("---")

# ══════════════════════════════════════════
# Sidebar
# ══════════════════════════════════════════
with st.sidebar:
    st.subheader("⚙️ إعدادات المسح")

    selected_pairs = st.multiselect(
        "الأزواج",
        list(SUPPORTED_PAIRS.keys()),
        default=list(SUPPORTED_PAIRS.keys()),
        format_func=lambda s:
            f"{SUPPORTED_PAIRS[s]['emoji']} {s}",
    )

    selected_tfs = st.multiselect(
        "الإطارات الزمنية",
        ["1m","5m","15m","30m","1h","4h","1d"],
        default=["15m", "1h", "4h"],
    )

    # ── وضع المسح ────────────────────────
    st.markdown("---")
    scan_mode = st.radio(
        "🎯 وضع المسح",
        options=["relaxed", "moderate", "strict"],
        index=1,
        format_func=lambda x: {
            "relaxed":  "🟡 مخفف  — فرص أكثر",
            "moderate": "🟠 متوسط — موصى به",
            "strict":   "🔴 صارم  — إشارات أجود",
        }[x],
    )

    # عرض المعايير الحالية
    thresholds = {
        "relaxed":  {"score": 5.0, "rr": 1.0, "conf": 35, "mtf": 0},
        "moderate": {"score": 6.0, "rr": 1.3, "conf": 45, "mtf": 25},
        "strict":   {"score": 7.5, "rr": 1.5, "conf": 60, "mtf": 50},
    }[scan_mode]

    st.caption(
        f"Score ≥ {thresholds['score']} | "
        f"R:R ≥ {thresholds['rr']} | "
        f"Conf ≥ {thresholds['conf']}% | "
        f"MTF ≥ {thresholds['mtf']}%"
    )

    st.markdown("---")
    use_ai  = st.toggle("🤖 Gemini AI", value=False,
                        help="أدق لكن أبطأ")
    account = st.number_input("💰 الرصيد ($)", 100.0,
                               1_000_000.0, 10_000.0)

    # ── Auto Scheduler ────────────────────
    st.markdown("---")
    st.subheader("🔄 التشغيل التلقائي")

    interval = st.select_slider(
        "فترة المسح",
        [5, 10, 15, 30, 60],
        value=15,
        format_func=lambda x: f"{x} دقيقة",
    )

    status = scheduler.get_status()
    if status["running"]:
        st.success(
            f"🟢 يعمل\n\n"
            f"القادم: **{status['next_scan_in_min']} دقيقة**"
        )
        if st.button("⏹️ إيقاف", use_container_width=True):
            scheduler.stop()
            st.rerun()
    else:
        if st.button("▶️ تشغيل تلقائي",
                     type="primary", use_container_width=True):
            scheduler.update_config(
                interval_minutes=interval,
                pairs=selected_pairs,
                timeframes=selected_tfs,
                use_ai=use_ai,
            )
            scheduler.start()
            st.rerun()

# ── Auto refresh ─────────────────────────
if scheduler.is_running:
    st_autorefresh(
        interval=interval * 60 * 1000,
        key="sched_rf",
    )

# ══════════════════════════════════════════
# Scan Controls
# ══════════════════════════════════════════
bc1, bc2 = st.columns([1, 3])
scan_btn  = bc1.button("🔍 مسح الآن",
                        type="primary", use_container_width=True)

if scan_btn:
    if not selected_pairs or not selected_tfs:
        st.warning("اختر أزواج وإطارات زمنية")
        st.stop()

    total = len(selected_pairs) * len(selected_tfs)

    with st.status(
        f"🔍 فحص {total} إعداد ({scan_mode}) …",
        expanded=True,
    ) as scan_status:

        st.write(
            f"📊 الأزواج: {', '.join(selected_pairs)}\n\n"
            f"⏰ الإطارات: {', '.join(selected_tfs)}\n\n"
            f"🎯 الوضع: {scan_mode}"
        )

        results = auto_scanner.scan_all(
            timeframes  = selected_tfs,
            pairs       = selected_pairs,
            use_ai      = use_ai,
            max_workers = 4,
            mode        = scan_mode,
        )

        stats = auto_scanner.scan_stats

        scan_status.update(
            label=(
                f"✅ اكتمل | "
                f"فُحص: {stats.get('total_checked',0)} | "
                f"وُجد: {stats.get('raw_found',0)} | "
                f"بعد الفلترة: {len(results)}"
            ),
            state="complete",
        )

    st.session_state["scan_results"] = results
    st.session_state["scan_mode"]    = scan_mode
    st.session_state["scan_time"]    = (
        datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    )
    st.session_state["scan_stats"]   = stats

elif scheduler.is_running and scheduler.last_results:
    st.session_state["scan_results"] = scheduler.last_results
    st.session_state["scan_time"]    = (
        scheduler.last_scan_at.strftime("%H:%M UTC")
        if scheduler.last_scan_at else "—"
    )

# ══════════════════════════════════════════
# Results
# ══════════════════════════════════════════
results   = st.session_state.get("scan_results", [])
scan_time = st.session_state.get("scan_time", "—")
s_stats   = st.session_state.get("scan_stats", {})

if not results:
    # ── No Results UI ─────────────────────
    st.markdown("---")

    if s_stats:
        st.info(
            f"🔍 فُحص **{s_stats.get('total_checked',0)}** إعداد | "
            f"وُجد خام: **{s_stats.get('raw_found',0)}** | "
            f"بعد الفلترة: **0**"
        )

    st.markdown(
        """
        <div style="text-align:center; padding:50px;
                    background:#1e293b; border-radius:16px">
            <div style="font-size:56px">🔍</div>
            <h3 style="color:#94a3b8; margin:16px 0 8px">
                لا توجد فرص حالياً
            </h3>
            <p style="color:#64748b; margin:0">
                حاول تغيير الوضع إلى <b style="color:#fbbf24">
                مخفف 🟡</b> أو أضف المزيد من الأزواج
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── نصائح التحسين ────────────────────
    st.markdown("---")
    st.subheader("💡 نصائح لإيجاد فرص أكثر")

    t1, t2, t3 = st.columns(3)
    t1.info(
        "**🟡 وضع مخفف**\n\n"
        "غيّر وضع المسح إلى **مخفف**\n"
        "لإيجاد فرص بمعايير أقل صرامة"
    )
    t2.info(
        "**➕ أزواج أكثر**\n\n"
        "أضف كل الأزواج المتاحة\n"
        "للبحث في نطاق أوسع"
    )
    t3.info(
        "**⏰ إطارات مختلفة**\n\n"
        "جرب إطار **1h** أو **4h**\n"
        "للحصول على إشارات أوضح"
    )

    # ── Quick Scan مخفف ───────────────────
    st.markdown("---")
    if st.button(
        "⚡ مسح سريع بوضع مخفف",
        type="primary",
        use_container_width=True,
    ):
        with st.spinner("🔍 مسح سريع..."):
            quick_results = auto_scanner.scan_all(
                timeframes  = ["1h", "4h"],
                pairs       = list(SUPPORTED_PAIRS.keys()),
                use_ai      = False,
                max_workers = 4,
                mode        = "relaxed",
            )

        st.session_state["scan_results"] = quick_results
        st.session_state["scan_mode"]    = "relaxed"
        st.session_state["scan_time"]    = (
            datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        )
        st.rerun()

    st.stop()

# ══════════════════════════════════════════
# KPI Strip
# ══════════════════════════════════════════
st.markdown("---")
mode_label = st.session_state.get("scan_mode", scan_mode)
st.caption(f"وضع المسح: **{mode_label}** · آخر مسح: {scan_time}")

k1,k2,k3,k4,k5 = st.columns(5)
k1.metric("🔢 الفرص",      len(results))
k2.metric("🟢 BUY",        sum(1 for r in results if r["side"]=="BUY"))
k3.metric("🔴 SELL",       sum(1 for r in results if r["side"]=="SELL"))
k4.metric("📐 متوسط R:R", f"1:{sum(r['rr_ratio'] for r in results)/len(results):.2f}")
k5.metric("⭐ أعلى Score", f"{results[0]['final_score']:.1f}/10")

st.markdown("---")

# ══════════════════════════════════════════
# Best Opportunity
# ══════════════════════════════════════════
best = results[0]
st.subheader("🏆 أفضل فرصة")

dc = "#22c55e" if best["side"] == "BUY" else "#ef4444"
dl = "📈 LONG"  if best["side"] == "BUY" else "📉 SHORT"
et = "🟢 Market" if best["entry_type"] == "MARKET" else "🔵 Limit"

# تحديد قوة الإشارة
score_val = best["final_score"]
if score_val >= 8:
    strength = "🔥 قوية جداً"
elif score_val >= 7:
    strength = "✅ جيدة"
elif score_val >= 6:
    strength = "⚠️ مقبولة"
else:
    strength = "🔍 ضعيفة"

st.markdown(
    f"""
    <div style="
        background:linear-gradient(135deg,#0f172a,#1e293b);
        border:2px solid {dc};
        border-radius:16px;
        padding:24px;
        margin-bottom:16px;
    ">
        <div style="display:flex;
                    justify-content:space-between;
                    align-items:center;
                    flex-wrap:wrap;
                    gap:12px">
            <div>
                <h2 style="color:{dc}; margin:0; font-size:24px">
                    {best['emoji']} {best['symbol']} &nbsp; {dl}
                </h2>
                <p style="color:#94a3b8; margin:6px 0 4px; font-size:14px">
                    {best['pair_name']} &nbsp;|&nbsp;
                    ⏰ {best['timeframe']} &nbsp;|&nbsp;
                    {et} &nbsp;|&nbsp;
                    {strength}
                </p>
                <p style="color:#64748b; font-size:12px; margin:0">
                    📌 {best['entry_reason']}
                </p>
                <p style="color:#475569; font-size:11px; margin:4px 0 0">
                    🏗 Structure: {best['structure']} &nbsp;|&nbsp;
                    📊 Filters: {best['filters_passed']} &nbsp;|&nbsp;
                    ⏱ MTF: {best['mtf_aligned']:.0f}%
                </p>
            </div>
            <div style="text-align:center; min-width:80px">
                <div style="font-size:48px; color:{dc};
                            font-weight:900; line-height:1">
                    {best['grade']}
                </div>
                <div style="color:#94a3b8; font-size:13px">
                    {best['final_score']:.1f} / 10
                </div>
                <div style="color:#64748b; font-size:11px">
                    {best['confidence']:.0f}% conf
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
    pct   = f"{diff/best['entry_price']*100:+.3f}%" if diff else None
    is_sl = lbl == "Stop Loss"
    col.metric(
        lbl,
        f"{val:.5f}",
        delta=pct,
        delta_color="inverse" if is_sl else "normal",
    )

# ── Risk ─────────────────────────────────
risk_r = calculate_risk(
    {
        "symbol":    best["symbol"],
        "side":      best["side"],
        "price":     str(best["entry_price"]),
        "timeframe": best["timeframe"],
        "atr":       str(best.get("atr", 0)),
    },
    best["final_score"],
    account,
)

rc = st.columns(4)
rc[0].metric("المخاطرة",      f"{risk_r['risk_percent']}%")
rc[1].metric("R:R",           f"1:{best['rr_ratio']}")
rc[2].metric("خسارة محتملة", f"-${risk_r['potential_loss']:.2f}")
rc[3].metric("ربح محتمل",    f"+${risk_r['potential_gain']:.2f}")

st.markdown("---")

# ══════════════════════════════════════════
# All Results
# ══════════════════════════════════════════
st.subheader(f"📋 كل الفرص ({len(results)})")

for i in range(0, len(results), 3):
    cols = st.columns(3)
    for j, col in enumerate(cols):
        idx = i + j
        if idx >= len(results):
            break
        r  = results[idx]
        dc = "#22c55e" if r["side"] == "BUY" else "#ef4444"
        et = "Market 🟢" if r["entry_type"] == "MARKET" else "Limit 🔵"
        pats = ", ".join(r.get("patterns", [])[:2]) or "لا أنماط"
        blocked = ", ".join(r.get("blocked_by", [])) or "✅ كل الفلاتر"

        with col:
            st.markdown(
                f"""
                <div style="background:#1e293b;
                            border-left:4px solid {dc};
                            border-radius:12px; padding:16px;
                            margin-bottom:12px">
                    <div style="display:flex;
                                justify-content:space-between">
                        <b style="color:{dc}; font-size:15px">
                            {r['emoji']} {r['symbol']}
                        </b>
                        <span style="color:{dc}; font-weight:700">
                            {r['grade']} · {r['final_score']:.1f}
                        </span>
                    </div>
                    <div style="color:#94a3b8; font-size:12px;
                                margin:4px 0">
                        {'📈' if r['side']=='BUY' else '📉'}
                        {r['side']} · ⏰{r['timeframe']} · {et}
                    </div>
                    <hr style="border-color:#334155; margin:8px 0">
                    <div style="font-size:12px; color:#e2e8f0;
                                line-height:2">
                        🎯 <b>{r['entry_price']:.5f}</b>
                        &nbsp; → &nbsp;
                        🛑 <b>{r['stop_loss']:.5f}</b><br>
                        ✅ TP1 <b>{r['take_profit_1']:.5f}</b><br>
                        ✅ TP2 <b>{r['take_profit_2']:.5f}</b>
                    </div>
                    <hr style="border-color:#334155; margin:8px 0">
                    <div style="font-size:11px; color:#64748b;
                                line-height:1.7">
                        📐 R:R 1:{r['rr_ratio']} &nbsp;|&nbsp;
                        🎯 {r['confidence']:.0f}%<br>
                        ⏱ MTF {r['mtf_aligned']:.0f}% &nbsp;|&nbsp;
                        🏗 {r['structure']}<br>
                        🔍 {r['filters_passed']} فلاتر<br>
                        🕯 {pats}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if st.button(
                "💾 حفظ",
                key=f"sv_{r['symbol']}_{r['timeframe']}_{idx}",
                use_container_width=True,
            ):
                t_id = save_trade(
                    {
                        "symbol": r["symbol"], "side": r["side"],
                        "price":  str(r["entry_price"]),
                        "timeframe": r["timeframe"],
                    },
                    {
                        "final_score": r["final_score"],
                        "grade":       r["grade"],
                        "breakdown":   r["breakdown"],
                        "approved":    True,
                    },
                    calculate_risk(
                        {
                            "symbol": r["symbol"], "side": r["side"],
                            "price":  str(r["entry_price"]),
                            "timeframe": r["timeframe"],
                            "atr":    str(r.get("atr", 0)),
                        },
                        r["final_score"], account,
                    ),
                    {
                        "final_score":      r["final_score"],
                        "analysis_summary": r["entry_reason"],
                        "market_condition": r["structure"],
                        "confidence": (
                            "HIGH"   if r["confidence"] > 70 else
                            "MEDIUM" if r["confidence"] > 50 else
                            "LOW"
                        ),
                    },
                )
                st.success(f"✅ Trade #{t_id}")
