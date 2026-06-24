from honest_backtest import bootstrap_ci, leaderboard_row


def _taker_rec(won, ask, ts_ms=1_717_200_000_000):
    return {
        "cid": "0x", "coin": "btc", "dur": "5m", "ts_ms": ts_ms, "s2c": 100,
        "yes": False, "won": won, "best_ask": ask, "fill_px": ask,
        "target_px": ask, "size": 20.0, "honest_sz": 20.0,
        "valid": True, "crossable": True, "persisted": True,
        "persist_known": True, "fillable": True, "has_tape": True,
        "fee_rate": 0.07, "tag": "", "mode": "taker",
    }


def test_edge_real_is_won_minus_fill_price():
    # one winner at 0.40, one loser at 0.40 → per-fill edge mean = (0.6 - 0.4)/2
    recs = [_taker_rec(True, 0.40), _taker_rec(False, 0.40)]
    row = leaderboard_row("t", "fam", "taker", recs)
    assert abs(row["paper"]["edge_real"] - 0.1) < 1e-9
    assert row["paper"]["wr"] == 0.5


def test_ghost_gap_is_paper_minus_persist():
    recs = [_taker_rec(True, 0.40), _taker_rec(False, 0.40)]
    row = leaderboard_row("t", "fam", "taker", recs)
    # all recs persist+fillable here, so paper == persist → ghost_gap 0
    assert row["ghost_gap"] == 0.0


def test_negative_edge_when_ask_above_winrate():
    # WR 0.5 but you pay 0.60 → edge_real negative (the efficient-venue case)
    recs = [_taker_rec(True, 0.60), _taker_rec(False, 0.60)]
    row = leaderboard_row("t", "fam", "taker", recs)
    assert row["paper"]["edge_real"] < 0


def test_roi_is_fee_aware_and_size_weighted():
    # single winning fill: 20 sh at 0.40, fee 0.07*0.4*0.6 per share
    recs = [_taker_rec(True, 0.40)]
    row = leaderboard_row("t", "fam", "taker", recs)
    roi_nofee, pnl_nofee, cost_nofee = row["roi_nofee"]
    # no-fee: win pays 20 sh * $1 = 20; cost = 20*0.40 = 8 → pnl 12
    assert abs(cost_nofee - 8.0) < 1e-6
    assert abs(pnl_nofee - 12.0) < 1e-6
    # fee line costs strictly more
    assert row["roi_real"][2] > cost_nofee


def test_bootstrap_ci_is_deterministic_with_seed():
    vals = [0.6, -0.4, 0.6, -0.4, 0.1]
    a = bootstrap_ci(vals, seed=42)
    b = bootstrap_ci(vals, seed=42)
    assert a == b
    assert a[0] <= a[1] <= a[2]
