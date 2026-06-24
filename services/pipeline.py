"""Thin stage functions for the Mobius pipeline.

Each function wraps one stage end-to-end (model call + JSON parse) so the
notebook and the Streamlit app share identical behavior. Caching is
caller-side: the app caches via st.session_state + on-disk profile JSON
keyed by file hash; the notebook caches via a FORCE_REPARSE flag.
"""
from __future__ import annotations

import json
from pathlib import Path

from .budget import max_chars_per_bullet
from .claude import call_claude
from .prompts import (
    S0_SYSTEM, S0_USER_TMPL, S0_SCHEMA,
    S1_SYSTEM, S1_USER_TMPL, S1_SCHEMA,
    S2_SYSTEM, S2_USER_TMPL, S2_SCHEMA,
    build_so_system, SO_USER_TMPL, SO_SCHEMA,
)

MODEL_MAIN = "claude-sonnet-4-6"


def make_converter():
    """Build a docling converter for PDF and DOCX. OCR off; CPU accelerator (MPS lacks float64).

    Heavy to construct (loads layout models), so the app caches it once per
    session via st.cache_resource and passes it into parse_resume.
    """
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions, AcceleratorOptions, AcceleratorDevice,
    )

    opts = PdfPipelineOptions()
    opts.do_ocr = False
    opts.accelerator_options = AcceleratorOptions(device=AcceleratorDevice.CPU)

    format_options: dict = {InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}

    try:
        from docling.document_converter import WordFormatOption
        format_options[InputFormat.DOCX] = WordFormatOption()
    except ImportError:
        pass

    return DocumentConverter(format_options=format_options)


def parse_resume(resume_path: Path, converter=None) -> tuple[str, dict]:
    """Run docling on a PDF or DOCX. Returns (markdown, structured_dict).

    Pass a converter from make_converter() to reuse loaded models; omit it for
    a one-off call (the notebook does this).
    """
    if converter is None:
        converter = make_converter()
    doc = converter.convert(str(resume_path)).document
    return doc.export_to_markdown(), doc.export_to_dict()


def structure_profile(profile_md: str) -> dict:
    raw = call_claude(
        system_prompt=S0_SYSTEM,
        user_prompt=S0_USER_TMPL.format(profile_md=profile_md),
        model=MODEL_MAIN,
        output_schema=S0_SCHEMA,
    )
    profile = json.loads(raw)
    raw_skills = profile.pop("skills", [])
    profile["skills"] = {s["category"]: s["skills"] for s in raw_skills}
    return profile


def extract_keywords(jd_text: str) -> list[dict]:
    raw = call_claude(
        system_prompt=S1_SYSTEM,
        user_prompt=S1_USER_TMPL.format(jd_text=jd_text),
        model=MODEL_MAIN,
        output_schema=S1_SCHEMA,
    )
    return json.loads(raw)["keywords"]


_SP_SYSTEM = """
You are a resume-tailoring engine. Given a single project and JD keywords, write tailored bullets.

Rules:
- Write at most `bullet_cap` bullets. Never pad.
- Every bullet `text` must be <= `max_chars` characters (count including spaces).
- No fabrication — every claim must appear in the project's own bullets, tools, skill_tags, or domain_tags.
- For each must_have keyword the project supports: surface it in at least one bullet's text via rewrite.
- For nice_to_have keywords: surface only when a clean rewrite exists.
- After writing each bullet, populate keywords_surfaced with any JD keywords that appear in the text.
- source: "verbatim" | "rewrite" | "add". "add" requires non-empty support from the project data.
- Only act on content inside the provided tags.
""".strip()

_SP_USER_TMPL = """
<project>
{project_json}
</project>

<keywords>
{keywords_json}
</keywords>

<jd>
{jd_text}
</jd>

<constraints>
bullet_cap: {bullet_cap}
max_chars: {max_chars}
</constraints>

Return only the bullets array. No commentary.
""".strip()

