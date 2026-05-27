"""
Entry Engine
────────────
يحدد بدقة:
  • نقطة الدخول المثلى
  • Stop Loss بناءً على Structure
  • Take Profit 1/2/3 بناءً على S/R
  • نوع الدخول: Market / Limit / Stop
"""

from __future__ import annotations
import pandas as pd
import numpy as np
import ta
from app.logger import main_logger


# ══════════════════════════════════════════
# Entry Decision
# ══════════════════════════════════════════

class EntryEngine:

    def analyze(self, df: pd.DataFrame, side: str, symbol: str) -> dict:
        """
        يحلل الشارت ويحدد أفضل نقطة دخول.

        Returns
        -------
        dict:
            entry_type    : "MARKET" | "LIMIT" | "WAIT"
            entry_price   : float
            stop_loss     : float
            take_profit_1 : float
            take_profit_2 : float
            take_profit_3 : float
            rr_ratio      : float
            confidence    : float  0-100
            reason        : str
            invalidation  : float  (السعر الذي يُلغي الإشارة)
        """
        if df is None or len(df) < 50:
            return self._no_entry("Insufficient data")

        price   = float(df["close"].iloc[-1])
        atr     = self._get_atr(df)
        sr      = self._find_sr_levels(df)
        structure = self._market_structure(df)
        entry   = self._find_entry(df, side, atr, sr)

        if entry["type"] == "WAIT":
            return self._no_entry(entry["reason"])

        sl   = self._calculate_sl(df, side, entry["price"], atr, sr)
        tps  = self._calculate_tps(side, entry["price"], sl, sr, atr)
        rr   = self._calc_rr(entry["price"], sl, tps["tp1"])
        conf = self._confidence(df, side, rr, structure)

        return {
            "entry_type":    entry["type"],
            "entry_price":   round(entry["price"], 5),
            "stop_loss":     round(sl, 5),
            "take_profit_1": round(tps["tp1"], 5),
            "take_profit_2": round(tps["tp2"], 5),
            "take_profit_3": round(tps["tp3"], 5),
            "rr_ratio":      round(rr, 2),
            "confidence":    round(conf, 1),
            "reason":        entry["reason"],
            "invalidation":  round(sl, 5),
            "atr":           round(atr, 6),
            "structure":     structure,
            "sr_levels":     sr,
        }

    # ── ATR ──────────────────────────────

    def _get_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        try:
            atr = ta.volatility.AverageTrueRange(
                df["high"], df["low"], df["close"], period
            ).average_true_range()
            return float(atr.iloc[-1])
        except Exception:
            return float((df["high"] - df["low"]).tail(14).mean())

    # ── Support / Resistance ──────────────

    def _find_sr_levels(self, df: pd.DataFrame) -> dict:
        """أقوى مستويات S/R بناءً على Pivot Points و Volume."""
        h  = df["high"].values
        lo = df["low"].values
        c  = df["close"].values
        price = c[-1]

        levels: list[float] = []

        # Pivot highs & lows
        for i in range(3, len(df) - 3):
            if all(h[i] >= h[i-j] for j in range(1,4)) and \
               all(h[i] >= h[i+j] for j in range(1,4)):
                levels.append(h[i])
            if all(lo[i] <= lo[i-j] for j in range(1,4)) and \
               all(lo[i] <= lo[i+j] for j in range(1,4)):
                levels.append(lo[i])

        # Round numbers (psychological levels)
        pip = price * 0.001
        rounded = round(price / pip) * pip
        for mult in [-3, -2, -1, 0, 1, 2, 3]:
            levels.append(rounded + mult * pip)

        if not levels:
            return {
                "supports":    [round(price * 0.997, 5),
                                round(price * 0.993, 5)],
                "resistances": [round(price * 1.003, 5),
                                round(price * 1.006, 5)],
                "nearest_support":    round(price * 0.997, 5),
                "nearest_resistance": round(price * 1.003, 5),
            }

        arr    = np.array(levels)
        below  = sorted(arr[arr < price], reverse=True)
        above  = sorted(arr[arr > price])

        return {
            "supports":    [round(x, 5) for x in below[:4]],
            "resistances": [round(x, 5) for x in above[:4]],
            "nearest_support":    round(below[0], 5) if below else round(price*0.997, 5),
            "nearest_resistance": round(above[0], 5) if above else round(price*1.003, 5),
        }

    # ── Market Structure ──────────────────

    def _market_structure(self, df: pd.DataFrame) -> str:
        c   = df["close"].values
        h   = df["high"].values
        lo  = df["low"].values
        n   = min(30, len(df))
        
        recent_h  = h[-n:]
        recent_lo = lo[-n:]
        
        ph = [recent_h[i] for i in range(1, n-1)
              if recent_h[i] > recent_h[i-1] and recent_h[i] > recent_h[i+1]]
        pl = [recent_lo[i] for i in range(1, n-1)
              if recent_lo[i] < recent_lo[i-1] and recent_lo[i] < recent_lo[i+1]]

        if len(ph) >= 2 and len(pl) >= 2:
            if ph[-1] > ph[-2] and pl[-1] > pl[-2]:
                return "BULLISH"
            elif ph[-1] < ph[-2] and pl[-1] < pl[-2]:
                return "BEARISH"
        return "NEUTRAL"

    # ── Entry Finder ──────────────────────

    def _find_entry(
        self, df: pd.DataFrame, side: str, atr: float, sr: dict
    ) -> dict:
        """
        يحدد نوع ومكان الدخول المثلى.
        
        MARKET : الدخول الفوري (الشمعة الحالية تؤكد)
        LIMIT  : أمر معلق عند مستوى أفضل
        WAIT   : لا يوجد إعداد جيد الآن
        """
        c     = df["close"].values
        o     = df["open"].values
        h     = df["high"].values
        lo    = df["low"].values
        price = c[-1]

        # ── تحقق من الشمعة الأخيرة ─────────
        last_body  = abs(c[-1] - o[-1])
        last_range = h[-1] - lo[-1]
        body_ratio = last_body / last_range if last_range > 0 else 0

        if side == "BUY":
            # شمعة صاعدة قوية = MARKET
            bullish_close = c[-1] > o[-1] and body_ratio > 0.6
            # الارتداد من support = LIMIT
            near_support = abs(price - sr["nearest_support"]) < atr * 1.5
            # Pin bar صاعد
            pin_bar = (
                lo[-1] < lo[-2] and
                c[-1] > (h[-1] + lo[-1]) / 2 and
                (c[-1] - lo[-1]) > (h[-1] - c[-1]) * 2
            )

            if bullish_close and near_support:
                return {
                    "type":  "MARKET",
                    "price": price,
                    "reason": (
                        f"Bullish close ({body_ratio:.0%} body) "
                        f"near support {sr['nearest_support']}"
                    ),
                }
            elif pin_bar:
                return {
                    "type":  "MARKET",
                    "price": price,
                    "reason": "Bullish Pin Bar at support",
                }
            elif near_support:
                limit_price = sr["nearest_support"] + atr * 0.3
                return {
                    "type":  "LIMIT",
                    "price": round(limit_price, 5),
                    "reason": (
                        f"Limit order at support "
                        f"{sr['nearest_support']} + buffer"
                    ),
                }
            else:
                return {
                    "type":   "WAIT",
                    "price":  price,
                    "reason": (
                        f"No clear BUY setup | "
                        f"Nearest support: {sr['nearest_support']} "
                        f"({abs(price-sr['nearest_support'])/atr:.1f} ATR away)"
                    ),
                }

        else:  # SELL
            bearish_close = c[-1] < o[-1] and body_ratio > 0.6
            near_resistance = (
                abs(price - sr["nearest_resistance"]) < atr * 1.5
            )
            pin_bar = (
                h[-1] > h[-2] and
                c[-1] < (h[-1] + lo[-1]) / 2 and
                (h[-1] - c[-1]) > (c[-1] - lo[-1]) * 2
            )

            if bearish_close and near_resistance:
                return {
                    "type":  "MARKET",
                    "price": price,
                    "reason": (
                        f"Bearish close ({body_ratio:.0%} body) "
                        f"near resistance {sr['nearest_resistance']}"
                    ),
                }
            elif pin_bar:
                return {
                    "type":  "MARKET",
                    "price": price,
                    "reason": "Bearish Pin Bar at resistance",
                }
            elif near_resistance:
                limit_price = sr["nearest_resistance"] - atr * 0.3
                return {
                    "type":  "LIMIT",
                    "price": round(limit_price, 5),
                    "reason": (
                        f"Limit order at resistance "
                        f"{sr['nearest_resistance']} - buffer"
                    ),
                }
            else:
                return {
                    "type":   "WAIT",
                    "price":  price,
                    "reason": (
                        f"No clear SELL setup | "
                        f"Nearest resistance: {sr['nearest_resistance']}"
                    ),
                }

    # ── Stop Loss ─────────────────────────

    def _calculate_sl(
        self,
        df: pd.DataFrame,
        side: str,
        entry: float,
        atr: float,
        sr: dict,
    ) -> float:
        """
        SL يُحدَّد بناءً على:
        1. ما وراء أقرب S/R بهامش ATR
        2. ما وراء آخر Swing High/Low
        3. الحد الأقصى: ATR × 2
        """
        lo = df["low"].values
        h  = df["high"].values

        if side == "BUY":
            # آخر Swing Low
            recent_lows = lo[-20:]
            swing_low   = float(recent_lows.min())

            # أقرب support
            support = sr.get("nearest_support", entry * 0.998)

            # SL = أدنى المستويين - هامش
            sl_candidate = min(swing_low, support) - atr * 0.5

            # لا يبعد أكثر من 3× ATR
            max_sl = entry - atr * 3.0
            return max(sl_candidate, max_sl)

        else:  # SELL
            recent_highs = h[-20:]
            swing_high   = float(recent_highs.max())
            resistance   = sr.get("nearest_resistance", entry * 1.002)

            sl_candidate = max(swing_high, resistance) + atr * 0.5
            max_sl       = entry + atr * 3.0
            return min(sl_candidate, max_sl)

    # ── Take Profits ──────────────────────

    def _calculate_tps(
        self,
        side: str,
        entry: float,
        sl: float,
        sr: dict,
        atr: float,
    ) -> dict:
        """
        TP1: أقرب S/R (1:1.5 R minimum)
        TP2: S/R التالي (1:2.5 R)
        TP3: امتداد ATR (1:4 R)
        """
        risk = abs(entry - sl)

        if side == "BUY":
            resistances = sr.get("resistances", [])

            # TP1 = أول resistance فوق السعر بعد 1.5R على الأقل
            tp1 = entry + risk * 1.5
            for r in resistances:
                if r > entry + risk * 1.2:
                    tp1 = r - atr * 0.2  # قبل الـ resistance بقليل
                    break

            tp2 = entry + risk * 2.5
            for r in resistances:
                if r > tp1 + risk * 0.5:
                    tp2 = r - atr * 0.2
                    break

            tp3 = entry + risk * 4.0

        else:  # SELL
            supports = sr.get("supports", [])

            tp1 = entry - risk * 1.5
            for s in supports:
                if s < entry - risk * 1.2:
                    tp1 = s + atr * 0.2
                    break

            tp2 = entry - risk * 2.5
            for s in supports:
                if s < tp1 - risk * 0.5:
                    tp2 = s + atr * 0.2
                    break

            tp3 = entry - risk * 4.0

        return {
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
        }

    # ── R:R ───────────────────────────────

    def _calc_rr(self, entry: float, sl: float, tp: float) -> float:
        risk   = abs(entry - sl)
        reward = abs(tp - entry)
        return round(reward / risk, 2) if risk > 0 else 0

    # ── Confidence ────────────────────────

    def _confidence(
        self, df: pd.DataFrame, side: str,
        rr: float, structure: str
    ) -> float:
        score = 50.0

        # Structure
        if side == "BUY"  and structure == "BULLISH": score += 20
        if side == "SELL" and structure == "BEARISH": score += 20
        if structure == "NEUTRAL": score += 5

        # R:R
        if rr >= 3.0: score += 20
        elif rr >= 2.0: score += 12
        elif rr >= 1.5: score += 6

        # RSI
        try:
            rsi = float(
                ta.momentum.RSIIndicator(df["close"], 14)
                  .rsi().iloc[-1]
            )
            if side == "BUY"  and 30 <= rsi <= 60: score += 10
            if side == "SELL" and 40 <= rsi <= 70: score += 10
        except Exception:
            pass

        return min(score, 100.0)

    # ── No Entry ──────────────────────────

    def _no_entry(self, reason: str) -> dict:
        return {
            "entry_type":    "WAIT",
            "entry_price":   0.0,
            "stop_loss":     0.0,
            "take_profit_1": 0.0,
            "take_profit_2": 0.0,
            "take_profit_3": 0.0,
            "rr_ratio":      0.0,
            "confidence":    0.0,
            "reason":        reason,
            "invalidation":  0.0,
            "atr":           0.0,
            "structure":     "UNKNOWN",
            "sr_levels":     {},
        }


# ── Singleton ─────────────────────────────
entry_engine = EntryEngine()
