"""
Auto Scanner
────────────
يفحص كل الأزواج على كل الإطارات تلقائياً
ويُعيد قائمة بأفضل فرص التداول الحالية.
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
# Scanner Config
# ══════════════════════════════════════════

SCAN_TIMEFRAMES = ["15m", "1h", "4h"]

MIN_CONFIDENCE  = 55.0   # حد أدنى للثقة
MIN_RR          = 1.5    # حد أدنى R:R
MIN_SCORE       = 6.5    # حد أدنى للنقاط (أقل من الـ Signal Analyzer)


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
        use_ai:      bool = False,      # AI اختياري لتسريع المسح
        max_workers: int  = 4,
    ) -> list[dict]:
        """
        يفحص كل الأزواج × الإطارات الزمنية.
        يُعيد قائمة مرتبة بأفضل الفرص.
        """
        tfs  = timeframes or SCAN_TIMEFRAMES
        syms = pairs      or list(SUPPORTED_PAIRS.keys())

        tasks = [
            (sym, tf)
            for sym in syms
            for tf  in tfs
        ]

        main_logger.info(
            f"🔍 Auto scan started | "
            f"{len(syms)} pairs × {len(tfs)} TFs = {len(tasks)} checks"
        )

        results: list[dict] = []

        # ── Multi-threaded scanning ────────
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {
                ex.submit(self._scan_one, sym, tf, use_ai): (sym, tf)
                for sym, tf in tasks
            }
            for future in as_completed(futures):
                sym, tf = futures[future]
                try:
                    result = future.result(timeout=30)
                    if result:
                        results.append(result)
                except Exception as e:
                    main_logger.warning(f"Scan error {sym} {tf}: {e}")

        # ── Sort by score ──────────────────
        results.sort(key=lambda x: x.get("final_score", 0), reverse=True)

        self.last_scan    = datetime.now(timezone.utc)
        self.last_results = results

        main_logger.info(
            f"✅ Scan complete | "
            f"Found {len(results)} opportunities"
        )

        return results

    # ── Scan One Pair/TF ──────────────────

    def _scan_one(
        self, symbol: str, timeframe: str, use_ai: bool
    ) -> dict | None:
        """
        يفحص زوجاً واحداً على إطار واحد.
        يُعيد None إذا لم توجد فرصة.
        """
        try:
            # ── 1. Fetch Data ──────────────
            df = data_fetcher.get_ohlcv(symbol, timeframe, limit=200)
            if df is None or len(df) < 60:
                return None

            indicators = data_fetcher.get_indicators(df)
            if not indicators:
                return None

            price = float(indicators.get("current_price", 0))
            if price == 0:
                return None

            # ── 2. Determine likely direction ──
            side = self._detect_direction(df, indicators)

            # ── 3. News Check ──────────────
            news = check_news_risk(symbol)
            if not news["safe"]:
                return None

            # ── 4. Entry Engine ────────────
            entry = entry_engine.analyze(df, side, symbol)

            if entry["entry_type"] == "WAIT":
                return None

            if entry["rr_ratio"] < MIN_RR:
                return None

            if entry["confidence"] < MIN_CONFIDENCE:
                return None

            # ── 5. Filters ─────────────────
            signal_data = {
                "symbol": symbol, "side": side,
                "price":  str(price),
                "timeframe": timeframe,
                **{k: str(v) for k, v in indicators.items()},
            }

            filters = run_all_filters(signal_data, indicators)

            # ── 6. Price Action ────────────
            pa = analyze_price_action(df, side)

            # ── 7. SMC ─────────────────────
            smc = analyze_smc(df, side)

            # ── 8. MTF ─────────────────────
            mtf = analyze_mtf(symbol, timeframe, side)

            # ── 9. Score ───────────────────
            score_result = calculate_score(
                ai_result     = {"final_score": 7.0,
                                 "approved": True},
                filter_result = filters,
                pa_result     = pa,
                smc_result    = smc,
                mtf_result    = mtf,
                news_result   = news,
            )

            if score_result["final_score"] < MIN_SCORE:
                return None

            # ── 10. AI (optional) ──────────
            ai_result = None
            if use_ai:
                ai_result = analyze_signal(signal_data, indicators)
                if not ai_result.get("approved"):
                    return None

                # Recalculate with AI score
                score_result = calculate_score(
                    ai_result     = ai_result,
                    filter_result = filters,
                    pa_result     = pa,
                    smc_result    = smc,
                    mtf_result    = mtf,
                    news_result   = news,
                )
                if score_result["final_score"] < MIN_SCORE:
                    return None

            # ── Build Result ───────────────
            pair_info = SUPPORTED_PAIRS.get(symbol, {})

            return {
                # Identity
                "symbol":     symbol,
                "timeframe":  timeframe,
                "side":       side,
                "pair_name":  pair_info.get("name", symbol),
                "emoji":      pair_info.get("emoji", "💱"),
                "category":   pair_info.get("category", "forex"),

                # Entry
                "entry_type":    entry["entry_type"],
                "entry_price":   entry["entry_price"],
                "stop_loss":     entry["stop_loss"],
                "take_profit_1": entry["take_profit_1"],
                "take_profit_2": entry["take_profit_2"],
                "take_profit_3": entry["take_profit_3"],
                "rr_ratio":      entry["rr_ratio"],
                "entry_reason":  entry["reason"],
                "structure":     entry["structure"],

                # Scores
                "final_score":   score_result["final_score"],
                "grade":         score_result["grade"],
                "breakdown":     score_result["breakdown"],
                "confidence":    entry["confidence"],

                # Analysis
                "patterns":      pa.get("patterns", []),
                "pa_score":      pa.get("score", 0),
                "smc_score":     smc.get("score", 0),
                "ob_found":      smc.get("ob", {}).get("found", False),
                "sweep":         smc.get("sweep", False),
                "bos":           smc.get("bos", False),
                "mtf_aligned":   mtf.get("alignment_pct", 0),
                "ai_used":       use_ai,
                "ai_score":      ai_result.get("final_score") if ai_result else None,

                # Meta
                "scanned_at":   datetime.now(timezone.utc).strftime(
                    "%Y-%m-%d %H:%M UTC"
                ),
                "atr":           entry.get("atr", 0),
                "sr_levels":     entry.get("sr_levels", {}),
            }

        except Exception as e:
            main_logger.warning(f"_scan_one error {symbol} {timeframe}: {e}")
            return None

    # ── Direction Detection ────────────────

    def _detect_direction(
        self, df: pd.DataFrame, ind: dict
    ) -> str:
        """
        يحدد الاتجاه المحتمل بناءً على مؤشرات متعددة.
        """
        bull_signals = 0
        bear_signals = 0

        price = float(ind.get("current_price", df["close"].iloc[-1]))

        # EMA alignment
        e20, e50, e200 = (
            float(ind.get("ema20",  0)),
            float(ind.get("ema50",  0)),
            float(ind.get("ema200", 0)),
        )
        if price > e200: bull_signals += 2
        else:            bear_signals += 2
        if e20 > e50:    bull_signals += 1
        else:            bear_signals += 1
        if price > e50:  bull_signals += 1
        else:            bear_signals += 1

        # RSI
        rsi = float(ind.get("rsi", 50))
        if rsi > 55:     bull_signals += 1
        elif rsi < 45:   bear_signals += 1

        # MACD
        hist = float(ind.get("macd_hist", 0))
        if hist > 0:     bull_signals += 1
        else:            bear_signals += 1

        # Stochastic
        k = float(ind.get("stoch_k", 50))
        if k < 25:       bull_signals += 2   # oversold = buy opportunity
        elif k > 75:     bear_signals += 2   # overbought = sell opportunity

        # Recent candle
        c = df["close"].values
        o = df["open"].values
        if c[-1] > o[-1]: bull_signals += 1
        else:             bear_signals += 1

        return "BUY" if bull_signals >= bear_signals else "SELL"


# ── Singleton ─────────────────────────────
auto_scanner = AutoScanner()
