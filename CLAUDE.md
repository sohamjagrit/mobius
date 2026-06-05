# Mobius

Resume tailoring pipeline. User uploads their master resume (PDF or DOCX), pastes a job description, and gets a one-page ATS-friendly LaTeX/PDF resume tailored to that JD — without fabricated claims.

Single-user, local-only. Cloned and run on the user's machine. No accounts, no hosting.

## Pipeline shape

```
PDF / DOCX
 └─ docling (no OCR, CPU-only)              → markdown + structured docling JSON
     └─ Stage 0 (Sonnet)                    → master profile JSON (skill_tags, domain_tags per item)
         + JD text + counts/per-item budget + max_chars_per_bullet (from calibration)
         └─ Stage 1 (Sonnet)                → keywords list
             └─ Stage 2 (Sonnet)            → delta JSON (bullets ≤ char cap + skills + decisions)
                 └─ Stage 3 audit           → rapidfuzz Layer 1 (auto-pass) → Haiku Layer 2 (rewrite/add only)
                     └─ apply_delta()       → renderable profile (master + delta merged)
                         └─ render.py       → Jinja LaTeX template → PDF (tectonic preferred, pdflatex fallback)
```

User data lives in-repo under `profiles/` and `tailored/` (both gitignored — see `config.py`). The UI is a Streamlit multipage app: `app.py` (nav entry) + `pages/` + shared `app_common.py`; backend stays in `services/`.

Cost per tailoring run after first-time setup: **~$0.17** (cached profile + caching enabled). First-time setup per user: **~$0.28** (adds Stage 0). Prompt caching is on by default — see `services/claude.py`.

## Files that matter

```
services/
  prompts/       # One module per pipeline stage. Single source of truth for prompts — both
    __init__.py  # the notebook and the app import the S*_SYSTEM / S*_USER_TMPL / S*_SCHEMA names from here.
    stage0_profile.py   # Stage 0 system prompt + user template + S0_SCHEMA (markdown → profile JSON).
    stage1_keywords.py  # Stage 1 (JD → keyword list) + S1_SCHEMA.
    stage2_tailor.py    # Stage 2 (profile + keywords + JD + budget → delta) + S2_SCHEMA.
    stage3_audit.py     # Stage 3 (fabrication audit) + S3_SCHEMA.
  claude.py      # Anthropic SDK wrapper. Caches system prompts via ephemeral cache_control.
                 # Accepts output_schema for guaranteed-valid JSON via output_config.
                 # Exposes LAST_USAGE + cost_usd() for token/cache/cost inspection.
  pipeline.py    # Thin stage functions: parse_resume (PDF + DOCX), structure_profile,
                 # extract_keywords, tailor, build_audit_pairs, audit. No caching inside —
                 # callers handle that.
  budget.py      # Counts + per-bullet char budget. estimate_lines() drives the live "≈ X lines,
                 # ≈ Y% of page" estimate; calculate_char_budget(lines)/max_chars_per_bullet(settings)
                 # derive the per-bullet char cap (from CHARS_PER_LINE, calibrated); bullet_overflows()
                 # is the warn-only post-gen check. Also default_settings(), valid_settings(),
                 # skills_kept(), DEFAULT_SECTION_ORDER, DEFAULT_LINES_PER_BULLET.
  pipeline.py    # (audit) rapidfuzz Layer-1 prefilter (prefilter_audit) auto-passes bullets close
                 # to their source; only low-similarity bullets escalate to Haiku. When none escalate,
                 # the Haiku call is skipped and billed $0. tailor() injects max_chars_per_bullet.
  render.py      # Resume JSON → LaTeX → PDF. Renders via a Jinja2 template (LaTeX-safe \VAR{}
                 # / %% delimiters); auto-detects tailored vs master shape. tectonic else pdflatex.
                 # apply_delta(master, delta) merges Stage 2 delta into master before rendering.
                 # Surfaced keywords are highlighted in blue bold in the rendered PDF.
  history.py     # Tailoring run persistence: save_run / list_runs / load_run under tailored/ type folders.
  templates/
    resume.tex.j2  # The one-page LaTeX layout (navy accent, small-caps section rules). Edit HERE to
                   # change the resume's look. Variables: font_size, margin, section_order (list),
                   # contact fields, experience/projects/education/skills. Bullets are pre-escaped
                   # LaTeX strings (use \VAR{ b }, NOT \VAR{ b | esc } — escaping happens in render.py).
                   # Stick to the proven package set (no JIT-fetched fonts) — re-run calibration if changed.

config.py        # Storage paths: profiles/ (master JSON, settings, docling) + tailored/ (type folders:
                 # delta/, resume/, tex/, pdf/, audit/, jd/, meta/). All gitignored.
app_common.py    # Shared Streamlit logic: load_master, profile_editor, page_fit_selection, run_pipeline,
                 # keyword_panel, structured_editor (+ char counters), recompile_from_editor, sidebar_summary,
                 # bootstrap()/has_profile()/has_settings() for nav gating.
app.py           # Multipage entry: st.navigation gated on setup state (onboarding always; configure once a
                 # resume loads; tailor/audit/history once settings saved).
pages/           # 1_onboarding (upload + review/edit), 2_configure (page-fit + char budget + layout),
                 # 3_tailor (JD → run → structured editor + live preview), 4_audit (report), 5_history.
calibrate_template.py  # One-time: measures CHARS_PER_LINE / ONE_PAGE_LINES for the template via pdfplumber.
                       # Run: uv run --with pdfplumber python calibrate_template.py [--font-size N --margin M]

research/
  trials.ipynb   # End-to-end R&D notebook. Uses an OLD inline copy of the prompts and imports
                 # services.* — safe to leave as-is; prefer editing prompts in services/prompts/.

profiles/        # <hash>.{json,settings.json,docling.md} + .last (gitignored).
tailored/        # One folder per file type (gitignored): delta/, resume/, tex/, pdf/, audit/, jd/, meta/.
                 # Each run is `{date}_{slug}` across all type folders.

.streamlit/
  config.toml    # The app's visual theme — Streamlit-native, NOT custom CSS. Inter (body +
                 # headings) + JetBrains Mono (code), neutral palette + one indigo accent,
                 # 8px radius, widget/sidebar borders. Defines BOTH [theme.light] and
                 # [theme.dark] so the in-app menu can toggle modes. Edit HERE for colors,
                 # fonts, radius — do not inject CSS via st.markdown for theming.
```

