# Dataset card — Polymarket crypto up/down microstructure (5m/15m)

Six weeks of real order-book microstructure, trade tape, and oracle-settled
resolutions for Polymarket's BTC/ETH/SOL/XRP **"Up or Down"** binary markets
(5-minute and 15-minute slots). Captured live, May 27 → Jun 24 2026.

Built following *Datasheets for Datasets* (Gebru et al.).

## Motivation

Why does retail lose the near-close crypto up/down game even when their signal
"predicts"? The honest answer needs real microstructure: the book you saw, the
trades that actually printed, and the ground-truth outcome — at sub-second
resolution near the close. This dataset is that substrate, released so the
[`honest-backtest`](https://github.com/JohanAlvarado/honest-backtest) results
are reproducible and so others can study adverse selection on a real venue.

## Composition

Three tables, published here as **parquet** (`parquet/{slots,book_snapshots,pm_trades}.parquet`)
— the same schema the `honest_backtest` adapters read:

| table | one row per | key fields |
|---|---|---|
| `slots` | market (a single up/down slot) | `condition_id`, `coin`, `duration`, `open_ts`, `close_ts`, `strike`, `spot_at_open/close`, `yes_token_id`, `no_token_id`, **`resolved_side`**, `fee_rate` |
| `book_snapshots` | top-of-book sample (~30s steady, ~1Hz near close) | `ts_ms`, `secs_to_close`, `yes/no` best `bid/ask` + sizes, top-5 `ladder` strings, `spot`, `ds_spot` |
| `pm_trades` | a real trade print | `ts_ms`, `token_id`, `price`, `size`, `taker_buy` (1=buy/0=sell) |

`condition_id`/`token_id`/`slug` are Polymarket-public market identifiers; they
map to real, already-closed markets. There is **no account, wallet, order, or
trade-of-ours information** of any kind (see Anonymization).

## Collection process

A single always-on recorder subscribed to Polymarket's CLOB market WebSocket
(book + trades) and an independent spot/oracle feed. `book_snapshots` sampled
top-of-book on a cadence that tightens to ~1Hz inside the final ~5s of each
slot. `pm_trades` is the raw public trade tape.

**Ground-truth resolution** (`slots.resolved_side`) comes ONLY from Polymarket's
gamma `outcomePrices` (the authoritative settlement oracle), backfilled by a
15-minute cron — **never** inferred from spot. A YES token pays $1 iff
`resolved_side='Yes'`; a NO token pays $1 iff `'No'`.

## Anonymization

The export whitelists three market-observation tables and a fixed column list.
Everything tied to the operator was excluded by construction: our orders, fills,
positions, round-trips, redemptions, on-chain tx hashes, strategy labels, and
maker/shadow decision logs. The exporter asserts: the output contains exactly
`{slots, book_snapshots, pm_trades}`, no column name matching
order/tx/wallet/strategy/pnl, and no wallet/tx-hash-shaped string in text fields.

## Known caveats (read before modeling)

- **Crossed / phantom book (~98% of raw deltas; visible in snapshots too).**
  Displayed ladders are frequently crossed (yes_ask + no_ask ≠ 1; sums < 1 seen
  routinely). The *inside* market must be anchored on `pm_trades` (real
  executions), not taken at face value from the book. This is the central data-
  quality fact — a naive "buy at displayed ask" backtest is fiction.
- **Stale levels rarely removed.** Old ladder levels persist; depth grows over a
  slot's life. Filter to recent/large sizes or anchor on the trade tape.
- **Window starts May 27 deliberately.** An earlier capture era (May 11–23) had
  ~39% of *tight-market* `resolved_side` corrupted by a spot-based inference bug,
  fixed by moving to gamma-only resolution. That era is **excluded** here.
- **`spot` is a Binance-frame consensus**, ~10bp off the data_streams oracle
  Polymarket settles on. For cross-probability features, use spot *moves* vs
  `spot_at_open`, not absolute spot-vs-strike. Grading uses `resolved_side`
  regardless, so outcomes are unaffected.
- Order-side data is intentionally absent (only the public trade tape is here);
  the order-rejection / fill-selection asymmetry is studied in the paper via the
  operator's private ledger, not in this public release.

## Recommended uses

Microstructure research; adverse-selection and execution-quality studies;
realistic backtesting with [`honest-backtest`](https://github.com/JohanAlvarado/honest-backtest);
calibration of fair-value models for short-horizon binary markets. **Not** a
source of a profitable trading signal — the accompanying paper shows realizable
edge is ~0 on this venue by construction.

## Reproduce the headline result

```bash
pip install "honest-backtest[parquet]"
huggingface-cli download kinzikdza/polymarket-updown-microstructure \
    --repo-type dataset --local-dir pm_data
python -m honest_backtest.examples.no_overpriced pm_data/parquet
# expect headline edge_real ~ 0 / negative (live anchor was -0.004)
```

## License

CC BY 4.0. Polymarket market identifiers are public; this release adds no
proprietary or personal data.
