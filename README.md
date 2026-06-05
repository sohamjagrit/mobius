# Mobius

Local resume tailoring pipeline. Upload your master resume (PDF or DOCX), paste a job description, and get a one-page ATS-friendly PDF tailored to that role — without fabricated claims.

No accounts. No hosting. Runs entirely on your machine against your own Anthropic API key.

## Prerequisites

- Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [Tectonic](https://tectonic-typesetting.github.io) for LaTeX compilation
- An [Anthropic API key](https://console.anthropic.com/)

Install Tectonic:

```bash
# macOS
brew install tectonic

# Debian / Ubuntu
apt install tectonic

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

Open `.env` and set your API key:

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

1. **Onboarding** — upload your master resume. Review and correct the parsed output.
2. **Configure** — set how many experiences, projects, and education entries to include, bullets per slot, and layout options. Saved once and reused for every job.
3. **Tailor** — paste a job description and run. The pipeline extracts keywords, writes a tailored delta, audits for fabrication, and renders a PDF.
4. **Audit** — review which bullets were rewritten or added and whether any flagged claims need attention.
5. **History** — reload any previous run to view or re-edit.

## Cost

| Stage | Model | Typical cost |
|---|---|---|
| 0 — profile (one-time per resume) | Sonnet | ~$0.11 |
| 1 — keywords | Sonnet | ~$0.03 |
| 2 — tailoring | Sonnet | ~$0.09 (with cache hit) |
| 3 — fabrication audit | Haiku | ~$0.005 (often $0 — skipped when rapidfuzz auto-passes all bullets) |

Per tailoring run after first setup: **~$0.17**. Stage 2 caches its system prompt — repeat runs within 5 minutes get roughly 90% off on input tokens.

## User data

Your resume and tailored outputs stay in `profiles/` and `tailored/` inside the repo, both gitignored. Nothing leaves your machine except API calls to Anthropic.
