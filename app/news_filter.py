"""
News Filter - مُصحَّح
إصلاح: كل خبر الآن مرتبط بالأزواج المتأثرة فقط
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta
from app.config import NEWS_BLOCK_MINUTES


# ══════════════════════════════════════════
# جدول الأخبار مع الأزواج المتأثرة
# ══════════════════════════════════════════

WEEKLY_HIGH_IMPACT: dict[int, list[dict]] = {

    # ── الاثنين ──────────────────────────
    0: [
        {
            "time": "08:00",
            "name": "German CPI",
            "impact": "🟠 MED",
            "affects": ["EUR/USD", "GBP/USD", "EUR/JPY"],
        },
        {
            "time": "09:00",
            "name": "Eurozone Sentix",
            "impact": "🟡 LOW",
            "affects": ["EUR/USD"],
        },
    ],

    # ── الثلاثاء ─────────────────────────
    1: [
        {
            "time": "09:30",
            "name": "UK CPI Inflation",
            "impact": "🔴 HIGH",
            "affects": ["GBP/USD", "GBP/JPY", "EUR/GBP"],
        },
        {
            "time": "13:30",
            "name": "US PPI",
            "impact": "🟠 MED",
            "affects": ["EUR/USD", "GBP/USD", "USD/JPY", "XAU/USD"],
        },
        {
            "time": "14:00",
            "name": "US Retail Sales",
            "impact": "🟠 MED",
            "affects": ["EUR/USD", "GBP/USD", "USD/JPY", "XAU/USD"],
        },
    ],

    # ── الأربعاء ─────────────────────────
    2: [
        {
            "time": "09:30",
            "name": "UK GDP",
            "impact": "🟠 MED",
            "affects": ["GBP/USD", "GBP/JPY"],
        },
        {
            "time": "13:30",
            "name": "US CPI Inflation",
            "impact": "🔴 HIGH",
            "affects": ["EUR/USD", "GBP/USD", "USD/JPY",
                        "USD/CHF", "XAU/USD", "XAG/USD"],
        },
        {
            "time": "14:30",
            "name": "US Crude Oil Inventories",
            "impact": "🟠 MED",
            "affects": ["WTI/USD"],          # ← يؤثر على النفط فقط
        },
        {
            "time": "18:00",
            "name": "FOMC Statement",
            "impact": "🔴 HIGH",
            "affects": ["EUR/USD", "GBP/USD", "USD/JPY",
                        "USD/CHF", "AUD/USD", "XAU/USD", "XAG/USD"],
        },
        {
            "time": "18:30",
            "name": "Fed Press Conference",
            "impact": "🔴 HIGH",
            "affects": ["EUR/USD", "GBP/USD", "USD/JPY",
                        "USD/CHF", "AUD/USD", "XAU/USD"],
        },
    ],

    # ── الخميس ───────────────────────────
    3: [
        {
            "time": "11:45",
            "name": "ECB Interest Rate Decision",
            "impact": "🔴 HIGH",
            "affects": ["EUR/USD", "GBP/USD", "EUR/JPY"],
        },
        {
            "time": "12:15",
            "name": "ECB Press Conference",
            "impact": "🔴 HIGH",
            "affects": ["EUR/USD", "EUR/JPY"],
        },
        {
            "time": "12:00",
            "name": "BOE Interest Rate Decision",
            "impact": "🔴 HIGH",
            "affects": ["GBP/USD", "GBP/JPY", "EUR/GBP"],
        },
        {
            "time": "13:30",
            "name": "US Initial Jobless Claims",
            "impact": "🟠 MED",
            "affects": ["EUR/USD", "GBP/USD", "USD/JPY", "XAU/USD"],
        },
        {
            "time": "13:30",
            "name": "US GDP",
            "impact": "🔴 HIGH",
            "affects": ["EUR/USD", "GBP/USD", "USD/JPY",
                        "USD/CHF", "XAU/USD"],
        },
    ],

    # ── الجمعة ───────────────────────────
    4: [
        {
            "time": "13:30",
            "name": "NFP - Non-Farm Payrolls",
            "impact": "🔴 HIGH",
            "affects": ["EUR/USD", "GBP/USD", "USD/JPY",
                        "USD/CHF", "AUD/USD", "XAU/USD", "XAG/USD"],
        },
        {
            "time": "13:30",
            "name": "US Unemployment Rate",
            "impact": "🔴 HIGH",
            "affects": ["EUR/USD", "GBP/USD", "USD/JPY",
                        "USD/CHF", "AUD/USD", "XAU/USD"],
        },
        {
            "time": "13:30",
            "name": "Average Hourly Earnings",
            "impact": "🟠 MED",
            "affects": ["EUR/USD", "GBP/USD", "USD/JPY", "XAU/USD"],
        },
        {
            "time": "15:00",
            "name": "US Consumer Sentiment",
            "impact": "🟡 LOW",
            "affects": ["EUR/USD", "XAU/USD"],
        },
    ],
}


# ══════════════════════════════════════════
# Main Function
# ══════════════════════════════════════════

def check_news_risk(symbol: str = "") -> dict:
    """
    يتحقق فقط من الأخبار التي تؤثر على الزوج المُحدَّد.

    Returns
    -------
    dict:
        safe       bool
        events     list  – الأخبار الخطيرة النشطة الآن
        upcoming   list  – الأخبار القادمة
        reason     str
    """
    now       = datetime.now(timezone.utc)
    weekday   = now.weekday()
    block_min = NEWS_BLOCK_MINUTES

    todays_events = WEEKLY_HIGH_IMPACT.get(weekday, [])
    dangerous: list[dict] = []
    upcoming:  list[dict] = []

    for ev in todays_events:

        # ── فلتر الزوج ────────────────────
        affected = ev.get("affects", [])

        # إذا لم يحدد الزوج → تحقق من كل الأخبار
        # إذا حُدِّد الزوج → تحقق فقط من الأخبار التي تؤثر عليه
        if symbol and affected and symbol not in affected:
            continue   # ← هذا الخبر لا يؤثر على الزوج المختار

        ev_time = _parse_event_time(ev["time"], now)
        diff    = (ev_time - now).total_seconds() / 60   # دقائق

        # فقط الأخبار عالية التأثير تُوقف التداول
        high_impact = "🔴 HIGH" in ev.get("impact", "")

        ev_full = {
            **ev,
            "utc_time":     ev["time"],
            "minutes_away": round(diff),
        }

        if high_impact and (-block_min <= diff <= block_min):
            dangerous.append(ev_full)
        elif 0 < diff <= 240:
            upcoming.append(ev_full)

    upcoming.sort(key=lambda x: x["minutes_away"])

    if dangerous:
        names = ", ".join(d["name"] for d in dangerous)
        return {
            "safe":       False,
            "events":     dangerous,
            "upcoming":   upcoming,
            "next_event": dangerous[0],
            "reason":     f"🚨 High-impact news active: {names}",
        }

    return {
        "safe":       True,
        "events":     [],
        "upcoming":   upcoming,
        "next_event": upcoming[0] if upcoming else None,
        "reason":     "✅ News environment is clear",
    }


def get_upcoming_events(hours_ahead: int = 8) -> list[dict]:
    """أخبار الساعات القادمة - بدون فلتر زوج."""
    now     = datetime.now(timezone.utc)
    weekday = now.weekday()
    events: list[dict] = []

    for day_offset in range(2):
        target_day = (weekday + day_offset) % 7
        for ev in WEEKLY_HIGH_IMPACT.get(target_day, []):
            ev_time = _parse_event_time(ev["time"], now)
            if day_offset == 1:
                ev_time += timedelta(days=1)
            diff = (ev_time - now).total_seconds() / 60
            if 0 < diff <= hours_ahead * 60:
                events.append({
                    **ev,
                    "minutes_away": round(diff),
                    "utc_time":     ev["time"],
                })

    return sorted(events, key=lambda x: x["minutes_away"])


# ══════════════════════════════════════════
# Helper
# ══════════════════════════════════════════

def _parse_event_time(time_str: str, now: datetime) -> datetime:
    h, m = map(int, time_str.split(":"))
    return now.replace(hour=h, minute=m, second=0, microsecond=0)
