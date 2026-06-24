"""Aggregate grade dicts → one leaderboard row, identically for every signal.

Headline metric is edge_real = mean(won − fill_px) over fills (per-fill,
pre-fee). $ROI is size-weighted and fee-aware — PM charges TAKERS
fee_rate*px*(1-px) per share (crypto fee_rate=0.07; verified
docs.polymarket.com/trading/fees) and NEVER charges makers, and sizes vary, so
$ROI ≠ per-fill edge.

Two honest taker lenses (both must clear 0 for a real edge):
  honest_persist   — book-persistence, FULL corpus. PRIMARY.
  honest_fillable  — tape-corroboration, needs a real trade tape. STRICTEST.
ghost_gap = paper edge − honest_persist edge = the adverse-selection drag.
"""
from __future__ import annotations

import random
import statistics
from collections import defaultdict
from datetime import datetime, timezone


def bootstrap_ci(vals, iters=2000, seed=42):
    n = len(vals)
    if n == 0:
        return (0.0, 0.0, 0.0)
    rng = random.Random(seed)
    means = []
    for _ in range(iters):
        means.append(sum(vals[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    return (means[int(0.025 * iters)], statistics.mean(vals),
            means[int(0.975 * iters)])


def iso_week(ts_ms):
    y, w, _ = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isocalendar()
    return f"{y}-W{w:02d}"


def _edge_stats(trades):
    """trades: list of (won01, fill_px, size, fee_rate)."""
    n = len(trades)
    if n == 0:
        return {"n": 0, "wr": None, "avg_px": None, "edge_real": None,
                "ci_lo": None, "ci_hi": None}
    per = [t[0] - t[1] for t in trades]
    lo, mean, hi = bootstrap_ci(per)
    return {"n": n,
            "wr": round(sum(t[0] for t in trades) / n, 4),
            "avg_px": round(sum(t[1] for t in trades) / n, 4),
            "edge_real": round(mean, 4),
            "ci_lo": round(lo, 4), "ci_hi": round(hi, 4)}


def _roi(trades, use_fee, is_maker=False):
    """Size-weighted $ROI. use_fee applies the real PM TAKER fee
    fee_rate*px*(1-px) per share (verified docs.polymarket.com/trading/fees:
    fee = shares*feeRate*p*(1-p), crypto feeRate=0.07). MAKERS ARE NEVER
    CHARGED (is_maker=True → 0; they also earn a ~20% taker-fee rebate, not
    credited here)."""
    cost = pnl = 0.0
    for won01, px, sz, fr in trades:
        fee = 0.0 if (is_maker or not use_fee) else (fr * px * (1.0 - px) * sz)
        c = px * sz + fee
        cost += c
        pnl += (sz if won01 > 0.5 else 0.0) - c
    return (round(pnl / cost, 4) if cost > 0 else None, round(pnl, 2),
            round(cost, 2))


def _taker_trades(recs, mode):
    out = []
    for r in recs:
        if not r["valid"] or not r["crossable"]:
            continue
        # Fill PRICE is always the decision-time best ask (you cross what you
        # saw). Persistence/tape only gate FILL vs MISS — crediting the cheaper
        # arrival ask would be optimistic price-improvement.
        if mode == "paper":
            px, sz = r["best_ask"], r["size"]
        elif mode == "honest_persist":
            # only grade where persistence is actually assessable (dense
            # cadence); early-firing signals fall back to the tape lens.
            if not (r["persist_known"] and r["persisted"]):
                continue
            px, sz = r["best_ask"], r["honest_sz"]
        elif mode == "honest_fillable":
            if not (r["has_tape"] and r["fillable"]):
                continue
            px, sz = r["best_ask"], r["honest_sz"]
        else:
            raise ValueError(mode)
        if sz <= 0:
            continue
        out.append((1.0 if r["won"] else 0.0, px, sz, r["fee_rate"]))
    return out


def _maker_trades(recs, honest):
    out = []
    for r in recs:
        if not r["has_tape"]:
            continue
        if honest:
            if r["filled"] <= 0:
                continue
            out.append((1.0 if r["won"] else 0.0, r["paid"] / r["filled"],
                        r["filled"], r["fee_rate"]))
        else:
            out.append((1.0 if r["won"] else 0.0, r["bid_px"], r["size"],
                        r["fee_rate"]))
    return out


def _breakdown(recs, keyfn, trades_fn):
    groups = defaultdict(list)
    for r in recs:
        groups[keyfn(r)].append(r)
    out = {}
    for k, rs in sorted(groups.items()):
        st = _edge_stats(trades_fn(rs))
        if st["n"] > 0:
            out[k] = {"n": st["n"], "edge_real": st["edge_real"],
                      "ci_lo": st["ci_lo"], "wr": st["wr"]}
    return out


def leaderboard_row(name, family, mode, recs):
    n_total = len(recs)
    row = {"name": name, "family": family, "mode": mode, "n_decisions": n_total}

    if mode == "taker":
        n_cross = sum(r["valid"] and r["crossable"] for r in recs)
        n_pk = sum(r["valid"] and r["crossable"] and r["persist_known"] for r in recs)
        n_persist = sum(r["valid"] and r["crossable"] and r["persist_known"]
                        and r["persisted"] for r in recs)
        n_tape = sum(r["valid"] and r["crossable"] and r["has_tape"] for r in recs)
        n_fillable = sum(r["valid"] and r["crossable"] and r["has_tape"]
                         and r["fillable"] for r in recs)
        paper = _edge_stats(_taker_trades(recs, "paper"))
        persist = _taker_trades(recs, "honest_persist")
        persist_st = _edge_stats(persist)
        fillable = _taker_trades(recs, "honest_fillable")
        fill_st = _edge_stats(fillable)
        ggap = (round(paper["edge_real"] - persist_st["edge_real"], 4)
                if paper["edge_real"] is not None
                and persist_st["edge_real"] is not None else None)
        row.update({
            "n_crossable": n_cross,
            "persist_rate": round(n_persist / n_pk, 4) if n_pk else None,
            "fill_rate": round(n_fillable / n_tape, 4) if n_tape else None,
            "paper": paper, "honest_persist": persist_st,
            "honest_fillable": fill_st, "ghost_gap": ggap,
        })
        # headline = the informative honest lens (persistence if densely
        # assessable, else tape). A signal is only "real" if BOTH lenses that
        # have n>=30 clear zero.
        if persist_st["n"] >= 30:
            headline, lens, hmode = persist_st, "persist", "honest_persist"
        else:
            headline, lens, hmode = fill_st, "fillable", "honest_fillable"
        row.update({
            "headline_lens": lens,
            "headline_edge_real": headline["edge_real"],
            "headline_ci_lo": headline["ci_lo"], "headline_n": headline["n"],
            "roi_nofee": _roi(persist, False),
            "roi_real": _roi(persist, True),
            "roi_real_fillable": _roi(fillable, True),
        })
        hfn = lambda rs: _taker_trades(rs, hmode)
    else:  # maker
        n_tape = sum(r["has_tape"] for r in recs)
        n_filled = sum(r["has_tape"] and r["filled"] > 0 for r in recs)
        paper = _edge_stats(_maker_trades(recs, honest=False))
        honest = _maker_trades(recs, honest=True)
        hon_st = _edge_stats(honest)
        ggap = (round(paper["edge_real"] - hon_st["edge_real"], 4)
                if paper["edge_real"] is not None
                and hon_st["edge_real"] is not None else None)
        row.update({
            "n_tape": n_tape, "n_filled": n_filled,
            "fill_rate": round(n_filled / n_tape, 4) if n_tape else None,
            "paper": paper, "honest": hon_st, "ghost_gap": ggap,
            "headline_edge_real": hon_st["edge_real"],
            "headline_ci_lo": hon_st["ci_lo"], "headline_n": hon_st["n"],
            "roi_nofee": _roi(honest, False, is_maker=True),
            "roi_real": _roi(honest, True, is_maker=True),
        })
        hfn = lambda rs: _maker_trades(rs, honest=True)

    bd_recs = recs if mode == "taker" else [r for r in recs if r["has_tape"]]
    row["by_coin"] = _breakdown(bd_recs, lambda r: r["coin"], hfn)
    row["by_dur"] = _breakdown(bd_recs, lambda r: r["dur"], hfn)
    row["by_week"] = _breakdown(bd_recs, lambda r: iso_week(r["ts_ms"]), hfn)
    return row
