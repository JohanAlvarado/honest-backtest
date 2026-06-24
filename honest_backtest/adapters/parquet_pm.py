"""Parquet adapter for the open Polymarket up/down dataset.

Loads `SlotCtx` from the three parquet tables published on the Hugging Face
dataset (`slots.parquet`, `book_snapshots.parquet`, `pm_trades.parquet`) — so you
can reproduce the results from the ~190 MB parquet release without the 2 GB
SQLite bundle. Same schema, same `SlotCtx` output as the sqlite adapter.

Needs the optional `[parquet]` extra (pandas + pyarrow):

    pip install "honest-backtest[parquet]"

    # fetch the parquet dir from the Hub, then:
    #   huggingface-cli download kinzikdza/polymarket-updown-microstructure \
    #       --repo-type dataset --local-dir pm_data
    from honest_backtest.adapters.parquet_pm import load_corpus
    ctxs = load_corpus("pm_data/parquet", coins=("btc",), durations=("5m",))

Ground-truth resolution comes ONLY from `slots.resolved_side`, never from spot.
"""
from __future__ import annotations

import os

from ..signal import DUR_SECS, SlotCtx, SlotMeta

# book_snapshots columns in the exact order SlotCtx.from_rows expects.
_TOPBOOK_COLS = ["ts_ms", "secs_to_close", "yes_bid", "yes_ask", "yes_bid_size",
                 "yes_ask_size", "no_bid", "no_ask", "no_bid_size",
                 "no_ask_size", "spot"]
_TRADE_COLS = ["ts_ms", "token_id", "price", "size", "taker_buy"]


def _path(parquet_dir: str, table: str) -> str:
    p = os.path.join(parquet_dir, f"{table}.parquet")
    if not os.path.exists(p):
        raise FileNotFoundError(f"{p} not found — point at the dataset's parquet/ dir")
    return p


def load_corpus(parquet_dir, coins=("btc", "eth", "sol", "xrp"),
                durations=("5m", "15m"), resolved_only=True, limit=None):
    """Yield a SlotCtx per matching resolved slot, read from the parquet tables
    in `parquet_dir`. Memory-conscious: filters book/trades to the selected
    slots before grouping."""
    try:
        import pandas as pd
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "the parquet adapter needs pandas + pyarrow — "
            'install with: pip install "honest-backtest[parquet]"') from e

    slots = pd.read_parquet(_path(parquet_dir, "slots"))
    slots = slots[slots["coin"].isin(coins) & slots["duration"].isin(durations)
                  & slots["strike"].notna()]
    if resolved_only:
        slots = slots[slots["resolved_side"].isin(["Yes", "No"])]
    slots = slots.sort_values("close_ts")
    if limit:
        slots = slots.head(int(limit))
    if slots.empty:
        return

    cids = set(slots["condition_id"])
    toks = set(slots["yes_token_id"]) | set(slots["no_token_id"])

    snaps = pd.read_parquet(_path(parquet_dir, "book_snapshots"))
    snaps = snaps[snaps["condition_id"].isin(cids)]
    snap_groups = {cid: g.sort_values("ts_ms") for cid, g in snaps.groupby("condition_id")}

    trades = pd.read_parquet(_path(parquet_dir, "pm_trades"))
    trades = trades[trades["token_id"].isin(toks)].sort_values("ts_ms")
    trade_groups = {tok: g for tok, g in trades.groupby("token_id")}

    for s in slots.itertuples(index=False):
        meta = SlotMeta(
            condition_id=s.condition_id, coin=s.coin, duration=s.duration,
            duration_s=DUR_SECS.get(s.duration, 0), open_ts=int(s.open_ts),
            close_ts=int(s.close_ts), strike=float(s.strike or 0.0),
            spot_at_open=float(s.spot_at_open or 0.0),
            spot_at_close=float(s.spot_at_close or 0.0),
            yes_token_id=s.yes_token_id, no_token_id=s.no_token_id,
            resolved_side=s.resolved_side,
            fee_rate=(None if s.fee_rate is None else float(s.fee_rate)),
            rebate_rate=(None if s.rebate_rate is None else float(s.rebate_rate)))

        g = snap_groups.get(s.condition_id)
        topbook = (list(g[_TOPBOOK_COLS].itertuples(index=False, name=None))
                   if g is not None else [])
        trows = []
        for tok in (s.yes_token_id, s.no_token_id):
            tg = trade_groups.get(tok)
            if tg is not None:
                trows.extend(tg[_TRADE_COLS].itertuples(index=False, name=None))
        trows.sort(key=lambda r: r[0])
        yield SlotCtx.from_rows(meta, topbook, trows)
