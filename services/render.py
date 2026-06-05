"""Render a resume JSON to LaTeX, then to PDF.

Accepts either Stage 0 output (master profile, top-level `contact` etc.)
or Stage 2 output (tailored, wrapped in `resume`). Per-bullet metadata
from Stage 2 (`source`, `reason`, `support`, …) is ignored — only `text`
is rendered.

Requires `tectonic` (preferred) or `pdflatex` on PATH. On macOS:
    brew install tectonic               # single binary, auto-fetches packages
    brew install --cask basictex        # alt: pdflatex, then `tlmgr install enumitem titlesec`

CLI:
    python -m services.render resumes/soham_jagrit_ironclad_ai.json
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import jinja2

_TEMPLATES = Path(__file__).parent / "templates"


_ESCAPE = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "$": r"\$",
    "&": r"\&",
    "#": r"\#",
    "^": r"\textasciicircum{}",
    "_": r"\_",
    "~": r"\textasciitilde{}",
    "%": r"\%",
}


def esc(s: Any) -> str:
    if s is None:
        return ""
    out = str(s)
    for k, v in _ESCAPE.items():
        out = out.replace(k, v)
    return out


def _highlight_keywords(text: str, keywords: list[str]) -> str:
    """Return LaTeX-escaped text with surfaced keywords wrapped in a color command."""
    if not keywords:
        return esc(text)
    pattern = re.compile(
        "|".join(re.escape(k) for k in sorted(keywords, key=len, reverse=True)),
        re.IGNORECASE,
    )
    parts: list[str] = []
    last = 0
    for m in pattern.finditer(text):
        parts.append(esc(text[last:m.start()]))
        parts.append(r"\textcolor{blue!70!black}{\textbf{" + esc(m.group()) + r"}}")
        last = m.end()
    parts.append(esc(text[last:]))
    return "".join(parts)


def _process_bullet(b: Any, *, highlight_keywords: bool = True) -> str:
    if isinstance(b, dict):
        text = b.get("text", "")
        if not highlight_keywords:
            return esc(text)
        kws = [k for k in (b.get("keywords_surfaced") or []) if k]
        return _highlight_keywords(text, kws)
    return esc(str(b))


def _join(items: list[str], sep: str = " $\\cdot$ ") -> str:
    return sep.join(x for x in items if x)


def _unwrap(profile: dict) -> tuple[dict, str]:
    """Tailored output wraps profile in `resume`; master is at top level."""
    if "resume" in profile and isinstance(profile["resume"], dict):
        r = profile["resume"]
        return r, r.get("target_role") or r.get("target_roles", "")
    return profile, profile.get("target_role") or profile.get("target_roles", "")


_env = jinja2.Environment(
    block_start_string=r"\BLOCK{", block_end_string="}",
    variable_start_string=r"\VAR{", variable_end_string="}",
    comment_start_string=r"\#{", comment_end_string="}",
    line_statement_prefix="%%", line_comment_prefix="%#",
    trim_blocks=True, lstrip_blocks=True, autoescape=False,
    loader=jinja2.FileSystemLoader(str(_TEMPLATES)),
)
_env.filters["esc"] = esc


def _strip_url(u: Any) -> str:
    return re.sub(r"^https?://(www\.)?", "", str(u or "")).rstrip("/")


def _norm_item(item: dict, *, highlight_keywords: bool = True) -> dict:
    out = dict(item)
    out["bullets"] = [
        t for t in (_process_bullet(b, highlight_keywords=highlight_keywords) for b in item.get("bullets", []))
        if t
    ]
    return out


def _skills_pairs(skills: Any) -> list[tuple[str, str]]:
    """Non-empty skill categories as (Title Cased label, value) in profile order."""
    if not isinstance(skills, dict):
        return []
    pairs = []
    for cat, val in skills.items():
        value = val if isinstance(val, str) else ", ".join(val or [])
        if value:
            pairs.append((cat.replace("_", " ").title(), value))
    return pairs


_DEFAULT_SECTION_ORDER = ["education", "experience", "projects", "skills"]


def render_latex(
    profile: dict,
    settings: dict | None = None,
    template: str = "resume.tex.j2",
    *,
    highlight_keywords: bool = True,
) -> str:
    r, target_role = _unwrap(profile)
    contact = r.get("contact", {}) or {}
    s = settings or {}

    def _link(raw_url: str, label: str) -> str:
        full = raw_url if raw_url.startswith("http") else "https://" + raw_url
        display = esc(_strip_url(raw_url))
        return rf"\href{{{full}}}{{{label}: {display}}}"

    parts = [esc(contact.get("phone", "")), esc(contact.get("email", ""))]
    if contact.get("linkedin_url"):
        parts.append(_link(contact["linkedin_url"], "LinkedIn"))
    if contact.get("github_url"):
        parts.append(_link(contact["github_url"], "GitHub"))
    contact_line = _join([p for p in parts if p])

    ctx = {
        "contact": contact,
        "target_role": target_role,
        "contact_line": contact_line,
        "education": r.get("education", []) or [],
        "experience": [
            _norm_item(e, highlight_keywords=highlight_keywords)
            for e in (r.get("experience", []) or []) if e.get("company")
        ],
        "projects": [
            _norm_item(p, highlight_keywords=highlight_keywords)
            for p in (r.get("projects", []) or []) if p.get("name")
        ],
        "skills":     _skills_pairs(r.get("skills")),
        "section_order": s.get("section_order") or _DEFAULT_SECTION_ORDER,
        "font_size":     s.get("font_size", 10),
        "margin":        s.get("margin", 0.4),
    }
    return _env.get_template(template).render(**ctx)


def compile_latex_bytes(latex: str, work_dir: Path, stem: str = "resume") -> bytes:
    work_dir.mkdir(parents=True, exist_ok=True)
    tex_path = work_dir / f"{stem}.tex"
    tex_path.write_text(latex, encoding="utf-8")
    return compile_pdf(tex_path).read_bytes()


def compile_pdf(tex_path: Path) -> Path:
    work = tex_path.parent
    pdf_path = tex_path.with_suffix(".pdf")

    if shutil.which("tectonic"):
        cmd = ["tectonic", "--keep-logs", "--chatter", "minimal", tex_path.name]
    elif shutil.which("pdflatex"):
        cmd = ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", tex_path.name]
    else:
        raise RuntimeError(
            "Neither tectonic nor pdflatex found on PATH. Install one:\n"
            "  brew install tectonic                     (single binary)\n"
            "  brew install --cask basictex              (then: sudo tlmgr install enumitem titlesec)\n"
            "Or compile the .tex elsewhere (Overleaf)."
        )

    result = subprocess.run(cmd, cwd=work, capture_output=True, text=True)
    if result.returncode != 0 or not pdf_path.exists():
        log = tex_path.with_suffix(".log")
        log_tail = log.read_text(encoding="utf-8", errors="ignore")[-2000:] if log.exists() else ""
        stderr_tail = (result.stderr or "")[-1000:]
        raise RuntimeError(
            f"{cmd[0]} failed.\n\n--- stderr ---\n{stderr_tail}\n\n--- log tail ---\n{log_tail}"
        )
    for ext in (".aux", ".log", ".out"):
        p = tex_path.with_suffix(ext)
        if p.exists():
            p.unlink()
    return pdf_path


def apply_delta(master: dict, delta: dict, budget: dict | None = None) -> dict:
    """Merge a Stage 2 delta into the master profile to produce a renderable resume.

    The delta already contains only the selected items in JD-relevance order
    (Stage 2 chose which items). Master provides structural fields the delta omits.
    """
    master_exp  = master.get("experience", []) or []
    master_proj = master.get("projects", []) or []
    master_edu  = master.get("education", []) or []

    edu_delta = {item["master_index"]: item for item in delta.get("education", [])}

    experience = []
    for item in delta.get("experience", []):
        i = item["master_index"]
        if 0 <= i < len(master_exp):
            merged = dict(master_exp[i])
            merged["bullets"] = item["bullets"]
            experience.append(merged)

    projects = []
    for item in delta.get("projects", []):
        i = item["master_index"]
        if 0 <= i < len(master_proj):
            merged = dict(master_proj[i])
            merged["bullets"] = item["bullets"]
            projects.append(merged)

    education = []
    for item in delta.get("education", []):
        i = item["master_index"]
        if 0 <= i < len(master_edu):
            merged = dict(master_edu[i])
            merged["relevant_courses"] = item.get("relevant_courses", merged.get("relevant_courses", []))
            education.append(merged)

    skills_raw = delta.get("skills", [])
    skills = (
        {s["category"]: s["skills"] for s in skills_raw}
        if isinstance(skills_raw, list)
        else (skills_raw or {})
    )

    return {
        "contact":    master.get("contact", {}),
        "target_role": delta.get("target_role", ""),
        "experience": experience,
        "projects":   projects,
        "skills":     skills,
        "education":  education,
    }


def render_pdf(profile: dict, out_stem: Path, settings: dict | None = None) -> Path:
    tex_path = out_stem.with_suffix(".tex")
    tex_path.write_text(render_latex(profile, settings=settings), encoding="utf-8")
    return compile_pdf(tex_path)


def _main():
    if len(sys.argv) < 2:
        print("usage: python -m services.render <resume.json> [out_stem]", file=sys.stderr)
        sys.exit(2)
    json_path = Path(sys.argv[1])
    out_stem = Path(sys.argv[2]) if len(sys.argv) > 2 else json_path.with_suffix("")
    profile = json.loads(json_path.read_text(encoding="utf-8"))
    pdf = render_pdf(profile, out_stem)
    print(f"Wrote {pdf}")


if __name__ == "__main__":
    _main()
