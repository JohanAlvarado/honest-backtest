#!/usr/bin/env python3
"""Export the OPEN, anonymized Polymarket up/down microstructure dataset.

Reads the production capture DB (telemetry.db) READ-ONLY and writes a clean
SQLite file containing ONLY market-observation tables — `slots`,
`book_snapshots`, `pm_trades` — in the schema the `honest_backtest` SQLite
adapter reads. The output is reproducible-by-construction: nothing of ours
(orders, fills, positions, PnL, tx hashes, strategies) is copied.

Safeguards:
  * WHITELIST of tables + columns (nothing else can leak).
  * Window May 27 → Jun 24 2026 — excludes the May 11–23 era where ~39% of
    tight-market `resolved_side` was corrupted before the gamma-only fix.
  * resolved_side IN ('Yes','No') only.
  * `raw_json` engine debug blob dropped (typed columns + ladders kept).
  * Post-export assertions: exact table set, no excluded tables, no identifier
    columns, and a string-scan for anything resembling a wallet/tx hash.

    python3 dataset/export_open_dataset.py --src /var/lib/pm-real-engine/telemetry.db \
        --out open_dataset.sqlite

Optional parquet (if pyarrow is installed): --parquet-dir out/parquet
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sqlite3
import sys

COINS = ("btc", "eth", "sol", "xrp")
DURATIONS = ("5m", "15m")

# Clean window (UTC). May 27 onward = gamma-only resolved_side (no corruption).
WINDOW_START = dt.datetime(2026, 5, 27, tzinfo=dt.timezone.utc)
WINDOW_END = dt.datetime(2026, 6, 25, tzinfo=dt.timezone.utc)

EXPECTED_TABLES = {"slots", "book_snapshots", "pm_trades"}

SLOTS_COLS = ("condition_id, coin, duration, slug, yes_token_id, no_token_id, "
              "open_ts, close_ts, strike, spot_at_open, spot_at_close, "
              "resolved_side, fee_rate, rebate_rate")
SNAP_COLS = ("ts_ms, condition_id, secs_to_close, yes_bid, yes_ask, "
             "yes_bid_size, yes_ask_size, yes_ladder, no_bid, no_ask, "
             "no_bid_size, no_ask_size, no_ladder, spot, ds_spot")
TRADE_COLS = "ts_ms, token_id, price, size, taker_buy"

# Anything that smells like a wallet/tx hash (0x + 64 hex). condition_id/token_id
# are PM-public market ids, NOT addresses; a 40/64-hex 0x in a *value* would be.
HEXISH = re.compile(r"0x[0-9a-fA-F]{40,}")


def epoch_s(d: dt.datetime) -> int:
    return int(d.timestamp())


def epoch_ms(d: dt.datetime) -> int:
    return int(d.timestamp() * 1000)


def build(src: str, out: str) -> sqlite3.Connection:
    if os.path.exists(out):
        os.remove(out)
    con = sqlite3.connect(out)
    con.execute("PRAGMA journal_mode=OFF")
    con.execute("PRAGMA synchronous=OFF")
    con.execute(f"ATTACH DATABASE 'file:{src}?mode=ro' AS src")  # RO attach
    cstart, cend = epoch_s(WINDOW_START), epoch_s(WINDOW_END)
    mstart, mend = epoch_ms(WINDOW_START), epoch_ms(WINDOW_END)
    coins_in = ",".join("'%s'" % c for c in COINS)
    durs_in = ",".join("'%s'" % d for d in DURATIONS)

    # --- slots (the membership filter for the other two) ---
    con.execute(f"CREATE TABLE slots AS SELECT {SLOTS_COLS} FROM src.slots "
                f"WHERE coin IN ({coins_in}) AND duration IN ({durs_in}) "
                f"AND resolved_side IN ('Yes','No') AND strike IS NOT NULL "
                f"AND open_ts >= {cstart} AND open_ts < {cend}")
    con.execute("CREATE INDEX idx_slots_cond ON slots(condition_id)")
    con.execute("CREATE INDEX idx_slots_coin_open ON slots(coin, open_ts)")

    # --- book_snapshots for the kept slots, within window ---
    con.execute(f"CREATE TABLE book_snapshots AS SELECT {SNAP_COLS} "
                f"FROM src.book_snapshots WHERE condition_id IN "
                f"(SELECT condition_id FROM slots) "
                f"AND ts_ms >= {mstart} AND ts_ms < {mend}")
    con.execute("CREATE INDEX idx_snap_cond_ts ON book_snapshots(condition_id, ts_ms)")

    # --- pm_trades for the kept tokens, within window ---
    con.execute(f"CREATE TABLE pm_trades AS SELECT {TRADE_COLS} "
                f"FROM src.pm_trades WHERE ts_ms >= {mstart} AND ts_ms < {mend} "
                f"AND token_id IN (SELECT yes_token_id FROM slots "
                f"UNION SELECT no_token_id FROM slots)")
    con.execute("CREATE INDEX idx_trades_token_ts ON pm_trades(token_id, ts_ms)")

    con.commit()
    con.execute("DETACH DATABASE src")
    return con


def assert_clean(con: sqlite3.Connection) -> None:
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables == EXPECTED_TABLES, f"unexpected tables: {tables}"

    # no identifier-ish columns anywhere
    banned = ("order_id", "tx_hash", "transaction_hash", "taker_order_id",
              "wallet", "proxy", "api_key", "secret", "strategy", "pnl")
    for t in tables:
        cols = [r[1].lower() for r in con.execute(f"PRAGMA table_info({t})")]
        bad = [c for c in cols if any(b in c for b in banned)]
        assert not bad, f"banned column(s) in {t}: {bad}"

    # string-scan a sample of text columns for wallet/tx-hash shapes
    for slug, in con.execute("SELECT slug FROM slots WHERE slug IS NOT NULL LIMIT 5000"):
        assert not HEXISH.search(slug or ""), f"hex-ish value in slug: {slug}"
    # condition_id/token_id ARE PM-public market ids (66-hex / decimal) — expected,
    # not addresses. We only forbid them appearing where a wallet could hide.
    print("anonymization asserts: PASS")


def summarize(con: sqlite3.Connection) -> None:
    for t in EXPECTED_TABLES:
        n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:<16} {n:>12,} rows")
    yes, no = con.execute(
        "SELECT SUM(resolved_side='Yes'), SUM(resolved_side='No') FROM slots"
    ).fetchone()
    print(f"  resolution balance: Yes={yes} No={no}")
    d0, d1 = con.execute(
        "SELECT MIN(date(open_ts,'unixepoch')), MAX(date(open_ts,'unixepoch')) "
        "FROM slots").fetchone()
    print(f"  window: {d0} → {d1}")


def to_parquet(con: sqlite3.Connection, pdir: str) -> None:
    try:
        import pyarrow as pa  # noqa
        import pyarrow.parquet as pq
    except ImportError:
        print("pyarrow not installed — skipping parquet (sqlite output is primary)")
        return
    os.makedirs(pdir, exist_ok=True)
    for t in EXPECTED_TABLES:
        cur = con.execute(f"SELECT * FROM {t}")
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        table = pa.table({c: [r[i] for r in rows] for i, c in enumerate(cols)})
        pq.write_table(table, os.path.join(pdir, f"{t}.parquet"), compression="snappy")
        print(f"  wrote {t}.parquet ({len(rows):,} rows)")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="/var/lib/pm-real-engine/telemetry.db")
    ap.add_argument("--out", default="open_dataset.sqlite")
    ap.add_argument("--parquet-dir", default="")
    args = ap.parse_args(argv)

    if not os.path.exists(args.src):
        print(f"source DB not found: {args.src}", file=sys.stderr)
        return 2
    print(f"exporting {args.src} → {args.out} (window "
          f"{WINDOW_START.date()} → {WINDOW_END.date()})")
    con = build(args.src, args.out)
    assert_clean(con)
    summarize(con)
    con.execute("VACUUM")
    if args.parquet_dir:
        to_parquet(con, args.parquet_dir)
    con.close()
    mb = os.path.getsize(args.out) / 1e6
    print(f"done: {args.out} ({mb:.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
