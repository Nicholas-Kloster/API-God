"""discovery.discover_independent backend behavior (finding #4): a failed xAI call must read as
not-searched (so a real coin is not penalized for silence that did not happen), while a
successful-but-empty search reads as searched-with-zero."""
import discovery
from conftest import FakeResp


def test_xai_http_error_is_not_searched(fake_http, monkeypatch):
    monkeypatch.setattr(discovery, "XAI_KEY", "k")
    fake_http({"api.x.ai": FakeResp(500, None, raise_json=True)})
    out = discovery.discover_independent("Mint", "owner", "TST")
    assert out["searched"] is False        # transport/HTTP failure != "found nobody"


def test_xai_genuine_empty_is_searched(fake_http, monkeypatch):
    monkeypatch.setattr(discovery, "XAI_KEY", "k")
    fake_http({"api.x.ai": FakeResp(200, {"output": "none", "citations": []})})
    out = discovery.discover_independent("Mint", "owner", "TST")
    assert out["searched"] is True and out["n_ca"] == 0
