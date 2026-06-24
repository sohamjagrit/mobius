"""App-level configuration: where user data lives.

Profiles and tailored outputs stay in the repo under profiles/ and tailored/
(both gitignored). Code lives alongside in services/, pages/, app.py.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parent
PROFILES = ROOT / "profiles"
TAILORED = ROOT / "tailored"

DELTA  = TAILORED / "delta"   # Stage 2 tailoring delta JSON
RESUME = TAILORED / "resume"  # merged renderable resume JSON
TEX    = TAILORED / "tex"
PDF    = TAILORED / "pdf"
JD     = TAILORED / "jd"
META   = TAILORED / "meta"
APPLICATIONS = TAILORED / "applications"

LAST_FILE = PROFILES / ".last"
ROLES_FILE = PROFILES / "roles.json"  # registry of role resumes + shared budget


def ensure_dirs() -> None:
    for d in (PROFILES, DELTA, RESUME, TEX, PDF, JD, META, APPLICATIONS):
        d.mkdir(parents=True, exist_ok=True)


def profile_path(file_hash: str) -> Path:
    return PROFILES / f"{file_hash}.json"


def settings_path(file_hash: str) -> Path:
    return PROFILES / f"{file_hash}.settings.json"


def docling_path(file_hash: str) -> Path:
    return PROFILES / f"{file_hash}.docling.md"


def run_paths(run_id: str) -> dict[str, Path]:
    """All artifact paths for one tailoring run, keyed by type."""
    return {
        "delta":  DELTA  / f"{run_id}.json",
        "resume": RESUME / f"{run_id}.json",
        "tex":    TEX    / f"{run_id}.tex",
        "pdf":    PDF    / f"{run_id}.pdf",
        "jd":     JD     / f"{run_id}.txt",
        "meta":   META   / f"{run_id}.json",
    }