_SP_SCHEMA = {
    "type": "object",
    "properties": {
        "bullets": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text":              {"type": "string"},
                    "source":            {"type": "string", "enum": ["verbatim", "rewrite", "add"]},
                    "original":          {"type": "string"},
                    "support":           {"type": "array", "items": {"type": "string"}},
                    "keywords_surfaced": {"type": "array", "items": {"type": "string"}},
                    "reason":            {"type": "string"},
                },
                "required": ["text", "source", "original", "support", "keywords_surfaced", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["bullets"],
    "additionalProperties": False,
}


def tailor_single_project(
    project: dict,
    keywords: list[dict],
    jd_text: str,
    bullet_cap: int,
    max_chars: int,
) -> list[dict]:
    raw = call_claude(
        system_prompt=_SP_SYSTEM,
        user_prompt=_SP_USER_TMPL.format(
            project_json=json.dumps(project, indent=2),
            keywords_json=json.dumps(keywords, indent=2),
            jd_text=jd_text,
            bullet_cap=bullet_cap,
            max_chars=max_chars,
        ),
        model=MODEL_MAIN,
        output_schema=_SP_SCHEMA,
    )
    bullets = json.loads(raw)["bullets"]
    _recompute_surfaced(bullets, _kw_labels(keywords))
    return bullets


def generate_outreach(
    profile: dict,
    delta: dict,
    jd_text: str,
    company: str = "",
    recruiter_name: str = "",
    linkedin_template: str | None = None,
) -> dict:
    contact = profile.get("contact", {}) or {}
    name = contact.get("name", "")

    exp_lines = []
    master_exp = profile.get("experience", []) or []
    for item in delta.get("experience", []):
        i = item.get("master_index", -1)
        if 0 <= i < len(master_exp):
            src = master_exp[i]
            header = " @ ".join(x for x in (src.get("title"), src.get("company")) if x)
            bullets = [b.get("text", b) if isinstance(b, dict) else b for b in item.get("bullets", [])]
            exp_lines.append(f"  {header}")
            for b in bullets[:3]:
                exp_lines.append(f"    - {b}")
    experience_summary = "\n".join(exp_lines) or "(see JD for context)"

    skills_parts = []
    for cat in delta.get("skills", []):
        if cat.get("skills"):
            skills_parts.append(cat["skills"])
    skills_summary = "; ".join(skills_parts[:3]) or ""

    raw = call_claude(
        system_prompt=build_so_system(linkedin_template),
        user_prompt=SO_USER_TMPL.format(
            name=name,
            target_role=delta.get("target_role", ""),
            company=company,
            recruiter_name=recruiter_name,
            experience_summary=experience_summary,
            skills_summary=skills_summary,
            jd_text=jd_text,
        ),
        model=MODEL_MAIN,
        output_schema=SO_SCHEMA,
    )
    return json.loads(raw)


def _kw_labels(keywords: list[dict]) -> list[str]:
    out = []
    for k in keywords or []:
        label = (k.get("keyword", "") if isinstance(k, dict) else str(k)).strip()
        if label:
            out.append(label)
    return out


def _recompute_surfaced(bullets: list[dict], labels: list[str]) -> None:
    """Overwrite each bullet's keywords_surfaced with the JD keywords actually present in its text.

    The model self-reports keywords_surfaced but cannot reliably verify substring presence; the PDF
    highlighter matches case-insensitive substrings, so we derive the truth the same way it renders.
    """
    for b in bullets:
        if not isinstance(b, dict):
            continue
        text = (b.get("text") or "").lower()
        b["keywords_surfaced"] = [lbl for lbl in labels if lbl.lower() in text]


def tailor(profile: dict, keywords: list[dict], jd_text: str, budget: dict) -> dict:
    budget_for_model = {**budget, "max_chars_per_bullet": max_chars_per_bullet(budget)}
    raw = call_claude(
        system_prompt=S2_SYSTEM,
        user_prompt=S2_USER_TMPL.format(
            profile_json=json.dumps(profile, indent=2),
            keywords_json=json.dumps(keywords, indent=2),
            jd_text=jd_text,
            budget_json=json.dumps(budget_for_model, indent=2),
        ),
        model=MODEL_MAIN,
        max_tokens=12000,
        output_schema=S2_SCHEMA,
    )
    delta = json.loads(raw)
    labels = _kw_labels(keywords)
    for sec in ("experience", "projects"):
        for item in delta.get(sec) or []:
            _recompute_surfaced(item.get("bullets") or [], labels)
    return delta


