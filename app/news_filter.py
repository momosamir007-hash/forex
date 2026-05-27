"""
Economic News Filter
────────────────────
يمنع التداول:
  • قبل 30 دقيقة من خبر قوي
  • بعد 30 دقيقة من خبر قوي
  • يستخدم ForexFactory عبر scraping بسيط
    أو قائمة ثابتة بالأوقات المعروفة
"""

from __future__ import annotations
import requests
from datetime import datetime, timezone, timedelta
from app.config import NEWS_BLOCK_MINUTES

# ─────────────────────────────────────────
# High-Impact News Schedule (UTC)
# أوقات ثابتة للأخبار عالية التأثير
# ─────────────────────────────────────────

WEEKLY_HIGH_IMPACT = {
    # يوم الاثنين = 0 … الجمعة = 4
    4: [   # الجمعة - أخطر يوم
        {"time": "13:30", "name": "NFP - Non-Farm Payrolls",    "impact": "🔴 HIGH"},
        {"time": "13:30", "name": "US Unemployment Rate",        "impact": "🔴 HIGH"},
        {"time": "13:30", "name": "Average Hourly Earnings",     "impact": "🟠 MED"},
    ],
    2: [   # الأربعاء
        {"time": "13:30", "name": "US CPI Inflation",            "impact": "🔴 HIGH"},
        {"time": "18:00", "name": "FOMC Statement",              "impact": "🔴 HIGH"},
        {"time": "18:30", "name": "Fed Press Conference",        "impact": "🔴 HIGH"},
        {"time": "14:30", "name": "US Crude Inventories",        "impact": "🟠 MED"},
    ],
    1: [   # الثلاثاء
        {"time": "13:30", "name": "US PPI",                      "impact": "🟠 MED"},
        {"time": "10:00", "name": "UK CPI",                      "impact": "🟠 MED"},
    ],
    3: [   # الخميس
        {"time": "11:45", "name": "ECB Interest Rate Decision",  "impact": "🔴 HIGH"},
        {"time": "12:30", "name": "ECB Press Conference",        "impact": "🔴 HIGH"},
        {"time": "12:00", "name": "BOE Interest Rate Decision",  "impact": "🔴 HIGH"},
        {"time": "13:30", "name": "US Initial Jobless Claims",   "impact": "🟠 MED"},
        {"time": "13:30", "name": "US GDP",                      "impact": "🔴 HIGH"},
    ],
    0: [   # الاثنين
        {"time": "08:00", "name": "German CPI",                  "impact": "🟠 MED"},
    ],
}

# ─────────────────────────────────────────
# Main Function
# ─────────────────────────────────────────

def check_news_risk(symbol: str = "") -> dict:
    """
    Returns
    -------
    dict:
        safe          bool
        events        list[dict]  – upcoming/recent high-impact events
        next_event    dict | None
        reason        str
    """
    now        = datetime.now(timezone.utc)
    weekday    = now.weekday()
    block_min  = NEWS_BLOCK_MINUTES

    todays_events = WEEKLY_HIGH_IMPACT.get(weekday, [])
    dangerous: list[dict] = []
    upcoming:  list[dict] = []

    for ev in todays_events:
        ev_time = _parse_event_time(ev["time"], now)
        diff    = (ev_time - now).total_seconds() / 60   # minutes

        ev_full = {**ev, "utc_time": ev["time"], "minutes_away": round(diff)}

        if -block_min <= diff <= block_min:
            dangerous.append(ev_full)
        elif 0 < diff <= 180:
            upcoming.append(ev_full)

    upcoming.sort(key=lambda x: x["minutes_away"])

    if dangerous:
        names = ", ".join(d["name"] for d in dangerous)
        return {
            "safe":        False,
            "events":      dangerous,
            "next_event":  dangerous[0],
            "reason":      f"🚨 High-impact news active: {names}",
        }

    return {
        "safe":       True,
        "events":     upcoming,
        "next_event": upcoming[0] if upcoming else None,
        "reason":     "✅ News environment is clear",
    }


def _parse_event_time(time_str: str, now: datetime) -> datetime:
    """Convert 'HH:MM' string to today's UTC datetime."""
    h, m = map(int, time_str.split(":"))
    return now.replace(hour=h, minute=m, second=0, microsecond=0)


def get_upcoming_events(hours_ahead: int = 8) -> list[dict]:
    """Return all events in the next N hours (for Dashboard display)."""
    now      = datetime.now(timezone.utc)
    weekday  = now.weekday()
    events   = []

    for day_offset in range(2):
        target_day = (weekday + day_offset) % 7
        for ev in WEEKLY_HIGH_IMPACT.get(target_day, []):
            ev_time = _parse_event_time(ev["time"], now)
            if day_offset == 1:
                ev_time += timedelta(days=1)
            diff = (ev_time - now).total_seconds() / 60
            if 0 < diff <= hours_ahead * 60:
                events.append({**ev, "minutes_away": round(diff),
                               "utc_time": ev["time"]})

    return sorted(events, key=lambda x: x["minutes_away"])
