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
