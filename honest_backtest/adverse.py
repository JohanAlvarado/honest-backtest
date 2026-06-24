"""Adverse-selection physics diagnostic — "see the future" before you POST.

Adverse selection on prediction-market takers is visible in hindsight (filled
WR << ghost WR; you get rejected on the winners) but hard to dodge at POST
latency. Instead of reacting to fills, use a Fokker-Planck / drift / vol model
to forecast settlement OUTCOME from spot physics at decision time — then flag
trades where the BOOK baited you (cheap ask) but physics disagrees.

All functions here are pure given a `SlotCtx` and an index; combine with
`fills.grade_taker` + `classify_fill` to bucket each decision into the
adverse-selection taxonomy (good_fill / adverse_fill / missed_winner / good_miss).
"""
from __future__ import annotations

import math

# ── physics primitives ──
BAYES_PRIOR = 0.3
DRIFT_FAST = 30.0
DRIFT_SLOW = 120.0
VOL_WIN = 60.0
VOL_FLOOR = 1e-7


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def fp_prob_yes(spot: float, strike: float, drift: float, vol: float, tau: float) -> float:
    """P(spot_T >= strike) under geometric Brownian motion with per-second
    drift and vol, tau seconds to close. The model's fair P(YES)."""
    if tau <= 0 or vol <= 0 or strike <= 0:
        return 1.0 if spot > strike else 0.0
    lm = math.log(spot / strike)
    d = (lm + (drift - 0.5 * vol * vol) * tau) / (vol * math.sqrt(tau))
    return normal_cdf(d)


def bayesian_drift(ctx, i: int) -> float:
    fast = ctx.drift_persec(i, DRIFT_FAST)
    slow = ctx.drift_persec(i, DRIFT_SLOW)
    return BAYES_PRIOR * slow + (1.0 - BAYES_PRIOR) * fast


def spot_toward_strike_bps(ctx, i: int, secs: float, strike: float) -> float:
    """Signed velocity toward strike in bps/sec. Positive = spot moving toward strike."""
    j = ctx._win_start(i, secs)
    if j >= i or ctx.spot[j] <= 0 or ctx.spot[i] <= 0 or strike <= 0:
        return 0.0
    dt = (ctx.ts[i] - ctx.ts[j]) / 1000.0
    if dt <= 0:
        return 0.0
    dist0 = abs(ctx.spot[j] - strike)
    dist1 = abs(ctx.spot[i] - strike)
    toward = (dist0 - dist1) / strike  # fraction of strike per window
    return toward / dt * 1e4  # bps per sec


def physics_features(ctx, i: int, buy_yes: bool) -> dict:
    strike = ctx.meta.strike
    spot = float(ctx.spot[i])
    tau = max(float(ctx.s2c[i]), 0.5)
    vol = max(ctx.realized_vol_persec(i, VOL_WIN), VOL_FLOOR)
    drift = bayesian_drift(ctx, i)
    p_yes = fp_prob_yes(spot, strike, drift, vol, tau)
    p_side = p_yes if buy_yes else (1.0 - p_yes)
    ask = ctx.ask(i, buy_yes)
    book_edge = p_side - ask if ask == ask and 0 < ask < 1 else float("nan")
    revert = spot_toward_strike_bps(ctx, i, 10.0, strike)
    drift_bps = drift * 1e4
    return {
        "p_yes": p_yes,
        "p_side": p_side,
        "book_edge": book_edge,
        "vol": vol,
        "drift_bps": drift_bps,
        "revert_bps": revert,
        "tau": tau,
        "spot_vs_strike_bps": (spot - strike) / strike * 1e4 if strike > 0 else 0.0,
    }


def adverse_score(feat: dict, buy_yes: bool) -> float:
    """Higher = more likely you'd be adversely selected (fill loser / miss winner).

    Core signal: book shows edge (cheap ask) but physics fair prob is BELOW the
    ask — the ask is bait, it will fill, and you lose. Near close, spot momentum
    away from your side amplifies the risk.
    """
    be = feat["book_edge"]
    if be != be:
        return 0.0

    # phantom bait: book_edge>0 but physics says we're overpaying
    bait = max(0.0, be) * max(0.0, feat["p_side"] - (1.0 - be)) if be > 0 else 0.0
    if be > 0 and feat["p_side"] < 0.5:
        bait = be + (0.5 - feat["p_side"])

    # momentum: does spot physics say our side LOSES from here?
    phys_favors_us = feat["p_side"] > 0.5
    mom_against = 0.0 if phys_favors_us else (0.5 - feat["p_side"])

    # near-close: small tau → informed flow dominates; amplify disagreement
    tau_w = 1.0 / max(feat["tau"], 5.0)
    return bait * 3.0 + mom_against * 2.0 + tau_w * max(0.0, -be) * 5.0


def classify_fill(g: dict) -> str:
    """Bucket a taker grade dict into the adverse-selection taxonomy."""
    if not g["crossable"]:
        return "no_signal"
    if g["persisted"]:
        return "adverse_fill" if not g["won"] else "good_fill"
    return "missed_winner" if g["won"] else "good_miss"
