"""Settlement vs ground-truth resolution + fee model.

Ground truth = the market's authoritative resolution (for Polymarket up/down,
`slots.resolved_side` from the gamma oracle — NEVER derived from spot). A bought
YES token pays $1 iff resolved 'Yes'; a bought NO token pays $1 iff resolved 'No'.
"""
from __future__ import annotations


def won_buy(token_yes: bool, resolved_side: str) -> bool:
    """Did buying this token side win? token_yes=True buys the YES token."""
    return token_yes == (resolved_side == "Yes")


def fee_per_share(px: float, model: str = "taker", fee_rate: float | None = 0.07,
                  is_maker: bool = False) -> float:
    """Per-share fee in $. Verified vs docs.polymarket.com/trading/fees:
    PM charges TAKERS  fee = shares * fee_rate * p * (1-p)  → per-share
    fee_rate*p*(1-p). MAKERS ARE NEVER CHARGED (is_maker → 0; they also earn a
    ~20% rebate of taker fees, not modelled). Crypto fee_rate = 0.07.

    A common mistake is `fee_rate*min(px,1-px)` and charging makers — that
    over-charges ~2x at mid prices and mis-attributes maker losses to fees
    (makers pay nothing; they die of adverse selection).

    - 'taker' (default): fee_rate * px * (1-px), the real PM taker fee.
    - 'zero'           : no fee (edge_real is fee-agnostic; for the no-fee $ROI line).
    """
    if is_maker or model == "zero":
        return 0.0
    fr = fee_rate if fee_rate else 0.07
    return fr * px * (1.0 - px)
