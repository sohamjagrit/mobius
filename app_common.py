"""Shared UI logic for the Mobius multipage app.

Page scripts under pages/ are thin wrappers that call the render_* functions
here. Backend stays in services/; storage paths come from config.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import tempfile
from datetime import date
from pathlib import Path

import streamlit as st

import config
from services import claude, history
from services.budget import (
    estimate_lines, default_settings, valid_settings, skills_kept,
    calculate_char_budget, max_chars_per_bullet, bullet_overflows,
    DEFAULT_SECTION_ORDER, DEFAULT_LINES_PER_BULLET,
)
from services.pipeline import (
    make_converter, parse_resume, structure_profile,
    extract_keywords, tailor, build_audit_pairs, audit,
)
from services.keyword_scan import scan_keywords
from services.render import render_latex, compile_latex_bytes, apply_delta

ss = st.session_state
RUN_KEYS = ("keywords", "tailored", "audit", "latex", "pdf_bytes", "pdf_bytes_clean", "kw_scan", "usages", "out_stem")


# --- helpers -----------------------------------------------------------------
def slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")
    return s or "resume"


@st.cache_resource
def get_converter():
    return make_converter()


def capture_usage(stage: str) -> dict:
    u = dict(claude.LAST_USAGE)
    u["stage"] = stage
    u["cost"] = claude.cost_usd(u)
    return u


def pdf_iframe(pdf_bytes: bytes) -> str:
    b64 = base64.b64encode(pdf_bytes).decode()
    return (
        f'<iframe src="data:application/pdf;base64,{b64}" '
        'width="100%" height="820" style="border:1px solid #ddd;"></iframe>'
    )


def seeded(widget, label, key, default, **kwargs):
    if key not in ss:
        ss[key] = default
    return widget(label, key=key, **kwargs)


def _lines(text: str) -> list[str]:
    return [x.strip() for x in (text or "").splitlines() if x.strip()]


def _csv(text: str) -> list[str]:
    return [x.strip() for x in (text or "").split(",") if x.strip()]


def clear_widget_state():
    for k in list(ss.keys()):
        if k.startswith(("pf_", "set_", "ed_")):
            ss.pop(k, None)


def bootstrap():
    """Load the last-used profile + settings into session, once per session."""
    config.ensure_dirs()
    if "booted" in ss:
        return
    ss.booted = True
    last = config.LAST_FILE.read_text(encoding="utf-8").strip() if config.LAST_FILE.exists() else ""
    if not last:
        return
    p, sp = config.profile_path(last), config.settings_path(last)
    if not p.exists():
        return
    b = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else None
    ss.profile_hash = last
    ss.profile = json.loads(p.read_text(encoding="utf-8"))
    ss.budget = b if valid_settings(b) else None


def has_profile() -> bool:
    return bool(ss.get("profile"))


def has_settings() -> bool:
    return has_profile() and valid_settings(ss.get("budget"))


def load_master(data: bytes, filename: str):
    file_hash = hashlib.sha256(data).hexdigest()
    if ss.get("profile_hash") == file_hash:
        return
    p = config.profile_path(file_hash)
    if p.exists():
        ss.profile = json.loads(p.read_text(encoding="utf-8"))
        st.success("Loaded cached profile for this file.")
    else:
        with st.status("First time for this file — parsing + extracting profile…", expanded=True) as status:
            st.write("Running docling (downloads layout model on first ever run)…")
            suffix = ".docx" if filename.lower().endswith(".docx") else ".pdf"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
                tf.write(data)
                tmp_path = Path(tf.name)
            try:
                md, _ = parse_resume(tmp_path, converter=get_converter())
            finally:
                tmp_path.unlink(missing_ok=True)
            st.write("Stage 0: structuring profile (Sonnet)…")
            profile = structure_profile(md)
            p.write_text(json.dumps(profile, indent=2), encoding="utf-8")
            config.docling_path(file_hash).write_text(md, encoding="utf-8")
            ss.profile = profile
            u = capture_usage("Stage 0 · profile")
            status.update(label=f"Profile ready · ${u['cost']:.4f}", state="complete")
    ss.profile_hash = file_hash
    sp = config.settings_path(file_hash)
    b = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else None
    ss.budget = b if valid_settings(b) else None
    clear_widget_state()
    for k in RUN_KEYS:
        ss.pop(k, None)


# --- onboarding (review/edit) ------------------------------------------------
def profile_editor(profile: dict):
    n_exp = len(profile.get("experience", []) or [])
    n_proj = len(profile.get("projects", []) or [])
    n_edu = len(profile.get("education", []) or [])
    skill_cats = list((profile.get("skills", {}) or {}).keys())

    with st.form("profile_editor"):
        contact = profile.get("contact", {}) or {}
        st.markdown("**Contact**")
        cc1, cc2 = st.columns(2)
        seeded(cc1.text_input, "Name", "pf_name", contact.get("name", ""))
        seeded(cc2.text_input, "Email", "pf_email", contact.get("email", ""))
        seeded(cc1.text_input, "Phone", "pf_phone", contact.get("phone", ""))
        seeded(cc2.text_input, "Location", "pf_location", contact.get("location", ""))
        seeded(cc1.text_input, "LinkedIn URL", "pf_linkedin", contact.get("linkedin_url", ""))
        seeded(cc2.text_input, "GitHub URL", "pf_github", contact.get("github_url", ""))

        st.markdown("**Experience**")
        for i, exp in enumerate(profile.get("experience", []) or []):
            head = " — ".join(x for x in (exp.get("company"), exp.get("title")) if x) or f"Experience {i + 1}"
            with st.expander(head):
                e1, e2 = st.columns(2)
                seeded(e1.text_input, "Company", f"pf_e{i}_company", exp.get("company", ""))
                seeded(e2.text_input, "Title", f"pf_e{i}_title", exp.get("title", ""))
                seeded(e1.text_input, "Dates", f"pf_e{i}_dates", exp.get("dates", ""))
                seeded(e2.text_input, "Location", f"pf_e{i}_location", exp.get("location", ""))
                seeded(st.text_area, "Bullets (one per line)", f"pf_e{i}_bullets",
                       "\n".join(exp.get("bullets", []) or []), height=150)
                seeded(st.text_input, "Skill tags (comma-separated)", f"pf_e{i}_skill",
                       ", ".join(exp.get("skill_tags", []) or []))
                seeded(st.text_input, "Domain tags (comma-separated)", f"pf_e{i}_domain",
                       ", ".join(exp.get("domain_tags", []) or []))

        st.markdown("**Projects**")
        for i, proj in enumerate(profile.get("projects", []) or []):
            with st.expander(proj.get("name") or f"Project {i + 1}"):
                seeded(st.text_input, "Name", f"pf_p{i}_name", proj.get("name", ""))
                seeded(st.text_input, "Tools", f"pf_p{i}_tools", proj.get("tools", ""))
                seeded(st.text_area, "Bullets (one per line)", f"pf_p{i}_bullets",
                       "\n".join(proj.get("bullets", []) or []), height=120)
                seeded(st.text_input, "Skill tags (comma-separated)", f"pf_p{i}_skill",
                       ", ".join(proj.get("skill_tags", []) or []))
                seeded(st.text_input, "Domain tags (comma-separated)", f"pf_p{i}_domain",
                       ", ".join(proj.get("domain_tags", []) or []))

        st.markdown("**Skills**")
        skills = profile.get("skills", {}) or {}
        for cat in skill_cats:
            val = skills.get(cat, "")
            seeded(st.text_input, cat.replace("_", " ").title(), f"pf_sk_{cat}",
                   ", ".join(val) if isinstance(val, list) else val)

        st.markdown("**Education**")
        for i, edu in enumerate(profile.get("education", []) or []):
            with st.expander(edu.get("institution") or f"Education {i + 1}"):
                g1, g2 = st.columns(2)
                seeded(g1.text_input, "Institution", f"pf_g{i}_institution", edu.get("institution", ""))
                seeded(g2.text_input, "Degree", f"pf_g{i}_degree", edu.get("degree", ""))
                seeded(g1.text_input, "Dates", f"pf_g{i}_dates", edu.get("dates", ""))
                seeded(g2.text_input, "Location", f"pf_g{i}_location", edu.get("location", ""))
                seeded(st.text_input, "Relevant courses (comma-separated)", f"pf_g{i}_courses",
                       ", ".join(edu.get("relevant_courses", []) or []))

        saved = st.form_submit_button("Save details")

    if saved:
        new = {
            "contact": {
                "name": ss["pf_name"], "email": ss["pf_email"], "phone": ss["pf_phone"],
                "location": ss["pf_location"], "linkedin_url": ss["pf_linkedin"], "github_url": ss["pf_github"],
            },
            "target_roles": profile.get("target_roles", ""),
            "experience": [{
                "company": ss[f"pf_e{i}_company"], "title": ss[f"pf_e{i}_title"],
                "location": ss[f"pf_e{i}_location"], "dates": ss[f"pf_e{i}_dates"],
                "skill_tags": _csv(ss[f"pf_e{i}_skill"]), "domain_tags": _csv(ss[f"pf_e{i}_domain"]),
                "bullets": _lines(ss[f"pf_e{i}_bullets"]),
            } for i in range(n_exp)],
            "projects": [{
                "name": ss[f"pf_p{i}_name"], "tools": ss[f"pf_p{i}_tools"],
                "skill_tags": _csv(ss[f"pf_p{i}_skill"]), "domain_tags": _csv(ss[f"pf_p{i}_domain"]),
                "bullets": _lines(ss[f"pf_p{i}_bullets"]),
            } for i in range(n_proj)],
            "skills": {c: ss.get(f"pf_sk_{c}", "") for c in skill_cats},
            "education": [{
                "institution": ss[f"pf_g{i}_institution"], "degree": ss[f"pf_g{i}_degree"],
                "location": ss[f"pf_g{i}_location"], "dates": ss[f"pf_g{i}_dates"],
                "relevant_courses": _csv(ss[f"pf_g{i}_courses"]),
            } for i in range(n_edu)],
        }
        ss.profile = new
        config.profile_path(ss.profile_hash).write_text(json.dumps(new, indent=2), encoding="utf-8")
        for k in list(ss.keys()):
            if k.startswith("set_"):
                ss.pop(k, None)
        st.success("Saved.")
        st.rerun()


# --- configure (page-fit selection) ------------------------------------------
_RANK_LABELS = ["Most relevant", "2nd", "3rd", "4th", "5th", "6th"]


def _rank_label(i: int) -> str:
    return _RANK_LABELS[i] if i < len(_RANK_LABELS) else f"#{i + 1}"


def count_slider(col, label, key, default, lo, hi):
    if hi <= lo:
        col.caption(f"{label}: {hi}")
        return hi
    return seeded(col.slider, label, key, max(lo, min(default, hi)), min_value=lo, max_value=hi)


def _bullet_caps_for_n(n: int, saved_caps: list, max_bullets: list[int], fallback: int, key_prefix: str) -> list[int]:
    caps: list[int] = []
    if n == 0:
        return caps
    cols = st.columns(min(n, 3))
    for rank in range(n):
        hi = max_bullets[rank] if rank < len(max_bullets) else fallback
        default = int(saved_caps[rank]) if rank < len(saved_caps) else min(fallback, hi)
        caps.append(count_slider(cols[rank % len(cols)],
                                 f"{_rank_label(rank)} (max {hi})",
                                 f"{key_prefix}{rank}", default, 1 if hi else 0, hi))
    return caps


def page_fit_selection(profile: dict) -> dict:
    st.caption("Saved once, reused for every job. Set how many items to include — Claude picks the most JD-relevant.")
    saved = {**default_settings(profile), **(ss.get("budget") or {})}
    estimate_slot = st.container()

    exp = profile.get("experience", []) or []
    proj = profile.get("projects", []) or []
    edu = profile.get("education", []) or []
    courses_max = max((len(e.get("relevant_courses", []) or []) for e in edu), default=1)

    st.markdown("**1 · Experiences** — how many to include, then bullets per slot.")
    n1, _, _ = st.columns(3)
    max_exp = count_slider(n1, f"Experiences (of {len(exp)})", "set_n_exp",
                           saved.get("max_experiences", len(exp)), 0, len(exp))
    if max_exp > 0:
        max_bullets_exp = [len(e.get("bullets", []) or []) for e in exp]
        max_bullets_exp_sorted = sorted(max_bullets_exp, reverse=True)[:max_exp]
        exp_bullets = _bullet_caps_for_n(max_exp, saved.get("experience_bullets") or [],
                                         max_bullets_exp_sorted, 4, "set_eb_")
    else:
        exp_bullets = []

    st.markdown("**2 · Projects** — how many to include, then bullets per slot.")
    p1, _, _ = st.columns(3)
    max_proj = count_slider(p1, f"Projects (of {len(proj)})", "set_n_proj",
                            saved.get("max_projects", len(proj)), 0, len(proj))
    if max_proj > 0:
        max_bullets_proj = [len(p.get("bullets", []) or []) for p in proj]
        max_bullets_proj_sorted = sorted(max_bullets_proj, reverse=True)[:max_proj]
        proj_bullets = _bullet_caps_for_n(max_proj, saved.get("project_bullets") or [],
                                          max_bullets_proj_sorted, 3, "set_pb_")
    else:
        proj_bullets = []

    st.markdown("**3 · Education**")
    e1, _, _ = st.columns(3)
    max_edu = count_slider(e1, f"Education (of {len(edu)})", "set_n_edu",
                           saved.get("max_education", len(edu)), 0, len(edu))
    max_courses = count_slider(st.columns(3)[0], "Courses per entry", "set_courses",
                               saved.get("max_courses", 3), 0, courses_max)

    st.markdown("**4 · Skills** — uncheck any you don't want on the resume.")
    excluded_saved = {str(x).strip().lower() for x in (saved.get("skills_excluded") or [])}
    excluded: list[str] = []
    skills = profile.get("skills", {}) or {}
    for cat, val in skills.items():
        tokens = val if isinstance(val, list) else _csv(val)
        if not tokens:
            continue
        st.caption(cat.replace("_", " ").title())
        cols = st.columns(4)
        for j, tok in enumerate(tokens):
            on = seeded(cols[j % 4].checkbox, tok, f"set_sk_{cat}_{j}",
                        tok.strip().lower() not in excluded_saved)
            if not on:
                excluded.append(tok.strip().lower())

    st.markdown("**5 · Bullet length** — sets the character budget Claude must fit each bullet within.")
    b1, _, _ = st.columns(3)
    lines_per_bullet = count_slider(b1, "Lines per bullet", "set_lpb",
                                    saved.get("lines_per_bullet", DEFAULT_LINES_PER_BULLET), 1, 3)
    char_cap = calculate_char_budget(lines_per_bullet)
    b1.caption(f"≈ {char_cap} characters per bullet")

    st.markdown("**6 · Layout**")
    l1, l2, l3 = st.columns(3)
    font_size = seeded(l1.selectbox, "Font size", "set_font_size",
                       saved.get("font_size", 10), options=[10, 11])
    margin = seeded(l2.selectbox, "Margins (in)", "set_margin",
                    saved.get("margin", 0.4), options=[0.4, 0.5, 0.6])
    section_order = seeded(l3.multiselect, "Section order", "set_section_order",
                           saved.get("section_order") or DEFAULT_SECTION_ORDER,
                           options=DEFAULT_SECTION_ORDER,
                           help="Drag to reorder — top = first on resume.")

    settings = {
        "max_experiences":    max_exp,
        "experience_bullets": exp_bullets,
        "max_projects":       max_proj,
        "project_bullets":    proj_bullets,
        "max_education":      max_edu,
        "max_courses":        max_courses,
        "lines_per_bullet":   lines_per_bullet,
        "skills_excluded":    excluded,
        "section_order":      section_order or DEFAULT_SECTION_ORDER,
        "font_size":          font_size,
        "margin":             margin,
    }

    est = estimate_lines(profile, settings)
    with estimate_slot:
        m1, m2 = st.columns(2)
        m1.metric("Estimated lines", est["total"], border=True)
        m2.metric("Page fill", f"{est['page_pct']}%", border=True)
        if est["page_pct"] > 100:
            st.warning("Likely over one page — deselect some items or lower a bullet count.",
                       icon=":material/warning:")
    return settings


# --- render / compile --------------------------------------------------------
def compile_resume_outputs(renderable: dict, budget: dict, paths: dict) -> tuple[str, bytes | None, bytes | None]:
    """Preview LaTeX/PDF with keyword highlights; on-disk + download PDF without."""
    latex_preview = render_latex(renderable, settings=budget, highlight_keywords=True)
    latex_clean = render_latex(renderable, settings=budget, highlight_keywords=False)
    paths["tex"].write_text(latex_clean, encoding="utf-8")
    try:
        pdf_preview = compile_latex_bytes(latex_preview, paths["tex"].parent, stem="_preview")
        pdf_clean = compile_latex_bytes(latex_clean, paths["tex"].parent, stem="resume")
        paths["pdf"].write_bytes(pdf_clean)
        (paths["tex"].parent / "_preview.pdf").unlink(missing_ok=True)
        return latex_preview, pdf_preview, pdf_clean
    except RuntimeError:
        return latex_preview, None, None


# --- pipeline ----------------------------------------------------------------
def run_pipeline(profile: dict, budget: dict, jd_text: str, jd_slug: str):
    if jd_slug.strip():
        (config.JD / f"{slugify(jd_slug)}.txt").write_text(jd_text, encoding="utf-8")

    profile_for_stage2 = {
        **profile,
        "skills": skills_kept(profile.get("skills") or {}, (budget or {}).get("skills_excluded")),
    }
    usages: list[dict] = []

    with st.status("Running pipeline…", expanded=True) as status:
        st.write("Stage 1: extracting keywords (Sonnet)…")
        keywords = extract_keywords(jd_text)
        usages.append(capture_usage("Stage 1 · keywords"))
        st.write(f"  {len(keywords)} keywords · ${usages[-1]['cost']:.4f}")

        st.write("Stage 2: tailoring (Sonnet)…")
        delta = tailor(profile_for_stage2, keywords, jd_text, budget)
        usages.append(capture_usage("Stage 2 · tailor"))
        st.write(f"  done · ${usages[-1]['cost']:.4f}")

        st.write("Stage 3: fabrication audit (rapidfuzz + Haiku)…")
        pairs = build_audit_pairs(profile_for_stage2, delta)
        audit_res = audit(pairs)
        usages.append(capture_usage("Stage 3 · audit"))
        st.write(f"  {len(pairs)} bullets checked · ${usages[-1]['cost']:.4f}")

        st.write("Rendering LaTeX + PDF…")
        renderable = apply_delta(profile, delta, budget)
        slug = slugify(jd_slug or delta.get("target_role") or "jd")
        run_id = f"{date.today().isoformat()}_{slug}"
        paths = config.run_paths(run_id)
        paths["tex"].parent.mkdir(parents=True, exist_ok=True)
        latex, pdf_bytes, pdf_bytes_clean = compile_resume_outputs(renderable, budget, paths)
        if pdf_bytes:
            status.update(label=f"Done · total ${sum(u['cost'] for u in usages):.4f}", state="complete")
        else:
            status.update(label="Tailored, but PDF compile failed", state="error")
            st.error("PDF compile failed — check the LaTeX tab for errors.")
        history.save_run(
            slug, jd_text, delta, renderable,
            paths["tex"].read_text(encoding="utf-8") if paths["tex"].exists() else latex,
            pdf_bytes_clean, audit_res, usages,
        )

    for k in list(ss.keys()):
        if k.startswith("ed_"):
            ss.pop(k, None)
    ss.keywords = keywords
    ss.tailored = delta
    ss.audit = audit_res
    ss.latex = latex
    ss.pdf_bytes = pdf_bytes
    ss.pdf_bytes_clean = pdf_bytes_clean
    ss.usages = usages
    ss.run_id = run_id
    ss.out_stem = str(config.run_paths(run_id)["tex"].with_suffix(""))


# --- keyword panel -----------------------------------------------------------
def keyword_panel():
    keywords = ss.get("keywords") or []
    tailored = ss.get("tailored") or {}
    if not keywords or not tailored:
        return

    delta = edited_delta_from_state(tailored)
    scan = scan_keywords(keywords, delta)
    ss.kw_scan = scan

    total = scan["total"]
    covered = scan["covered"]
    missing = scan["missing"]

    st.subheader("Keyword coverage")
    st.caption("Scanned locally from your current editor text — updates as you edit, no API call.")
    m1, m2 = st.columns([1, 3])
    m1.metric("Covered", f"{len(covered)} / {total}", border=True)
    with m2:
        st.progress(len(covered) / total, text=f"{scan['pct']}% of JD keywords in resume text")

    if missing:
        st.markdown("**Gaps** — not found in your current text. Add only if you have the experience.")
        st.markdown(" ".join(f":red-badge[{n}]" for n in missing))
        if st.button("Add gaps to notes", icon=":material/note_add:"):
            existing = ss.get("scratch_notes", "")
            ss["scratch_notes"] = (existing + ("\n" if existing else "") + "\n".join(missing)).strip()
            st.rerun()

    with st.expander(f"Covered keywords ({len(covered)})", icon=":material/check_circle:"):
        if scan["in_bullets"]:
            st.caption("In a bullet")
            st.markdown(" ".join(f":violet-badge[{n}]" for n in scan["in_bullets"]))
        if scan["in_skills"]:
            st.caption("In skills")
            st.markdown(" ".join(f":green-badge[{n}]" for n in scan["in_skills"]))
        if scan["in_other"]:
            st.caption("In role or courses")
            st.markdown(" ".join(f":blue-badge[{n}]" for n in scan["in_other"]))

    seeded(st.text_area, "Scratch notes — keywords to weave in manually later", "scratch_notes", "", height=140)


# --- structured editor -------------------------------------------------------
def edited_delta_from_state(delta: dict) -> dict:
    out = json.loads(json.dumps(delta))
    out["target_role"] = ss.get("ed_role", out.get("target_role", ""))
    for section in ("experience", "projects"):
        for i, item in enumerate(out.get(section, []) or []):
            for b, bullet in enumerate(item.get("bullets", []) or []):
                key = f"ed_{section}_{i}_{b}"
                if key in ss:
                    bullet["text"] = ss[key]
    for i, item in enumerate(out.get("education", []) or []):
        key = f"ed_edu_{i}_courses"
        if key in ss:
            item["relevant_courses"] = _csv(ss[key])
    for j, cat in enumerate(out.get("skills", []) or []):
        key = f"ed_sk_{j}"
        if key in ss:
            cat["skills"] = ss[key]
    return out


def recompile_from_editor(profile: dict, delta: dict, budget: dict):
    renderable = apply_delta(profile, delta, budget)
    run_id = ss.get("run_id") or Path(ss.out_stem).name
    paths = config.run_paths(run_id)
    paths["resume"].write_text(json.dumps(renderable, indent=2), encoding="utf-8")
    paths["delta"].write_text(json.dumps(delta, indent=2), encoding="utf-8")
    ss.tailored = delta
    try:
        latex, pdf_bytes, pdf_bytes_clean = compile_resume_outputs(renderable, budget, paths)
        ss.latex = latex
        ss.pdf_bytes = pdf_bytes
        ss.pdf_bytes_clean = pdf_bytes_clean
        return None
    except RuntimeError as e:
        ss.latex = render_latex(renderable, settings=budget, highlight_keywords=True)
        ss.pdf_bytes = None
        ss.pdf_bytes_clean = None
        return str(e)


# --- shared sidebar ----------------------------------------------------------
def sidebar_summary():
    with st.sidebar:
        st.markdown("### :material/contrast: Mobius")
        st.caption("Resume tailoring, no fabrication.")
        profile = ss.get("profile")
        if profile:
            contact = profile.get("contact") or {}
            st.markdown(f"**{contact.get('name') or 'Your resume'}**")
            if contact.get("email"):
                st.caption(contact["email"])
        b = ss.get("budget") or {}
        if valid_settings(b):
            c1, c2, c3 = st.columns(3)
            c1.metric("Exp", b.get("max_experiences", "—"))
            c2.metric("Proj", b.get("max_projects", "—"))
            c3.metric("Edu", b.get("max_education", "—"))
        if ss.get("usages"):
            st.metric("Last run cost", f"${sum(u['cost'] for u in ss.usages):.4f}")
