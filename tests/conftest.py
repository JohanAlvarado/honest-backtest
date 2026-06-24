"""Synthetic SlotCtx builders so the core tests need no real data."""
from __future__ import annotations

from honest_backtest import SlotCtx, SlotMeta

# A fixed mid-2026 UTC timestamp base (ms) for deterministic iso_week.
BASE_MS = 1_717_200_000_000  # 2024-06-01-ish; only used for grouping keys


def make_meta(resolved_side="No", strike=50_000.0, **kw):
    d = dict(
        condition_id="0xtest", coin="btc", duration="5m", duration_s=300,
        open_ts=BASE_MS // 1000, close_ts=BASE_MS // 1000 + 300,
        strike=strike, spot_at_open=strike, spot_at_close=strike,
        yes_token_id="Y", no_token_id="N", resolved_side=resolved_side,
        fee_rate=0.07, rebate_rate=0.0,
    )
    d.update(kw)
    return SlotMeta(**d)


def make_ctx(topbook, trades=None, **meta_kw):
    """topbook: list of (ts_ms, s2c, yb, ya, ybs, yas, nb, na, nbs, nas, spot).
    trades: list of (ts_ms, token_id, price, size, taker_buy)."""
    return SlotCtx.from_rows(make_meta(**meta_kw), topbook, trades or [])
