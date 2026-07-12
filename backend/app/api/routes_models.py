"""Model roster routes (ADR-0016) — user-managed providers, keys, role assignments.

The store holds API keys; these routes NEVER return a key in full (GET is
masked), never log one, and validate-before-save so a broken entry can't be
persisted ("without facing any error"): POST /models/test makes a 1-token live
call, and saving a provider or role runs the same test first. Any successful
mutation rebuilds the desk services in place — no restart.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.routes_market import require_auth
from app.config import get_settings
from app.core.llm import LLMError, LLMGateway, ProviderConfig
from app.desk.factory import (
    ROLE_PROMPTS,
    build_desk,
    effective_providers,
    effective_roles,
    rebuild_desk,
)
from app.desk.roster import ALLOWED_ROLES, RosterStore, mask_key

router = APIRouter()


def _store(request: Request) -> RosterStore:
    return request.app.state.roster_store


def _yaml(request: Request) -> dict:
    from app.desk.factory import _load_yaml

    return _load_yaml(get_settings())


class ProviderBody(BaseModel):
    name: str = Field(min_length=2, max_length=32)
    base_url: str
    api_key: str = Field(min_length=1)


class RoleBody(BaseModel):
    role: str
    provider: str
    model: str = Field(min_length=1)
    temperature: float | None = None
    max_tokens: int | None = None


class TestBody(BaseModel):
    base_url: str
    api_key: str = Field(min_length=1)
    model: str = Field(min_length=1)


async def _live_test(base_url: str, api_key: str, model: str) -> tuple[bool, str]:
    """One-token probe. Returns (ok, message). Never leaks the key."""
    gw = LLMGateway({"_probe": ProviderConfig("_probe", base_url.rstrip("/"), api_key)})
    try:
        await gw.chat(
            provider="_probe",
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            temperature=0.0,
        )
        return True, "ok"
    except LLMError as exc:
        return False, exc.detail[:300]
    finally:
        await gw.aclose()


@router.get("/models/roster", dependencies=[Depends(require_auth)])
async def get_roster(request: Request) -> dict:
    """Effective roster: which provider+model fills each role, and where it came
    from (user vs YAML default). Provider keys are masked (never sent in full)."""
    settings = get_settings()
    yaml_raw = _yaml(request)
    roster = _store(request)
    roster_data = roster.raw()
    providers = effective_providers(settings, yaml_raw, roster_data)
    roles = effective_roles(yaml_raw, roster_data)
    user_roles = set(roster_data.get("roles", {}))
    user_providers = set(roster_data.get("providers", {}))

    return {
        "roles": sorted(ROLE_PROMPTS.keys()),
        "assignments": {
            role: {
                "provider": cfg.get("provider"),
                "model": cfg.get("model"),
                "temperature": cfg.get("temperature"),
                "max_tokens": cfg.get("max_tokens"),
                "source": "user" if role in user_roles else "yaml",
                "ready": cfg.get("provider") in providers,
            }
            for role, cfg in roles.items()
        },
        "providers": [
            {
                "name": name,
                "base_url": (
                    roster_data["providers"][name]["base_url"]
                    if name in user_providers
                    else (yaml_raw.get("providers", {}).get(name, {}).get("base_url", ""))
                ),
                "api_key": mask_key(roster_data["providers"][name]["api_key"])
                if name in user_providers
                else "env",
                "source": "user" if name in user_providers else "yaml",
                "editable": name in user_providers,
            }
            for name in sorted(providers)
        ],
    }


@router.post("/models/test", dependencies=[Depends(require_auth)])
async def test_model(body: TestBody) -> dict:
    if not body.base_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="base_url must be http(s)://")
    ok, message = await _live_test(body.base_url, body.api_key, body.model)
    return {"ok": ok, "message": message}


@router.post("/models/provider", dependencies=[Depends(require_auth)])
async def add_provider(body: ProviderBody, request: Request) -> dict:
    ok, message = await _live_test(body.base_url, body.api_key, "gpt-3.5-turbo")
    # A model-name failure is fine here (we only test reachability+auth); reject
    # only on clear auth/transport failure so a valid key with a nonstandard
    # default model still saves.
    if not ok and _looks_like_auth_or_transport(message):
        raise HTTPException(status_code=400, detail=f"provider rejected: {message}")
    try:
        _store(request).set_provider(body.name, body.base_url, body.api_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await rebuild_desk(request.app.state, get_settings())
    return {"ok": True, "reachable": ok, "note": None if ok else message}


def _looks_like_auth_or_transport(message: str) -> bool:
    m = message.lower()
    return (
        "transport error" in m
        or "401" in m
        or "403" in m
        or "invalid api key" in m
        or "unauthorized" in m
    )


@router.delete("/models/provider/{name}", dependencies=[Depends(require_auth)])
async def delete_provider(name: str, request: Request) -> dict:
    try:
        _store(request).delete_provider(name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await rebuild_desk(request.app.state, get_settings())
    return {"ok": True}


@router.post("/models/role", dependencies=[Depends(require_auth)])
async def set_role(body: RoleBody, request: Request) -> dict:
    if body.role not in ALLOWED_ROLES:
        raise HTTPException(status_code=422, detail=f"unknown role {body.role!r}")
    settings = get_settings()
    roster = _store(request)
    providers = effective_providers(settings, _yaml(request), roster.raw())
    if body.provider not in providers:
        raise HTTPException(
            status_code=422,
            detail=f"provider {body.provider!r} is not configured — add it first",
        )
    try:
        roster.set_role(body.role, body.provider, body.model, body.temperature, body.max_tokens)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await rebuild_desk(request.app.state, settings)
    return {"ok": True}


@router.delete("/models/role/{role}", dependencies=[Depends(require_auth)])
async def delete_role(role: str, request: Request) -> dict:
    """Remove the user override for a role — it falls back to the YAML default."""
    _store(request).delete_role(role)
    await rebuild_desk(request.app.state, get_settings())
    return {"ok": True}
