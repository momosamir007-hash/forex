"""
Auto Scanner - نسخة مُصحَّحة
يرفض الإشارات المتناقضة ويُنوّع النتائج
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.config          import SUPPORTED_PAIRS, TIMEFRAME_WEIGHTS
from app.market_filters  import data_fetcher, run_all_filters
from app.price_action    import analyze_price_action
from app.smart_money     import analyze_smc
from app.multi_timeframe import analyze_mtf
from app.news_filter     import check_news_risk
from app.signal_scorer   import calculate_score
from app.entry_engine    import entry_engine
from app.ai_filter       import analyze_signal
from app.logger          import main_logger


# ══════════════════════════════════════════
# Constants
# ══════════════════════════════════════════

SCAN_TIMEFRAMES  = ["15m", "1h", "4h"]
MIN_CONFIDENCE   = 50.0
MIN_RR           = 1.5
MIN_SCORE        = 6.5
MIN_MTF_ALIGN    = 40.0    # ← جديد: رفض إذا MTF أقل من 40%
MAX_PER_SYMBOL   = 1       # ← جديد: أفضل فرصة واحدة فقط لكل زوج


# ══════════════════════════════════════════
# Scanner
# ══════════════════════════════════════════

class AutoScanner:

    def __init__(self):
        self.last_scan:    datetime | None = None
        self.last_results: list[dict]      = []

    # ── Full Scan ─────────────────────────

    def scan_all(
        self,
        timeframes:  list[str] | None = None,
        pairs:       list[str] | None = None,
        use_ai:      bool = False,
        max_workers: int  = 4,
    ) -> list[dict]:

        tfs  = timeframes or SCAN_TIMEFRAMES
        syms = pairs      or list(SUPPORTED_PAIRS.keys())

        tasks = [(sym, tf) for sym in syms for tf in tfs]

        main_logger.info(
            f"🔍 Scan started | {len(tasks)} checks"
        )

        raw_results: list[dict] = []

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {
                ex.submit(self._scan_one, sym, tf, use_ai): (sym, tf)
                for sym, tf in tasks
            }
            for future in as_completed(futures):
                sym, tf = futures[future]
                try:
                    r = future.result(timeout=30)
                    if r:
                        raw_results.append(r)
                except Exception as e:
                    main_logger.warning(f"Scan error {sym} {tf}: {e}")

        # ── فلترة ومعالجة النتائج ──────────
        results = self._post_process(raw_results)

        self.last_scan    = datetime.now(timezone.utc)
        self.last_results = results

        main_logger.info(
            f"✅ Scan done | Raw: {len(raw_results)} | "
            f"After filter: {len(results)}"
        )
        return results

    # ── Post Processing ───────────────────

    def _post_process(self, raw: list[dict]) -> list[dict]:
        """
        1. رفض إذا MTF منخفض
        2. رفض إذا Pattern يتعارض مع الاتجاه
        3. أفضل فرصة فقط لكل زوج
        4. ترتيب حسب النقاط
        """
        filtered: list[dict] = []

        for r in raw:
            # ── فلتر MTF ──────────────────
            if r.get("mtf_aligned", 0) < MIN_MTF_ALIGN:
                main_logger.debug(
                    f"Rejected {r['symbol']} {r['timeframe']}: "
                    f"MTF {r['mtf_aligned']:.0f}% < {MIN_MTF_ALIGN}%"
                )
                continue

            # ── فلتر تعارض الأنماط ────────
            if self._has_conflicting_patterns(r):
                main_logger.debug(
                    f"Rejected {r['symbol']} {r['timeframe']}: "
                    f"Conflicting patterns for {r['side']}"
                )
                continue

            # ── فلتر Structure ────────────
            if self._structure_conflicts(r):
                main_logger.debug(
                    f"Rejected {r['symbol']} {r['timeframe']}: "
                    f"Structure {r['structure']} conflicts with {r['side']}"
                )
                continue

            filtered.append(r)

        # ── أفضل فرصة لكل زوج ────────────
        best_per_symbol: dict[str, dict] = {}
        for r in filtered:
            sym = r["symbol"]
            if sym not in best_per_symbol or \
               r["final_score"] > best_per_symbol[sym]["final_score"]:
                best_per_symbol[sym] = r

        # ── ترتيب نهائي ───────────────────
        final = sorted(
            best_per_symbol.values(),
            key=lambda x: (x["final_score"], x["rr_ratio"]),
            reverse=True,
        )
        return final

    def _has_conflicting_patterns(self, r: dict) -> bool:
        """
        يرفض إذا كانت الأنماط تعارض الاتجاه
        """
        patterns = r.get("patterns", [])
        side     = r.get("side", "BUY")

        BEARISH_PATTERNS = {
            "Bearish Engulfing 🔴",
            "Evening Star 🌆",
            "Shooting Star ⭐",
            "Bearish Pin Bar 📌",
            "Three Black Crows 🐦‍⬛",
            "Hanging Man 🪓",
        }
        BULLISH_PATTERNS = {
            "Bullish Engulfing 🟢",
            "Morning Star 🌟",
            "Hammer 🔨",
            "Bullish Pin Bar 📍",
            "Three White Soldiers 💪",
        }

        if side == "BUY":
            # إذا كل الأنماط هبوطية = تعارض
            if patterns and all(p in BEARISH_PATTERNS for p in patterns):
                return True
        else:
            if patterns and all(p in BULLISH_PATTERNS for p in patterns):
                return True

        return False

    def _structure_conflicts(self, r: dict) -> bool:
        """
        يرفض إذا كان Structure معاكس تماماً للاتجاه
        (BEARISH structure + BUY = تعارض خطير)
        """
        structure = r.get("structure", "NEUTRAL")
        side      = r.get("side", "BUY")

        if side == "BUY"  and structure == "BEARISH":
            return True
        if side == "SELL" and structure == "BULLISH":
            return True

        return False

    # ── Scan One ─────────────────────────

    def _scan_one(
        self,
        symbol:    str,
        timeframe: str,
        use_ai:    bool,
    ) -> dict | None:

        try:
            # 1. Fetch Data
            df = data_fetcher.get_ohlcv(symbol, timeframe, limit=200)
            if df is None or len(df) < 60:
                return None

            indicators = data_fetcher.get_indicators(df)
            if not indicators:
                return None

            price = float(indicators.get("current_price", 0))
            if price == 0:
                return None

            # 2. Direction
            side = self._detect_direction(df, indicators)

            # 3. News
            news = check_news_risk(symbol)
            if not news["safe"]:
                return None

            # 4. Entry Engine
            entry = entry_engine.analyze(df, side, symbol)

            if entry["entry_type"] == "WAIT":
                return None
            if entry["rr_ratio"] < MIN_RR:
                return None
            if entry["confidence"] < MIN_CONFIDENCE:
                return None

            # 5. Filters
            signal_data = {
                "symbol":    symbol,
                "side":      side,
                "price":     str(price),
                "timeframe": timeframe,
                **{k: str(v) for k, v in indicators.items()},
            }
            filters = run_all_filters(signal_data, indicators)

            # 6. PA
            pa = analyze_price_action(df, side)

            # 7. SMC
            smc = analyze_smc(df, side)

            # 8. MTF
            mtf = analyze_mtf(symbol, timeframe, side)
            mtf_pct = float(mtf.get("alignment_pct", 0))

            # ← رفض مبكر إذا MTF منخفض
            if mtf_pct < MIN_MTF_ALIGN:
                return None

            # 9. Score
            score_result = calculate_score(
                ai_result     = {"final_score": 7.0, "approved": True},
                filter_result = filters,
                pa_result     = pa,
                smc_result    = smc,
                mtf_result    = mtf,
                news_result   = news,
            )

            if score_result["final_score"] < MIN_SCORE:
                return None

            # 10. AI (optional)
            ai_result = None
            if use_ai:
                ai_result = analyze_signal(signal_data, indicators)
                if not ai_result.get("approved"):
                    return None
                score_result = calculate_score(
                    ai_result, filters, pa, smc, mtf, news
                )
                if score_result["final_score"] < MIN_SCORE:
                    return None

            pair_info = SUPPORTED_PAIRS.get(symbol, {})

            return {
                "symbol":        symbol,
                "timeframe":     timeframe,
                "side":          side,
                "pair_name":     pair_info.get("name", symbol),
                "emoji":         pair_info.get("emoji", "💱"),
                "category":      pair_info.get("category", "forex"),
                "entry_type":    entry["entry_type"],
                "entry_price":   entry["entry_price"],
                "stop_loss":     entry["stop_loss"],
                "take_profit_1": entry["take_profit_1"],
                "take_profit_2": entry["take_profit_2"],
                "take_profit_3": entry["take_profit_3"],
                "rr_ratio":      entry["rr_ratio"],
                "entry_reason":  entry["reason"],
                "structure":     entry["structure"],
                "risk_distance": entry.get("risk_distance", 0),
                "final_score":   score_result["final_score"],
                "grade":         score_result["grade"],
                "breakdown":     score_result["breakdown"],
                "confidence":    entry["confidence"],
                "patterns":      pa.get("patterns", []),
                "pa_score":      pa.get("score", 0),
                "smc_score":     smc.get("score", 0),
                "ob_found":      smc.get("ob", {}).get("found", False),
                "sweep":         smc.get("sweep", False),
                "bos":           smc.get("bos", False),
                "mtf_aligned":   mtf_pct,
                "ai_used":       use_ai,
                "ai_score":      (ai_result.get("final_score")
                                  if ai_result else None),
                "scanned_at":    datetime.now(timezone.utc).strftime(
                    "%Y-%m-%d %H:%M UTC"
                ),
                "atr":           entry.get("atr", 0),
                "sr_levels":     entry.get("sr_levels", {}),
            }

        except Exception as e:
            main_logger.warning(
                f"_scan_one error {symbol} {timeframe}: {e}"
            )
            return None

    # ── Direction Detection ────────────────

    def _detect_direction(
        self,
        df:  pd.DataFrame,
        ind: dict,
    ) -> str:
        bull = 0
        bear = 0

        price = float(ind.get("current_price",
                              df["close"].iloc[-1]))
        e20   = float(ind.get("ema20",  0))
        e50   = float(ind.get("ema50",  0))
        e200  = float(ind.get("ema200", 0))

        # EMA (أعلى وزن)
        if price > e200: bull += 3
        else:            bear += 3
        if e20 > e50:    bull += 2
        else:            bear += 2
        if price > e50:  bull += 1
        else:            bear += 1

        # RSI
        rsi = float(ind.get("rsi", 50))
        if rsi < 35:     bull += 2   # oversold = فرصة شراء
        elif rsi > 65:   bear += 2   # overbought = فرصة بيع
        elif rsi > 50:   bull += 1
        else:            bear += 1

        # MACD
        hist = float(ind.get("macd_hist", 0))
        if hist > 0: bull += 1
        else:        bear += 1

        # Stochastic
        k = float(ind.get("stoch_k", 50))
        if k < 20:   bull += 2
        elif k > 80: bear += 2

        # آخر شمعة
        c = df["close"].values
        o = df["open"].values
        if c[-1] > o[-1]: bull += 1
        else:             bear += 1

        return "BUY" if bull >= bear else "SELL"


# ── إصلاح import ──────────────────────────
import pandas as pd   # كان ناقصاً في النسخة السابقة

# ── Singleton ─────────────────────────────
auto_scanner = AutoScanner()
