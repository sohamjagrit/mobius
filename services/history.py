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
    audit: list,
    usages: list,
) -> str:
    """Persist one run. Same slug on the same day overwrites the prior save."""
    run_id = _run_id(slug)
    paths = config.run_paths(run_id)

    paths["jd"].write_text(jd_text or "", encoding="utf-8")
    paths["delta"].write_text(json.dumps(delta, indent=2), encoding="utf-8")
    paths["resume"].write_text(json.dumps(renderable, indent=2), encoding="utf-8")
    paths["tex"].write_text(latex or "", encoding="utf-8")
    paths["audit"].write_text(json.dumps(audit or [], indent=2), encoding="utf-8")
    if pdf_bytes:
        paths["pdf"].write_bytes(pdf_bytes)

    flagged = sum(1 for r in (audit or []) if not r.get("ok", True))
    meta = {
        "slug": slug,
        "name": run_id,
        "date": date.today().isoformat(),
        "role": delta.get("target_role", ""),
        "cost": round(sum(u.get("cost", 0) for u in (usages or [])), 4),
        "flagged": flagged,
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
    return {
        "jd_text": paths["jd"].read_text(encoding="utf-8") if paths["jd"].exists() else "",
        "tailored": json.loads(paths["delta"].read_text(encoding="utf-8")),
        "latex": paths["tex"].read_text(encoding="utf-8") if paths["tex"].exists() else "",
        "pdf_bytes": pdf.read_bytes() if pdf.exists() else None,
        "audit": json.loads(paths["audit"].read_text(encoding="utf-8")) if paths["audit"].exists() else [],
        "out_stem": str(paths["tex"].with_suffix("")),
        "run_id": run_id,
    }
