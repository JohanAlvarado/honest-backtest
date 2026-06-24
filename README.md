# honest-backtest

**Your prediction-market backtest is lying to you. This one tells the truth.**

Most backtests paper-fill at the displayed ask and report a win rate. On an
efficient venue the transactable price *already contains the signal* — so
`WR ≈ ask` by construction, and the "edge" you see is an artifact of filling at
prices you could never actually get. Deploy on that and you lose money the
backtest swore you'd make.

`honest-backtest` grades every decision against the price you **could actually
transact at**:

- **`edge_real = mean(won − fill_px)`** — the only honest headline. Win rate
  alone is meaningless; if you pay the ask and the ask equals your win rate, your
  edge is zero.
- **Realizable fills**, not the paper ask — two lenses:
  - *book-persistence*: did the ask still rest at your limit ~1s later, or did it
    pull above it (the classic "asks vanish on the winners")?
  - *tape-corroboration*: did a **real trade** print at your price? Proves the
    ask was genuine, not a thin phantom ladder.
- **Real fees** — PM taker fee is `fee_rate·p·(1−p)` per share; makers pay 0. No
  hand-wavy `min(p,1−p)`.
- **Adverse-selection diagnostic** — a Fokker-Planck fair-value model flags
  trades where the book *baited* you (cheap ask) but the physics disagree: the
  fills you get are the losers; the winners reject you.
- **`ghost_gap`** = paper edge − honest edge = the adverse-selection drag, in one
  number.

This is the harness that retrodicted six consecutive live strategy deaths on
Polymarket up/down markets — every one looked great on paper and lost real money.

## Install

```bash
pip install honest-backtest      # numpy is the only dependency
```

## Quick start

```python
from honest_backtest import Signal, Decision, evaluate

class BuyTheCheapNo(Signal):
    name, family, mode = "cheap_no", "demo", "taker"
    def decide(self, ctx, i):
        # read ONLY indices <= i (no lookahead). Return a Decision or None.
        if ctx.book_ok(i) and 0 < ctx.na[i] < 0.40 and ctx.yes_mid(i) >= 0.56:
            return Decision(i=i, ts_ms=int(ctx.ts[i]), token_yes=False,
                            action="taker", target_px=float(ctx.na[i]), size=20.0)
        return None

row = evaluate(BuyTheCheapNo(), ctxs)   # ctxs: iterable of SlotCtx
print(row["headline_edge_real"], row["ghost_gap"])
```

Bring your own `SlotCtx` stream (build them from your data with
`SlotCtx.from_rows`), or use the bundled SQLite adapter for the
[open Polymarket up/down dataset](#dataset):

```python
from honest_backtest.adapters.sqlite_pm import load_corpus
ctxs = load_corpus("open_dataset.sqlite", coins=("btc",), durations=("5m",))
```

## The calibration anchor

The shipped example `no_overpriced` is a **calibration gate**, not a strategy to
trade. Live it ran 325 fills at WR 0.382 vs avg ask 0.386 → `edge_real = −0.004`.
A naive paper backtest of the same rule showed *+0.07*. The honest harness must
reproduce ~0/negative here:

```bash
python -m honest_backtest.examples.no_overpriced open_dataset.sqlite
```

If it prints a strongly positive `edge_real`, the fill model has drifted
optimistic — that's a bug in `fills.py`, not an edge.

## Why `edge_real`, not WR

> WR > 50% with ask > WR is **not** an edge — the market priced higher than you
> win. Only WR > ask is a real edge.

On an efficient venue, `corr(signal, outcome)` is usually positive (momentum,
spot-vs-strike *do* predict) — but that's not the same as beating the
**transactable** price. The gap between the two is adverse selection, and it's
exactly what `ghost_gap` measures.

## API

| function | what it does |
|---|---|
| `evaluate(signal, ctxs)` | run a signal over a corpus → one leaderboard row |
| `run_signal(signal, ctxs)` | → raw per-decision grade dicts |
| `grade_taker(ctx, decision)` | book-persistence + tape-corroboration fill grade |
| `grade_maker(ctx, decision)` | queue-aware resting-bid fill grade |
| `leaderboard_row(name, family, mode, recs)` | aggregate grades → edge_real, CIs, $ROI, breakdowns |
| `physics_features(ctx, i, buy_yes)` / `adverse_score(feat, buy_yes)` | adverse-selection diagnostic |
| `won_buy`, `fee_per_share`, `fp_prob_yes`, `bootstrap_ci` | building blocks |

`Signal`, `SlotCtx`, `SlotMeta`, `Decision` are the data model. A `Signal`
implements `decide(ctx, i)` reading only indices `<= i`.

## Dataset

The companion open dataset (6 weeks of real Polymarket BTC/ETH/SOL/XRP up/down
microstructure — book snapshots, trade tape, and gamma-oracle resolutions) ships
in the schema this library's SQLite adapter reads. See the dataset card for
provenance and caveats.

## License

Apache-2.0.
