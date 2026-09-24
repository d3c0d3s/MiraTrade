import math
from datetime import date

import pandas as pd

from mirabot.config import OptionParams
from mirabot.options_trades import (bs_delta, bs_price, monthly_expiry, option_contract,
                                    simulate_option, strike_for_delta)


def test_put_call_parity():
    s, k, t, r, v = 100, 95, 0.25, 0.04, 0.3
    assert math.isclose(bs_price(s, k, t, r, v, "C") - bs_price(s, k, t, r, v, "P"),
                        s - k * math.exp(-r * t), abs_tol=1e-9)


def test_strike_hits_target_delta_on_listed_grid():
    k = strike_for_delta(180, 45 / 365, 0.04, 0.35, 0.65)
    assert k % 2.5 == 0 and k < 180                      # in the money call
    assert abs(bs_delta(180, k, 45 / 365, 0.04, 0.35) - 0.65) < 0.05


def test_monthly_expiry_is_third_friday_near_target():
    exp = monthly_expiry(date(2026, 9, 24), 45, 30)
    assert exp == date(2026, 11, 20) and exp.weekday() == 4


def _trade(exit_px, reason, days):
    entry = pd.Timestamp("2026-08-03")
    return {"entry_date": entry, "exit_date": entry + pd.Timedelta(days=days),
            "entry": 100.0, "stop": 97.0, "target": 106.0, "exit": exit_px, "exit_reason": reason}


def test_simulated_call_follows_the_stock():
    p = OptionParams()
    win = simulate_option(_trade(106.0, "target", 6), 0.30, p)
    loss = simulate_option(_trade(97.0, "stop", 1), 0.30, p)
    assert win["opt_ret"] > 0.2 and win["opt_r"] > 1       # leverage on a 2R stock move
    assert loss["opt_ret"] < 0 and -1.3 < loss["opt_r"] < -0.9  # about -1R at the stop
    flat = simulate_option(_trade(100.0, "time", 21), 0.30, p)
    assert flat["opt_ret"] < 0                               # spread + theta cost a flat trade


def test_contract_pricing_includes_spread():
    c = option_contract(50.0, date(2026, 9, 24), 0.4, OptionParams())
    assert c["ask"] > c["mid"] > 0 and c["strike"] % 1.0 == 0
