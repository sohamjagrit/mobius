"""Tailoring run history.

Each run is identified by `{date}_{slug}` and stored under tailored/ with one
folder per file type (delta/, resume/, tex/, pdf/, audit/, jd/, meta/).
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import config


def _run_id(slug: str) -> str:
    return f"{date.today().isoformat()}_{slug or 'jd'}"


def save_run(
    slug: str,
    jd_text: str,
    delta: dict,
    renderable: dict,
    latex: str,
    pdf_bytes: bytes | None,
    usages: list,
    role_resume: str = "",
) -> str:
    """Persist one run. Same slug on the same day overwrites the prior save."""
    run_id = _run_id(slug)
    paths = config.run_paths(run_id)

    paths["jd"].write_text(jd_text or "", encoding="utf-8")
    paths["delta"].write_text(json.dumps(delta, indent=2), encoding="utf-8")
    paths["resume"].write_text(json.dumps(renderable, indent=2), encoding="utf-8")
    paths["tex"].write_text(latex or "", encoding="utf-8")
    if pdf_bytes:
        paths["pdf"].write_bytes(pdf_bytes)

    meta = {
        "slug": slug,
        "name": run_id,
        "date": date.today().isoformat(),
        "role": delta.get("target_role", ""),
        "role_resume": role_resume,
        "cost": round(sum(u.get("cost", 0) for u in (usages or [])), 4),
        "has_pdf": bool(pdf_bytes),
    }
    paths["meta"].write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return run_id


def list_runs() -> list[dict]:
    """Saved runs, newest run_id first."""
    if not config.META.exists():
        return []
    runs = []
    for meta_file in sorted(config.META.glob("*.json"), reverse=True):
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        meta["run_id"] = meta.get("name", meta_file.stem)
        runs.append(meta)
    return runs


def load_run(run_id: str) -> dict:
    """Reload a saved run into the shape the tailor screen expects."""
    paths = config.run_paths(run_id)
    pdf = paths["pdf"]
    meta_path = paths["meta"]
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    return {
        "jd_text": paths["jd"].read_text(encoding="utf-8") if paths["jd"].exists() else "",
        "tailored": json.loads(paths["delta"].read_text(encoding="utf-8")),
        "latex": paths["tex"].read_text(encoding="utf-8") if paths["tex"].exists() else "",
        "pdf_bytes": pdf.read_bytes() if pdf.exists() else None,
        "out_stem": str(paths["tex"].with_suffix("")),
        "run_id": run_id,
        "run_slug": meta.get("slug", run_id),
    }


def load_run_by_slug(slug: str) -> dict | None:
    """Load the most recent run matching a slug."""
    runs = list_runs()
    for run in runs:
        if run.get("slug") == slug:
            return load_run(run["run_id"])
    return None
