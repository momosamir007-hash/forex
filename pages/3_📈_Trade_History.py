
import streamlit as st
import pandas as pd
from app.database import (
    get_all_trades, get_all_rejected,
    update_trade_result, init_db,
)

st.set_page_config(page_title="Trade History", page_icon="📈", layout="wide")
init_db()

st.title("📈 Trade History")
st.markdown("---")

tab1, tab2 = st.tabs(["✅ Approved Trades", "🚫 Rejected Signals"])

# ══════════════════════════════════════════
# Approved
# ══════════════════════════════════════════
with tab1:
    trades = get_all_trades()
    if not trades:
        st.info("No approved trades yet.")
    else:
        df = pd.DataFrame(trades)
        df["created_at"] = (
            pd.to_datetime(df["created_at"])
              .dt.strftime("%Y-%m-%d %H:%M")
        )

        # ── Filters ──
        fc1, fc2, fc3 = st.columns(3)
        syms = df["symbol"].unique().tolist()
        sym_f  = fc1.multiselect("Symbol",    syms,            default=syms)
        side_f = fc2.multiselect("Direction", ["BUY","SELL"],  default=["BUY","SELL"])
        res_f  = fc3.multiselect("Result",
                                  ["WIN","LOSS","None"],
                                  default=["WIN","LOSS","None"])

        mask = (
            df["symbol"].isin(sym_f) &
            df["side"].isin(side_f) &
            df["result"].astype(str).isin(res_f)
        )
        view = df[mask]

        st.dataframe(
            view[[
                "id","symbol","side","entry_price",
                "stop_loss","take_profit","final_score",
                "grade","confidence","status",
                "result","pnl_percent","created_at",
            ]].rename(columns={
                "entry_price":"Entry","stop_loss":"SL",
                "take_profit":"TP1","final_score":"Score",
                "pnl_percent":"P&L%","created_at":"Date",
            }),
            use_container_width=True,
            height=400,
        )

        st.caption(f"Showing {len(view)} of {len(df)} trades")

        # ── Update Result ──
        st.markdown("---")
        st.subheader("✏️ Update Trade Result")
        uc1, uc2, uc3, uc4 = st.columns(4)
        ids     = [t["id"] for t in trades]
        sel_id  = uc1.selectbox("Trade ID", ids)
        sel_res = uc2.selectbox("Result",   ["WIN","LOSS"])
        sel_pnl = uc3.number_input("P&L %", value=0.0, format="%.2f")
        if uc4.button("💾 Update", type="primary"):
            update_trade_result(sel_id, sel_res, sel_pnl)
            st.success(f"Trade #{sel_id} → {sel_res} ({sel_pnl:+.2f}%)")
            st.rerun()

# ══════════════════════════════════════════
# Rejected
# ══════════════════════════════════════════
with tab2:
    rejected = get_all_rejected()
    if not rejected:
        st.info("No rejected signals.")
    else:
        rdf = pd.DataFrame(rejected)
        rdf["created_at"] = (
            pd.to_datetime(rdf["created_at"])
              .dt.strftime("%Y-%m-%d %H:%M")
        )

        # ── Score filter ──
        min_s = st.slider("Min score filter", 0.0, 10.0, 0.0, 0.5)
        rdf   = rdf[rdf["score"] >= min_s]

        st.dataframe(
            rdf[[
                "id","symbol","side","price",
                "timeframe","score","reason","created_at",
            ]],
            use_container_width=True,
            height=400,
        )
        st.caption(f"Total rejected: {len(rdf)}")
