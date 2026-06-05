"""One-time calibration for the resume template's char/line budget.

Renders probe resumes through the real render path, then measures the rendered
geometry with pdfplumber to derive:

  CHARS_PER_LINE  — how many characters fit on one bullet line before wrapping
  ONE_PAGE_LINES  — how many text lines fit on a single page (body, ex-header)

Run it transiently (no permanent dependency):

    uv run --with pdfplumber python calibrate_template.py
    uv run --with pdfplumber python calibrate_template.py --font-size 11 --margin 0.5

Copy the printed constants into services/budget.py. Re-run whenever the
template layout, default font size, or default margin changes.
"""
from __future__ import annotations

import argparse
import statistics
import tempfile
from pathlib import Path

import pdfplumber

from services.render import render_pdf

_LOREM = (
    "Engineered a distributed data pipeline that processed millions of records "
    "daily by orchestrating ingestion, validation, and transformation stages "
    "across a fault tolerant streaming architecture with comprehensive monitoring "
    "and automated recovery to guarantee end to end reliability for downstream teams "
)


def _probe_profile(bullet_text: str, n_bullets: int = 1) -> dict:
    return {
        "contact": {"name": "Calibration Probe", "email": "probe@example.com"},
        "target_role": "",
        "experience": [{
            "company": "Probe Co", "title": "Probe", "dates": "2024", "location": "Earth",
            "bullets": [bullet_text] * n_bullets,
        }],
        "projects": [], "skills": {}, "education": [],
    }


def _line_texts(page) -> list[str]:
    """Visual lines on a page, clustered by baseline (handles ascender/descender)."""
    return [ln["text"] for ln in page.extract_text_lines(layout=False)]


def calibrate_chars_per_line(settings: dict) -> int:
    """Render one very long bullet and measure full (wrapped) line lengths."""
    long_bullet = (_LOREM * 4).strip()
    profile = _probe_profile(long_bullet)
    with tempfile.TemporaryDirectory() as d:
        pdf = render_pdf(profile, Path(d) / "cpl", settings=settings)
        with pdfplumber.open(pdf) as doc:
            texts = _line_texts(doc.pages[0])
    lengths = sorted((len(t) for t in texts if len(t) > 30), reverse=True)
    full = lengths[:-1] or lengths
    return int(statistics.median(full)) if full else 0


def calibrate_one_page_lines(settings: dict) -> int:
    """Render many one-line bullets and count text lines that fit on page 1."""
    profile = _probe_profile("Short single line bullet for page capacity probe.", n_bullets=120)
    with tempfile.TemporaryDirectory() as d:
        pdf = render_pdf(profile, Path(d) / "opl", settings=settings)
        with pdfplumber.open(pdf) as doc:
            return len(_line_texts(doc.pages[0]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--font-size", type=int, default=10)
    ap.add_argument("--margin", type=float, default=0.4)
    args = ap.parse_args()
    settings = {"font_size": args.font_size, "margin": args.margin,
                "section_order": ["experience"]}

    cpl = calibrate_chars_per_line(settings)
    opl = calibrate_one_page_lines(settings)

    print(f"# calibrated at font_size={args.font_size}pt, margin={args.margin}in")
    print(f"CHARS_PER_LINE = {cpl}")
    print(f"ONE_PAGE_LINES = {opl}")


if __name__ == "__main__":
    main()
