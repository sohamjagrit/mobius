"""Job application tracker."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import config


def applications_file() -> Path:
    return config.APPLICATIONS / "applications.json"


def load_applications() -> list[dict]:
    """Load all tracked applications."""
    f = applications_file()
    if not f.exists():
        return []
    return json.loads(f.read_text(encoding="utf-8"))


def save_applications(apps: list[dict]) -> None:
    """Persist applications."""
    config.ensure_dirs()
    applications_file().write_text(json.dumps(apps, indent=2), encoding="utf-8")


def add_application(
    company: str,
    role: str,
    status: str,
    notes: str,
    resume_slug: str,
) -> None:
    """Track a new application."""
    apps = load_applications()
    apps.append({
        "id": f"{company.lower()}_{datetime.now().isoformat()}",
        "company": company,
        "role": role,
        "date_applied": datetime.now().date().isoformat(),
        "status": status,
        "notes": notes,
        "resume_slug": resume_slug,
        "date_created": datetime.now().isoformat(),
        "last_updated": datetime.now().isoformat(),
    })
    save_applications(apps)


def update_application(app_id: str, status: str, notes: str) -> None:
    """Update application status and notes."""
    apps = load_applications()
    for app in apps:
        if app["id"] == app_id:
            app["status"] = status
            app["notes"] = notes
            app["last_updated"] = datetime.now().isoformat()
            break
    save_applications(apps)


def get_application(app_id: str) -> dict | None:
    """Get a single application."""
    for app in load_applications():
        if app["id"] == app_id:
            return app
    return None
