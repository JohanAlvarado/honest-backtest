"""no_overpriced — the CALIBRATION ANCHOR for the honest harness.

Thesis: PM books systematically overprice YES on moderate favourites; buy the
cheap NO ask in the slot's first ~60s when yes_mid is high and no_ask is cheap.

This is the canonical calibration anchor. Live ran 325 fills, WR 0.382 vs avg
ask 0.386 → edge_real = -0.004 (≈ breakeven-negative). The honest harness, run
over the tape window, MUST land near zero / negative here — the "+0.07 edge" a
naive paper backtest shows is the illusion the ghost_gap exposes. If
honest_fillable shows a real positive edge for THIS signal, the fill model is
still optimistic and fills.py needs fixing before any new claim.

    python -m honest_backtest.examples.no_overpriced path/to/open_dataset.sqlite
"""
from __future__ import annotations

import json
import sys

from honest_backtest import Decision, Signal, evaluate


class NoOverpriced(Signal):
    name = "no_overpriced"
    family = "paper-clob/calibrated-fair"
    mode = "taker"
    coins = ("btc", "eth")
    durations = ("5m", "15m")
    once = True

    MAX_NO_ASK = 0.45     # backtest cap (live used 0.40)
    MIN_YES_MID = 0.56
    MAX_AGE_S = 60        # T+0..60s entry window
    SIZE = 20.0

    def decide(self, ctx, i):
        if not ctx.book_ok(i):
            return None
        if ctx.elapsed_s(i) > self.MAX_AGE_S:
            return None
        ym = ctx.yes_mid(i)
        na = ctx.na[i]
        if ym >= self.MIN_YES_MID and 0.0 < na < self.MAX_NO_ASK:
            return Decision(i=i, ts_ms=int(ctx.ts[i]), token_yes=False,
                            action="taker", target_px=float(na), size=self.SIZE)
        return None


def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv:
        print("usage: python -m honest_backtest.examples.no_overpriced "
              "<open_dataset.sqlite | parquet_dir/>")
        return 2
    src = argv[0]
    # dispatch by source: a .sqlite file → sqlite adapter; a directory (the
    # dataset's parquet/ folder) → parquet adapter.
    if os.path.isdir(src) or src.endswith(".parquet"):
        from honest_backtest.adapters.parquet_pm import load_corpus
    else:
        from honest_backtest.adapters.sqlite_pm import load_corpus
    ctxs = list(load_corpus(src, coins=NoOverpriced.coins,
                            durations=NoOverpriced.durations))
    row = evaluate(NoOverpriced(), ctxs)
    print(json.dumps(row, indent=2))
    he = row.get("headline_edge_real")
    print(f"\nheadline edge_real = {he}  (calibration expects <= ~0.02; "
          f"a strongly positive value means the fill model is too optimistic)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