## Conventions to follow

- **No comments in code unless they explain WHY**, not what. Identifiers do "what".
- **No emojis.**
- **Terse output to the user.** Don't recap diffs the user just saw.
- **No backwards-compat shims.** Just change the code.
- **Don't pad with try/except** for things that can't actually happen. Validate at boundaries (user input, external APIs) only.
- **Prefer editing existing files** to creating new ones.
- **Never commit anything** unless the user asks.
- This repo is **not a git repo** today. Treat file edits as destructive — there's no `git checkout` safety net.

## Hard rules baked into the prompts (do NOT relax without asking)

1. **No fabrication, ever.** Stage 0 and Stage 2 both refuse to invent. If a JD keyword has no profile evidence, it goes in `keywords_unmatched`, not in a bullet.
2. **`add` bullets require `support`.** Stage 2's only way to introduce new bullets is to cite verbatim quotes from elsewhere in the profile. No `support` array = no add.
3. **Bullets verbatim through Stage 0.** Stage 0 preserves bullets character-for-character, including typos. Light touches happen in Stage 2 only.
4. **No summary/objective section.** Header has the candidate's name, then one verbatim `target_role` line from the JD, then contact. That's it.
5. **User sets the counts + position-indexed bullet caps; Stage 2 picks which items.** The user chooses HOW MANY experiences / projects / education entries to keep, AND a bullet cap per selection slot (slot 0 = most-relevant item, slot 1 = second, etc.). Stage 2 keeps the most JD-relevant items up to the counts, caps each kept item's bullets at its slot cap, orders kept items by relevance, and logs what it dropped.
6. **Per-bullet character cap (page-fit guarantee).** The user picks `lines_per_bullet`; `max_chars_per_bullet` is derived from the calibrated `CHARS_PER_LINE` and passed into Stage 2, which must keep each bullet's `text` within it. Post-gen this is a **warn-only** check (`bullet_overflows`) surfaced in the editor — the pipeline never auto-truncates; the user trims manually.

## Budget (settings) shape — Stage 2 input

