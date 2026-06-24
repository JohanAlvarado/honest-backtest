# Why retail loses the near-close crypto up/down game

*A measured account of adverse selection on Polymarket's short-horizon binary
markets, with an open dataset and a reproducible backtest harness.*

## Abstract

We ran fifteen distinct trading signals on Polymarket's BTC/ETH/SOL/XRP "Up or
Down" 5- and 15-minute markets, both in offline backtest and with live capital.
Every signal that looked profitable on paper lost money — or broke even
negative — in production. Across the live fills, realized win rate equals the
price paid to one decimal place: `edge_real = WR − avg_ask ≈ 0`. We show this is
not bad luck but structure. The settlement oracle makes the outcome
near-deterministic in the final ~1.7 seconds, below execution latency; and the
fills a taker actually receives are adversely selected — you fill the losers and
get rejected on the winners. A backtest that paper-fills at the displayed ask
cannot see either effect, which is why it is always optimistic. We release the
six-week microstructure dataset and the "honest" backtest harness that
retrodicts all six live strategy deaths, so the claim is checkable.

## 1. Setup: the venue is efficient, so the price already contains the signal

Polymarket up/down markets are binary: a YES token pays \$1 if the coin closed
up over the slot, a NO token pays \$1 if down. On an efficient venue the
transactable ask approximates the true outcome probability, `ask ≈ P(win)`. If
you pay the ask and the ask equals your win rate, your per-fill edge

```
edge_real = E[won − ask_paid]
```

is zero by construction. This is the single most important and most ignored fact
in prediction-market backtesting. A signal can have genuinely predictive power —
`corr(signal, outcome) > 0` — and still have **no extractable edge**, because the
price has already priced it. Win rate alone is therefore meaningless: `WR > 50%`
with `ask > WR` is not an edge.

Measured over 325 real fills of our best offline candidate (`no_overpriced`):
realized WR **0.382** vs average ask **0.386** → `edge_real = −0.004`. The same
rule's paper backtest had projected WR **70.5%**. The gap between 70.5% and 38.9%
is the subject of this paper.

## 2. Physics: the outcome is decided below your latency

Polymarket settles these markets on the Chainlink **data_streams** oracle — the
"price to beat" is the oracle value at slot open, and the outcome is the oracle
value at slot close. From the recorded oracle stream we find:

- When the spot–strike distance at close exceeds ~10 bp, the outcome is
  effectively deterministic (96–99% concordant with the sign of the distance).
- Inside ~5 bp it is a coin flip (42–48%).
- The transition resolves in the **final ~1.7 seconds**, governed by the oracle's
  heartbeat — *below* a retail taker's round-trip POST latency (~190 ms plus the
  uncertainty of where in the heartbeat you land).

So the only slots whose outcome is still uncertain when you can act are the
coin-flips; the decided ones are decided in a window you cannot trade into. This
already explains why directional signals, spread capture, "arbitrage," and
maker-rewards strategies all collapsed: there is no stable, transactable
mispricing left in the window a retail latency budget can reach.

## 3. Mechanism: fill self-selection (you fill the losers)

The deeper killer is *which* fills you get. We joined our submission ledger
(matched orders vs `http_400` rejects) to the gamma resolutions and compared the
would-win rate of each cohort:

| signal | rejected-order would-win | filled-order would-win | gap |
|---|---|---|---|
| entropy | 78.5% | 57.4% | **−21 pp** |
| momentum | 66.7% | 34.8% | **−32 pp** |
| no_overpriced | (≈) | (≈) | −4 pp |

The rejects are disproportionately the winners; the fills are disproportionately
the losers. When your order would have won, the resting liquidity vanishes or the
book reprices and you are rejected (`http_400`); when it would have lost, the
liquidity is there and you fill. The gap scales with proximity to close — early-
firing signals (`no_overpriced`, T+0–60 s) show a small gap; near-close signals
show a large one. This is textbook adverse selection, and it is **not** a bug to
fix with faster code at the margin: it is the informed flow on the other side of
your trade, and at the limit it is just the latency race of §2.

## 4. Method: an honest harness, anchored to a known live result

