"""
Final Signal Scorer
───────────────────
يجمع نتائج كل الطبقات في نقطة واحدة نهائية.
"""

from __future__ import annotations
from app.config import MIN_SIGNAL_SCORE, SCORE_WEIGHTS


def calculate_score(
    ai_result:     dict,
    filter_result: dict,
    pa_result:     dict | None = None,
    smc_result:    dict | None = None,
    mtf_result:    dict | None = None,
    news_result:   dict | None = None,
) -> dict:
    """
    Weighted final score from all analysis layers.

    Weights (from config.py):
        trend        20%
        price_action 20%
        smart_money  15%
        ai           15%
        momentum     10%
        volume        8%
        mtf           7%
        news          5%
    """
    W = SCORE_WEIGHTS
    f = filter_result.get("filters", {})

    # ── Individual scores ────────────────
    trend_s  = 10.0 if f.get("Trend",      {}).get("passed") else 3.0
    vol_s    = _vol_score(f.get("Volume",   {}).get("value", 1.0))
    mom_s    = _rsi_score(f.get("RSI",      {}).get("value", 50))
    ai_s     = ai_result.get("final_score", 5.0)

    pa_s     = (pa_result  or {}).get("score",  5.0)
    smc_s    = (smc_result or {}).get("score",  5.0)
    mtf_s    = (mtf_result or {}).get("score",  7.0)
    news_s   = 10.0 if (news_result or {}).get("safe", True) else 2.0

    final = (
        trend_s * W["trend"]        +
        pa_s    * W["price_action"] +
        smc_s   * W["smart_money"]  +
        ai_s    * W["ai"]           +
        mom_s   * W["momentum"]     +
        vol_s   * W["volume"]       +
        mtf_s   * W["mtf"]          +
        news_s  * W["news"]
    )
    final = round(final, 2)

    # ── Hard blocks (instant reject) ─────
    hard_blocks: list[str] = []

    if not (news_result or {}).get("safe", True):
        hard_blocks.append("High-impact news active 📰")

    if (pa_result or {}).get("ranging"):
        hard_blocks.append("Ranging market detected ↔️")

    if not (mtf_result or {}).get("aligned", True):
        hard_blocks.append(
            f"MTF misaligned "
            f"({(mtf_result or {}).get('alignment_pct', 0):.0f}%)"
        )

    rejected_by_block = len(hard_blocks) > 0

    approved = final >= MIN_SIGNAL_SCORE and not rejected_by_block

    return {
        "final_score":   final,
        "approved":      approved,
        "grade":         _grade(final),
        "hard_blocks":   hard_blocks,
        "breakdown": {
            "trend":        round(trend_s, 2),
            "price_action": round(pa_s,    2),
            "smart_money":  round(smc_s,   2),
            "ai":           round(ai_s,    2),
            "momentum":     round(mom_s,   2),
            "volume":       round(vol_s,   2),
            "mtf":          round(mtf_s,   2),
            "news":         round(news_s,  2),
        },
    }


# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────

def _vol_score(vr: float | None) -> float:
    if vr is None: return 6.0
    if vr >= 3.0:  return 10.0
    if vr >= 2.0:  return 9.0
    if vr >= 1.5:  return 7.0
    if vr >= 1.0:  return 5.0
    return 2.0


def _rsi_score(rsi: float) -> float:
    if 45 <= rsi <= 65: return 9.0
    if 35 <= rsi <= 75: return 7.0
    if 25 <= rsi <= 80: return 5.0
    return 2.0


def _grade(s: float) -> str:
    if s >= 9.0: return "A+"
    if s >= 8.5: return "A"
    if s >= 8.0: return "A-"
    if s >= 7.5: return "B+"
    if s >= 7.0: return "B"
    if s >= 6.0: return "C"
    return "F"