```json
{
  "max_experiences": 3,
  "max_projects": 2,
  "max_education": 2,
  "experience_bullets": [4, 3, 3],
  "project_bullets": [3, 3],
  "max_courses": 3,
  "lines_per_bullet": 2,
  "skills_excluded": ["c", "html"],
  "section_order": ["education", "experience", "projects", "skills"],
  "font_size": 10,
  "margin": 0.4
}
```

- `max_*` are counts. If a count >= items available, keep them all; if 0, drop the section.
- Stage 2 selects the most JD-relevant items up to each count and orders kept items by relevance.
- `experience_bullets` / `project_bullets` are **position-indexed** caps: slot 0 = most-relevant kept item, slot 1 = second, etc. Length should equal the corresponding `max_*` count.
- `lines_per_bullet` sets the per-bullet character cap. `tailor()` injects `max_chars_per_bullet = calculate_char_budget(lines_per_bullet)` into the budget the model sees — this key is derived at call time, not stored.
- `max_courses: 0` keeps a kept education entry but hides its courses line.
- `skills_excluded` (lowercased) is applied in `run_pipeline` before Stage 2 via `budget.skills_kept`, so excluded skills never reach the model or the render. Non-destructive — the master profile keeps every parsed skill.
- `section_order`: list controlling which sections appear and in what order in the rendered PDF.
- `font_size`: LaTeX document font size in pt (10 or 11).
- `margin`: page margin in inches (0.4, 0.5, or 0.6).
- Settings are set ONCE at setup, saved to `profiles/<hash>.settings.json`, and reused for every JD.
- `default_settings()` in `services/budget.py` is the UI's preload. `valid_settings()` requires `max_experiences`; legacy-shape settings are treated as stale and re-defaulted on the next configure load.

## Stage 2 delta shape

Stage 2 outputs a **delta** — only what changes — not a full resume reconstruction:

```json
{
  "target_role": "Senior Data Scientist",
  "experience": [
    {
      "master_index": 2,
      "bullets": [
        {"text": "...", "source": "verbatim|rewrite|add",
         "original": "...", "support": [], "keywords_surfaced": ["python", "ml"], "reason": ""}
      ]
    }
  ],
  "projects": [...],
  "skills": [{"category": "languages", "skills": "Python, SQL"}],
  "education": [{"master_index": 0, "relevant_courses": ["Machine Learning"]}],
  "decisions": {
    "bullets_dropped": [{"master_path": "experience[2].bullets[3]", "text": "...", "reason": "..."}],
    "keywords_unmatched": ["anti-money laundering"]
  }
}
```

`apply_delta(master, delta)` in `services/render.py` merges this into the master profile (adds back company/title/dates etc.) before passing to `render_latex()`.

## Keyword highlighting in the PDF

Keywords from `bullets[].keywords_surfaced` are automatically highlighted **blue bold** (`\textcolor{blue!70!black}{\textbf{...}}`) in the rendered PDF. This is a review aid — shows the user exactly what Claude surfaced. Highlighting is done in `render.py` (`_highlight_keywords`) before LaTeX escaping, so the template uses `\VAR{ b }` (no `esc` filter) for bullets.

## Streamlit app (multipage: `app.py` entry + `pages/` + `app_common.py`)

`app.py` calls `app_common.bootstrap()` (loads the last resume via `profiles/.last`) then builds `st.navigation` **gated on setup state**: onboarding is always available; configure unlocks once a resume is loaded; tailor/audit/history unlock once valid settings are saved. The shared sidebar (`sidebar_summary`) shows the app mark, candidate name/email, a page-fit summary, and last-run cost on every page. All page logic lives in `app_common.py`; the `pages/*.py` files are thin wrappers.

