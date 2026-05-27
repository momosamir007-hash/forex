"""
Market Filters + TwelveData Fetcher
─────────────────────────────────────
• TwelveDataFetcher  – جلب بيانات OHLCV وحساب المؤشرات
• run_all_filters    – تشغيل جميع فلاتر السوق
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd
import ta

import requests

from app.config import (
    TWELVEDATA_API_KEY,
    TWELVEDATA_BASE,
    TIMEFRAME_MAP,
    MIN_VOLUME_RATIO,
    TRADING_START_HOUR,
    TRADING_END_HOUR,
    SESSIONS,
)
from app.logger import filter_logger


# ══════════════════════════════════════════
# TwelveData Fetcher
# ══════════════════════════════════════════

class TwelveDataFetcher:
    """
    Fetch OHLCV candles from TwelveData REST API
    and compute technical indicators.

    Built-in cache (60 s TTL) to avoid redundant requests.
    """

    # {cache_key: (timestamp, DataFrame)}
    _cache: dict[str, tuple[float, pd.DataFrame]] = {}
    _TTL   = 60   # seconds

    # ── Public: OHLCV ─────────────────────

    def get_ohlcv(
        self,
        symbol:    str,
        timeframe: str,
        limit:     int = 200,
    ) -> pd.DataFrame | None:
        """
        Return OHLCV DataFrame.
        Columns: open, high, low, close, volume
        Index:   datetime (UTC)
        """
        cache_key = f"{symbol}|{timeframe}|{limit}"
        cached    = self._cache.get(cache_key)

        if cached and (time.time() - cached[0]) < self._TTL:
            filter_logger.debug(f"Cache hit: {cache_key}")
            return cached[1]

        interval = TIMEFRAME_MAP.get(timeframe, "15min")

        try:
            resp = requests.get(
                f"{TWELVEDATA_BASE}/time_series",
                params={
                    "symbol":     symbol,
                    "interval":   interval,
                    "apikey":     TWELVEDATA_API_KEY,
                    "outputsize": limit,
                    "format":     "JSON",
                },
                timeout=12,
            )
            resp.raise_for_status()
            payload = resp.json()

            # ── API error ─────────────────
            if payload.get("status") == "error":
                filter_logger.error(
                    f"TwelveData API error for {symbol}: "
                    f"{payload.get('message','unknown')}"
                )
                return None

            values = payload.get("values", [])
            if not values:
                filter_logger.warning(f"No values returned for {symbol}")
                return None

            # ── Build DataFrame ───────────
            df = pd.DataFrame(values)
            df["datetime"] = pd.to_datetime(df["datetime"])
            df = df.set_index("datetime").sort_index()

            for col in ["open", "high", "low", "close"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            # volume absent for many FX pairs
            if "volume" in df.columns:
                df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)
            else:
                df["volume"] = 0.0

            df = df.dropna(subset=["open", "high", "low", "close"])

            self._cache[cache_key] = (time.time(), df)

            filter_logger.info(
                f"✅ TwelveData: {symbol} {timeframe} "
                f"→ {len(df)} candles"
            )
            return df

        except requests.exceptions.Timeout:
            filter_logger.error(f"TwelveData timeout for {symbol}")
            return None

        except requests.exceptions.RequestException as e:
            filter_logger.error(f"TwelveData request error: {e}")
            return None

        except Exception as e:
            filter_logger.error(f"TwelveData unexpected error: {e}")
            return None

    # ── Public: Indicators ────────────────

    def get_indicators(
        self,
        df: pd.DataFrame | None,
    ) -> dict:
        """
        Calculate all technical indicators from OHLCV DataFrame.
        Returns empty dict if data is insufficient.
        """
        if df is None or len(df) < 50:
            filter_logger.warning("Insufficient data for indicators")
            return {}

        c  = df["close"]
        h  = df["high"]
        lo = df["low"]
        v  = df["volume"]

        try:
            # ── Moving Averages ───────────
            ema20  = ta.trend.EMAIndicator(c, 20).ema_indicator()
            ema50  = ta.trend.EMAIndicator(c, 50).ema_indicator()
            ema200 = ta.trend.EMAIndicator(c, 200).ema_indicator()

            # ── MACD ──────────────────────
            macd_obj  = ta.trend.MACD(c)
            macd_line = macd_obj.macd()
            macd_sig  = macd_obj.macd_signal()
            macd_hist = macd_obj.macd_diff()

            # ── RSI ───────────────────────
            rsi = ta.momentum.RSIIndicator(c, 14).rsi()

            # ── Volatility ────────────────
            atr = ta.volatility.AverageTrueRange(
                h, lo, c, 14
            ).average_true_range()

            bb  = ta.volatility.BollingerBands(c, 20, 2)

            # ── Stochastic ────────────────
            stoch = ta.momentum.StochasticOscillator(
                h, lo, c, 14, 3
            )

            # ── Volume ────────────────────
            vol_sma   = v.rolling(20).mean()
            vol_ratio = (v / vol_sma).fillna(1.0)

            return {
                # EMAs
                "ema20":          round(float(ema20.iloc[-1]),  6),
                "ema50":          round(float(ema50.iloc[-1]),  6),
                "ema200":         round(float(ema200.iloc[-1]), 6),

                # MACD
                "macd":           round(float(macd_line.iloc[-1]), 6),
                "macd_signal":    round(float(macd_sig.iloc[-1]),  6),
                "macd_hist":      round(float(macd_hist.iloc[-1]), 6),

                # RSI
                "rsi":            round(float(rsi.iloc[-1]), 2),

                # Stochastic
                "stoch_k":        round(float(stoch.stoch().iloc[-1]),        2),
                "stoch_d":        round(float(stoch.stoch_signal().iloc[-1]), 2),

                # ATR & BB
                "atr":            round(float(atr.iloc[-1]),              6),
                "bb_upper":       round(float(bb.bollinger_hband().iloc[-1]), 6),
                "bb_middle":      round(float(bb.bollinger_mavg().iloc[-1]),  6),
                "bb_lower":       round(float(bb.bollinger_lband().iloc[-1]), 6),
                "bb_width":       round(float(bb.bollinger_wband().iloc[-1]), 6),

                # Volume
                "volume":         round(float(v.iloc[-1]),        2),
                "volume_sma":     round(float(vol_sma.iloc[-1]),  2),
                "volume_ratio":   round(float(vol_ratio.iloc[-1]), 3),

                # Price reference
                "current_price":  round(float(c.iloc[-1]),          6),
                "prev_close":     round(float(c.iloc[-2]),           6),
                "high_session":   round(float(h.tail(24).max()),     6),
                "low_session":    round(float(lo.tail(24).min()),    6),
            }

        except Exception as e:
            filter_logger.error(f"Indicator calculation error: {e}")
            return {}


# ══════════════════════════════════════════
# Market Filters
# ══════════════════════════════════════════

def run_all_filters(data: dict, ind: dict) -> dict:
    """
    Run every market filter and aggregate results.

    Returns
    -------
    dict:
        passed     bool   – True only if ALL filters pass
        filters    dict   – per-filter results
        blocked_by list   – names of failing filters
    """
    side  = data.get("side",  "BUY")
    price = float(data.get("price", 0))

    checks = {
        "Trend":      _trend_filter(side, price, ind),
        "Volume":     _volume_filter(ind),
        "RSI":        _rsi_filter(side, ind),
        "MACD":       _macd_filter(side, ind),
        "Stochastic": _stoch_filter(side, ind),
        "Volatility": _volatility_filter(ind),
        "Session":    _session_filter(),
        "Spread":     _spread_filter(ind),
    }

    blocked = [k for k, v in checks.items() if not v["passed"]]

    return {
        "passed":     len(blocked) == 0,
        "filters":    checks,
        "blocked_by": blocked,
    }


# ══════════════════════════════════════════
# Individual Filters
# ══════════════════════════════════════════

def _trend_filter(side: str, price: float, ind: dict) -> dict:
    """EMA alignment check (20 / 50 / 200)."""
    if not ind:
        return {"passed": True, "reason": "ℹ️ No indicator data"}

    e20  = ind.get("ema20",  0)
    e50  = ind.get("ema50",  0)
    e200 = ind.get("ema200", 0)

    if side == "BUY":
        passed = price > e200 and e20 > e50
        reason = (
            "✅ Bullish: price > EMA200 & EMA20 > EMA50"
            if passed else
            "❌ Bearish EMA structure — against BUY"
        )
    else:
        passed = price < e200 and e20 < e50
        reason = (
            "✅ Bearish: price < EMA200 & EMA20 < EMA50"
            if passed else
            "❌ Bullish EMA structure — against SELL"
        )

    return {
        "passed": passed,
        "reason": reason,
        "values": {
            "price": price,
            "ema20": e20,
            "ema50": e50,
            "ema200": e200,
        },
    }


def _volume_filter(ind: dict) -> dict:
    """Volume must be at least MIN_VOLUME_RATIO × 20-period average."""
    if not ind:
        return {"passed": True, "reason": "ℹ️ No indicator data"}

    # FX pairs have no real volume from TwelveData
    if ind.get("volume", 0) == 0:
        return {
            "passed": True,
            "reason": "ℹ️ Volume unavailable for this symbol — skipped",
            "value":  None,
        }

    vr     = ind.get("volume_ratio", 1.0)
    passed = vr >= MIN_VOLUME_RATIO

    return {
        "passed": passed,
        "reason": (
            f"✅ Volume ×{vr:.2f} ≥ minimum ×{MIN_VOLUME_RATIO}"
            if passed else
            f"❌ Volume ×{vr:.2f} < minimum ×{MIN_VOLUME_RATIO}"
        ),
        "value": vr,
    }


def _rsi_filter(side: str, ind: dict) -> dict:
    """RSI must not be at extremes for the signal direction."""
    if not ind:
        return {"passed": True, "reason": "ℹ️ No indicator data"}

    rsi = ind.get("rsi", 50.0)

    if side == "BUY":
        passed = rsi < 75
        reason = (
            f"✅ RSI {rsi:.1f} — not overbought"
            if passed else
            f"❌ RSI {rsi:.1f} — overbought (≥ 75) on BUY"
        )
    else:
        passed = rsi > 25
        reason = (
            f"✅ RSI {rsi:.1f} — not oversold"
            if passed else
            f"❌ RSI {rsi:.1f} — oversold (≤ 25) on SELL"
        )

    return {"passed": passed, "reason": reason, "value": rsi}


def _macd_filter(side: str, ind: dict) -> dict:
    """MACD histogram must support the signal direction."""
    if not ind:
        return {"passed": True, "reason": "ℹ️ No indicator data"}

    macd = ind.get("macd",      0.0)
    sig  = ind.get("macd_signal", 0.0)
    hist = ind.get("macd_hist",   0.0)

    if side == "BUY":
        passed = macd > sig or hist > 0
        reason = (
            "✅ MACD bullish momentum"
            if passed else
            "❌ MACD bearish — against BUY"
        )
    else:
        passed = macd < sig or hist < 0
        reason = (
            "✅ MACD bearish momentum"
            if passed else
            "❌ MACD bullish — against SELL"
        )

    return {
        "passed": passed,
        "reason": reason,
        "values": {"macd": macd, "signal": sig, "hist": hist},
    }


def _stoch_filter(side: str, ind: dict) -> dict:
    """Stochastic Oscillator confirmation."""
    if not ind:
        return {"passed": True, "reason": "ℹ️ No indicator data"}

    k = ind.get("stoch_k", 50.0)
    d = ind.get("stoch_d", 50.0)

    if side == "BUY":
        # Not overbought AND K crossing above D
        passed = k < 80 and k >= d
        reason = (
            f"✅ Stoch K:{k:.1f} D:{d:.1f} — bullish"
            if passed else
            f"❌ Stoch K:{k:.1f} D:{d:.1f} — overbought or bearish cross"
        )
    else:
        passed = k > 20 and k <= d
        reason = (
            f"✅ Stoch K:{k:.1f} D:{d:.1f} — bearish"
            if passed else
            f"❌ Stoch K:{k:.1f} D:{d:.1f} — oversold or bullish cross"
        )

    return {"passed": passed, "reason": reason,
            "values": {"k": k, "d": d}}


def _volatility_filter(ind: dict) -> dict:
    """ATR as % of price must be ≤ 5% (not excessively volatile)."""
    if not ind:
        return {"passed": True, "reason": "ℹ️ No indicator data"}

    atr   = ind.get("atr",           0.0)
    price = ind.get("current_price",  1.0)

    if price == 0:
        return {"passed": True, "reason": "ℹ️ Price is zero — skipped"}

    atr_pct = atr / price * 100
    passed  = atr_pct <= 5.0

    return {
        "passed": passed,
        "reason": (
            f"✅ ATR {atr_pct:.3f}% — within acceptable range"
            if passed else
            f"❌ ATR {atr_pct:.3f}% — too volatile (> 5%)"
        ),
        "value": round(atr_pct, 4),
    }


def _session_filter() -> dict:
    """Trading must be within the configured UTC session window."""
    now  = datetime.now(timezone.utc)
    hour = now.hour

    in_window = TRADING_START_HOUR <= hour <= TRADING_END_HOUR

    # Which named sessions are currently open?
    open_sessions: list[str] = []
    for name, (start, end) in SESSIONS.items():
        if start < end:
            if start <= hour < end:
                open_sessions.append(name)
        else:                        # wraps midnight
            if hour >= start or hour < end:
                open_sessions.append(name)

    label = ", ".join(open_sessions) if open_sessions else "none"

    return {
        "passed": in_window,
        "reason": (
            f"✅ Active session ({label}) — {hour:02d}:00 UTC"
            if in_window else
            f"❌ Outside trading window "
            f"({TRADING_START_HOUR:02d}:00–{TRADING_END_HOUR:02d}:00 UTC)"
        ),
    }


def _spread_filter(ind: dict) -> dict:
    """
    Proxy spread check via Bollinger Band width.
    Very tight BB width can indicate illiquid conditions.
    """
    if not ind:
        return {"passed": True, "reason": "ℹ️ No indicator data"}

    price = ind.get("current_price", 0)
    upper = ind.get("bb_upper",      0)
    lower = ind.get("bb_lower",      0)

    if not upper or not lower or price == 0:
        return {"passed": True, "reason": "ℹ️ BB data unavailable — skipped"}

    bb_width_pct = (upper - lower) / price * 100
    passed       = bb_width_pct > 0.05

    return {
        "passed": passed,
        "reason": (
            f"✅ BB width {bb_width_pct:.3f}% — spread acceptable"
            if passed else
            f"❌ BB width {bb_width_pct:.3f}% — spread too tight"
        ),
        "value": round(bb_width_pct, 4),
    }


# ══════════════════════════════════════════
# Singleton
# ══════════════════════════════════════════

try:
    data_fetcher = TwelveDataFetcher()
    filter_logger.info("✅ TwelveDataFetcher initialized")
except Exception as _e:
    filter_logger.error(f"TwelveDataFetcher init failed: {_e}")
    data_fetcher = None  # type: ignore
