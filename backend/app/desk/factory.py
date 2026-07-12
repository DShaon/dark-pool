"""Build desk services from config/models.yaml + the user roster (ADR-0004/0016).

`config/models.yaml` is the shipped DEFAULT; the file-backed `RosterStore`
(ADR-0016) OVERLAYS it — a user-added provider or role assignment wins, and
removing it falls back to YAML. Only providers whose key is actually present
(env for YAML providers, inline for roster providers) are registered, so a
missing key degrades that provider instead of crashing startup (NFR-3).

`build_desk` is called at startup AND re-called by the /models routes to
rebuild services in place when the roster changes — no restart required.
"""

from decimal import Decimal
from pathlib import Path

import yaml

from app.config import Settings
from app.core.llm import LLMGateway, ProviderConfig
from app.desk.analysts import AnalystPanel, Seat
from app.desk.cio import CIOSynthesizer
from app.desk.quick_read import QuickReadConfig, QuickReadService
from app.desk.roster import RosterStore
from app.desk.scenario import ScenarioService

# Every model role → its prompt file. The single source of truth shared by the
# builder and the roster routes (role validation, UI role matrix).
ROLE_PROMPTS: dict[str, str] = {
    "quick_read": "quick_read.md",
    "trend": "trend.md",
    "contrarian": "contrarian.md",
    "derivatives": "derivatives.md",
    "risk": "risk_officer.md",
    "cio": "cio_synthesis.md",
    "scenario": "scenario.md",
}
_ANALYST_ROLES = ("trend", "contrarian", "derivatives", "risk")


def _load_yaml(settings: Settings) -> dict:
    cfg_path = Path(settings.models_config_path)
    if not cfg_path.exists():
        return {}
    return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}


def effective_providers(
    settings: Settings, yaml_raw: dict, roster_data: dict
) -> dict[str, ProviderConfig]:
    """YAML providers (keys from env) overlaid by roster providers (inline keys)."""
    providers: dict[str, ProviderConfig] = {}
    for name, p in (yaml_raw.get("providers") or {}).items():
        key = getattr(settings, p.get("key_setting", ""), None)
        if key and p.get("base_url"):
            providers[name] = ProviderConfig(name=name, base_url=p["base_url"], api_key=key)
    for name, p in (roster_data.get("providers") or {}).items():
        if p.get("api_key") and p.get("base_url"):
            providers[name] = ProviderConfig(
                name=name, base_url=p["base_url"], api_key=p["api_key"]
            )
    return providers


def effective_roles(yaml_raw: dict, roster_data: dict) -> dict[str, dict]:
    """Role → resolved model config, YAML defaults overlaid by roster roles."""
    roles: dict[str, dict] = {}
    if yaml_raw.get("quick_read"):
        roles["quick_read"] = dict(yaml_raw["quick_read"])
    an = yaml_raw.get("analysts") or {}
    defaults = an.get("defaults") or {}
    for mandate in _ANALYST_ROLES:
        seat = (an.get("seats") or {}).get(mandate)
        if seat:
            roles[mandate] = {**defaults, **seat}
    for extra in ("cio", "scenario"):
        if yaml_raw.get(extra):
            roles[extra] = dict(yaml_raw[extra])
    for role, cfg in (roster_data.get("roles") or {}).items():
        roles[role] = {**roles.get(role, {}), **cfg}
    return roles


def _qr_config(role_cfg: dict, default_max: int = 1200) -> QuickReadConfig:
    return QuickReadConfig(
        provider=role_cfg["provider"],
        model=role_cfg["model"],
        temperature=float(role_cfg.get("temperature", 0.3)),
        max_tokens=int(role_cfg.get("max_tokens", default_max)),
        json_mode=bool(role_cfg.get("json_mode", True)),
    )


def _service_for(
    gateway: LLMGateway,
    settings: Settings,
    role: str,
    role_cfg: dict,
    providers: dict[str, ProviderConfig],
) -> QuickReadService | None:
    """A QuickReadService for a role, or None if its provider/prompt is missing."""
    if role_cfg.get("provider") not in providers:
        return None
    prompt_path = Path(settings.prompts_dir) / ROLE_PROMPTS[role]
    if not prompt_path.exists():
        return None
    return QuickReadService(
        gateway=gateway,
        config=_qr_config(role_cfg),
        prompt=prompt_path.read_text(encoding="utf-8"),
    )


def build_desk(
    settings: Settings,
) -> tuple[
    LLMGateway | None,
    QuickReadService | None,
    AnalystPanel | None,
    CIOSynthesizer | None,
    ScenarioService | None,
]:
    yaml_raw = _load_yaml(settings)
    roster_data = RosterStore(Path(settings.roster_config_path)).raw()
    providers = effective_providers(settings, yaml_raw, roster_data)
    if not providers:
        return None, None, None, None, None
    gateway = LLMGateway(providers)
    roles = effective_roles(yaml_raw, roster_data)

    # ── Quick Read (tier 1) ──
    service: QuickReadService | None = None
    if "quick_read" in roles:
        service = _service_for(gateway, settings, "quick_read", roles["quick_read"], providers)

    # ── Full Desk analyst panel (tier 2) ──
    an = yaml_raw.get("analysts") or {}
    seats: list[Seat] = []
    for mandate in _ANALYST_ROLES:
        if mandate not in roles:
            continue
        seat_service = _service_for(gateway, settings, mandate, roles[mandate], providers)
        if seat_service is not None:
            seats.append(Seat(mandate=mandate, service=seat_service))  # type: ignore[arg-type]
    panel = AnalystPanel(seats, min_survivors=int(an.get("min_survivors", 3))) if seats else None

    # ── CIO synthesis (ADR-0006/0015) ──
    cio: CIOSynthesizer | None = None
    cio_cfg = roles.get("cio")
    cio_prompt = Path(settings.prompts_dir) / ROLE_PROMPTS["cio"]
    if cio_cfg and cio_cfg.get("provider") in providers and cio_prompt.exists():
        cio = CIOSynthesizer(
            gateway=gateway,
            config=_qr_config(cio_cfg, default_max=1600),
            prompt=cio_prompt.read_text(encoding="utf-8"),
            risk_pct=Decimal(str(settings.risk_pct_per_trade)),
            max_position_pct=Decimal(str(settings.max_position_pct)),
        )

    # ── Scenario path (ADR-0017 §2) ──
    scenario: ScenarioService | None = None
    scen_cfg = roles.get("scenario")
    scen_prompt = Path(settings.prompts_dir) / ROLE_PROMPTS["scenario"]
    if scen_cfg and scen_cfg.get("provider") in providers and scen_prompt.exists():
        scenario = ScenarioService(
            gateway=gateway,
            config=_qr_config(scen_cfg, default_max=900),
            prompt=scen_prompt.read_text(encoding="utf-8"),
        )

    return gateway, service, panel, cio, scenario


async def rebuild_desk(app_state, settings: Settings) -> None:
    """Rebuild all desk services in place after a roster change and close the
    old gateway's client. Routes read `app.state.*` fresh each request, so the
    swap takes effect immediately — no restart."""
    old_gateway: LLMGateway | None = getattr(app_state, "llm_gateway", None)
    (
        app_state.llm_gateway,
        app_state.quick_read,
        app_state.analyst_panel,
        app_state.cio,
        app_state.scenario,
    ) = build_desk(settings)
    if old_gateway is not None:
        import contextlib

        with contextlib.suppress(Exception):
            await old_gateway.aclose()