- **1 · Onboarding** (`render via profile_editor`). `st.file_uploader` (PDF/DOCX). Hash bytes (SHA256); load `profiles/<hash>.json` if present, else run docling + Stage 0 and save `<hash>.json` + `<hash>.docling.md`. `@st.cache_resource` the `DocumentConverter`. Then a review/edit form ("Save details" rewrites the cached `<hash>.json`). Skill categories are dynamic.
- **2 · Configure** (`page_fit_selection`). Count sliders (how many exp/proj/edu) → per-slot bullet caps ("Most relevant / 2nd / 3rd…") → skill checkboxes (`skills_excluded`) + courses slider → **bullet length** slider (`lines_per_bullet`, shows the derived `≈ N characters per bullet`) → layout (font/margin/section order). Live "≈ X lines, ≈ Y% of page" via `estimate_lines`. "Save settings & start tailoring" writes `<hash>.settings.json`, records `.last`, and `st.switch_page`s to Tailor.
- **3 · Tailor** (`run_pipeline` + structured/LaTeX editor toggle). JD `st.text_area` + optional slug. "Tailor resume" fires Stage 1 → 2 → 3 → render, saving artifacts under `tailored/{delta,resume,tex,pdf,audit,jd,meta}/<date>_<slug>.*`, with per-stage cost meters. **Keyword panel** (semantic): covered/total metric + progress bar; gaps from `decisions.keywords_unmatched` as red badges; covered split into violet (woven in) vs green (already present). **Editor** (left): select Structured or LaTeX. Structured uses four section tabs (Education, Experience, Projects, Skills) with per-field char counters and live recompile; LaTeX is raw source. `.tex`/`.pdf` downloads in both modes. **Preview** (right): base64 `<iframe>` PDF + a pass/flag audit summary linking to the Audit page. Metadata (company/title/dates) is read-only from master — the editor only edits bullet `text` + skills + target_role.
- **4 · Audit.** Full report: checked/passed/flagged metrics; flagged bullets (with `layer` = rapidfuzz/haiku + novel claims); passed list with fuzzy match scores.
- **5 · History** (`services/history`). Lists saved runs (role, date, flagged count, cost); "Reload" loads a run back into session and `st.switch_page`s to Tailor.

`st.session_state` holds: `profile_hash`, `profile`, `budget` (settings), `keywords`, `tailored` (delta), `audit`, `latex`, `pdf_bytes`, `usages`, `out_stem`, plus `ed_*` editor widget keys and `booted`.

**UI conventions** (match the existing style when editing the app):
- **Theme via `.streamlit/config.toml` only** — never inject CSS through `st.markdown(..., unsafe_allow_html=True)` for colors/fonts/spacing. The one allowed raw-HTML exception is the PDF preview `<iframe>` (`pdf_iframe`), which Streamlit can't do natively.
- Material Symbols (`:material/...:`) over emojis for icons on buttons, callouts, expanders.
- Sentence case for titles and labels. `st.caption` for hints, not `st.info`. Badges (`:green-badge[...]`) over bulleted status lists.
- Cross-page navigation uses `st.page_link` / `st.switch_page`; nav gating lives in `app.py` via `has_profile()` / `has_settings()`.

## Onboarding (planned README content, not yet written)

```bash
git clone <repo>
cd mobius
uv sync                               # installs anthropic, docling, streamlit, etc.
cp .env.example .env                  # then add ANTHROPIC_API_KEY
brew install tectonic                 # macOS; Linux: apt/dnf; Windows: scoop
uv run streamlit run app.py
```

First parse downloads docling layout model (~hundreds of MB, one-time). Tectonic downloads LaTeX packages JIT on first compile (~5–10 s, cached after).

## TODOs before sharing (in priority order)

1. ~~**Build the app.**~~ DONE — multipage flow (onboarding/configure/tailor/audit/history), char budgets, rapidfuzz+Haiku audit, structured/LaTeX editor toggle, `profiles/` + `tailored/` storage (gitignored).
2. **Fill in few-shot examples** in the `services/prompts/` package (one file per stage). Stage 2's examples are the highest leverage (4 cases: verbatim / rewrite / add-with-support / rejected-add). Stage 0 wants 1 example. Stage 3 wants 2 (clean rewrite + subtle fabrication).
3. **Write `README.md`** with the onboarding steps above.
4. **Add `.env.example`** with `ANTHROPIC_API_KEY=` placeholder.
5. ~~**Remove personal data.**~~ DONE — user data lives in gitignored `profiles/` and `tailored/`.

## Known behavior / gotchas