A backtest can only mislead if it fills at prices you could not get. We grade
every decision against a **realizable** fill instead of the displayed ask, with
two lenses:

- **book-persistence** — re-check the ask ~1 s after the decision; if it has
  repriced above your limit, you missed (the "asks pull on winners" effect of §3).
- **tape-corroboration** — require a *real* trade print at your price within a
  short window, proving the ask was genuine and not a thin phantom ladder
  (displayed books are crossed/phantom ~98% of the time on this venue).

The headline is `edge_real = mean(won − fill_px)` with bootstrap confidence
intervals; `ghost_gap = paper_edge − honest_edge` quantifies the adverse-
selection drag in one number. Fees use the verified PM model
(`taker = fee_rate·p·(1−p)`; makers pay zero and earn a rebate — so the popular
"fees killed the maker" story is false; makers died of adverse selection).

We **calibrate** the harness to a known live outcome: `no_overpriced` must grade
near zero/negative, because it did (`−0.004`) over 325 live fills. Re-running it
through the harness on the open dataset reproduces a paper edge of **−0.003** and
a strict-lens (tape) edge of **−0.05** — recovering the live result and exposing
the paper "+0.07" as the illusion. If the harness ever shows a strong positive
edge here, the fill model has drifted optimistic; that is a harness bug, not an
edge.

## 5. Results: zero of fifteen clear the realizable bar

Swept across all fifteen signals over the corpus, **none** clears `edge_real > 0`
at `n ≥ 40` under the realizable lens. Every taker family lands negative
(momentum ≈ −0.08, entropy ≈ −0.07, velocity/momentum-oracle ≈ −0.08); every
maker family lands −0.15 to −0.25 honest. The paper/persistence lens is *fooled*
by the same fill self-selection — e.g. momentum reads **+0.64** on the persistence
lens but **−0.08** on the realizable lens; that 0.7 gap *is* the adverse
selection, made visible.

The harness **retrodicts all six live deaths.** The most striking is `velrider`,
the strongest offline candidate we ever produced: out-of-sample temporal split
held, the edge sat on a broad parameter plateau (not a spike), and the bootstrap
CI cleared zero. It still died live — 1 win, 6 losses (WR 14% vs 72% offline) —
and the fill ledger showed exactly the §3 mechanism: a winner lost to an
`http_400`, a loser filled deep. The lesson, stated plainly: **OOS + plateau +
bootstrap rigor offline cannot certify a prediction-market taker edge**, because
the backtest measures correlation against the *observed* price, while live fills
self-select against you and reject you on the winners.

## 6. Conclusion

On this venue, for this game, realizable edge is ≈ 0 by construction and negative
after adverse selection. The honest contribution is not a winning strategy — it
is the **measurement**: an open dataset of real microstructure with ground-truth
resolutions, and a harness that refuses to fill at prices you can't get and
therefore reproduces reality instead of flattering it. The remaining lever for
anyone who wants to play is pure execution speed (win the §2 latency race), which
is an infrastructure problem, not a signal problem.

## Reproducibility

- **Dataset**: `slots`, `book_snapshots`, `pm_trades`, May 27 – Jun 24 2026, BTC/
  ETH/SOL/XRP 5m & 15m, gamma-oracle resolutions. See `dataset/DATASHEET.md`.
- **Harness**: `pip install honest-backtest`. Reproduce the calibration anchor:
  `python -m honest_backtest.examples.no_overpriced open_dataset.sqlite`.
- All numbers above are regenerable from the dataset + harness; the live-only
  cohort comparison of §3 uses the operator's private submission ledger, which is
  not part of the public release (only the public trade tape is).

## Limitations

The live falsifications used real but modest capital (tens to low-hundreds of
dollars per arc); n is small per strategy, which is *why* we lean on the
mechanism (oracle physics + measured fill self-selection) rather than on any one
arc's P&L. The dataset is six weeks of four coins on one venue; generalization to
other venues, horizons, or regimes is unestablished. The fair-value model in the
adverse-selection diagnostic is a lognormal/Fokker-Planck approximation, useful
as a selector, not a calibrated probability.
