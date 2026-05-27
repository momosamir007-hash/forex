"""
Entry Engine - نسخة مُصحَّحة
يحسب R:R حقيقي بناءً على ATR والـ Structure
"""

from __future__ import annotations
import pandas as pd
import numpy as np
import ta
from app.logger import main_logger


class EntryEngine:

    def analyze(
        self,
        df:     pd.DataFrame,
        side:   str,
        symbol: str,
    ) -> dict:
        if df is None or len(df) < 50:
            return self._no_entry("Insufficient data")

        price = float(df["close"].iloc[-1])
        atr   = self._get_atr(df)

        if atr == 0:
            return self._no_entry("ATR is zero")

        sr        = self._find_sr_levels(df)
        structure = self._market_structure(df)
        entry     = self._find_entry(df, side, atr, sr)

        if entry["type"] == "WAIT":
            return self._no_entry(entry["reason"])

        sl  = self._calculate_sl(df, side, entry["price"], atr, sr)
        tps = self._calculate_tps(side, entry["price"], sl, sr, atr)

        # ── التحقق من R:R الحقيقي ──────────
        risk   = abs(entry["price"] - sl)
        reward = abs(tps["tp1"] - entry["price"])

        if risk == 0:
            return self._no_entry("Risk distance is zero")

        rr = round(reward / risk, 2)

        # ── رفض إذا R:R أقل من 1.3 ──────────
        if rr < 1.3:
            return self._no_entry(
                f"R:R {rr} too low (min 1.3) | "
                f"Risk: {risk:.5f} | Reward: {reward:.5f}"
            )

        conf = self._confidence(df, side, rr, structure, sr, atr)

        main_logger.debug(
            f"Entry: {symbol} {side} @ {entry['price']:.5f} | "
            f"SL: {sl:.5f} | TP1: {tps['tp1']:.5f} | "
            f"R:R: {rr} | Conf: {conf:.0f}%"
        )

        return {
            "entry_type":    entry["type"],
            "entry_price":   round(entry["price"], 5),
            "stop_loss":     round(sl, 5),
            "take_profit_1": round(tps["tp1"], 5),
            "take_profit_2": round(tps["tp2"], 5),
            "take_profit_3": round(tps["tp3"], 5),
            "rr_ratio":      rr,
            "confidence":    round(conf, 1),
            "reason":        entry["reason"],
            "invalidation":  round(sl, 5),
            "atr":           round(atr, 6),
            "structure":     structure,
            "sr_levels":     sr,
            "risk_distance": round(risk, 6),
            "reward_distance": round(reward, 6),
        }

    # ── ATR ──────────────────────────────

    def _get_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        try:
            val = ta.volatility.AverageTrueRange(
                df["high"], df["low"], df["close"], period
            ).average_true_range().iloc[-1]
            return float(val) if not np.isnan(val) else 0.0
        except Exception:
            return float((df["high"] - df["low"]).tail(14).mean())

    # ── Support / Resistance ──────────────

    def _find_sr_levels(self, df: pd.DataFrame) -> dict:
        h  = df["high"].values
        lo = df["low"].values
        c  = df["close"].values
        price = float(c[-1])
        n = len(df)

        levels: list[float] = []

        # Pivot highs & lows (lookback 3)
        for i in range(3, n - 3):
            if (h[i] > h[i-1] and h[i] > h[i-2] and
                    h[i] > h[i+1] and h[i] > h[i+2]):
                levels.append(float(h[i]))
            if (lo[i] < lo[i-1] and lo[i] < lo[i-2] and
                    lo[i] < lo[i+1] and lo[i] < lo[i+2]):
                levels.append(float(lo[i]))

        # Recent swing points (last 50 candles)
        recent_h  = h[-50:]
        recent_lo = lo[-50:]
        levels.append(float(recent_h.max()))
        levels.append(float(recent_lo.min()))

        # Session high/low (last 20)
        levels.append(float(h[-20:].max()))
        levels.append(float(lo[-20:].min()))

        if not levels:
            atr_est = float((df["high"] - df["low"]).tail(14).mean())
            return {
                "supports":           [round(price - atr_est * 1.5, 5),
                                       round(price - atr_est * 3.0, 5)],
                "resistances":        [round(price + atr_est * 1.5, 5),
                                       round(price + atr_est * 3.0, 5)],
                "nearest_support":    round(price - atr_est * 1.5, 5),
                "nearest_resistance": round(price + atr_est * 1.5, 5),
            }

        arr   = np.array(list(set(levels)))
        below = np.sort(arr[arr < price])[::-1]  # نزولي
        above = np.sort(arr[arr > price])         # تصاعدي

        return {
            "supports":    [round(x, 5) for x in below[:5]],
            "resistances": [round(x, 5) for x in above[:5]],
            "nearest_support":    round(float(below[0]), 5) if len(below) else round(price * 0.997, 5),
            "nearest_resistance": round(float(above[0]), 5) if len(above) else round(price * 1.003, 5),
        }

    # ── Market Structure ──────────────────

    def _market_structure(self, df: pd.DataFrame) -> str:
        h  = df["high"].values
        lo = df["low"].values
        n  = min(40, len(df))

        rh  = h[-n:]
        rlo = lo[-n:]

        ph = [rh[i] for i in range(1, n-1)
              if rh[i] > rh[i-1] and rh[i] > rh[i+1]]
        pl = [rlo[i] for i in range(1, n-1)
              if rlo[i] < rlo[i-1] and rlo[i] < rlo[i+1]]

        if len(ph) >= 2 and len(pl) >= 2:
            hh = ph[-1] > ph[-2]
            hl = pl[-1] > pl[-2]
            lh = ph[-1] < ph[-2]
            ll = pl[-1] < pl[-2]

            if hh and hl:  return "BULLISH"
            if lh and ll:  return "BEARISH"

        # EMA fallback
        c    = df["close"]
        e20  = float(c.ewm(span=20).mean().iloc[-1])
        e50  = float(c.ewm(span=50).mean().iloc[-1])
        cur  = float(c.iloc[-1])

        if cur > e20 > e50:  return "BULLISH"
        if cur < e20 < e50:  return "BEARISH"
        return "NEUTRAL"

    # ── Entry Finder ──────────────────────

    def _find_entry(
        self,
        df:   pd.DataFrame,
        side: str,
        atr:  float,
        sr:   dict,
    ) -> dict:
        c  = df["close"].values
        o  = df["open"].values
        h  = df["high"].values
        lo = df["low"].values
        price = float(c[-1])

        # حجم الجسم والظل
        body       = abs(c[-1] - o[-1])
        candle_rng = h[-1] - lo[-1]
        body_ratio = body / candle_rng if candle_rng > 0 else 0

        ns  = sr["nearest_support"]
        nr  = sr["nearest_resistance"]
        dist_to_support    = abs(price - ns)
        dist_to_resistance = abs(price - nr)

        if side == "BUY":
            near_support  = dist_to_support  < atr * 2.0
            bullish_close = c[-1] > o[-1] and body_ratio > 0.55
            pin_bar       = (
                lo[-1] < lo[-2] and
                (c[-1] - lo[-1]) > (h[-1] - c[-1]) * 2.0 and
                body_ratio < 0.4
            )
            engulfing = (
                c[-1] > o[-1] and
                c[-2] < o[-2] and
                c[-1] > o[-2] and
                o[-1] < c[-2]
            )

            if engulfing and near_support:
                return {
                    "type": "MARKET",
                    "price": price,
                    "reason": (
                        f"Bullish Engulfing near support "
                        f"{ns:.5f} (distance: {dist_to_support:.5f})"
                    ),
                }
            if bullish_close and near_support:
                return {
                    "type": "MARKET",
                    "price": price,
                    "reason": (
                        f"Bullish close ({body_ratio:.0%} body) "
                        f"near support {ns:.5f}"
                    ),
                }
            if pin_bar and near_support:
                return {
                    "type": "MARKET",
                    "price": price,
                    "reason": f"Bullish Pin Bar at support {ns:.5f}",
                }
            if near_support and dist_to_support < atr * 1.0:
                limit_p = round(ns + atr * 0.2, 5)
                return {
                    "type": "LIMIT",
                    "price": limit_p,
                    "reason": (
                        f"Limit BUY at support zone "
                        f"{ns:.5f} + buffer"
                    ),
                }
            return {
                "type": "WAIT",
                "price": price,
                "reason": (
                    f"No BUY setup | "
                    f"Support {dist_to_support/atr:.1f}× ATR away"
                ),
            }

        else:  # SELL
            near_resistance = dist_to_resistance < atr * 2.0
            bearish_close   = c[-1] < o[-1] and body_ratio > 0.55
            pin_bar         = (
                h[-1] > h[-2] and
                (h[-1] - c[-1]) > (c[-1] - lo[-1]) * 2.0 and
                body_ratio < 0.4
            )
            engulfing = (
                c[-1] < o[-1] and
                c[-2] > o[-2] and
                c[-1] < o[-2] and
                o[-1] > c[-2]
            )

            if engulfing and near_resistance:
                return {
                    "type": "MARKET",
                    "price": price,
                    "reason": (
                        f"Bearish Engulfing near resistance "
                        f"{nr:.5f}"
                    ),
                }
            if bearish_close and near_resistance:
                return {
                    "type": "MARKET",
                    "price": price,
                    "reason": (
                        f"Bearish close ({body_ratio:.0%} body) "
                        f"near resistance {nr:.5f}"
                    ),
                }
            if pin_bar and near_resistance:
                return {
                    "type": "MARKET",
                    "price": price,
                    "reason": f"Bearish Pin Bar at resistance {nr:.5f}",
                }
            if near_resistance and dist_to_resistance < atr * 1.0:
                limit_p = round(nr - atr * 0.2, 5)
                return {
                    "type": "LIMIT",
                    "price": limit_p,
                    "reason": (
                        f"Limit SELL at resistance zone "
                        f"{nr:.5f} - buffer"
                    ),
                }
            return {
                "type": "WAIT",
                "price": price,
                "reason": (
                    f"No SELL setup | "
                    f"Resistance {dist_to_resistance/atr:.1f}× ATR away"
                ),
            }

    # ── Stop Loss ─────────────────────────

    def _calculate_sl(
        self,
        df:    pd.DataFrame,
        side:  str,
        entry: float,
        atr:   float,
        sr:    dict,
    ) -> float:
        lo = df["low"].values
        h  = df["high"].values

        if side == "BUY":
            # أدنى نقطة في آخر 10 شموع
            recent_low = float(lo[-10:].min())
            support    = float(sr.get("nearest_support", entry - atr * 2))

            # SL = أدنى المستويين - هامش ATR
            sl = min(recent_low, support) - atr * 0.3

            # ضمان الحد الأدنى والأقصى
            sl = max(sl, entry - atr * 3.5)   # لا يبعد أكثر من 3.5 ATR
            sl = min(sl, entry - atr * 0.8)   # لا يكون قريب جداً

        else:
            recent_high = float(h[-10:].max())
            resistance  = float(sr.get("nearest_resistance", entry + atr * 2))

            sl = max(recent_high, resistance) + atr * 0.3
            sl = min(sl, entry + atr * 3.5)
            sl = max(sl, entry + atr * 0.8)

        return round(sl, 5)

    # ── Take Profits ──────────────────────

    def _calculate_tps(
        self,
        side:  str,
        entry: float,
        sl:    float,
        sr:    dict,
        atr:   float,
    ) -> dict:
        risk = abs(entry - sl)

        # TP الأساسية بناءً على R:R مضمون
        if side == "BUY":
            base_tp1 = entry + risk * 1.5
            base_tp2 = entry + risk * 2.5
            base_tp3 = entry + risk * 4.0

            # تحسين TP1 بناءً على أقرب Resistance
            resistances = sr.get("resistances", [])
            tp1 = base_tp1
            for r in resistances:
                if base_tp1 * 0.9 < r < base_tp1 * 1.3:
                    tp1 = r - atr * 0.15   # قبل الـ resistance بقليل
                    break

            tp2 = base_tp2
            for r in resistances:
                if tp1 < r < base_tp3:
                    tp2 = r - atr * 0.15
                    break

            tp3 = base_tp3

        else:  # SELL
            base_tp1 = entry - risk * 1.5
            base_tp2 = entry - risk * 2.5
            base_tp3 = entry - risk * 4.0

            supports = sr.get("supports", [])
            tp1 = base_tp1
            for s in supports:
                if base_tp1 * 0.97 < s < base_tp1 * 1.1:
                    tp1 = s + atr * 0.15
                    break

            tp2 = base_tp2
            for s in supports:
                if base_tp3 < s < tp1:
                    tp2 = s + atr * 0.15
                    break

            tp3 = base_tp3

        return {
            "tp1": round(tp1, 5),
            "tp2": round(tp2, 5),
            "tp3": round(tp3, 5),
        }

    # ── Confidence ────────────────────────

    def _confidence(
        self,
        df:        pd.DataFrame,
        side:      str,
        rr:        float,
        structure: str,
        sr:        dict,
        atr:       float,
    ) -> float:
        score = 40.0   # base أقل من السابق

        # ── Structure (أهم عامل) ──────────
        if side == "BUY":
            if structure == "BULLISH": score += 25
            elif structure == "NEUTRAL": score += 10
            else: score -= 10   # BEARISH structure = خطر
        else:
            if structure == "BEARISH": score += 25
            elif structure == "NEUTRAL": score += 10
            else: score -= 10

        # ── R:R ──────────────────────────
        if rr >= 3.0:   score += 20
        elif rr >= 2.0: score += 13
        elif rr >= 1.5: score += 7
        else:           score += 2

        # ── RSI ──────────────────────────
        try:
            rsi = float(
                ta.momentum.RSIIndicator(df["close"], 14)
                  .rsi().iloc[-1]
            )
            if side == "BUY":
                if 25 <= rsi <= 45:  score += 10   # oversold = ممتاز
                elif 45 <= rsi <= 60: score += 6
                elif rsi > 70:        score -= 8
            else:
                if 55 <= rsi <= 75:  score += 10
                elif 40 <= rsi <= 55: score += 6
                elif rsi < 30:        score -= 8
        except Exception:
            pass

        # ── Volume (إذا متوفر) ────────────
        try:
            v     = df["volume"]
            v_avg = float(v.rolling(20).mean().iloc[-1])
            v_cur = float(v.iloc[-1])
            if v_avg > 0:
                v_ratio = v_cur / v_avg
                if v_ratio >= 2.0:   score += 8
                elif v_ratio >= 1.5: score += 4
        except Exception:
            pass

        # ── Distance to S/R ──────────────
        price = float(df["close"].iloc[-1])
        if side == "BUY":
            ns = sr.get("nearest_support", price)
            dist = abs(price - ns) / atr if atr else 0
            if dist <= 0.5:  score += 8    # قريب جداً من support
            elif dist <= 1.0: score += 4
        else:
            nr = sr.get("nearest_resistance", price)
            dist = abs(price - nr) / atr if atr else 0
            if dist <= 0.5:  score += 8
            elif dist <= 1.0: score += 4

        return max(0.0, min(100.0, score))

    # ── No Entry ──────────────────────────

    def _no_entry(self, reason: str) -> dict:
        return {
            "entry_type":      "WAIT",
            "entry_price":     0.0,
            "stop_loss":       0.0,
            "take_profit_1":   0.0,
            "take_profit_2":   0.0,
            "take_profit_3":   0.0,
            "rr_ratio":        0.0,
            "confidence":      0.0,
            "reason":          reason,
            "invalidation":    0.0,
            "atr":             0.0,
            "structure":       "UNKNOWN",
            "sr_levels":       {},
            "risk_distance":   0.0,
            "reward_distance": 0.0,
        }


# ── Singleton ─────────────────────────────
entry_engine = EntryEngine()
