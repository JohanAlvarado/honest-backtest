import math

from honest_backtest import adverse_score, classify_fill, fp_prob_yes, normal_cdf


def test_normal_cdf_known_points():
    assert abs(normal_cdf(0.0) - 0.5) < 1e-9
    assert normal_cdf(5.0) > 0.999
    assert normal_cdf(-5.0) < 0.001


def test_fp_prob_yes_monotonic_in_spot():
    # higher spot above strike → higher P(YES)
    lo = fp_prob_yes(spot=50_010, strike=50_000, drift=0.0, vol=1e-4, tau=60)
    hi = fp_prob_yes(spot=50_100, strike=50_000, drift=0.0, vol=1e-4, tau=60)
    assert hi > lo
    assert 0.0 <= lo <= 1.0 and 0.0 <= hi <= 1.0


def test_fp_prob_yes_degenerate_tau():
    assert fp_prob_yes(50_100, 50_000, 0.0, 1e-4, tau=0) == 1.0
    assert fp_prob_yes(49_900, 50_000, 0.0, 1e-4, tau=0) == 0.0


def test_adverse_score_nonnegative_and_zero_when_no_book_edge():
    feat = {"book_edge": float("nan"), "p_side": 0.5, "tau": 30.0}
    assert adverse_score(feat, buy_yes=False) == 0.0
    feat2 = {"book_edge": 0.1, "p_side": 0.3, "tau": 5.0}
    assert adverse_score(feat2, buy_yes=False) >= 0.0


def test_classify_fill_taxonomy():
    base = {"crossable": True, "persisted": True, "won": True}
    assert classify_fill(base) == "good_fill"
    assert classify_fill({**base, "won": False}) == "adverse_fill"
    assert classify_fill({**base, "persisted": False, "won": True}) == "missed_winner"
    assert classify_fill({**base, "persisted": False, "won": False}) == "good_miss"
    assert classify_fill({**base, "crossable": False}) == "no_signal"
