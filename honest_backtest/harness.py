"""Walk a corpus of SlotCtx through a Signal and grade every decision.

This is the glue: `run_signal` produces the raw grade dicts (one per fired
decision), `evaluate` aggregates them into a single leaderboard row. Bring your
own SlotCtx stream (from the sqlite adapter, parquet, an API, or hand-built).
"""
from __future__ import annotations

from .fills import grade_maker, grade_taker
from .metrics import leaderboard_row


def run_signal(signal, ctxs, latency_ms: int = 1000, tape_window_ms: int = 1500):
    """Run `signal` over an iterable of SlotCtx; return the list of grade dicts.

    Honors `signal.once` (stop after the first decision per slot) and routes to
    the taker or maker fill model by `signal.mode`. No-lookahead is structural:
    decide(ctx, i) only ever sees indices <= i.
    """
    recs = []
    for ctx in ctxs:
        for i in range(ctx.n):
            d = signal.decide(ctx, i)
            if d is None:
                continue
            if d.action == "maker" or signal.mode == "maker":
                recs.append(grade_maker(ctx, d))
            else:
                recs.append(grade_taker(ctx, d, latency_ms=latency_ms,
                                        tape_window_ms=tape_window_ms))
            if signal.once:
                break
    return recs


def evaluate(signal, ctxs, latency_ms: int = 1000, tape_window_ms: int = 1500):
    """Run `signal` and return one leaderboard row (edge_real across the honest
    lenses, ghost_gap, $ROI, and by-coin/dur/week breakdowns)."""
    recs = run_signal(signal, ctxs, latency_ms=latency_ms,
                      tape_window_ms=tape_window_ms)
    return leaderboard_row(signal.name, signal.family, signal.mode, recs)
