"""Local JD keyword coverage scan — no API calls.

Matches Stage 1 keywords against the user's current tailored resume text
(bullets, skills, role, courses) from the editor session state.
"""
from __future__ import annotations

import re


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _kw_label(k) -> str:
    return _norm(k.get("keyword", "") if isinstance(k, dict) else str(k))


def _bullet_texts(delta: dict) -> list[str]:
    out: list[str] = []
    for sec in ("experience", "projects"):
        for item in delta.get(sec) or []:
            for b in item.get("bullets") or []:
                t = b.get("text", "") if isinstance(b, dict) else str(b)
                if t.strip():
                    out.append(t)
    return out


def _skills_text(delta: dict) -> str:
    parts: list[str] = []
    for cat in delta.get("skills") or []:
        if isinstance(cat, dict):
            parts.append(cat.get("skills", ""))
        else:
            parts.append(str(cat))
    return _norm(" ".join(parts))


def _corpus_parts(delta: dict) -> list[str]:
    parts: list[str] = []
    role = delta.get("target_role", "")
    if role:
        parts.append(role)
    parts.extend(_bullet_texts(delta))
    for item in delta.get("education") or []:
        parts.extend(item.get("relevant_courses") or [])
    for cat in delta.get("skills") or []:
        if isinstance(cat, dict):
            parts.append(cat.get("skills", ""))
    return [p for p in parts if p.strip()]


def _matches(keyword: str, haystack: str) -> bool:
    kw = _norm(keyword)
    if not kw or not haystack:
        return False
    if re.search(rf"\b{re.escape(kw)}\b", haystack):
        return True
    return kw in haystack


def scan_keywords(jd_keywords: list, delta: dict) -> dict:
    """Return coverage breakdown for the keyword panel."""
    corpus = _norm(" ".join(_corpus_parts(delta)))
    bullets = _norm(" ".join(_bullet_texts(delta)))
    skills = _skills_text(delta)

    labels = [_kw_label(k) for k in (jd_keywords or [])]
    labels = [x for x in labels if x]

    covered: list[str] = []
    missing: list[str] = []
    in_bullets: list[str] = []
    in_skills: list[str] = []
    in_other: list[str] = []

    for label in labels:
        if _matches(label, corpus):
            covered.append(label)
            if _matches(label, bullets):
                in_bullets.append(label)
            elif _matches(label, skills):
                in_skills.append(label)
            else:
                in_other.append(label)
        else:
            missing.append(label)

    total = len(labels)
    return {
        "total": total,
        "covered": covered,
        "missing": missing,
        "in_bullets": in_bullets,
        "in_skills": in_skills,
        "in_other": in_other,
        "pct": round(100 * len(covered) / total, 1) if total else 0.0,
    }
