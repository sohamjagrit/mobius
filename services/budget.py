"""Budget helpers for the one-page line estimate.

The user sets counts (how many of each section to keep) and per-slot bullet caps.
Stage 2 picks which items by JD relevance. Bullet caps are position-indexed:
experience_bullets[0] = cap for the most-relevant selected experience, [1] for
the second, etc.

Settings shape:
    {
      "max_experiences":   3,
      "experience_bullets": [4, 3, 3],
      "max_projects":      2,
      "project_bullets":   [3, 3],
      "max_education":     2,
      "max_courses":       3,
      "skills_excluded":   ["c", "html"],
      "section_order":     ["education", "experience", "projects", "skills"],
      "font_size":         10,
      "margin":            0.4
    }
"""
from __future__ import annotations

import math

CHARS_PER_LINE = 122          # measured at 10pt / 0.4in via calibrate_template.py
ONE_PAGE_LINES = 55           # text lines that fit on one page at the same settings
BUDGET_SAFETY = 0.95          # budget at 95% of theoretical capacity to absorb minor overruns
DEFAULT_LINES_PER_BULLET = 2

HEADER_BLOCK_LINES        = 3
SECTION_HEADING_LINES     = 1.5
EXPERIENCE_HEADER_LINES   = 2
PROJECT_HEADER_LINES      = 1
EDUCATION_HEADER_LINES    = 2
EDUCATION_COURSES_LINES   = 1


def lines_for_text(text: str, cpl: int = CHARS_PER_LINE) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / cpl))


def calculate_char_budget(lines: int, cpl: int = CHARS_PER_LINE) -> int:
    """Character cap for a bullet allowed to span `lines` rendered lines.

    Budgets at BUDGET_SAFETY of theoretical capacity so a slightly-long bullet
    doesn't wrap past its allotted lines.
    """
    return int(max(lines, 1) * cpl * BUDGET_SAFETY)


def max_chars_per_bullet(settings: dict) -> int:
    """Per-bullet character cap derived from the settings' lines_per_bullet."""
    lpb = int((settings or {}).get("lines_per_bullet", DEFAULT_LINES_PER_BULLET))
    return calculate_char_budget(lpb)


def bullet_overflows(delta: dict, limit: int) -> list[dict]:
    """Warn-only check: tailored bullets whose text exceeds `limit` characters.

    Returns one record per offending bullet: {pair_id, length, limit, over}.
    The pipeline never auto-edits these — the editor surfaces them so the user
    can trim manually (per the no-auto-truncate decision).
    """
    out: list[dict] = []
    for section in ("experience", "projects"):
        for item in (delta.get(section) or []):
            idx = item.get("master_index")
            for b_idx, bullet in enumerate(item.get("bullets") or []):
                text = bullet.get("text", "") if isinstance(bullet, dict) else str(bullet)
                if len(text) > limit:
                    out.append({
                        "pair_id": f"{section}[{idx}].bullets[{b_idx}]",
                        "length": len(text),
                        "limit": limit,
                        "over": len(text) - limit,
                    })
    return out


def _item_lines(item: dict, cap: int, header_lines: float) -> float:
    bullets = (item.get("bullets") or [])[:max(cap, 0)]
    return header_lines + sum(lines_for_text(b) for b in bullets)


def _top_n_cost(items: list, n: int, caps: list, header_lines: float, fallback: int) -> float:
    """Upper-bound line cost of keeping n items, each scored under its position cap."""
    costs = sorted(
        (_item_lines(it, int(caps[i]) if i < len(caps) else fallback, header_lines)
         for i, it in enumerate(items)),
        reverse=True,
    )
    return float(sum(costs[:max(n, 0)]))


def skills_kept(skills: dict, excluded) -> dict:
    """Return skills with `excluded` (lowercased) tokens removed, category by category."""
    drop = {str(x).strip().lower() for x in (excluded or [])}
    out: dict = {}
    for cat, val in (skills or {}).items():
        tokens = val if isinstance(val, list) else [t.strip() for t in str(val).split(",")]
        kept = [t for t in tokens if t and t.strip().lower() not in drop]
        out[cat] = ", ".join(kept)
    return out


def estimate_lines(profile: dict, settings: dict) -> dict:
    """Estimate line count for a profile rendered under `settings`.

    Returns {"total", "page_pct", "by_section"}.
    """
    by_section = {"header": HEADER_BLOCK_LINES, "experience": 0.0, "projects": 0.0, "skills": 0.0, "education": 0.0}

    exp  = profile.get("experience", []) or []
    proj = profile.get("projects", []) or []
    edu  = profile.get("education", []) or []

    n_exp = min(int(settings.get("max_experiences", 0)), len(exp))
    if n_exp > 0:
        caps = settings.get("experience_bullets") or []
        by_section["experience"] = SECTION_HEADING_LINES + _top_n_cost(exp, n_exp, caps, EXPERIENCE_HEADER_LINES, 4)

    n_proj = min(int(settings.get("max_projects", 0)), len(proj))
    if n_proj > 0:
        caps = settings.get("project_bullets") or []
        by_section["projects"] = SECTION_HEADING_LINES + _top_n_cost(proj, n_proj, caps, PROJECT_HEADER_LINES, 3)

    skills = skills_kept(profile.get("skills") or {}, settings.get("skills_excluded"))
    non_empty = [v for v in skills.values() if v]
    if non_empty:
        by_section["skills"] = SECTION_HEADING_LINES + sum(lines_for_text(v) for v in non_empty)

    n_edu = min(int(settings.get("max_education", 0)), len(edu))
    if n_edu > 0:
        mc  = int(settings.get("max_courses", 0))
        per = EDUCATION_HEADER_LINES + (EDUCATION_COURSES_LINES if mc > 0 else 0)
        by_section["education"] = SECTION_HEADING_LINES + n_edu * per

    by_section = {k: round(v, 1) for k, v in by_section.items()}
    total = sum(by_section.values())
    return {"total": round(total, 1), "page_pct": round(100 * total / ONE_PAGE_LINES, 1), "by_section": by_section}


DEFAULT_SECTION_ORDER = ["education", "experience", "projects", "skills"]


def default_settings(profile: dict, exp_cap: int = 4, proj_cap: int = 3, max_courses: int = 3) -> dict:
    """UI preload: keep all items; per-slot bullet cap defaults to item's own count (capped)."""
    exp  = profile.get("experience", []) or []
    proj = profile.get("projects", []) or []
    return {
        "max_experiences":   len(exp),
        "experience_bullets": [min(exp_cap,  len(e.get("bullets", []) or [])) for e in exp],
        "max_projects":      len(proj),
        "project_bullets":   [min(proj_cap,  len(p.get("bullets", []) or [])) for p in proj],
        "max_education":     len(profile.get("education", []) or []),
        "max_courses":       max_courses,
        "lines_per_bullet":  DEFAULT_LINES_PER_BULLET,
        "skills_excluded":   [],
        "section_order":     DEFAULT_SECTION_ORDER[:],
        "font_size":         10,
        "margin":            0.4,
    }


def valid_settings(settings: dict) -> bool:
    return isinstance(settings, dict) and "max_experiences" in settings
