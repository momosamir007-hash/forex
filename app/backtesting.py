"""
Backtesting Engine
──────────────────
يختبر أي استراتيجية على بيانات تاريخية حقيقية من TwelveData.

الاستخدام:
    engine = BacktestEngine(symbol, timeframe, candles)
    result = engine.run(strategy_params)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Literal

from app.logger import main_logger


# ══════════════════════════════════════════════════
# Data Classes
# ══════════════════════════════════════════════════

@dataclass
class TradeResult:
    index:      int
    side:       Literal["BUY", "SELL"]
    entry:      float
    sl:         float
    tp:         float
    tp2:        float
    tp3:        float
    result:     Literal["WIN", "LOSS", "OPEN"]
    r_multiple: float
    bars_held:  int
    entry_time: pd.Timestamp | None = None
    exit_time:  pd.Timestamp  | None = None

    def to_dict(self) -> dict:
        return {
            "index":      self.index,
            "side":       self.side,
            "entry":      round(self.entry,  5),
            "sl":         round(self.sl,     5),
            "tp":         round(self.tp,     5),
            "tp2":        round(self.tp2,    5),
            "tp3":        round(self.tp3,    5),
            "result":     self.result,
            "r_multiple": round(self.r_multiple, 3),
            "bars_held":  self.bars_held,
            "entry_time": str(self.entry_time),
            "exit_time":  str(self.exit_time),
        }


@dataclass
class BacktestStats:
    total_trades:  int   = 0
    winning:       int   = 0
    losing:        int   = 0
    win_rate:      float = 0.0
    total_r:       float = 0.0
    avg_win_r:     float = 0.0
    avg_loss_r:    float = 0.0
    profit_factor: float = 0.0
    max_drawdown:  float = 0.0
    sharpe:        float = 0.0
    expectancy:    float = 0.0
    avg_bars_held: float = 0.0
    best_trade:    float = 0.0
    worst_trade:   float = 0.0
    consecutive_losses: int = 0


# ══════════════════════════════════════════════════
# Backtest Engine
# ══════════════════════════════════════════════════

class BacktestEngine:
    """
    Core backtesting engine.

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV DataFrame (index = datetime).
    rr_target : float
        Target Risk:Reward ratio for TP1.
    atr_sl_mult : float
        ATR multiplier for Stop Loss distance.
    max_bars : int
        Maximum bars to hold a trade before closing at market.
    """

    def __init__(
        self,
        df:          pd.DataFrame,
        rr_target:   float = 2.0,
        atr_sl_mult: float = 1.5,
        max_bars:    int   = 20,
    ):
        self.df          = df.copy()
        self.rr_target   = rr_target
        self.atr_sl_mult = atr_sl_mult
        self.max_bars    = max_bars

        self._prepare()

    # ── Prepare indicators ───────────────

    def _prepare(self):
        df = self.df

        # EMAs
        df["ema20"]  = df["close"].ewm(span=20,  adjust=False).mean()
        df["ema50"]  = df["close"].ewm(span=50,  adjust=False).mean()
        df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()

        # RSI
        df["rsi"] = self._rsi(df["close"], 14)

        # ATR
        df["atr"] = self._atr(df, 14)

        # MACD
        ema12       = df["close"].ewm(span=12, adjust=False).mean()
        ema26       = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"]  = ema12 - ema26
        df["macd_s"]= df["macd"].ewm(span=9, adjust=False).mean()

        # Volume ratio
        if df["volume"].sum() > 0:
            df["vol_ratio"] = df["volume"] / df["volume"].rolling(20).mean()
        else:
            df["vol_ratio"] = 1.0

        self.df = df.dropna().reset_index(drop=False)

    # ── Generate Signals ─────────────────

    def generate_signals(self, params: dict) -> pd.Series:
        """
        Generate BUY(1) / SELL(-1) / HOLD(0) signals.

        params keys
        -----------
        ema_fast   int   – fast EMA period
        ema_slow   int   – slow EMA period
        rsi_ob     int   – RSI overbought threshold
        rsi_os     int   – RSI oversold threshold
        require_macd bool – require MACD confirmation
        require_vol  bool – require volume surge
        """
        df = self.df

        ema_fast     = params.get("ema_fast",    20)
        ema_slow     = params.get("ema_slow",    50)
        rsi_ob       = params.get("rsi_ob",      70)
        rsi_os       = params.get("rsi_os",      30)
        require_macd = params.get("require_macd", True)
        require_vol  = params.get("require_vol",  False)

        # Recalculate EMAs with custom periods
        fast = df["close"].ewm(span=ema_fast, adjust=False).mean()
        slow = df["close"].ewm(span=ema_slow, adjust=False).mean()

        signals = pd.Series(0, index=df.index)

        for i in range(1, len(df)):
            # ── BUY conditions ──────────────
            cross_up    = fast.iloc[i] > slow.iloc[i] and fast.iloc[i-1] <= slow.iloc[i-1]
            above_200   = df["close"].iloc[i] > df["ema200"].iloc[i]
            rsi_buy     = df["rsi"].iloc[i] < rsi_ob
            macd_buy    = df["macd"].iloc[i] > df["macd_s"].iloc[i] if require_macd else True
            vol_buy     = df["vol_ratio"].iloc[i] >= 1.2 if require_vol else True

            if cross_up and above_200 and rsi_buy and macd_buy and vol_buy:
                signals.iloc[i] = 1
                continue

            # ── SELL conditions ─────────────
            cross_dn    = fast.iloc[i] < slow.iloc[i] and fast.iloc[i-1] >= slow.iloc[i-1]
            below_200   = df["close"].iloc[i] < df["ema200"].iloc[i]
            rsi_sell    = df["rsi"].iloc[i] > rsi_os
            macd_sell   = df["macd"].iloc[i] < df["macd_s"].iloc[i] if require_macd else True
            vol_sell    = df["vol_ratio"].iloc[i] >= 1.2 if require_vol else True

            if cross_dn and below_200 and rsi_sell and macd_sell and vol_sell:
                signals.iloc[i] = -1

        return signals

    # ── Run Backtest ─────────────────────

    def run(self, params: dict) -> tuple[list[TradeResult], BacktestStats]:
        """
        Execute backtest.

        Returns
        -------
        (trades, stats)
        """
        signals = self.generate_signals(params)
        df      = self.df
        trades: list[TradeResult] = []

        in_trade = False

        for i in range(len(df) - self.max_bars - 1):
            if in_trade:
                continue

            sig = signals.iloc[i]
            if sig == 0:
                continue

            side  = "BUY" if sig == 1 else "SELL"
            entry = float(df["close"].iloc[i])
            atr   = float(df["atr"].iloc[i])

            if atr == 0:
                continue

            sl_dist = atr * self.atr_sl_mult

            if side == "BUY":
                sl  = entry - sl_dist
                tp  = entry + sl_dist * self.rr_target
                tp2 = entry + sl_dist * self.rr_target * 1.6
                tp3 = entry + sl_dist * self.rr_target * 2.5
            else:
                sl  = entry + sl_dist
                tp  = entry - sl_dist * self.rr_target
                tp2 = entry - sl_dist * self.rr_target * 1.6
                tp3 = entry - sl_dist * self.rr_target * 2.5

            # ── Simulate forward ────────────
            result    = "OPEN"
            bars_held = 0
            exit_i    = i

            for j in range(i + 1, min(i + self.max_bars + 1, len(df))):
                h_j = float(df["high"].iloc[j])
                l_j = float(df["low"].iloc[j])
                bars_held += 1
                exit_i = j

                if side == "BUY":
                    if l_j <= sl:
                        result = "LOSS"; break
                    if h_j >= tp:
                        result = "WIN";  break
                else:
                    if h_j >= sl:
                        result = "LOSS"; break
                    if l_j <= tp:
                        result = "WIN";  break

            # Skip open trades
            if result == "OPEN":
                continue

            r_mult  = self.rr_target if result == "WIN" else -1.0
            e_time  = df.index[i]   if isinstance(df.index[i], pd.Timestamp) \
                      else df["datetime"].iloc[i] if "datetime" in df.columns else None
            ex_time = df.index[exit_i] if isinstance(df.index[exit_i], pd.Timestamp) \
                      else df["datetime"].iloc[exit_i] if "datetime" in df.columns else None

            trades.append(TradeResult(
                index=i, side=side,
                entry=entry, sl=sl, tp=tp, tp2=tp2, tp3=tp3,
                result=result, r_multiple=r_mult,
                bars_held=bars_held,
                entry_time=e_time, exit_time=ex_time,
            ))

        stats = self._calculate_stats(trades)
        main_logger.info(
            f"Backtest done | Trades: {stats.total_trades} | "
            f"WR: {stats.win_rate:.1f}% | R: {stats.total_r:.2f}"
        )
        return trades, stats

    # ── Statistics ───────────────────────

    def _calculate_stats(self, trades: list[TradeResult]) -> BacktestStats:
        if not trades:
            return BacktestStats()

        s = BacktestStats()
        r_series = np.array([t.r_multiple for t in trades])

        s.total_trades = len(trades)
        s.winning      = sum(1 for t in trades if t.result == "WIN")
        s.losing       = sum(1 for t in trades if t.result == "LOSS")
        s.win_rate     = s.winning / s.total_trades * 100
        s.total_r      = float(r_series.sum())

        wins   = r_series[r_series > 0]
        losses = r_series[r_series < 0]

        s.avg_win_r  = float(wins.mean())   if len(wins)   else 0.0
        s.avg_loss_r = float(losses.mean()) if len(losses) else 0.0

        gross_profit = float(wins.sum())   if len(wins)   else 0.0
        gross_loss   = float(abs(losses.sum())) if len(losses) else 1.0
        s.profit_factor = gross_profit / gross_loss if gross_loss else 0.0

        s.max_drawdown = float(self._max_drawdown(r_series))

        s.expectancy   = (
            (s.win_rate / 100 * s.avg_win_r) +
            ((1 - s.win_rate / 100) * s.avg_loss_r)
        )

        s.avg_bars_held = float(
            np.mean([t.bars_held for t in trades])
        )

        s.best_trade  = float(r_series.max())
        s.worst_trade = float(r_series.min())

        # Sharpe (simple)
        if r_series.std() > 0:
            s.sharpe = float(r_series.mean() / r_series.std() * np.sqrt(252))

        # Max consecutive losses
        max_cl = cl = 0
        for r in r_series:
            if r < 0:
                cl += 1
                max_cl = max(max_cl, cl)
            else:
                cl = 0
        s.consecutive_losses = max_cl

        return s

    @staticmethod
    def _max_drawdown(r: np.ndarray) -> float:
        cum  = np.cumsum(r)
        peak = np.maximum.accumulate(cum)
        dd   = peak - cum
        return float(dd.max())

    # ── Indicator helpers ────────────────

    @staticmethod
    def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain  = delta.clip(lower=0).rolling(period).mean()
        loss  = (-delta.clip(upper=0)).rolling(period).mean()
        rs    = gain / loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        h, l, c = df["high"], df["low"], df["close"]
        tr = pd.concat([
            h - l,
            (h - c.shift()).abs(),
            (l - c.shift()).abs(),
        ], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    # ── Export ───────────────────────────

    def trades_to_df(self, trades: list[TradeResult]) -> pd.DataFrame:
        return pd.DataFrame([t.to_dict() for t in trades])
