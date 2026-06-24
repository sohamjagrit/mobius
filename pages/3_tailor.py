import hashlib
import json
from pathlib import Path

import streamlit as st

import app_common as ac
import config
import editor_sections as eds
from services.budget import max_chars_per_bullet, bullet_overflows
from services.render import compile_pdf
from services import tracker

ss = st.session_state
profile = ss.get("profile")
budget = ss.get("budget")
if not (profile and ac.valid_settings(budget)):
    st.warning("Finish setup first — upload a resume and save your page-fit settings.", icon=":material/tune:")
    st.page_link("pages/1_onboarding.py", label="Go to onboarding", icon=":material/upload_file:")
    st.stop()

name = (profile.get("contact") or {}).get("name", "your resume")
st.title("Tailor your resume")
role_name = ss.get("active_role_name")
st.caption(f"Tailoring {name}"
           + (f" · {role_name} resume" if role_name else "")
           + " to a job description. No fabrication.")

ac.role_bar()

jd_text = st.text_area("Job description", height=260, key="jd_text",
                       placeholder="Paste the full job description here…")
jd_slug = st.text_input("Save as", key="jd_slug",
                        placeholder="acme-data-scientist",
                        help="Names the saved run and the downloaded files.")

jd_hash = hashlib.sha256((jd_text or "").encode()).hexdigest()
pre_analyzed = bool(ss.get("keywords")) and ss.get("jd_analyzed_hash") == jd_hash

a1, a2 = st.columns(2)
if a1.button("Analyze JD", icon=":material/search:", disabled=not (jd_text.strip() and jd_slug.strip()),
             use_container_width=True):
    ac.analyze_jd(jd_text, profile)
    st.rerun()

if pre_analyzed:
    pre = ss.get("pre_scan") or {}
    total = pre.get("total", 0)
    covered_pre = pre.get("covered", [])
    missing_pre = pre.get("missing", [])
    if total:
        p1, p2 = st.columns([1, 3])
        p1.metric("Already in master", f"{len(covered_pre)} / {total}", border=True)
        with p2:
            st.progress(len(covered_pre) / total,
                        text=f"{pre.get('pct', 0)}% of JD keywords already in your master resume")
        if missing_pre:
            st.caption("Not yet in master — Stage 2 will try to surface these from your experience:")
            st.markdown(" ".join(f":orange-badge[{n}]" for n in missing_pre))

if a2.button("Tailor resume", type="primary", icon=":material/auto_awesome:",
             disabled=not (jd_text.strip() and jd_slug.strip()), use_container_width=True):
    ac.run_pipeline(profile, budget, jd_text, jd_slug)

if ss.get("usages"):
    cols = st.columns(len(ss.usages) + 1)
    for col, u in zip(cols, ss.usages):
        col.metric(u["stage"], f"${u['cost']:.4f}", border=True)
    cols[-1].metric("Total", f"${sum(u['cost'] for u in ss.usages):.4f}", border=True)

if not ss.get("tailored"):
    st.stop()

cap = max_chars_per_bullet(budget)


def _preview_panel():
    st.subheader("Preview", divider="gray")
    st.caption("Surfaced keywords are highlighted here only — downloads are clean.")
    if ss.get("pdf_bytes"):
        st.markdown(ac.pdf_iframe(ss.pdf_bytes), unsafe_allow_html=True)
    else:
        st.warning("No PDF — fix the content or LaTeX and recompile.", icon=":material/error:")


def _download_pdf(prefix: str):
    pdf = ss.get("pdf_bytes_clean") or ss.get("pdf_bytes")
    fname = f"{ss.get('run_slug', 'resume')}.pdf"
    if pdf:
        st.download_button("Download .pdf", pdf, icon=":material/picture_as_pdf:",
                           use_container_width=True, file_name=fname,
                           mime="application/pdf", key=f"{prefix}_dl_pdf")


def _download_latex_row(prefix: str):
    slug = ss.get("run_slug", "resume")
    d1, d2 = st.columns(2)
    d1.download_button("Download .tex", ss.latex, icon=":material/download:",
                       use_container_width=True, file_name=f"{slug}.tex",
                       key=f"{prefix}_dl_tex")
    pdf = ss.get("pdf_bytes_clean") or ss.get("pdf_bytes")
    if pdf:
        d2.download_button("Download .pdf", pdf, icon=":material/picture_as_pdf:",
                           use_container_width=True, file_name=f"{slug}.pdf",
                           mime="application/pdf", key=f"{prefix}_dl_pdf")


