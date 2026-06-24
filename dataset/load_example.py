#!/usr/bin/env python3
"""Closes the reproducibility loop: load the open dataset and grade the
calibration signal — straight from the published SQLite, no private DB.

    python3 dataset/load_example.py open_dataset.sqlite
"""
from __future__ import annotations

import json
import sys

from honest_backtest import evaluate
from honest_backtest.adapters.sqlite_pm import load_corpus
from honest_backtest.examples.no_overpriced import NoOverpriced


def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv:
        print("usage: python3 dataset/load_example.py <open_dataset.sqlite>")
        return 2
    ctxs = list(load_corpus(argv[0], coins=NoOverpriced.coins,
                            durations=NoOverpriced.durations))
    print(f"loaded {len(ctxs)} resolved slots from the open dataset")
    row = evaluate(NoOverpriced(), ctxs)
    print(json.dumps({k: row[k] for k in
                      ("n_decisions", "paper", "honest_fillable",
                       "headline_edge_real", "headline_lens", "ghost_gap")},
                     indent=2))
    print("\nThe headline edge_real should sit at ~0 / negative — the whole "
          "point: on an efficient venue the transactable price already prices "
          "the signal, so there is no realizable edge to harvest.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
