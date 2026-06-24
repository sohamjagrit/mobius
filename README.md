# Mobius

Local resume tailoring pipeline. Upload your master resume (PDF or DOCX), paste a job description, and get a one-page ATS-friendly PDF tailored to that role — without fabricated claims.

No accounts. No hosting. Runs entirely on your machine against your own Anthropic API key.

## How it works

```
PDF / DOCX
 └── docling (CPU, no OCR)         → markdown
     └── Stage 0 · Sonnet          → master profile JSON  (one-time per resume)
         └── Stage 1 · Sonnet      → keyword list with must_have / nice_to_have
             └── Stage 2 · Sonnet  → delta JSON (selected items + tailored bullets)
                 └── render.py     → Jinja2 → LaTeX → PDF  (tectonic or pdflatex)
```

Stage 2 outputs a **delta** — only what changes — not a full reconstruction. It selects the most JD-relevant items up to your configured counts, rewrites bullets to surface `must_have` keywords, and logs every dropped bullet and unmatched keyword. Nothing is fabricated: every claim must trace back to your master profile.

## Features

- **No fabrication** — hard constraint baked into every prompt. If a keyword has no profile evidence it goes to `keywords_unmatched`, not into a bullet.
- **Pre-tailor keyword scan** — "Analyze JD" runs Stage 1 and immediately shows which keywords are already in your master resume vs. which are gaps, before spending on Stage 2.
- **Live keyword coverage** — after tailoring, a local (no-API) scan updates in real time as you edit bullets.
- **Add gaps to skills** — select missing keywords and add them to a skill category with one click; PDF recompiles instantly.
- **Structured editor** — edit bullets, courses, and skills with per-field character counters against the calibrated one-page budget.
- **Cold outreach generator** — one extra Sonnet call produces a LinkedIn connection note (≤300 chars) and a cold email grounded in your tailored resume.
- **Full history** — every run is saved locally; reload any previous run to view or re-edit.

## Prerequisites

- Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [Tectonic](https://tectonic-typesetting.github.io) for LaTeX compilation
- An [Anthropic API key](https://console.anthropic.com/)

Install Tectonic:

```bash
# macOS
brew install tectonic

# Windows
scoop install tectonic
```

## Setup

```bash
git clone <repo-url>
cd mobius
uv sync
cp .env.example .env
```

Open `.env` and add your key:

```
ANTHROPIC_API_KEY=sk-ant-...
```

## Run

```bash
uv run streamlit run app.py
```

The app opens at `http://localhost:8501`.

**First run:** docling downloads its layout model (~several hundred MB, one-time). Tectonic fetches LaTeX packages on the first PDF compile (~5–10 seconds, cached after).

## Workflow

1. **Onboarding** — upload your master resume. Review and correct the parsed profile.
2. **Configure** — set how many experiences, projects, and education entries to include, bullets per slot, and layout (font, margins, section order). Saved once, reused for every job.
3. **Tailor** — paste a job description. Optionally click "Analyze JD" to preview keyword coverage before running. Click "Tailor resume" to run the full pipeline and get your PDF.
4. **Edit** — use the structured editor (with character counters) or raw LaTeX. Preview updates live. Download a clean PDF with no keyword highlights.
5. **History** — reload any previous run to view or re-edit.

## Cost

| Stage | Model | Typical cost |
|---|---|---|
| 0 — profile structuring (one-time per resume) | Sonnet | ~$0.11 |
| 1 — keyword extraction | Sonnet | ~$0.03 |
| 2 — tailoring | Sonnet | ~$0.09 (with cache hit) |
| Outreach (optional) | Sonnet | ~$0.03 |

Per tailoring run after first setup: **~$0.12**. Stage 2 caches its system prompt — repeat runs within 5 minutes get roughly 90% off on input tokens. If you ran "Analyze JD" before tailoring, Stage 1 is reused at no extra cost.

## Data and privacy

Your resume and all outputs stay in `profiles/` and `tailored/` inside the repo directory — both gitignored. The only data that leaves your machine is the text sent to Anthropic's API.
