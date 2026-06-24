"""Cached first-page thumbnails of a base resume, for the role-picker tiles.

Best-effort: rendering/compiling can fail (no tectonic, bad LaTeX). Callers get
None and show a fallback rather than breaking the page. Cached on disk keyed by
the profile content + the layout-affecting settings, so edits or a font/margin/
section-order change rebuild, but reruns are free.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from io import BytesIO
from pathlib import Path

import config
from .render import render_latex, compile_latex_bytes

THUMBS = config.PROFILES / ".thumbs"
_LAYOUT_KEYS = ("section_order", "font_size", "margin")


def _key(profile: dict, settings: dict) -> str:
    sig = {"p": profile, "s": {k: (settings or {}).get(k) for k in _LAYOUT_KEYS}}
    return hashlib.sha256(json.dumps(sig, sort_keys=True, default=str).encode()).hexdigest()[:20]


def _path(profile: dict, settings: dict) -> Path:
    return THUMBS / f"{_key(profile, settings)}.png"


def is_cached(profile: dict, settings: dict) -> bool:
    return _path(profile, settings).exists()


def role_thumbnail(profile: dict, settings: dict, scale: float = 2.0) -> bytes | None:
    """PNG bytes of the resume's first page (top-cropped to a card aspect)."""
    if not profile:
        return None
    out = _path(profile, settings)
    if out.exists():
        return out.read_bytes()

    try:
        import pypdfium2 as pdfium

        latex = render_latex(profile, settings=settings, highlight_keywords=False)
        with tempfile.TemporaryDirectory() as d:
            pdf = compile_latex_bytes(latex, Path(d), stem="thumb")
        doc = pdfium.PdfDocument(pdf)
        img = doc[0].render(scale=scale).to_pil()
        crop_h = min(img.height, int(img.width * 1.15))
        img = img.crop((0, 0, img.width, crop_h))
        buf = BytesIO()
        img.save(buf, format="PNG")
        png = buf.getvalue()
    except Exception:
        return None  # best-effort preview; never block tailoring on a render failure

    THUMBS.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png)
    return png
