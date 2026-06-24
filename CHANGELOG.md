# Changelog

## 0.2.0

- Parquet adapter (`adapters.parquet_pm.load_corpus`): reproduce results from the
  ~190 MB parquet release on Hugging Face, no 2 GB SQLite needed. Optional extra
  `pip install "honest-backtest[parquet]"` (pandas + pyarrow).
- The `no_overpriced` example and `dataset/load_example.py` now auto-dispatch on
  the source: a `.sqlite` file uses the sqlite adapter, a directory uses parquet.

## 0.1.0

Initial public release.

- Core data model: `Signal`, `SlotCtx`, `SlotMeta`, `Decision`.
- Honest fill models: `grade_taker` (book-persistence + tape-corroboration),
  `grade_maker` (queue-aware resting bid).
- `leaderboard_row` / `evaluate`: `edge_real`, bootstrap CIs, size-weighted
  fee-aware `$ROI`, `ghost_gap`, and by-coin/duration/week breakdowns.
- Adverse-selection diagnostic: `physics_features`, `adverse_score`,
  `classify_fill` (Fokker-Planck fair-value vs the bait ask).
- Real PM fee model in `fee_per_share` (`fee_rate·p·(1−p)`, makers free).
- Optional SQLite adapter (`adapters.sqlite_pm`) for the open dataset schema.
- `no_overpriced` calibration example (anchors the harness to the live −0.004).
