"""Calibration gate against real data.

`no_overpriced` ran 325 live fills at WR 0.382 vs avg ask 0.386 → edge_real
−0.004. The honest harness MUST reproduce a near-zero / negative edge over the
open dataset. If it shows a strongly positive edge, the fill model is too
optimistic and fills.py is wrong.

Skipped unless a dataset is provided via the HB_SAMPLE_DB env var (or a file at
tests/data/sample.sqlite), so the synthetic test suite stays self-contained.
The published open dataset (in the sqlite_pm adapter schema) is the input here.
"""
from __future__ import annotations

import os

import pytest

from honest_backtest import evaluate
from honest_backtest.examples.no_overpriced import NoOverpriced

_SAMPLE = os.environ.get("HB_SAMPLE_DB") or os.path.join(
    os.path.dirname(__file__), "data", "sample.sqlite")


@pytest.mark.skipif(not os.path.exists(_SAMPLE),
                    reason="no sample dataset (set HB_SAMPLE_DB to run)")
def test_no_overpriced_calibrates_near_zero():
    from honest_backtest.adapters.sqlite_pm import load_corpus
    ctxs = list(load_corpus(_SAMPLE, coins=NoOverpriced.coins,
                            durations=NoOverpriced.durations))
    assert ctxs, "sample dataset has no matching slots"
    row = evaluate(NoOverpriced(), ctxs)
    edge = row["headline_edge_real"]
    assert edge is not None, "no fills graded — sample too small or no tape"
    # The whole thesis: realizable edge is ~0/negative on an efficient venue.
    assert edge <= 0.03, (
        f"no_overpriced headline edge_real={edge} > 0.03 — fill model is "
        f"too optimistic (the live anchor was -0.004)")
