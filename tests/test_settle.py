from honest_backtest import fee_per_share, won_buy


def test_won_buy():
    # buying YES wins iff resolved Yes; buying NO wins iff resolved No.
    assert won_buy(True, "Yes") is True
    assert won_buy(True, "No") is False
    assert won_buy(False, "No") is True
    assert won_buy(False, "Yes") is False


def test_fee_taker_is_rate_times_p_times_1mp():
    # PM taker fee = fee_rate * p * (1-p) per share.
    assert abs(fee_per_share(0.5, fee_rate=0.07) - 0.07 * 0.25) < 1e-12
    assert abs(fee_per_share(0.1, fee_rate=0.07) - 0.07 * 0.1 * 0.9) < 1e-12


def test_fee_maker_and_zero_are_free():
    assert fee_per_share(0.5, is_maker=True) == 0.0
    assert fee_per_share(0.5, model="zero") == 0.0


def test_fee_default_rate():
    # default fee_rate falls back to 0.07
    assert abs(fee_per_share(0.5, fee_rate=None) - 0.07 * 0.25) < 1e-12
