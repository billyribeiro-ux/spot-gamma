"""Contract-level GEX math with hand-computable values."""
from datetime import date, datetime

from spotgamma.gex import aggregate_by_strike, contract_gex, net_gex
from spotgamma.models import ChainSnapshot, OptionContract, OptionType


def _snap(contracts):
    return ChainSnapshot(
        symbol="SPX",
        spot=100.0,
        timestamp=datetime(2026, 5, 29, 15, 0, 0),
        contracts=contracts,
    )


def test_contract_gex_formula_and_sign():
    # GEX = gamma * OI * multiplier(100) * spot^2 * 0.01
    #     = 0.01 * 1000 * 100 * 100^2 * 0.01 = 100_000
    call = OptionContract(option_type=OptionType.CALL, strike=100, expiration=date(2026, 6, 30), open_interest=1000, gamma=0.01)
    snap = _snap([call])
    assert contract_gex(call, snap) == 100_000.0  # calls positive

    put = call.model_copy(update={"option_type": OptionType.PUT})
    assert contract_gex(put, snap) == -100_000.0  # puts negative


def test_net_gex_cancels_equal_call_put():
    exp = date(2026, 6, 30)
    call = OptionContract(option_type=OptionType.CALL, strike=100, expiration=exp, open_interest=500, gamma=0.02)
    put = OptionContract(option_type=OptionType.PUT, strike=100, expiration=exp, open_interest=500, gamma=0.02)
    assert net_gex(_snap([call, put])) == 0.0


def test_aggregate_by_strike_buckets():
    exp = date(2026, 6, 30)
    contracts = [
        OptionContract(option_type=OptionType.CALL, strike=110, expiration=exp, open_interest=1000, gamma=0.01),
        OptionContract(option_type=OptionType.PUT, strike=90, expiration=exp, open_interest=2000, gamma=0.01),
    ]
    by_strike = aggregate_by_strike(_snap(contracts))
    strikes = {s.strike: s for s in by_strike}
    assert strikes[110].call_gex > 0 and strikes[110].put_gex == 0
    assert strikes[90].put_gex < 0 and strikes[90].call_gex == 0
    # put OI is 2x the call OI -> net is negative overall
    assert net_gex(_snap(contracts)) < 0


def test_source_gamma_used_at_snapshot_spot_only():
    # At a different spot, source gamma is ignored and BS is recomputed.
    exp = date(2026, 6, 30)
    c = OptionContract(option_type=OptionType.CALL, strike=100, expiration=exp, open_interest=1000, gamma=0.01, implied_volatility=0.2)
    snap = _snap([c])
    at_spot = contract_gex(c, snap, snap.spot)
    shifted = contract_gex(c, snap, snap.spot * 1.05)
    assert at_spot == 100_000.0
    assert shifted != at_spot  # recomputed via Black-Scholes
