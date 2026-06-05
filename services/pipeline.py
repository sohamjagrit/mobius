"""Thin stage functions for the Mobius pipeline.

Each function wraps one stage end-to-end (model call + JSON parse) so the
notebook and the Streamlit app share identical behavior. Caching is
caller-side: the app caches via st.session_state + on-disk profile JSON
keyed by file hash; the notebook caches via a FORCE_REPARSE flag.
"""
from __future__ import annotations

import json
from pathlib import Path

from rapidfuzz import fuzz

from . import claude
from .budget import max_chars_per_bullet
from .claude import call_claude
from .prompts import (
    S0_SYSTEM, S0_USER_TMPL, S0_SCHEMA,
    S1_SYSTEM, S1_USER_TMPL, S1_SCHEMA,
    S2_SYSTEM, S2_USER_TMPL, S2_SCHEMA,
    S3_SYSTEM, S3_USER_TMPL, S3_SCHEMA,
)

MODEL_MAIN  = "claude-sonnet-4-6"
MODEL_AUDIT = "claude-haiku-4-5-20251001"


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
    return json.loads(raw)


def build_audit_pairs(profile: dict, delta: dict) -> list[dict]:
    pairs = []
    for section in ("experience", "projects"):
        master_list = profile.get(section, []) or []
        for item in delta.get(section, []):
            idx = item.get("master_index")
            master_item = master_list[idx] if isinstance(idx, int) and 0 <= idx < len(master_list) else {}
            for b_idx, bullet in enumerate(item.get("bullets", [])):
                src = bullet.get("source")
                if src not in ("rewrite", "add"):
                    continue
                pairs.append({
                    "pair_id":     f"{section}[{idx}].bullets[{b_idx}]",
                    "source":      src,
                    "text":        bullet.get("text", ""),
                    "original":    bullet.get("original", "") if src == "rewrite" else "",
                    "support":     bullet.get("support", []) if src == "add" else [],
                    "skill_tags":  master_item.get("skill_tags", []),
                    "domain_tags": master_item.get("domain_tags", []),
                })
    return pairs


FUZZ_THRESHOLD = 70   # token_set_ratio; at/above this a bullet is close enough to its source to auto-pass


def _source_text(pair: dict) -> str:
    """The material a bullet must trace back to: its origin + supporting context."""
    parts = [pair.get("original", "")]
    parts += list(pair.get("support", []) or [])
    parts += list(pair.get("skill_tags", []) or [])
    parts += list(pair.get("domain_tags", []) or [])
    return " ".join(p for p in parts if p)


def prefilter_audit(audit_pairs: list[dict], threshold: int = FUZZ_THRESHOLD) -> tuple[list[dict], list[dict]]:
    """Layer 1 — rapidfuzz. Split pairs into (escalate_to_haiku, auto_passed).

    A bullet whose text closely matches its source material (high token_set_ratio)
    is almost certainly faithful, so it skips the LLM check. Everything else
    escalates to Haiku for a semantic fabrication review.
    """
    escalate, auto_passed = [], []
    for pair in audit_pairs:
        src = _source_text(pair)
        score = fuzz.token_set_ratio(pair.get("text", ""), src) if src else 0.0
        if src and score >= threshold:
            auto_passed.append({
                "pair_id": pair["pair_id"],
                "ok": True,
                "novel_claims": [],
                "layer": "rapidfuzz",
                "score": round(score, 1),
            })
        else:
            escalate.append(pair)
    return escalate, auto_passed


def audit(audit_pairs: list[dict]) -> list[dict]:
    if not audit_pairs:
        _zero_audit_usage()
        return []

    escalate, results = prefilter_audit(audit_pairs)
    if not escalate:
        _zero_audit_usage()
        return results

    raw = call_claude(
        system_prompt=S3_SYSTEM,
        user_prompt=S3_USER_TMPL.format(audit_pairs_json=json.dumps(escalate, indent=2)),
        model=MODEL_AUDIT,
        output_schema=S3_SCHEMA,
    )
    try:
        haiku = json.loads(raw)["results"]
        for r in haiku:
            r.setdefault("layer", "haiku")
        results.extend(haiku)
    except (json.JSONDecodeError, KeyError):
        results.append({
            "pair_id": "_unparsed",
            "ok": False,
            "novel_claims": ["Stage 3 returned invalid JSON; bullets were not auto-audited. Re-run to re-check."],
            "layer": "haiku",
        })
    return results


def _zero_audit_usage() -> None:
    """No Haiku call happened — overwrite LAST_USAGE so cost is attributed as $0."""
    claude.LAST_USAGE.clear()
    claude.LAST_USAGE.update({
        "model": MODEL_AUDIT,
        "input_tokens": 0, "output_tokens": 0,
        "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
    })
