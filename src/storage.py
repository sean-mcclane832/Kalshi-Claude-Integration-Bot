"""SQLite storage for estimates, notifications, and resolutions."""
import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.config import DB_PATH

logger = logging.getLogger(__name__)

DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    """Create tables if they don't exist."""
    with _conn() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS data_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            run_id TEXT NOT NULL,
            market_ticker TEXT NOT NULL,
            snapshot_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS estimates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            run_id TEXT NOT NULL,
            market_ticker TEXT NOT NULL,
            market_question TEXT,
            claude_prob REAL,
            confidence TEXT,
            reasoning TEXT,
            key_risks TEXT,
            kalshi_implied_yes REAL,
            kalshi_implied_no REAL,
            edge REAL,
            model TEXT,
            prompt_hash TEXT,
            data_quality TEXT DEFAULT 'ok'
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            run_id TEXT NOT NULL,
            market_ticker TEXT NOT NULL,
            side TEXT,
            edge REAL,
            claude_prob REAL,
            kalshi_implied REAL,
            ntfy_status INTEGER
        );

        CREATE TABLE IF NOT EXISTS resolutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_ticker TEXT NOT NULL,
            resolved_ts TEXT,
            resolved_yes INTEGER,  -- 1=YES, 0=NO, NULL=unknown
            resolution_price REAL,
            notes TEXT,
            UNIQUE(market_ticker)
        );
        """)
    logger.info("Database initialized at %s", DB_PATH)


def log_snapshot(run_id: str, ticker: str, snapshot: dict) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        con.execute(
            "INSERT INTO data_snapshots (ts, run_id, market_ticker, snapshot_json) VALUES (?,?,?,?)",
            (ts, run_id, ticker, json.dumps(snapshot)),
        )


def log_estimate(
    run_id: str,
    ticker: str,
    question: str,
    claude_prob: float,
    confidence: str,
    reasoning: str,
    key_risks: list,
    kalshi_implied_yes: Optional[float],
    kalshi_implied_no: Optional[float],
    edge: Optional[float],
    model: str,
    prompt: str,
    data_quality: str = "ok",
) -> int:
    ts = datetime.now(timezone.utc).isoformat()
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    with _conn() as con:
        cur = con.execute(
            """INSERT INTO estimates
               (ts, run_id, market_ticker, market_question, claude_prob, confidence,
                reasoning, key_risks, kalshi_implied_yes, kalshi_implied_no, edge,
                model, prompt_hash, data_quality)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ts, run_id, ticker, question, claude_prob, confidence, reasoning,
             json.dumps(key_risks), kalshi_implied_yes, kalshi_implied_no, edge,
             model, prompt_hash, data_quality),
        )
        return cur.lastrowid


def log_notification(
    run_id: str,
    ticker: str,
    side: str,
    edge: float,
    claude_prob: float,
    kalshi_implied: float,
    ntfy_status: int,
) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        con.execute(
            """INSERT INTO notifications
               (ts, run_id, market_ticker, side, edge, claude_prob, kalshi_implied, ntfy_status)
               VALUES (?,?,?,?,?,?,?,?)""",
            (ts, run_id, ticker, side, edge, claude_prob, kalshi_implied, ntfy_status),
        )


def get_last_notification(ticker: str) -> Optional[sqlite3.Row]:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM notifications WHERE market_ticker=? ORDER BY ts DESC LIMIT 1",
            (ticker,),
        ).fetchone()
    return row


def upsert_resolution(ticker: str, resolved_yes: Optional[int], resolution_price: Optional[float], notes: str = "") -> None:
    ts = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        con.execute(
            """INSERT INTO resolutions (market_ticker, resolved_ts, resolved_yes, resolution_price, notes)
               VALUES (?,?,?,?,?)
               ON CONFLICT(market_ticker) DO UPDATE SET
                 resolved_ts=excluded.resolved_ts,
                 resolved_yes=excluded.resolved_yes,
                 resolution_price=excluded.resolution_price,
                 notes=excluded.notes""",
            (ticker, ts, resolved_yes, resolution_price, notes),
        )
