#!/usr/bin/env python3
"""Stream the open-dataset SQLite into per-table parquet for the HuggingFace
dataset viewer (which can't read .sqlite). Memory-safe: reads in row batches and
appends to a ParquetWriter — never loads a full table into RAM. Snappy-compressed;
token_id/condition_id dict-encode well so the files stay small.

    python3 dataset/sqlite_to_parquet.py --src /root/open_dataset.sqlite \
        --out /root/open_dataset_parquet

Output: <out>/{slots,book_snapshots,pm_trades}.parquet
"""
from __future__ import annotations

import argparse
import os
import sqlite3

import pyarrow as pa
import pyarrow.parquet as pq

BATCH = 100_000

# explicit schemas (avoids NULL-in-first-batch type inference bugs)
I64, F64, STR = pa.int64(), pa.float64(), pa.string()
SCHEMAS = {
    "slots": pa.schema([
        ("condition_id", STR), ("coin", STR), ("duration", STR), ("slug", STR),
        ("yes_token_id", STR), ("no_token_id", STR), ("open_ts", I64),
        ("close_ts", I64), ("strike", F64), ("spot_at_open", F64),
        ("spot_at_close", F64), ("resolved_side", STR), ("fee_rate", F64),
        ("rebate_rate", F64)]),
    "book_snapshots": pa.schema([
        ("ts_ms", I64), ("condition_id", STR), ("secs_to_close", I64),
        ("yes_bid", F64), ("yes_ask", F64), ("yes_bid_size", F64),
        ("yes_ask_size", F64), ("yes_ladder", STR), ("no_bid", F64),
        ("no_ask", F64), ("no_bid_size", F64), ("no_ask_size", F64),
        ("no_ladder", STR), ("spot", F64), ("ds_spot", F64)]),
    "pm_trades": pa.schema([
        ("ts_ms", I64), ("token_id", STR), ("price", F64), ("size", F64),
        ("taker_buy", I64)]),
}


def convert(src: str, out: str) -> None:
    os.makedirs(out, exist_ok=True)
    con = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=60)
    con.execute("PRAGMA busy_timeout=60000")
    for table, schema in SCHEMAS.items():
        cols = [f.name for f in schema]
        total = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        path = os.path.join(out, f"{table}.parquet")
        cur = con.execute(f"SELECT {', '.join(cols)} FROM {table}")
        writer = pq.ParquetWriter(path, schema, compression="snappy")
        done = 0
        while True:
            rows = cur.fetchmany(BATCH)
            if not rows:
                break
            data = {c: [r[i] for r in rows] for i, c in enumerate(cols)}
            writer.write_table(pa.table(data, schema=schema))
            done += len(rows)
            print(f"  {table}: {done:,}/{total:,}", flush=True)
        writer.close()
        mb = os.path.getsize(path) / 1e6
        print(f"wrote {path} ({mb:.0f} MB, {total:,} rows)")
    con.close()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="/root/open_dataset.sqlite")
    ap.add_argument("--out", default="/root/open_dataset_parquet")
    a = ap.parse_args(argv)
    convert(a.src, a.out)
    print("done")


if __name__ == "__main__":
    raise SystemExit(main())
