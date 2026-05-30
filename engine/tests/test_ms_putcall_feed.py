"""Put/call live-feed wiring (§7): chain-volume parser + rolling-history store.

Network-free. The pure parser is fed a synthetic Yahoo option-chain payload; the
rolling history is exercised against a tmp_path so no real ``instance/`` file is
touched. Mirrors the shapes verified live from Yahoo's options endpoint (the
front block ships with the base request; ``volume`` may be null and is treated
as 0).
"""

from datetime import date

from spotgamma.marketstructure.feeds import (
    _sum_chain_volumes,
    update_put_call_history,
)
from spotgamma.marketstructure.putcall import (
    PutCallStats,
    put_call_proxy,
    put_call_signal,
    zscore,
)


# A synthetic payload matching the live ``optionChain.result[0]`` shape: an
# ``options`` list of expiration blocks, each with ``calls``/``puts`` whose
# entries carry a ``volume`` (sometimes null/missing — Yahoo really does that).
def _synthetic_result() -> dict:
    return {
        "expirationDates": [1_700_000_000, 1_700_600_000, 1_701_200_000],
        "options": [
            {
                "expirationDate": 1_700_000_000,
                "calls": [
                    {"strike": 540.0, "volume": 100},
                    {"strike": 545.0, "volume": None},  # null -> 0
                    {"strike": 550.0},  # missing -> 0
                ],
                "puts": [
                    {"strike": 540.0, "volume": 200},
                    {"strike": 535.0, "volume": 50},
                ],
            }
        ],
    }


# --- pure volume-summing parser --------------------------------------------
def test_sum_chain_volumes_handles_null_and_missing():
    put_vol, call_vol = _sum_chain_volumes(_synthetic_result())
    assert call_vol == 100.0  # 100 + null(0) + missing(0)
    assert put_vol == 250.0  # 200 + 50


def test_sum_chain_volumes_sums_multiple_expiration_blocks():
    result = {
        "options": [
            {"calls": [{"volume": 10}], "puts": [{"volume": 5}]},
            {"calls": [{"volume": 20}], "puts": [{"volume": 7}]},
        ]
    }
    put_vol, call_vol = _sum_chain_volumes(result)
    assert call_vol == 30.0 and put_vol == 12.0


def test_sum_chain_volumes_empty_payload_is_zero():
    assert _sum_chain_volumes({}) == (0.0, 0.0)
    assert _sum_chain_volumes({"options": []}) == (0.0, 0.0)


def test_parser_feeds_proxy_ratio():
    put_vol, call_vol = _sum_chain_volumes(_synthetic_result())
    assert put_call_proxy(put_vol, call_vol) == 2.5  # 250 / 100


# --- rolling-history persistence (append / dedup / zscore) ------------------
def test_history_append_and_dedup_by_date(tmp_path):
    p = tmp_path / "putcall_history.json"
    update_put_call_history(0.9, today=date(2026, 1, 5), path=str(p))
    update_put_call_history(1.0, today=date(2026, 1, 6), path=str(p))
    # same-day write overwrites (dedup by date), not appends a duplicate
    out = update_put_call_history(1.1, today=date(2026, 1, 6), path=str(p))
    assert out == [0.9, 1.1]  # chronological; the 1.0 was replaced by 1.1


def test_history_tolerates_missing_and_corrupt_file(tmp_path):
    p = tmp_path / "sub" / "putcall_history.json"  # parent dir does not exist yet
    out = update_put_call_history(0.8, today=date(2026, 1, 5), path=str(p))
    assert out == [0.8] and p.exists()
    # corrupt the file -> next call starts fresh, does not raise
    p.write_text("{ not valid json")
    out = update_put_call_history(0.7, today=date(2026, 1, 6), path=str(p))
    assert out == [0.7]


def test_history_window_trims_to_trailing(tmp_path):
    p = tmp_path / "putcall_history.json"
    out = []
    for i in range(1, 31):  # 30 distinct days
        out = update_put_call_history(float(i), today=date(2026, 1, i), path=str(p), window=20)
    assert len(out) == 20  # trimmed to the trailing window
    assert out[0] == 11.0 and out[-1] == 30.0  # most recent last


def test_history_then_zscore_is_meaningful(tmp_path):
    p = tmp_path / "putcall_history.json"
    history = []
    for i in range(1, 26):  # 25 obs around ~0.9
        ratio = 0.9 + 0.01 * (i % 5)
        history = update_put_call_history(ratio, today=date(2026, 1, i), path=str(p))
    assert len(history) == 25
    z, pct = zscore(1.3, history)  # well above the ~0.9 cluster
    assert z is not None and z > 0 and pct is not None and pct > 50


# --- signal abstains with insufficient history -----------------------------
def test_signal_abstains_below_20_observations(tmp_path):
    p = tmp_path / "putcall_history.json"
    history = []
    for i in range(1, 11):  # only 10 obs (< 20)
        history = update_put_call_history(0.9, today=date(2026, 1, i), path=str(p))
    z, pct = zscore(0.9, history)
    assert z is None and pct is None  # not enough history to z-score
    sig = put_call_signal(PutCallStats(ratio=0.9, z=z, percentile=pct))
    assert sig.score == 0.0 and "insufficient history" in sig.detail
