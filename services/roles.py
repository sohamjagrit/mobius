"""Role resumes: multiple base profiles (e.g. DS, MLE, AIE) sharing one budget.

Each role points to an already-parsed profile (profiles/<hash>.json from Stage 0);
a role is just a named pointer to one of those files. The registry
(profiles/roles.json) tracks the roles, which one is active, and the single
shared page-fit budget that applies to whichever role is active.

The pipeline is unchanged: selecting a role decides which profile gets handed to
Stage 2. apply_delta merges against that same profile, so indexing stays aligned.
"""
from __future__ import annotations

import json
import re

import config


def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")
    return s or "role"


def load_registry() -> dict:
    if config.ROLES_FILE.exists():
        reg = json.loads(config.ROLES_FILE.read_text(encoding="utf-8"))
    else:
        reg = {}
    reg.setdefault("roles", [])
    reg.setdefault("active", None)
    reg.setdefault("shared_settings", None)
    return reg


def save_registry(reg: dict) -> None:
    config.ROLES_FILE.write_text(json.dumps(reg, indent=2), encoding="utf-8")


def list_roles() -> list[dict]:
    return load_registry()["roles"]


def get_role(role_id: str) -> dict | None:
    return next((r for r in list_roles() if r["id"] == role_id), None)


def active_role(reg: dict | None = None) -> dict | None:
    reg = reg or load_registry()
    return next((r for r in reg["roles"] if r["id"] == reg.get("active")), None)


def _unique_id(base: str, roles: list[dict]) -> str:
    ids = {r["id"] for r in roles}
    rid, n = base, 2
    while rid in ids:
        rid, n = f"{base}_{n}", n + 1
    return rid


def add_role(name: str, file_hash: str, make_active: bool = True) -> dict:
    """Register a parsed resume as a role. Dedupes by file hash; re-adding an
    existing file keeps its current name (rename explicitly to change it)."""
    reg = load_registry()
    role = next((r for r in reg["roles"] if r["hash"] == file_hash), None)
    if role is None:
        role = {"id": _unique_id(_slug(name), reg["roles"]), "name": name or "Resume", "hash": file_hash}
        reg["roles"].append(role)
    if make_active or reg.get("active") is None:
        reg["active"] = role["id"]
    save_registry(reg)
    return role


def rename_role(role_id: str, new_name: str) -> None:
    reg = load_registry()
    for r in reg["roles"]:
        if r["id"] == role_id:
            r["name"] = new_name.strip() or r["name"]
    save_registry(reg)


def remove_role(role_id: str) -> None:
    reg = load_registry()
    reg["roles"] = [r for r in reg["roles"] if r["id"] != role_id]
    if reg.get("active") == role_id:
        reg["active"] = reg["roles"][0]["id"] if reg["roles"] else None
    save_registry(reg)


def set_active(role_id: str) -> None:
    reg = load_registry()
    if any(r["id"] == role_id for r in reg["roles"]):
        reg["active"] = role_id
        save_registry(reg)


def get_settings() -> dict | None:
    return load_registry().get("shared_settings")


def save_settings(settings: dict) -> None:
    reg = load_registry()
    reg["shared_settings"] = settings
    save_registry(reg)


def role_profile(role: dict) -> dict | None:
    p = config.profile_path(role["hash"])
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def migrate_if_needed() -> None:
    """Seed the registry from a pre-roles single-profile setup so existing users
    keep their resume + settings. Runs once; no-op if a registry already exists."""
    if config.ROLES_FILE.exists():
        return
    last = config.LAST_FILE.read_text(encoding="utf-8").strip() if config.LAST_FILE.exists() else ""
    if not last or not config.profile_path(last).exists():
        return
    sp = config.settings_path(last)
    reg = {
        "roles": [{"id": "default", "name": "Default", "hash": last}],
        "active": "default",
        "shared_settings": json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else None,
    }
    save_registry(reg)
