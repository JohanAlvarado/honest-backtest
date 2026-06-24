from honest_backtest import evaluate, run_signal
from honest_backtest.examples.no_overpriced import NoOverpriced

from .conftest import make_ctx

# yes_mid = (0.55+0.62)/2 = 0.585 >= 0.56 ; no_ask 0.40 < 0.45 ; elapsed 10s < 60
#       ts_ms  s2c  yb    ya    ybs  yas  nb    na    nbs  nas  spot
FIRES = (1000, 290, 0.55, 0.62, 100, 100, 0.35, 0.40, 100, 100, 50000.0)
HOLD = (2000, 289, 0.55, 0.62, 100, 100, 0.35, 0.40, 100, 100, 50000.0)


def test_run_signal_fires_once_per_slot():
    ctx = make_ctx([FIRES, HOLD], resolved_side="No")
    recs = run_signal(NoOverpriced(), [ctx])
    assert len(recs) == 1            # once=True
    assert recs[0]["mode"] == "taker"
    assert recs[0]["yes"] is False   # buys NO
    assert recs[0]["won"] is True


def test_evaluate_returns_leaderboard_row():
    ctxs = [make_ctx([FIRES, HOLD], resolved_side="No"),
            make_ctx([FIRES, HOLD], resolved_side="Yes")]  # one win, one loss
    row = evaluate(NoOverpriced(), ctxs)
    assert row["name"] == "no_overpriced"
    assert row["mode"] == "taker"
    assert row["n_decisions"] == 2
    assert "paper" in row and "honest_persist" in row and "ghost_gap" in row
    # bought NO at 0.40; one win one loss → paper edge_real = (0.6 - 0.4)/2 = 0.1
    assert abs(row["paper"]["edge_real"] - 0.1) < 1e-9
