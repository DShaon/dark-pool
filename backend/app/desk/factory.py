"""Build desk services from config/models.yaml + Settings (config over code).

Only providers whose key is actually present in settings are registered, so a
missing key degrades that provider instead of crashing startup. If the Quick
Read seat's provider has no key, the service is None and the API reports 503
for /quickread — everything else keeps working (NFR-3).
"""

from pathlib import Path

import yaml

from app.config import Settings
from app.core.llm import LLMGateway, ProviderConfig
from app.desk.analysts import AnalystPanel, Seat
from app.desk.quick_read import QuickReadConfig, QuickReadService

# Mandate → prompt filename (RISK OFFICER's file keeps its fuller name).
_ANALYST_PROMPTS = {
    "trend": "trend.md",
    "contrarian": "contrarian.md",
    "derivatives": "derivatives.md",
    "risk": "risk_officer.md",
}


def _make_service(
    gateway: LLMGateway, prompts_dir: str, prompt_file: str, seat_cfg: dict, defaults: dict
) -> QuickReadService:
    prompt_path = Path(prompts_dir) / prompt_file
    return QuickReadService(
        gateway=gateway,
        config=QuickReadConfig(
            provider=seat_cfg["provider"],
            model=seat_cfg["model"],
            temperature=float(seat_cfg.get("temperature", defaults.get("temperature", 0.3))),
            max_tokens=int(seat_cfg.get("max_tokens", defaults.get("max_tokens", 1200))),
            json_mode=bool(seat_cfg.get("json_mode", defaults.get("json_mode", True))),
        ),
        prompt=prompt_path.read_text(encoding="utf-8"),
    )


def build_desk(
    settings: Settings,
) -> tuple[LLMGateway | None, QuickReadService | None, AnalystPanel | None]:
    cfg_path = Path(settings.models_config_path)
    if not cfg_path.exists():
        return None, None, None
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

    providers: dict[str, ProviderConfig] = {}
    for name, p in (raw.get("providers") or {}).items():
        key = getattr(settings, p["key_setting"], None)
        if key:
            providers[name] = ProviderConfig(name=name, base_url=p["base_url"], api_key=key)
    if not providers:
        return None, None, None
    gateway = LLMGateway(providers)

    # ── Quick Read (tier 1) ──
    qr = raw.get("quick_read") or {}
    service: QuickReadService | None = None
    if qr.get("provider") in providers:
        service = _make_service(gateway, settings.prompts_dir, "quick_read.md", qr, {})

    # ── Full Desk analyst panel (tier 2) — only seats whose provider has a key
    #    and whose prompt file exists are registered; the rest simply don't run. ──
    an = raw.get("analysts") or {}
    defaults = an.get("defaults") or {}
    seats: list[Seat] = []
    for mandate, prompt_file in _ANALYST_PROMPTS.items():
        seat_cfg = (an.get("seats") or {}).get(mandate)
        if not seat_cfg or seat_cfg.get("provider") not in providers:
            continue
        if not (Path(settings.prompts_dir) / prompt_file).exists():
            continue
        seats.append(
            Seat(
                mandate=mandate,  # type: ignore[arg-type]
                service=_make_service(gateway, settings.prompts_dir, prompt_file, seat_cfg, defaults),
            )
        )
    panel = AnalystPanel(seats, min_survivors=int(an.get("min_survivors", 3))) if seats else None

    return gateway, service, panel
