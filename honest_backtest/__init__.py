"""honest-backtest — grade prediction-market strategies against the price you
could ACTUALLY transact at.

Most backtests paper-fill at the displayed ask and report a win rate. On an
efficient venue the transactable price already contains the signal, so WR ≈ ask
by construction and the "edge" is an illusion. This library corrects for that:

  edge_real = mean(won − fill_px)         # per-fill, the only honest headline
  realizable fills  (book-persistence + tape-corroboration, not the paper ask)
  real PM fees      (taker fee = fee_rate·p·(1−p); makers pay 0)
  adverse-selection diagnostic (physics fair-value vs the bait ask)

Quick start:

    from honest_backtest import Signal, Decision, evaluate

    class MySignal(Signal):
        name, family, mode = "my_sig", "demo", "taker"
        def decide(self, ctx, i):
            ...  # return Decision(...) or None, reading only indices <= i

    row = evaluate(MySignal(), ctxs)   # ctxs: iterable of SlotCtx
    print(row["headline_edge_real"], row["ghost_gap"])
"""
from __future__ import annotations

from .adverse import (
    adverse_score,
    classify_fill,
    fp_prob_yes,
    normal_cdf,
    physics_features,
)
from .fills import grade_maker, grade_taker
from .harness import evaluate, run_signal
from .metrics import bootstrap_ci, leaderboard_row
from .settle import fee_per_share, won_buy
from .signal import Decision, Signal, SlotCtx, SlotMeta

__version__ = "0.2.0"

__all__ = [
    "Signal", "SlotCtx", "SlotMeta", "Decision",
    "grade_taker", "grade_maker",
    "leaderboard_row", "bootstrap_ci",
    "evaluate", "run_signal",
    "won_buy", "fee_per_share",
    "physics_features", "adverse_score", "classify_fill",
    "fp_prob_yes", "normal_cdf",
    "__version__",
]
