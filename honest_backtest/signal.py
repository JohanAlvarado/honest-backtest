"""Data model + Signal interface. Every strategy implements `Signal`.

No-lookahead is structural: the runner calls `decide(ctx, i)` walking snapshots
in order; a signal may read only ctx fields at indices <= i. Fills are then
simulated FORWARD from the decision's snapshot. A signal that peeks at j>i is a
bug (lookahead) — keep decide() reading [:i+1] only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

DUR_SECS = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400}


@dataclass
class SlotMeta:
    condition_id: str
    coin: str
    duration: str
    duration_s: int
    open_ts: int          # unix seconds
    close_ts: int         # unix seconds
    strike: float
    spot_at_open: float
    spot_at_close: float
    yes_token_id: str
    no_token_id: str
    resolved_side: str    # 'Yes' | 'No'
    fee_rate: float | None
    rebate_rate: float | None

    @property
    def resolved_yes(self) -> bool:
        return self.resolved_side == "Yes"


@dataclass
class Decision:
    """A single entry. token_yes=True buys the YES token, False the NO token.
    action 'taker' = marketable IOC buy up to target_px; 'maker' = post a
    resting bid at target_px. size in shares."""
    i: int
    ts_ms: int
    token_yes: bool
    action: str           # 'taker' | 'maker'
    target_px: float
    size: float
    tag: str = ""


class SlotCtx:
    """Per-slot replay. Numpy arrays (not per-snapshot objects) for speed.
    Built once, iterated by every signal.

    `snaps` is an 11-tuple of equal-length numpy arrays:
      (ts_ms, secs_to_close, yes_bid, yes_ask, yes_bid_size, yes_ask_size,
       no_bid, no_ask, no_bid_size, no_ask_size, spot)
    `trades` is a 5-tuple of equal-length arrays:
      (ts_ms, is_yes(bool), price, size, taker_buy(bool))
    Build one from your own data source via `from_rows` or the constructor.
    """

    def __init__(self, meta: SlotMeta, snaps, trades):
        self.meta = meta
        (self.ts, self.s2c, self.yb, self.ya, self.ybs, self.yas,
         self.nb, self.na, self.nbs, self.nas, self.spot) = snaps
        self.n = int(self.ts.size)
        # trades: ts_ms, is_yes(bool), price, size, taker_buy(bool)
        (self.tr_ts, self.tr_yes, self.tr_px, self.tr_sz, self.tr_buy) = trades
        self.has_tape = bool(self.tr_ts.size > 0)

    # ---- builders ----
    @classmethod
    def from_rows(cls, meta: SlotMeta, topbook_rows, trade_rows):
        """topbook_rows: list of 11-tuples (ts_ms, s2c, yb, ya, ybs, yas, nb,
        na, nbs, nas, spot). trade_rows: list of (ts_ms, token_id, price, size,
        taker_buy). token_id is matched against meta.yes_token_id."""
        cols = list(zip(*topbook_rows)) if topbook_rows else [()] * 11

        def arr(j, dt=np.float64):
            return np.asarray(cols[j], dtype=dt) if cols[j] else np.zeros(0, dt)

        snaps = (arr(0, np.int64), arr(1, np.int64), arr(2), arr(3), arr(4),
                 arr(5), arr(6), arr(7), arr(8), arr(9), arr(10))
        if trade_rows:
            tts, ttok, tpx, tsz, tbuy = zip(*trade_rows)
            is_yes = np.asarray([t == meta.yes_token_id for t in ttok], dtype=bool)
            trades = (np.asarray(tts, np.int64), is_yes,
                      np.asarray(tpx, np.float64), np.asarray(tsz, np.float64),
                      np.asarray(tbuy, np.int64).astype(bool))
        else:
            z = np.zeros(0)
            trades = (np.zeros(0, np.int64), np.zeros(0, bool), z, z,
                      np.zeros(0, bool))
        return cls(meta, snaps, trades)

    # ---- per-side top-of-book accessors ----
    def ask(self, i, yes):  return self.ya[i] if yes else self.na[i]
    def bid(self, i, yes):  return self.yb[i] if yes else self.nb[i]
    def ask_sz(self, i, yes): return self.yas[i] if yes else self.nas[i]
    def bid_sz(self, i, yes): return self.ybs[i] if yes else self.nbs[i]

    def mid(self, i, yes):
        b, a = self.bid(i, yes), self.ask(i, yes)
        if b > 0 and a > b and a < 1.0:
            return 0.5 * (a + b)
        return float("nan")

    def yes_mid(self, i):
        return self.mid(i, True)

    def book_ok(self, i):
        """Both sides have a sane two-sided book at i."""
        return (self.yb[i] > 0 and self.ya[i] > self.yb[i] and self.ya[i] < 1.0
                and self.na[i] > 0 and self.nb[i] >= 0)

    def elapsed_s(self, i):
        return self.meta.duration_s - int(self.s2c[i])

    # ---- spot-history features (window ends at snapshot i) ----
    def _win_start(self, i, secs):
        lo_ts = self.ts[i] - secs * 1000
        return int(np.searchsorted(self.ts, lo_ts, side="left"))

    def spot_ret_bps(self, i, secs):
        """log-return * 1e4 of spot over the last `secs` up to i."""
        j = self._win_start(i, secs)
        if j >= i or self.spot[j] <= 0 or self.spot[i] <= 0:
            return 0.0
        return math.log(self.spot[i] / self.spot[j]) * 1e4

    def realized_vol_persec(self, i, secs):
        """stdev of per-snapshot log-returns within the window, per sqrt-sec."""
        j = self._win_start(i, secs)
        s = self.spot[j:i + 1]
        if s.size < 3:
            return 1e-5
        s = s[s > 0]
        if s.size < 3:
            return 1e-5
        lr = np.diff(np.log(s))
        dt = np.diff(self.ts[j:i + 1]) / 1000.0
        dt = dt[:lr.size]
        m = dt > 0
        if m.sum() < 2:
            return 1e-5
        norm = lr[m] / np.sqrt(dt[m])
        return float(max(np.std(norm), 1e-5))

    def drift_persec(self, i, secs):
        """mean log-return per second over the window."""
        j = self._win_start(i, secs)
        if j >= i:
            return 0.0
        s = self.spot[j:i + 1]
        s = s[s > 0]
        if s.size < 2:
            return 0.0
        total_lr = math.log(s[-1] / s[0])
        total_dt = (self.ts[i] - self.ts[j]) / 1000.0
        return total_lr / total_dt if total_dt > 0 else 0.0


class Signal:
    """Subclass and implement decide(). Set class attrs to scope the universe."""
    name = "base"
    family = "base"
    mode = "taker"                      # 'taker' | 'maker'
    coins = ("btc", "eth", "sol", "xrp")
    durations = ("5m", "15m")
    once = True                          # stop after first decision per slot

    def decide(self, ctx: SlotCtx, i: int):
        """Return a Decision (or None) using ONLY ctx data at indices <= i."""
        raise NotImplementedError
