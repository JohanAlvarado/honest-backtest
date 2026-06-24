from honest_backtest import Decision, grade_maker, grade_taker

from .conftest import make_ctx

# Two snapshots 1s apart. Buying NO at 0.40 (resolved 'No' → win).
#               ts_ms s2c  yb   ya  ybs yas  nb   na  nbs nas  spot
SNAP0 = (1000, 300, 0.55, 0.65, 100, 100, 0.35, 0.40, 100, 100, 50000.0)
SNAP1_HOLD = (2000, 299, 0.55, 0.65, 100, 100, 0.35, 0.40, 100, 100, 50000.0)
SNAP1_PULL = (2000, 299, 0.55, 0.65, 100, 100, 0.45, 0.50, 100, 100, 50000.0)


def _decision():
    return Decision(i=0, ts_ms=1000, token_yes=False, action="taker",
                    target_px=0.45, size=20.0)


def test_taker_persists_and_fills_when_ask_holds():
    ctx = make_ctx([SNAP0, SNAP1_HOLD], resolved_side="No")
    g = grade_taker(ctx, _decision(), latency_ms=1000)
    assert g["valid"] and g["crossable"]
    assert g["persist_known"] and g["persisted"]
    assert abs(g["fill_px"] - 0.40) < 1e-9
    assert g["won"] is True


def test_taker_misses_when_ask_pulls_above_limit():
    ctx = make_ctx([SNAP0, SNAP1_PULL], resolved_side="No")
    g = grade_taker(ctx, _decision(), latency_ms=1000)
    assert g["persist_known"] is True
    assert g["persisted"] is False  # ask repriced to 0.50 > 0.45 limit → miss


def test_taker_fillable_requires_real_tape_print():
    # a real taker_buy on NO at <= limit within the window proves the ask.
    trades = [(1500, "N", 0.40, 50, 1)]
    ctx = make_ctx([SNAP0, SNAP1_HOLD], trades=trades, resolved_side="No")
    g = grade_taker(ctx, _decision(), latency_ms=1000, tape_window_ms=1500)
    assert g["has_tape"] is True
    assert g["fillable"] is True


def test_taker_not_fillable_without_tape():
    ctx = make_ctx([SNAP0, SNAP1_HOLD], resolved_side="No")
    g = grade_taker(ctx, _decision(), latency_ms=1000)
    assert g["has_tape"] is False
    assert g["fillable"] is False


def test_taker_not_crossable_when_ask_above_target():
    # ask 0.40 but target only 0.30 → not crossable
    d = Decision(i=0, ts_ms=1000, token_yes=False, action="taker",
                 target_px=0.30, size=20.0)
    ctx = make_ctx([SNAP0, SNAP1_HOLD], resolved_side="No")
    g = grade_taker(ctx, d)
    assert g["crossable"] is False


def test_maker_fills_against_sell_tape():
    # post a resting NO bid at 0.35; a taker SELL of NO at 0.35 hits it.
    # queue ahead (nbs at i) is 100; the sell must exceed it to reach us.
    trades = [(1500, "N", 0.35, 130, 0)]  # taker_buy=0 → SELL
    ctx = make_ctx([SNAP0], trades=trades, resolved_side="No")
    d = Decision(i=0, ts_ms=1000, token_yes=False, action="maker",
                 target_px=0.35, size=20.0)
    g = grade_maker(ctx, d)
    assert g["filled"] > 0       # 130 sold, 100 ahead → 30 reaches us, capped at 20
    assert abs(g["filled"] - 20.0) < 1e-9
    assert g["won"] is True