- **Audit is two-layer.** `pipeline.prefilter_audit` (rapidfuzz `token_set_ratio`, threshold 70) auto-passes bullets whose `text` closely matches their source material; only low-similarity bullets escalate to Haiku. If nothing escalates, the Haiku call is skipped and `_zero_audit_usage()` makes the Stage 3 cost $0. Auto-passed results carry `layer: "rapidfuzz"` + a `score`; Haiku results carry `layer: "haiku"`.
- **Stage 3 (Haiku) occasionally emits invalid JSON.** `pipeline.audit` catches the `JSONDecodeError` and returns one advisory flag (`pair_id: "_unparsed"`, `ok: false`) instead of crashing the run. The tailored resume still renders; the audit panel shows the advisory so the user knows to re-run. Don't "fix" this by removing the try/except — it's a real external-boundary guard.
- **Char budget is warn-only.** `bullet_overflows` flags bullets over `max_chars_per_bullet` in the editor; the pipeline never auto-truncates. `CHARS_PER_LINE`/`ONE_PAGE_LINES` in `services/budget.py` are calibrated against `resume.tex.j2` — re-run `calibrate_template.py` if the template/default font/margin changes.
- **Settings migration:** `valid_settings()` requires the `max_experiences` key. Any old `<hash>.settings.json` using a different shape (e.g. the legacy `selected_experiences` shape) is treated as stale and silently re-defaulted on the next configure load.
- **Skill exclusion is reversible** — the master `<hash>.json` keeps every parsed skill; only `skills_excluded` in settings hides them, applied in `run_pipeline` before Stage 2.
- **Keyword highlighting is review-only** — it appears in every tailored PDF render. If the user wants a clean final PDF without highlights, they can clear `keywords_surfaced` from the saved JSON or re-render the master profile directly.
- **Skill categories are dynamic** — Stage 0 infers category names from the resume content. There is no hardcoded `SKILL_CATEGORIES` list anywhere. The profile's `skills` dict keys are the ground truth.

## Decisions already settled — do not re-litigate

- **Output format**: structured JSON, rendered via `services/render.py` to LaTeX → PDF. Not markdown, not plain text.
- **Stage 0 = caching is per-profile (file hash), not per-JD.** Don't re-run Stage 0 on every tailoring run.
- **Tailoring input includes the raw JD**, not just the keyword list. The model has the JD for tone/positioning context; the no-fabrication rule prevents drift.
- **`add` bullets allowed only with `support` quotes** from elsewhere in the profile. This is the answer to "if missing but similar experience, add a sentence" — implemented as a hard contract, not a soft suggestion.
- **No summary section.** Header has `target_role` verbatim from the JD. That's the only JD-derived text in the header.
- **Stage 2 outputs a delta, not a full reconstruction.** `apply_delta()` in `render.py` merges it with the master before rendering. The master profile is never mutated.
- **JD relevance drives item selection AND ordering.** The user picks counts (how many to keep); Stage 2 chooses the most JD-relevant items up to those counts and orders them by relevance.
- **Structured output via `output_config`.** All four stages use `output_schema` in `call_claude()` for guaranteed-valid JSON. No `parse_json_blob` fallback needed.
- **No accounts, no hosting.** Clone-and-run only. API key from `.env` only — no in-app input.

## Cost model

| Stage | Model | Per-run cost (warm cache) |
|---|---|---|
| 0 (one-time per user) | Sonnet 4.6 | ~$0.11 |
| 1 | Sonnet 4.6 | ~$0.03 |
| 2 | Sonnet 4.6 | ~$0.09 (with cache hit) |
| 3 | Haiku 4.5 | ~$0.005 (often **$0** — skipped when rapidfuzz auto-passes all bullets) |

Per tailoring run after first setup: **~$0.17**. The Stage 2 system prompt is cached (`cache_control: ephemeral`) — repeat runs within 5 min get ~90% off on those tokens.

## Run commands

```bash
# notebook R&D
uv run jupyter lab

# render any profile JSON to PDF (bare `python` is not on PATH — use uv run)
uv run python -m services.render profiles/<hash>.json
uv run python -m services.render tailored/resume/<date>_<slug>.json

# recalibrate the char/line budget after template/font/margin changes
uv run --with pdfplumber python calibrate_template.py

# Streamlit app (default workflow)
uv run streamlit run app.py
```

## Environment

- Python 3.12+. Uses `uv` for env management.
- macOS-only assumptions today: `brew install tectonic`, and docling's MPS-float64 workaround (forces CPU in `parse_resume`). The CPU forcing is harmless on Linux/Windows; the brew step needs a non-mac equivalent (`apt install tectonic` / `scoop install tectonic`) in the README.
- `.env` at repo root: `ANTHROPIC_API_KEY=sk-ant-...`. `services/claude.py` loads it via `python-dotenv`.
