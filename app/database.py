"""
Database Layer - SQLAlchemy + SQLite
يشمل جميع العمليات على قاعدة البيانات.
"""

import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, Float,
    String, DateTime, Boolean, Text, JSON,
    func,
)
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import DATABASE_URL

# ── إنشاء مجلد data تلقائياً ─────────────
os.makedirs("data", exist_ok=True)

engine       = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine
)
Base = declarative_base()


# ══════════════════════════════════════════
# Models
# ══════════════════════════════════════════

class Trade(Base):
    __tablename__ = "trades"

    id               = Column(Integer, primary_key=True, index=True)
    symbol           = Column(String(20), nullable=False, index=True)
    side             = Column(String(10), nullable=False)
    entry_price      = Column(Float)
    stop_loss        = Column(Float)
    take_profit      = Column(Float)
    take_profit_2    = Column(Float)
    take_profit_3    = Column(Float)
    timeframe        = Column(String(10))

    # Scores
    final_score      = Column(Float, default=0)
    trend_score      = Column(Float, default=0)
    volume_score     = Column(Float, default=0)
    momentum_score   = Column(Float, default=0)
    pa_score         = Column(Float, default=0)
    smc_score        = Column(Float, default=0)
    mtf_score        = Column(Float, default=0)
    grade            = Column(String(5))

    # AI
    ai_analysis      = Column(Text)
    market_condition = Column(String(30))
    confidence       = Column(String(20))

    # Status
    status           = Column(String(20), default="ACTIVE")
    result           = Column(String(20))       # WIN / LOSS / None
    pnl_percent      = Column(Float)
    approved         = Column(Boolean, default=True)
    rejection_reason = Column(String(500))

    # Meta
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow,
                         onupdate=datetime.utcnow)
    raw_data    = Column(JSON)


class RejectedSignal(Base):
    __tablename__ = "rejected_signals"

    id         = Column(Integer, primary_key=True, index=True)
    symbol     = Column(String(20), index=True)
    side       = Column(String(10))
    price      = Column(Float)
    timeframe  = Column(String(10))
    reason     = Column(String(1000))
    score      = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


# ══════════════════════════════════════════
# Init
# ══════════════════════════════════════════

def init_db() -> None:
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)


# ══════════════════════════════════════════
# Write Operations
# ══════════════════════════════════════════

def save_trade(
    trade_data:   dict,
    score_result: dict,
    risk:         dict,
    ai_result:    dict,
) -> int:
    """Save an approved trade. Returns the new trade ID."""
    db = SessionLocal()
    try:
        bd = score_result.get("breakdown", {})

        trade = Trade(
            symbol           = trade_data.get("symbol"),
            side             = trade_data.get("side"),
            entry_price      = risk.get("entry"),
            stop_loss        = risk.get("stop_loss"),
            take_profit      = risk.get("take_profit"),
            take_profit_2    = risk.get("take_profit_2"),
            take_profit_3    = risk.get("take_profit_3"),
            timeframe        = trade_data.get("timeframe"),
            final_score      = score_result.get("final_score", 0),
            trend_score      = bd.get("trend",        0),
            volume_score     = bd.get("volume",       0),
            momentum_score   = bd.get("momentum",     0),
            pa_score         = bd.get("price_action", 0),
            smc_score        = bd.get("smart_money",  0),
            mtf_score        = bd.get("mtf",          0),
            grade            = score_result.get("grade"),
            ai_analysis      = ai_result.get("analysis_summary"),
            market_condition = ai_result.get("market_condition"),
            confidence       = ai_result.get("confidence"),
            approved         = True,
            status           = "ACTIVE",
            raw_data         = trade_data,
        )
        db.add(trade)
        db.commit()
        db.refresh(trade)
        return trade.id
    finally:
        db.close()


def save_rejected(data: dict, reason: str, score: float) -> None:
    """Save a rejected signal."""
    db = SessionLocal()
    try:
        r = RejectedSignal(
            symbol    = data.get("symbol"),
            side      = data.get("side"),
            price     = float(data.get("price", 0)),
            timeframe = data.get("timeframe"),
            reason    = reason,
            score     = score,
        )
        db.add(r)
        db.commit()
    finally:
        db.close()


def update_trade_result(
    trade_id: int,
    result:   str,
    pnl:      float,
) -> bool:
    """Update trade result (WIN/LOSS) and P&L. Returns True on success."""
    db = SessionLocal()
    try:
        trade = db.query(Trade).filter(Trade.id == trade_id).first()
        if not trade:
            return False
        trade.result      = result
        trade.pnl_percent = pnl
        trade.status      = "CLOSED"
        trade.updated_at  = datetime.utcnow()
        db.commit()
        return True
    finally:
        db.close()


# ══════════════════════════════════════════
# Read Operations
# ══════════════════════════════════════════

def get_all_trades() -> list[dict]:
    db = SessionLocal()
    try:
        rows = (
            db.query(Trade)
              .order_by(Trade.created_at.desc())
              .all()
        )
        return [_trade_to_dict(r) for r in rows]
    finally:
        db.close()


def get_all_rejected() -> list[dict]:
    db = SessionLocal()
    try:
        rows = (
            db.query(RejectedSignal)
              .order_by(RejectedSignal.created_at.desc())
              .all()
        )
        return [
            {
                "id":         r.id,
                "symbol":     r.symbol,
                "side":       r.side,
                "price":      r.price,
                "timeframe":  r.timeframe,
                "reason":     r.reason,
                "score":      r.score,
                "created_at": r.created_at,
            }
            for r in rows
        ]
    finally:
        db.close()


def get_stats() -> dict:
    """Return overall performance statistics."""
    db = SessionLocal()
    try:
        total    = db.query(Trade).filter(Trade.approved == True).count()
        winners  = db.query(Trade).filter(Trade.result == "WIN").count()
        losers   = db.query(Trade).filter(Trade.result == "LOSS").count()
        rejected = db.query(RejectedSignal).count()

        avg_score = db.query(func.avg(Trade.final_score)).scalar() or 0.0
        total_pnl = db.query(func.sum(Trade.pnl_percent)).scalar() or 0.0
        win_rate  = (winners / total * 100) if total > 0 else 0.0

        return {
            "total_trades":     total,
            "winning_trades":   winners,
            "losing_trades":    losers,
            "pending_trades":   total - winners - losers,
            "rejected_signals": rejected,
            "win_rate":         round(win_rate, 2),
            "total_pnl":        round(float(total_pnl), 2),
            "avg_score":        round(float(avg_score), 2),
        }
    finally:
        db.close()


# ── Helper ────────────────────────────────

def _trade_to_dict(t: Trade) -> dict:
    return {
        "id":              t.id,
        "symbol":          t.symbol,
        "side":            t.side,
        "entry_price":     t.entry_price,
        "stop_loss":       t.stop_loss,
        "take_profit":     t.take_profit,
        "take_profit_2":   t.take_profit_2,
        "take_profit_3":   t.take_profit_3,
        "timeframe":       t.timeframe,
        "final_score":     t.final_score,
        "trend_score":     t.trend_score,
        "volume_score":    t.volume_score,
        "momentum_score":  t.momentum_score,
        "pa_score":        t.pa_score,
        "smc_score":       t.smc_score,
        "mtf_score":       t.mtf_score,
        "grade":           t.grade,
        "ai_analysis":     t.ai_analysis,
        "market_condition":t.market_condition,
        "confidence":      t.confidence,
        "status":          t.status,
        "result":          t.result,
        "pnl_percent":     t.pnl_percent,
        "created_at":      t.created_at,
    }
