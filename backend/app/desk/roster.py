"""User-managed model roster (ADR-0016) — runtime providers + role assignments.

File-backed (`backend/data/roster.json`, gitignored, atomic writes — same
pattern as `monitor/state.py`). It OVERLAYS `config/models.yaml`: the shipped
YAML is the default, anything here wins. Deleting an entry falls back to YAML.

Key security (invariant 4): API keys live ONLY in this gitignored file. They
are never returned to the browser in full (`masked()` gives `····last4`), never
logged, never placed in YAML. The store is the single writer.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Literal

Role = Literal[
    "quick_read", "trend", "contrarian", "derivatives", "risk", "cio", "scenario"
]
ALLOWED_ROLES: tuple[str, ...] = (
    "quick_read", "trend", "contrarian", "derivatives", "risk", "cio", "scenario",
)

_PROVIDER_RE = re.compile(r"^[a-z0-9_-]{2,32}$")


def mask_key(key: str) -> str:
    """`sk-or-v1-…abcd` -> `····abcd`. Never reveals more than the last 4."""
    if not key:
        return ""
    tail = key[-4:] if len(key) >= 4 else key
    return f"····{tail}"


def _atomic_write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


class RosterStore:
    """`{providers: {name: {base_url, api_key}}, roles: {role: {provider, model,
    temperature?, max_tokens?}}}`. All mutations validate before writing."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    # ── read ──
    def _load(self) -> dict:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {"providers": {}, "roles": {}}
        if not isinstance(data, dict):
            return {"providers": {}, "roles": {}}
        data.setdefault("providers", {})
        data.setdefault("roles", {})
        return data

    def raw(self) -> dict:
        """The full roster INCLUDING keys — server-side use only (build_desk)."""
        return self._load()

    def providers(self) -> dict[str, dict]:
        return self._load()["providers"]

    def roles(self) -> dict[str, dict]:
        return self._load()["roles"]

    def masked_view(self) -> dict:
        """Browser-safe: keys replaced by `····last4`."""
        data = self._load()
        return {
            "providers": {
                name: {"base_url": p.get("base_url", ""), "api_key": mask_key(p.get("api_key", ""))}
                for name, p in data["providers"].items()
            },
            "roles": data["roles"],
        }

    # ── write ──
    def set_provider(self, name: str, base_url: str, api_key: str) -> None:
        name = name.strip().lower()
        if not _PROVIDER_RE.match(name):
            raise ValueError("provider name must be 2–32 chars: a–z, 0–9, _ or -")
        base_url = base_url.strip().rstrip("/")
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        if not api_key or not api_key.strip():
            raise ValueError("api_key is required")
        data = self._load()
        data["providers"][name] = {"base_url": base_url, "api_key": api_key.strip()}
        _atomic_write_json(self._path, data)

    def delete_provider(self, name: str) -> None:
        data = self._load()
        used_by = [r for r, c in data["roles"].items() if c.get("provider") == name]
        if used_by:
            raise ValueError(
                f"provider {name!r} is in use by role(s): {', '.join(used_by)} — "
                "reassign those roles first"
            )
        data["providers"].pop(name, None)
        _atomic_write_json(self._path, data)

    def set_role(
        self,
        role: str,
        provider: str,
        model: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> None:
        if role not in ALLOWED_ROLES:
            raise ValueError(f"unknown role {role!r}; one of {', '.join(ALLOWED_ROLES)}")
        if not model or not model.strip():
            raise ValueError("model is required")
        cfg: dict = {"provider": provider, "model": model.strip()}
        if temperature is not None:
            cfg["temperature"] = float(temperature)
        if max_tokens is not None:
            cfg["max_tokens"] = int(max_tokens)
        data = self._load()
        data["roles"][role] = cfg
        _atomic_write_json(self._path, data)

    def delete_role(self, role: str) -> None:
        data = self._load()
        data["roles"].pop(role, None)
        _atomic_write_json(self._path, data)


__all__ = ["RosterStore", "Role", "ALLOWED_ROLES", "mask_key"]
