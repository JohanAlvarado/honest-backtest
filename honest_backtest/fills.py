"""Honest fill models. The core of the discovery: instead of paper-filling at
the displayed ask, we model the two ways a prediction-market entry fails to
transact at the price you saw — and expose the gap the adverse-selection /
phantom-book loss lived in.

TAKER (marketable IOC buy):
  * book-persistence  — your order arrives ~latency_ms after the decision. If
    the ask has repriced ABOVE your limit by then (the classic "asks pull on
    the winners"), you miss; otherwise you fill at the arrival ask. Works on
    the FULL corpus (no tape needed). PRIMARY honest lens.
  * tape-corroboration — a REAL taker_buy print on your token at <= your limit
    landed within tape_window_ms. Proves the displayed ask was genuine, not a
    thin phantom ladder. STRICTEST lens (needs a real trade tape).

MAKER: queue-aware fill of a resting bid against real trades (FIFO,
optimistic — the paper-vs-tape gap is the honest signal).

A grade dict only carries flags; metrics.py turns them into per-mode PnL.
"""
from __future__ import annotations

import numpy as np

from .settle import won_buy

EPS = 1e-9


def grade_taker(ctx, d, latency_ms: int = 1000, tape_window_ms: int = 1500,
                max_gap_ms: int = 4000) -> dict:
    i, yes = d.i, d.token_yes
    ts, n = ctx.ts, ctx.n
    ask = ctx.ya[i] if yes else ctx.na[i]
    asz = ctx.yas[i] if yes else ctx.nas[i]
    won = won_buy(yes, ctx.meta.resolved_side)
    valid = (ask == ask) and (0.0 < ask < 1.0)
    crossable = bool(valid and ask <= d.target_px + EPS)
    limit = d.target_px + EPS

    # --- book-persistence: re-check the ask at arrival (decision ts + latency) ---
    persist_known = False
    persisted = True
    fill_px = float(ask) if valid else float("nan")
    if crossable:
        arr = d.ts_ms + latency_ms
        k = int(np.searchsorted(ts, arr, side="left"))
        if k < n and (ts[k] - arr) <= max_gap_ms:
            persist_known = True
            ask_k = ctx.ya[k] if yes else ctx.na[k]
            if (ask_k == ask_k) and 0.0 < ask_k < 1.0 and ask_k <= limit:
                fill_px = float(ask_k)        # pay what's resting at arrival
            else:
                persisted = False             # ask pulled above limit → miss
        # else: cadence too sparse to assess → neutral (fill at decision ask)

    # --- tape corroboration (phantom-book filter) ---
    fillable = False
    if crossable and ctx.tr_ts.size:
        lo, hi = d.ts_ms, d.ts_ms + tape_window_ms
        m = ((ctx.tr_yes == yes) & ctx.tr_buy
             & (ctx.tr_px <= limit) & (ctx.tr_ts >= lo) & (ctx.tr_ts <= hi))
        fillable = bool(m.any())

    honest_sz = d.size
    if valid and asz == asz and asz > 0:
        honest_sz = min(d.size, float(asz))

    return {
        "cid": ctx.meta.condition_id, "coin": ctx.meta.coin,
        "dur": ctx.meta.duration, "ts_ms": int(d.ts_ms),
        "s2c": int(ctx.s2c[i]), "yes": bool(yes),
        "won": bool(won), "best_ask": float(ask) if valid else float("nan"),
        "fill_px": fill_px, "target_px": float(d.target_px),
        "size": float(d.size), "honest_sz": float(honest_sz),
        "valid": bool(valid), "crossable": crossable,
        "persisted": bool(persisted), "persist_known": bool(persist_known),
        "fillable": fillable, "has_tape": ctx.has_tape,
        "fee_rate": float(ctx.meta.fee_rate or 0.0), "tag": d.tag, "mode": "taker",
    }


def grade_maker(ctx, d) -> dict:
    """Resting BID of d.size at d.target_px posted at snapshot i; consume real
    trades that hit it (taker SELL <= our bid), FIFO behind the resting size
    at our level; hold residual to settlement. FIFO priority is optimistic."""
    i, yes = d.i, d.token_yes
    bidpx = d.target_px
    qa = ctx.ybs[i] if yes else ctx.nbs[i]
    qa = float(qa) if (qa == qa and qa > 0) else 0.0
    size_rem = d.size
    filled = paid = 0.0
    won = won_buy(yes, ctx.meta.resolved_side)

    if ctx.tr_ts.size:
        mask = ((ctx.tr_yes == yes) & (~ctx.tr_buy)
                & (ctx.tr_px <= bidpx + EPS) & (ctx.tr_ts >= d.ts_ms))
        for k in np.nonzero(mask)[0]:
            tsz = float(ctx.tr_sz[k])
            eat = min(tsz, qa); qa -= eat; left = tsz - eat
            if left > EPS and size_rem > EPS:
                f = min(left, size_rem)
                size_rem -= f; filled += f; paid += f * bidpx
            if size_rem <= EPS:
                break

    return {
        "cid": ctx.meta.condition_id, "coin": ctx.meta.coin,
        "dur": ctx.meta.duration, "ts_ms": int(d.ts_ms), "yes": bool(yes),
        "won": bool(won), "bid_px": float(bidpx), "size": float(d.size),
        "filled": float(filled), "paid": float(paid),
        "fillable": bool(filled > EPS), "has_tape": ctx.has_tape,
        "fee_rate": float(ctx.meta.fee_rate or 0.0), "tag": d.tag, "mode": "maker",
    }
