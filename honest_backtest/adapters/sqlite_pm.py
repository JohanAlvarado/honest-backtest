"""SQLite adapter for the paper-clob / Polymarket up/down corpus schema.

OPTIONAL — the core library takes in-memory `SlotCtx` and never touches a DB.
This adapter loads `SlotCtx` objects from a SQLite file with the published
schema (tables `slots`, `book_snapshots`, `pm_trades`). The open dataset ships
in this schema, so this is the zero-friction path to reproduce the leaderboard.

Ground-truth resolution comes ONLY from `slots.resolved_side` (a gamma-oracle
backfill), NEVER derived from spot.

    from honest_backtest.adapters.sqlite_pm import load_corpus
    ctxs = load_corpus("open_dataset.sqlite", coins=("btc",), durations=("5m",))
"""
from __future__ import annotations

import sqlite3

from ..signal import DUR_SECS, SlotCtx, SlotMeta


def connect(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=60)
    con.execute("PRAGMA busy_timeout=60000")
    return con


def load_slots(con, coins, durations, since_ms=None, until_ms=None,
               resolved_only=True, limit=None):
    where = ["coin IN (%s)" % ",".join("?" * len(coins)),
             "duration IN (%s)" % ",".join("?" * len(durations)),
             "strike IS NOT NULL"]
    params = list(coins) + list(durations)
    if resolved_only:
        where.append("resolved_side IN ('Yes','No')")
    if since_ms is not None:
        where.append("close_ts >= ?"); params.append(since_ms // 1000)
    if until_ms is not None:
        where.append("close_ts <= ?"); params.append(until_ms // 1000)
    sql = ("SELECT condition_id, coin, duration, open_ts, close_ts, strike, "
           "spot_at_open, spot_at_close, yes_token_id, no_token_id, "
           "resolved_side, fee_rate, rebate_rate FROM slots WHERE "
           + " AND ".join(where) + " ORDER BY close_ts")
    if limit:
        sql += f" LIMIT {int(limit)}"
    return con.execute(sql, params).fetchall()


def load_topbook(con, cid, open_ts, close_ts):
    return con.execute(
        "SELECT ts_ms, secs_to_close, yes_bid, yes_ask, yes_bid_size, "
        "yes_ask_size, no_bid, no_ask, no_bid_size, no_ask_size, spot "
        "FROM book_snapshots WHERE condition_id=? "
        "AND ts_ms BETWEEN ?*1000 AND ?*1000 ORDER BY ts_ms",
        (cid, open_ts, close_ts)).fetchall()


def load_trades(con, yes_tok, no_tok, open_ts, close_ts):
    return con.execute(
        "SELECT ts_ms, token_id, price, size, taker_buy FROM pm_trades "
        "WHERE token_id IN (?,?) AND ts_ms BETWEEN ?*1000 AND ?*1000 "
        "ORDER BY ts_ms",
        (yes_tok, no_tok, open_ts, close_ts)).fetchall()


def load_corpus(db_path, coins=("btc", "eth", "sol", "xrp"),
                durations=("5m", "15m"), since_ms=None, until_ms=None,
                limit=None):
    """Yield SlotCtx for each resolved slot matching the filters."""
    con = connect(db_path)
    try:
        slots = load_slots(con, coins, durations, since_ms, until_ms, limit=limit)
        for (cid, coin, dur, open_ts, close_ts, strike, sao, sac,
             ytok, ntok, resolved, fee_rate, rebate_rate) in slots:
            meta = SlotMeta(
                condition_id=cid, coin=coin, duration=dur,
                duration_s=DUR_SECS.get(dur, 0), open_ts=open_ts,
                close_ts=close_ts, strike=strike or 0.0,
                spot_at_open=sao or 0.0, spot_at_close=sac or 0.0,
                yes_token_id=ytok, no_token_id=ntok, resolved_side=resolved,
                fee_rate=fee_rate, rebate_rate=rebate_rate)
            topbook = load_topbook(con, cid, open_ts, close_ts)
            trades = load_trades(con, ytok, ntok, open_ts, close_ts)
            yield SlotCtx.from_rows(meta, topbook, trades)
    finally:
        con.close()
