"""
Dynamic Risk Manager
────────────────────
• يحسب SL/TP بناءً على ATR + S/R
• يضبط حجم الصفقة بناءً على النقاط السابقة
• يضمن R:R ≥ MIN_RR_RATIO دائمًا
"""

from __future__ import annotations
from app.config import MIN_RR_RATIO, TIMEFRAME_WEIGHTS


def calculate_risk(
    data:            dict,
    ai_score:        float = 7.0,
    account_balance: float = 10_000.0,
    sr_levels:       dict | None = None,
) -> dict:
    entry    = float(data.get("price", 0))
    side     = data.get("side", "BUY")
    tf       = data.get("timeframe", "15m")
    atr      = float(data.get("atr", entry * 0.002))
    sr       = sr_levels or {}

    risk_pct = _dynamic_risk(ai_score)
    sl_tp    = _calculate_sl_tp(entry, side, tf, atr, sr)

    risk_per_unit = abs(entry - sl_tp["stop_loss"])
    reward        = abs(sl_tp["take_profit"] - entry)

    rr = round(reward / risk_per_unit, 2) if risk_per_unit else 0

    # ── Enforce minimum R:R ──────────────
    if rr < MIN_RR_RATIO:
        factor = MIN_RR_RATIO / rr if rr > 0 else MIN_RR_RATIO
        if side == "BUY":
            sl_tp["take_profit"]   = entry + reward * factor
            sl_tp["take_profit_2"] = entry + reward * factor * 1.6
            sl_tp["take_profit_3"] = entry + reward * factor * 2.5
        else:
            sl_tp["take_profit"]   = entry - reward * factor
            sl_tp["take_profit_2"] = entry - reward * factor * 1.6
            sl_tp["take_profit_3"] = entry - reward * factor * 2.5
        rr = MIN_RR_RATIO

    position_size = (
        (account_balance * risk_pct / 100) / risk_per_unit
        if risk_per_unit else 0
    )

    return {
        "entry":           round(entry, 5),
        "stop_loss":       round(sl_tp["stop_loss"],     5),
        "take_profit":     round(sl_tp["take_profit"],   5),
        "take_profit_2":   round(sl_tp["take_profit_2"], 5),
        "take_profit_3":   round(sl_tp["take_profit_3"], 5),
        "risk_percent":    risk_pct,
        "position_size":   round(position_size, 4),
        "rr_ratio":        rr,
        "potential_loss":  round(account_balance * risk_pct / 100, 2),
        "potential_gain":  round(account_balance * risk_pct * rr / 100, 2),
    }


def _dynamic_risk(score: float) -> float:
    """More conservative scaling."""
    if score >= 9.0: return 2.0
    if score >= 8.5: return 1.75
    if score >= 8.0: return 1.5
    if score >= 7.5: return 1.25
    if score >= 7.0: return 1.0
    return 0.5


def _calculate_sl_tp(
    entry: float, side: str, tf: str, atr: float, sr: dict
) -> dict:
    mult = {
        "1m":  (1.0, 1.5, 2.5, 4.0),
        "5m":  (1.2, 2.0, 3.0, 5.0),
        "15m": (1.5, 2.5, 4.0, 6.5),
        "30m": (1.8, 3.0, 5.0, 8.0),
        "1h":  (2.0, 3.5, 6.0, 10.0),
        "4h":  (2.5, 4.0, 7.0, 12.0),
        "1d":  (3.0, 5.0, 9.0, 15.0),
    }.get(tf, (1.5, 2.5, 4.0, 6.5))

    sl_m, tp1_m, tp2_m, tp3_m = mult

    if side == "BUY":
        sl  = entry - atr * sl_m
        tp1 = entry + atr * tp1_m
        tp2 = entry + atr * tp2_m
        tp3 = entry + atr * tp3_m

        # Snap SL to support if close
        support = sr.get("nearest_support", 0)
        if support and abs(sl - support) / entry < 0.002:
            sl = support - atr * 0.3

    else:
        sl  = entry + atr * sl_m
        tp1 = entry - atr * tp1_m
        tp2 = entry - atr * tp2_m
        tp3 = entry - atr * tp3_m

        # Snap SL to resistance if close
        resistance = sr.get("nearest_resistance", 0)
        if resistance and abs(sl - resistance) / entry < 0.002:
            sl = resistance + atr * 0.3

    return {
        "stop_loss":    sl,
        "take_profit":  tp1,
        "take_profit_2": tp2,
        "take_profit_3": tp3,
    }
