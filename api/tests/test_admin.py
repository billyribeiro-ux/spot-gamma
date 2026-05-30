"""Admin "Connections hub" API tests.

These avoid the network entirely: source listing, credential masking/persistence,
active-source selection, error handling, and the optional admin-token gate. The
module-level config (token, store path) is read at import, so tests that change
it reload ``api.main`` with the patched environment.
"""

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SPOTGAMMA_CONFIG", str(tmp_path / "creds.json"))
    monkeypatch.delenv("SPOTGAMMA_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("SPOTGAMMA_SOURCE", raising=False)
    import api.main as m

    importlib.reload(m)
    return TestClient(m.app)


def test_lists_every_source_with_default_active(client):
    body = client.get("/admin/sources").json()
    assert body["active"] == "sample"
    names = {s["name"] for s in body["sources"]}
    assert {"cboe", "tradier", "schwab", "polygon", "thetadata", "tastytrade", "sample"} == names
    cboe = next(s for s in body["sources"] if s["name"] == "cboe")
    assert cboe["needs_credentials"] is False and cboe["configured"] is True


def test_save_persists_but_never_echoes_secret(client):
    r = client.put("/admin/sources/polygon", json={"credentials": {"api_key": "SUPERSECRET"}})
    assert r.status_code == 200
    poly = next(s for s in client.get("/admin/sources").json()["sources"] if s["name"] == "polygon")
    field = poly["fields"][0]
    assert field["saved"] is True  # we know it's set
    assert field["value"] == ""  # but the value is never returned
    assert poly["configured"] is True
    # and the secret is not present anywhere in the serialized response
    assert "SUPERSECRET" not in r.text


def test_clearing_a_field_with_empty_string(client):
    client.put("/admin/sources/polygon", json={"credentials": {"api_key": "abc"}})
    client.put("/admin/sources/polygon", json={"credentials": {"api_key": ""}})
    poly = next(s for s in client.get("/admin/sources").json()["sources"] if s["name"] == "polygon")
    assert poly["fields"][0]["saved"] is False and poly["configured"] is False


def test_set_active_drives_health_and_levels_default(client):
    assert client.put("/admin/active/cboe").json() == {"active": "cboe"}
    assert client.get("/admin/sources").json()["active"] == "cboe"
    assert client.get("/health").json()["active_source"] == "cboe"


def test_unknown_source_is_404(client):
    assert client.put("/admin/active/nope").status_code == 404
    assert client.post("/admin/sources/nope/test").status_code == 404
    assert client.put("/admin/sources/nope", json={"credentials": {}}).status_code == 404


def test_connection_offline_paths(client):
    # sample needs no network and reports ready
    ok = client.post("/admin/sources/sample/test").json()
    assert ok["ok"] is True and "latency_ms" in ok
    # schwab without a token fails gracefully (no network, clear message)
    bad = client.post("/admin/sources/schwab/test").json()
    assert bad["ok"] is False and "SCHWAB_ACCESS_TOKEN" in bad["message"]


def test_admin_token_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("SPOTGAMMA_CONFIG", str(tmp_path / "creds.json"))
    monkeypatch.setenv("SPOTGAMMA_ADMIN_TOKEN", "s3cret")
    import api.main as m

    importlib.reload(m)
    c = TestClient(m.app)
    try:
        assert c.get("/admin/sources").status_code == 401
        assert c.get("/admin/sources", headers={"X-Admin-Token": "wrong"}).status_code == 401
        assert c.get("/admin/sources", headers={"X-Admin-Token": "s3cret"}).status_code == 200
        # the public levels/health endpoints stay ungated
        assert c.get("/health").status_code == 200
    finally:
        monkeypatch.delenv("SPOTGAMMA_ADMIN_TOKEN", raising=False)
        importlib.reload(m)


def test_thinkscript_endpoint_renders_engine_study(client):
    # The /thinkscript endpoint returns the engine-rendered study (sample source),
    # i.e. the same Phase-4 features as the CLI: cloud, regime bg, alerts.
    r = client.get("/thinkscript/SPX")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    body = r.text
    assert "input callWall" in body and "input hedgeWall" in body
    assert "AddCloud" in body and "AssignBackgroundColor" in body and "Alert(" in body


def test_market_structure_endpoint(client, monkeypatch):
    # Stub the external feeds so the test is network-free; sample source gives gamma.
    from spotgamma.marketstructure import read as ms_read

    class _Q:
        def __init__(self, p):
            self.price = p

    quotes = {"^VIX": 15.3, "^VIX3M": 18.6, "^VVIX": 86.0, "DX-Y.NYB": 98.9}
    series = {"BAMLH0A0HYM2": 2.72, "T10Y2Y": 0.47}

    class _Pt:
        def __init__(self, v):
            self.value = v

    monkeypatch.setattr(ms_read, "fetch_quote", lambda t: _Q(quotes[t]), raising=False)
    # fetch_series/latest are imported inside build_market_structure; patch at source

    def fake_series(sid):
        return [_Pt(series[sid])]

    monkeypatch.setattr("spotgamma.marketstructure.fred.fetch_series", fake_series)
    monkeypatch.setattr("spotgamma.marketstructure.quotes.fetch_quote", lambda t: _Q(quotes[t]))

    resp = client.get("/market-structure?symbol=SPX")
    assert resp.status_code == 200
    body = resp.json()
    assert body["bias"] in {"risk-on", "neutral", "risk-off"}
    assert body["vol_regime"] in {"calm", "normal", "stressed", "crisis"}
    assert -1.5 <= body["regime_score"] <= 1.5
    keys = {s["key"] for s in body["signals"]}
    assert "vix" in keys and "credit" in keys  # core signals present