def _structured_footer():
    edited = ac.edited_delta_from_state(ss.tailored)
    overflows = bullet_overflows(edited, cap)
    if overflows:
        st.warning(f"{len(overflows)} bullet(s) over the {cap}-char budget — trim them to stay on one page.",
                   icon=":material/warning:")
    content_hash = hashlib.sha256(json.dumps(edited, sort_keys=True).encode()).hexdigest()
    changed = content_hash != ss.get("ed_hash")
    live = ss.get("ed_live", True)
    if st.button("Recompile", icon=":material/refresh:", use_container_width=True,
                 key="recompile_structured") or (live and changed):
        with st.spinner("Compiling…"):
            err = ac.recompile_from_editor(profile, edited, budget)
        ss.ed_hash = content_hash
        if err:
            st.error(err)
        else:
            st.rerun()
    _download_pdf("structured")


def _sync_section_tabs(sec_edu, sec_exp, sec_proj, sec_skills):
    """Streamlit requires content inside each tab's with-block; we only track selection."""
    with sec_edu:
        if sec_edu.open:
            ss.ed_section = "education"
    with sec_exp:
        if sec_exp.open:
            ss.ed_section = "experience"
    with sec_proj:
        if sec_proj.open:
            ss.ed_section = "projects"
    with sec_skills:
        if sec_skills.open:
            ss.ed_section = "skills"


if ss.get("_project_swap"):
    label = "Re-tailoring swapped project…" if ss["_project_swap"].get("mode") == "retailor" else "Swapping project…"
    with st.spinner(label):
        err = ac.execute_project_swap()
    if err:
        st.error(err)
    else:
        st.rerun()

left, right = st.columns(2)

with left:
    st.subheader("Result", divider="gray")
    ac.seeded(st.text_input, "Target role", "ed_role", ss.tailored.get("target_role", ""))
    ac.seeded(st.toggle, "Live preview (recompile on edit)", "ed_live", True)
    st.caption(f"Counters show characters vs the ≈{cap}-char budget. "
               "Metadata (company, title, dates) comes from your master and isn't editable here.")
    tab_editor, tab_latex = st.tabs(["Editor", "LaTeX"], on_change="rerun")

    with tab_editor:
        if tab_editor.open:
            sec_edu, sec_exp, sec_proj, sec_skills = st.tabs(
                list(eds.section_tab_labels(ss.tailored)), on_change="rerun",
            )
            _sync_section_tabs(sec_edu, sec_exp, sec_proj, sec_skills)
            eds.render_active_section(profile, ss.tailored, budget, ss.get("ed_section", "experience"))
            _structured_footer()

    with tab_latex:
        if tab_latex.open:
            st.caption("Edit the raw LaTeX source and recompile.")
            raw = st.text_area("LaTeX source", value=ss.latex, height=520,
                               key="latex_editor", label_visibility="collapsed")
            if st.button("Recompile from LaTeX", icon=":material/refresh:",
                         use_container_width=True, key="recompile_latex"):
                run_id = ss.get("run_id") or Path(ss.out_stem).name
                tex_path = config.run_paths(run_id)["tex"]
                tex_path.write_text(raw, encoding="utf-8")
                try:
                    pdf_bytes = compile_pdf(tex_path).read_bytes()
                    config.run_paths(run_id)["pdf"].write_bytes(pdf_bytes)
                    ss.pdf_bytes = pdf_bytes
                    ss.pdf_bytes_clean = pdf_bytes
                    ss.latex = raw
                    st.rerun()
                except RuntimeError as e:
                    st.error(str(e))
            _download_latex_row("latex")

with right:
    _preview_panel()

ac.keyword_panel()
ac.outreach_panel()

st.divider()
st.markdown("### :material/assignment: Track your application")
st.caption("Did you apply? Save this as a job application and track its status.")

col1, col2 = st.columns(2)
company = col1.text_input("Company", key="app_company", placeholder="e.g., Google")
role = col2.text_input("Role", key="app_role", placeholder="e.g., Senior Data Scientist")

status = st.selectbox("Status", ["Applied", "Pending", "Interviewing", "Rejected", "Offer"], key="app_status")
notes = st.text_area("Notes", key="app_notes", placeholder="Any notes about the application…", height=80)

if st.button("Save application", icon=":material/bookmark:", use_container_width=True, key="save_app"):
    if company.strip() and role.strip():
        tracker.add_application(
            company=company.strip(),
            role=role.strip(),
            status=status,
            notes=notes.strip(),
            resume_slug=ss.get("run_slug", "resume"),
        )
        st.success(f"Tracked application to {company} for {role}!", icon=":material/check_circle:")
        st.info("View and update all your applications on the **Job Tracker** page.", icon=":material/info:")
    else:
        st.error("Please fill in company and role.")
