"""Per-section fields for the tailor page structured editor."""
from __future__ import annotations

import streamlit as st

from app_common import seeded
from services.budget import max_chars_per_bullet

ss = st.session_state


def _counter_badge(n: int, cap: int) -> str:
    if cap <= 0:
        return f":gray-badge[{n} chars]"
    pct = n / cap
    color = "green" if pct <= 0.9 else ("orange" if pct <= 1.0 else "red")
    return f":{color}-badge[{n} / {cap}]"


def _read_only_head(master_item: dict, section: str) -> str:
    if section == "experience":
        bits = [master_item.get("company"), master_item.get("title"), master_item.get("dates")]
    else:
        bits = [master_item.get("name"), master_item.get("tools")]
    return "  ·  ".join(x for x in bits if x) or "(item)"


def _edu_head(master_item: dict) -> str:
    bits = [master_item.get("institution"), master_item.get("degree"), master_item.get("dates")]
    return "  ·  ".join(x for x in bits if x) or "(entry)"


def _bullet_fields(section: str, items: list, master_list: list, cap: int):
    for i, item in enumerate(items):
        idx = item.get("master_index")
        m = master_list[idx] if isinstance(idx, int) and 0 <= idx < len(master_list) else {}
        with st.expander(_read_only_head(m, section), expanded=(i == 0)):
            for b, bullet in enumerate(item.get("bullets", []) or []):
                key = f"ed_{section}_{i}_{b}"
                seeded(st.text_area, f"{section} {i} bullet {b}", key, bullet.get("text", ""),
                       height=70, label_visibility="collapsed")
                st.markdown(_counter_badge(len(ss.get(key, "")), cap))


def section_tab_labels(delta: dict) -> tuple[str, str, str, str]:
    edu = delta.get("education", []) or []
    exp = delta.get("experience", []) or []
    proj = delta.get("projects", []) or []
    skills = delta.get("skills", []) or []
    return (
        f"Education ({len(edu)})",
        f"Experience ({len(exp)})",
        f"Projects ({len(proj)})",
        f"Skills ({len(skills)})",
    )


def render_education_section(profile: dict, delta: dict):
    master_edu = profile.get("education", []) or []
    edu_items = delta.get("education", []) or []
    if not edu_items:
        st.caption("No education entries in this tailored resume.")
        return
    for i, item in enumerate(edu_items):
        idx = item.get("master_index")
        m = master_edu[idx] if isinstance(idx, int) and 0 <= idx < len(master_edu) else {}
        st.caption(_edu_head(m))
        courses = item.get("relevant_courses", []) or []
        seeded(st.text_input, "Relevant courses (comma-separated)",
               f"ed_edu_{i}_courses", ", ".join(courses))


def render_experience_section(profile: dict, delta: dict, budget: dict):
    cap = max_chars_per_bullet(budget)
    exp_items = delta.get("experience", []) or []
    if not exp_items:
        st.caption("No experience entries in this tailored resume.")
        return
    _bullet_fields("experience", exp_items, profile.get("experience", []) or [], cap)


def render_projects_section(profile: dict, delta: dict, budget: dict):
    cap = max_chars_per_bullet(budget)
    proj_items = delta.get("projects", []) or []
    if not proj_items:
        st.caption("No project entries in this tailored resume.")
        return
    _bullet_fields("projects", proj_items, profile.get("projects", []) or [], cap)


def render_skills_section(delta: dict):
    skills = delta.get("skills", []) or []
    if not skills:
        st.caption("No skills in this tailored resume.")
        return
    for j, cat in enumerate(skills):
        seeded(st.text_input, cat.get("category", f"skills {j}").replace("_", " ").title(),
               f"ed_sk_{j}", cat.get("skills", ""))


def render_active_section(profile: dict, delta: dict, budget: dict, section: str):
    if section == "education":
        render_education_section(profile, delta)
    elif section == "experience":
        render_experience_section(profile, delta, budget)
    elif section == "projects":
        render_projects_section(profile, delta, budget)
    elif section == "skills":
        render_skills_section(delta)
