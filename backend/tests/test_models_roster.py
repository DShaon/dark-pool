"""Roster store + /models routes (ADR-0016) — no network (live test mocked).

Verifies: keys are masked on read and never leak; YAML defaults overlay
correctly (roster wins); a provider in use can't be deleted; validation
rejects bad input; role assignment requires a configured provider.
"""

import pytest
from fastapi.testclient import TestClient

from app.desk import factory
from app.desk.factory import effective_providers, effective_roles
from app.desk.roster import RosterStore, mask_key
from app.main import create_app

YAML = {
    "providers": {"groq": {"base_url": "https://groq.test/v1", "key_setting": "groq_api_key"}},
    "quick_read": {"provider": "groq", "model": "llama-3.3-70b"},
    "analysts": {
        "min_survivors": 3,
        "defaults": {"temperature": 0.4, "max_tokens": 1100},
        "seats": {
            "trend": {"provider": "groq", "model": "llama-3.3-70b"},
            "risk": {"provider": "groq", "model": "llama-3.3-70b"},
        },
    },
    "cio": {"provider": "groq", "model": "llama-3.3-70b", "temperature": 0.2},
}


class FakeSettings:
    groq_api_key = "gsk_secret_key_1234"


# ── store ──


def test_mask_never_reveals_more_than_last_four():
    assert mask_key("sk-or-v1-abcdef1234") == "····1234"
    assert mask_key("xy") == "····xy"
    assert mask_key("") == ""


def test_store_roundtrip_and_masking(tmp_path):
    store = RosterStore(tmp_path / "roster.json")
    store.set_provider("deepseek", "https://api.deepseek.com/v1/", "sk-deep-9999")
    assert store.providers()["deepseek"]["base_url"] == "https://api.deepseek.com/v1"  # trailing / stripped
    assert store.raw()["providers"]["deepseek"]["api_key"] == "sk-deep-9999"  # full key server-side
    masked = store.masked_view()
    assert masked["providers"]["deepseek"]["api_key"] == "····9999"  # never full to the browser


def test_store_validation(tmp_path):
    store = RosterStore(tmp_path / "roster.json")
    with pytest.raises(ValueError):
        store.set_provider("BAD NAME", "https://x.test", "k")
    with pytest.raises(ValueError):
        store.set_provider("ok", "ftp://x.test", "k")  # not http(s)
    with pytest.raises(ValueError):
        store.set_provider("ok", "https://x.test", "  ")  # empty key
    with pytest.raises(ValueError):
        store.set_role("not_a_role", "groq", "m")


def test_delete_provider_refused_when_a_role_uses_it(tmp_path):
    store = RosterStore(tmp_path / "roster.json")
    store.set_provider("deepseek", "https://api.deepseek.com/v1", "sk-1")
    store.set_role("cio", "deepseek", "deepseek-chat")
    with pytest.raises(ValueError, match="in use"):
        store.delete_provider("deepseek")
    store.delete_role("cio")
    store.delete_provider("deepseek")  # now allowed
    assert "deepseek" not in store.providers()


# ── effective overlay ──


def test_effective_providers_roster_overrides_yaml(tmp_path):
    roster = {"providers": {"groq": {"base_url": "https://override.test", "api_key": "roster-key"}}}
    provs = effective_providers(FakeSettings(), YAML, roster)
    assert provs["groq"].api_key == "roster-key"  # roster wins
    assert provs["groq"].base_url == "https://override.test"


def test_effective_providers_env_key_when_no_roster():
    provs = effective_providers(FakeSettings(), YAML, {})
    assert provs["groq"].api_key == "gsk_secret_key_1234"  # from env/settings


def test_effective_roles_overlay_and_defaults():
    roster = {"roles": {"cio": {"provider": "deepseek", "model": "deepseek-chat"}}}
    roles = effective_roles(YAML, roster)
    assert roles["trend"]["temperature"] == 0.4  # analyst default merged in
    assert roles["cio"]["provider"] == "deepseek"  # roster override
    assert roles["quick_read"]["model"] == "llama-3.3-70b"  # yaml default kept


# ── routes ──


@pytest.fixture
def client(tmp_path, monkeypatch):
    app = create_app()

    async def fake_test(base_url, api_key, model):
        return True, "ok"

    async def fake_rebuild(app_state, settings):
        return None

    monkeypatch.setattr("app.api.routes_models._live_test", fake_test)
    monkeypatch.setattr("app.api.routes_models.rebuild_desk", fake_rebuild)
    with TestClient(app) as c:
        app.state.roster_store = RosterStore(tmp_path / "roster.json")
        yield c


def test_add_provider_then_roster_shows_it_masked(client):
    r = client.post(
        "/models/provider",
        json={"name": "deepseek", "base_url": "https://api.deepseek.com/v1", "api_key": "sk-deep-abcd"},
    )
    assert r.status_code == 200 and r.json()["ok"] is True

    roster = client.get("/models/roster").json()
    ds = next(p for p in roster["providers"] if p["name"] == "deepseek")
    assert ds["api_key"] == "····abcd"  # masked, never full
    assert ds["editable"] is True


def test_assign_role_requires_configured_provider(client):
    # unknown provider is rejected
    r = client.post("/models/role", json={"role": "cio", "provider": "ghost", "model": "x"})
    assert r.status_code == 422

    client.post(
        "/models/provider",
        json={"name": "deepseek", "base_url": "https://api.deepseek.com/v1", "api_key": "sk-1"},
    )
    ok = client.post("/models/role", json={"role": "cio", "provider": "deepseek", "model": "deepseek-chat"})
    assert ok.status_code == 200
    roster = client.get("/models/roster").json()
    assert roster["assignments"]["cio"]["source"] == "user"
    assert roster["assignments"]["cio"]["provider"] == "deepseek"


def test_delete_provider_in_use_conflicts(client):
    client.post(
        "/models/provider",
        json={"name": "deepseek", "base_url": "https://api.deepseek.com/v1", "api_key": "sk-1"},
    )
    client.post("/models/role", json={"role": "cio", "provider": "deepseek", "model": "deepseek-chat"})
    r = client.delete("/models/provider/deepseek")
    assert r.status_code == 409  # in use
    client.delete("/models/role/cio")
    assert client.delete("/models/provider/deepseek").status_code == 200


def test_test_endpoint_reports_result(client):
    r = client.post(
        "/models/test",
        json={"base_url": "https://api.deepseek.com/v1", "api_key": "sk-1", "model": "deepseek-chat"},
    )
    assert r.status_code == 200 and r.json() == {"ok": True, "message": "ok"}
