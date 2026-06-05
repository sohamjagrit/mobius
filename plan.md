# Resume Tailoring App — Full Implementation Plan

## Overview

An open-source resume tailoring app for students. Students upload a master resume, configure section budgets, paste a job description, and get a tailored one-page resume — with a structured editor, live PDF preview, and hallucination auditing.

**Stack:** Python, Streamlit, Anthropic API (Sonnet for tailoring, Haiku for audit), Docling, LaTeX (Tectonic), rapidfuzz

---

## Architecture Summary

```
Master Resume (PDF/DOCX)
        │
        ▼
   Docling Parser ──► Structured Markdown ──► User Review/Edit (Streamlit)
                                                       │
                                                       ▼
                                              Source-of-Truth JSON
                                                       │
                            ┌──────────────────────────┤
                            │                          │
                            ▼                          ▼
                   Budget Configuration         Job Description
                   (user-defined per section)    (pasted by user)
                            │                          │
                            └──────────┬───────────────┘
                                       │
                                       ▼
                              Claude Sonnet API
                              (single-shot tailoring call)
                                       │
                                       ▼
                              Structured JSON Output
                                       │
                         ┌─────────────┼─────────────┐
                         │             │             │
                         ▼             ▼             ▼
                  Structured      LaTeX Template   Hallucination
                  Editor UI       + Tectonic       Audit Layer
                  (per-field      Compile          (rapidfuzz +
                  textboxes +                      Haiku)
                  char counters)       │
                         │             ▼                │
                         │        PDF Preview           ▼
                         │        (live, debounced)  Audit Report
                         │             │             (separate page)
                         └──────┬──────┘
                                ▼
                         User Tweaks
                         (edit fields → recompile → iterate)
                                │
                                ▼
                         Final PDF Download
                         (saved to history)
```

---

## Phase 1 — Onboarding & Master Resume

### What it does
Student uploads their master resume (the "everything" resume, can be multi-page). Docling parses it into structured markdown. Student reviews and corrects it in a Streamlit editor. This becomes the source-of-truth for all tailoring.

### Implementation details

1. **File upload**: Streamlit `file_uploader` accepting `.pdf` and `.docx`
2. **Docling parsing**: Convert to structured markdown with sections identified
   - Sections to extract: Contact Info, Education, Experience (multiple), Projects (multiple), Skills, Relevant Courses, Certifications (optional)
   - Each experience/project should be parsed into: title, organization, date range, bullet points
3. **User review UI**: Streamlit text editors per section so user can correct parsing errors
4. **Storage**: Save as a structured JSON file locally
   ```json
   {
     "contact": { "name": "", "email": "", "phone": "", "linkedin": "", "github": "" },
     "education": { "school": "", "degree": "", "gpa": "", "graduation": "" },
     "experiences": [
       {
         "id": "exp_1",
         "title": "",
         "company": "",
         "dates": "",
         "bullets": ["...", "..."]
       }
     ],
     "projects": [
       {
         "id": "proj_1",
         "name": "",
         "tech_stack": "",
         "dates": "",
         "bullets": ["...", "..."]
       }
     ],
     "skills": { "languages": [], "frameworks": [], "tools": [], "other": [] },
     "courses": []
   }
   ```

### Decisions
- Docling may not perfectly parse every resume format — the review step catches this
- Store master JSON at `~/.resumeapp/master.json` or equivalent
- Consider validating that required sections exist before proceeding

---

## Phase 2 — Budget Configuration

### What it does
Student configures how much space each section gets on the one-page resume. They pick which experiences/projects to include, how many bullets per item, and how many lines per bullet. The app converts these line budgets into character budgets using a pre-calibrated constant.

### Implementation details

1. **Template calibration constant** (DO THIS FIRST — see calibration section below)
   ```python
   CHARS_PER_LINE = <measured_value>  # e.g., 85 for your template
   ```

2. **Budget config UI in Streamlit**:
   - Select which experiences to include (checkboxes from master list)
   - For each selected experience: number of bullets (slider 1-5), lines per bullet (slider 1-3)
   - Same for projects
   - Skills: total lines budget (slider 1-3)
   - Courses: total lines budget (slider 1-2)
   - Show a running "total lines used / total lines available" counter

3. **Smart defaults**:
   ```python
   DEFAULTS = {
       "num_experiences": 2,
       "bullets_per_experience": 3,
       "lines_per_bullet": 2,
       "num_projects": 2,
       "bullets_per_project": 3,
       "lines_per_bullet_project": 2,
       "skills_lines": 2,
       "courses_lines": 1,
   }
   ```

4. **Budget calculation**:
   ```python
   def calculate_char_budget(lines, chars_per_line):
       # Safety margin: 95% of theoretical max
       return int(lines * chars_per_line * 0.95)
   ```

5. **Total page budget validation**:
   - Measure total available content lines for your template (excluding headers, spacing, contact info)
   - Sum all user-allocated lines
   - Warn if total exceeds available lines (red counter)
   - This catches overflow BEFORE calling Claude

### Template Calibration (one-time setup)

**TODO: Soham needs to do this step.**

Process:
1. Take your fixed LaTeX template
2. In one content field (e.g., an experience bullet), insert a string of known length: `"a" * 200`
3. Compile with Tectonic
4. Check the PDF — count how many characters fit on one line before wrapping
5. That number is your `CHARS_PER_LINE`
6. Also measure: total content lines available on one page (count rendered lines in a "full" resume)
7. Store both as constants:
   ```python
   CHARS_PER_LINE = ??       # e.g., 85
   TOTAL_CONTENT_LINES = ??  # e.g., 45
   ```

---

## Phase 3 — Tailoring Engine (Single Claude Call)

### What it does
Takes the master resume markdown, user's budget config (as character limits), and a pasted job description. Makes a single Claude Sonnet API call. Returns structured JSON fitting within all budgets.

### Implementation details

1. **API call config**:
   ```python
   model = "claude-sonnet-4-20250514"
   temperature = 0  # maximize consistency
   ```

2. **System prompt** (draft — refine based on testing):

   ```
   You are a resume tailoring expert for students. Your job is to take a student's
   master resume and a job description, and produce a tailored resume that maximizes
   the student's chances of getting an interview.

   CRITICAL RULES:
   1. You may ONLY use information from the master resume. Do not invent, fabricate,
      or embellish any experience, skill, project, or achievement. If the master
      resume says "contributed to," you must not write "led" or "spearheaded."
   2. You must stay STRICTLY within the character limits provided for each field.
      If a field has a max of 170 characters, your output for that field must be
      ≤ 170 characters. Count carefully. This is non-negotiable.
   3. Tailor content to the job description by:
      - Prioritizing relevant experience and skills
      - Using keywords from the JD naturally (not keyword-stuffing)
      - Reordering bullet points so the most relevant appear first
      - Adjusting phrasing to align with the role's language
   4. Every bullet point should follow the STAR format where possible:
      accomplished [X] as measured by [Y] by doing [Z]
   5. Use strong action verbs. Quantify achievements where data exists in the master.

   OUTPUT FORMAT:
   Return ONLY valid JSON matching the schema provided. No markdown, no commentary.
   ```

3. **User message construction**:
   ```python
   user_message = f"""
   ## Master Resume
   {master_markdown}

   ## Job Description
   {job_description}

   ## Budget Configuration
   Generate content for the following fields with STRICT character limits:

   ### Experiences
   {format_experience_budgets(budget_config)}
   # Example output per experience:
   # - exp_1 (Software Engineer Intern @ Google):
   #   - bullet_1: max 170 chars
   #   - bullet_2: max 170 chars
   #   - bullet_3: max 170 chars

   ### Projects
   {format_project_budgets(budget_config)}

   ### Skills
   {format_skills_budget(budget_config)}

   ### Relevant Courses
   {format_courses_budget(budget_config)}

   ## Output Schema
   {json_schema}
   """
   ```

4. **JSON Schema for output**:
   ```json
   {
     "experiences": [
       {
         "id": "exp_1",
         "title": "string (from master, unchanged)",
         "company": "string (from master, unchanged)",
         "dates": "string (from master, unchanged)",
         "bullets": ["string (max N chars)", "..."]
       }
     ],
     "projects": [
       {
         "id": "proj_1",
         "name": "string (from master, unchanged)",
         "tech_stack": "string (tailored to JD, from master skills only)",
         "dates": "string (from master, unchanged)",
         "bullets": ["string (max N chars)", "..."]
       }
     ],
     "skills": {
       "languages": "string (max N chars, single line)",
       "frameworks": "string (max N chars, single line)",
       "tools": "string (max N chars, single line)"
     },
     "courses": "string (max N chars)"
   }
   ```

5. **Post-generation validation** (before rendering):
   ```python
   def validate_output(output_json, budget_config):
       violations = []
       for exp in output_json["experiences"]:
           for i, bullet in enumerate(exp["bullets"]):
               max_chars = budget_config[exp["id"]][f"bullet_{i}"]["max_chars"]
               if len(bullet) > max_chars:
                   violations.append({
                       "field": f"{exp['id']}.bullet_{i}",
                       "actual": len(bullet),
                       "limit": max_chars,
                       "overshoot": len(bullet) - max_chars
                   })
       return violations
   ```
   If violations exist, either truncate gracefully (trim to last complete word within limit) or display as warnings in the editor.

### Key considerations
- The system prompt emphasizes character counting because Claude is reasonably good at this but not perfect — hence the post-validation
- Temperature 0 reduces variance in output length
- Keeping title, company, dates unchanged from master avoids hallucination in metadata fields
- The `id` field links output back to master for the audit layer

---

## Phase 4 — Structured Editor + Live Preview

### What it does
After Claude generates the JSON, Streamlit displays a structured editor: one textbox per field (per bullet, per skill line, etc.) with character counters. A live PDF preview updates on every keystroke (debounced). Student tweaks until satisfied.

### Implementation details

1. **Editor layout** (Streamlit two-column):
   ```
   ┌─────────────────────────┬──────────────────────┐
   │  STRUCTURED EDITOR      │  PDF PREVIEW          │
   │                         │                       │
   │  ── Experience 1 ──     │                       │
   │  [Role @ Company]       │   ┌───────────────┐   │
   │  [Bullet 1........]     │   │               │   │
   │           142/170 chars  │   │   Rendered    │   │
   │  [Bullet 2........]     │   │     PDF       │   │
   │           158/170 chars  │   │               │   │
   │  [Bullet 3........]     │   │               │   │
   │           130/170 chars  │   │               │   │
   │                         │   │               │   │
   │  ── Project 1 ──        │   │               │   │
   │  [Bullet 1........]     │   └───────────────┘   │
   │            98/170 chars  │                       │
   │  ...                    │                       │
   └─────────────────────────┴──────────────────────┘
   ```

2. **Character counter behavior**:
   - Green: ≤ 90% of budget
   - Yellow: 90-100% of budget
   - Red: > 100% of budget (overflow warning)

3. **Debounced live compilation**:
   ```python
   # Use streamlit-debounce or a timer-based approach
   # On each edit:
   # 1. Update the JSON from textbox values
   # 2. Fill LaTeX template with updated JSON
   # 3. Compile with Tectonic (subprocess)
   # 4. Display PDF in right panel

   import subprocess
   import time

   def compile_latex(tex_content, output_dir):
       tex_path = f"{output_dir}/resume.tex"
       with open(tex_path, "w") as f:
           f.write(tex_content)
       result = subprocess.run(
           ["tectonic", tex_path],
           capture_output=True, text=True, timeout=10
       )
       if result.returncode == 0:
           return f"{output_dir}/resume.pdf"
       return None
   ```

4. **Template filling**:
   ```python
   def fill_template(template_str, resume_json):
       # Replace placeholders in LaTeX template with JSON values
       # Use string replacement or Jinja2 with LaTeX-safe escaping
       filled = template_str
       for exp in resume_json["experiences"]:
           for i, bullet in enumerate(exp["bullets"]):
               placeholder = f"%%{exp['id']}_bullet_{i}%%"
               filled = filled.replace(placeholder, latex_escape(bullet))
       # ... same for projects, skills, courses
       return filled
   ```

5. **Streamlit debounce consideration**:
   - Tectonic compilation takes ~1-2 seconds
   - Debounce at 500ms-1000ms after last keystroke
   - Show a small "compiling..." spinner during compilation
   - Cache the last successful PDF so the preview doesn't flash blank

---

## Phase 5 — Hallucination Audit

### What it does
Checks that Claude's tailored output doesn't invent information not in the master resume. Two layers: rapidfuzz for string matching, Haiku for semantic/nuance checks. Results shown as a separate audit report page.

### Implementation details

1. **Layer 1 — rapidfuzz matching**:
   ```python
   from rapidfuzz import fuzz, process

   def audit_string_match(generated_bullet, master_bullets, threshold=60):
       """
       Check if the generated bullet can be traced back to master content.
       Returns best match and similarity score.
       """
       best_match = process.extractOne(
           generated_bullet,
           master_bullets,
           scorer=fuzz.token_sort_ratio
       )
       if best_match and best_match[1] >= threshold:
           return {"status": "pass", "match": best_match[0], "score": best_match[1]}
       else:
           return {"status": "flag", "match": best_match[0] if best_match else None,
                   "score": best_match[1] if best_match else 0}
   ```

2. **Layer 2 — Haiku semantic check** (only for flagged items from Layer 1):
   ```python
   haiku_prompt = """
   You are a resume audit assistant. Compare the GENERATED bullet point against
   the SOURCE content from the student's master resume.

   Flag if ANY of the following are true:
   1. FABRICATION: The generated bullet mentions skills, tools, technologies,
      or achievements not present in the source
   2. INFLATION: The generated bullet exaggerates scope (e.g., "contributed to"
      becomes "led" or "spearheaded")
   3. METRIC INVENTION: Numbers or percentages that don't appear in the source
   4. ROLE INFLATION: Job responsibilities elevated beyond what's in the source

   GENERATED: {generated_bullet}

   SOURCE CONTENT (all bullets from this role in master resume):
   {source_bullets}

   Respond in JSON:
   {
     "verdict": "pass" | "flag",
     "issue_type": null | "fabrication" | "inflation" | "metric_invention" | "role_inflation",
     "explanation": "brief explanation if flagged",
     "original_source": "the specific source text this maps to, or null"
   }
   """
   ```

3. **Audit report UI** (separate Streamlit page/tab):
   ```
   ┌──────────────────────────────────────────────┐
   │  AUDIT REPORT                                │
   │                                              │
   │  ✅ Experience 1, Bullet 1 — PASS (92% match)│
   │  ⚠️ Experience 1, Bullet 2 — FLAGGED         │
   │     Issue: INFLATION                         │
   │     Generated: "Led a team of 5 engineers"   │
   │     Source: "Worked with a team of engineers" │
   │     Suggestion: Change "Led" to "Collaborated│
   │     with"                                    │
   │                                              │
   │  ✅ Project 1, Bullet 1 — PASS (87% match)   │
   │  ...                                         │
   │                                              │
   │  Summary: 8/10 passed, 2 flagged             │
   └──────────────────────────────────────────────┘
   ```

4. **Audit trigger**: Run automatically after Claude generates output, before user enters the editor. Show a badge on the audit tab ("2 items flagged").

---

## Phase 6 — History & Persistence

### What it does
Each tailored resume is saved with its JD, so students can go back to previous versions.

### Implementation details

1. **Storage structure**:
   ```
   ~/.resumeapp/
   ├── master.json
   ├── config.json  (CHARS_PER_LINE, template path, defaults)
   └── history/
       ├── 2026-06-04_google-swe-intern/
       │   ├── jd.txt
       │   ├── tailored.json
       │   ├── resume.tex
       │   ├── resume.pdf
       │   └── audit_report.json
       └── 2026-06-05_meta-ds-intern/
           └── ...
   ```

2. **Streamlit sidebar**: List previous tailored resumes, click to reload into editor.

3. **Naming**: Auto-generate folder name from date + first few words of company/role in JD (regex extract or Claude-extracted during tailoring).

---

## File Structure (suggested)

```
resume-tailor/
├── app.py                    # Streamlit entry point
├── requirements.txt
├── README.md
├── config.py                 # Constants (CHARS_PER_LINE, TOTAL_CONTENT_LINES, defaults)
├── templates/
│   └── resume_template.tex   # The fixed LaTeX template with placeholders
├── src/
│   ├── parser.py             # Docling parsing logic
│   ├── budget.py             # Budget calculation (lines → chars)
│   ├── tailor.py             # Claude API call + prompt construction
│   ├── renderer.py           # LaTeX template filling + Tectonic compilation
│   ├── audit.py              # rapidfuzz + Haiku hallucination checking
│   ├── history.py            # Save/load tailored versions
│   └── utils.py              # LaTeX escaping, JSON validation, etc.
├── pages/
│   ├── 1_onboarding.py       # Master resume upload + review
│   ├── 2_configure.py        # Budget configuration
│   ├── 3_tailor.py           # JD input + tailoring + editor + preview
│   └── 4_audit.py            # Audit report
└── tests/
    ├── test_budget.py
    ├── test_tailor.py
    └── test_audit.py
```

---

## Prompt Engineering Notes

### Why character limits work better than line limits in the prompt
Claude operates in tokens, not rendered lines. "Write 2 lines" is ambiguous — Claude doesn't know your font or column width. "Write ≤ 170 characters" is unambiguous and measurable. Claude is reasonably good at hitting character targets (within ~5-10%), especially at temperature 0.

### Why we pass the full master resume
Giving Claude the complete master resume context means it can make intelligent choices about what to prioritize for a given JD. If we only passed pre-selected bullets, Claude couldn't rewrite or recombine information across different sections.

### Why structured JSON output (not raw LaTeX)
- Separates content from presentation
- Makes post-validation easy (character counting on JSON fields)
- Enables the structured editor UI
- Template changes don't require prompt changes
- Easier to audit (structured data vs. parsing LaTeX)

### Safety margin
Budget at 95% of theoretical character capacity. A 2-line bullet in a template with 85 chars/line = 170 chars theoretical → budget Claude for 161 chars. This absorbs minor overruns without visible impact.

---

## Dependencies

```txt
streamlit
anthropic
docling
rapidfuzz
pymupdf          # for PDF page count validation (optional)
python-dotenv    # for API key management
```

LaTeX: Tectonic (installed separately via `cargo install tectonic` or system package manager)

---

## Environment Variables

```
ANTHROPIC_API_KEY=sk-...
```

---

## What to Do Next

1. **Calibrate your template** — measure CHARS_PER_LINE and TOTAL_CONTENT_LINES (see Phase 2)
2. **Set up the repo** with the file structure above
3. **Build Phase 1** (Docling parsing + Streamlit review UI)
4. **Build Phase 2** (budget config UI + calculation logic)
5. **Build Phase 3** (Claude API integration + prompt + JSON schema)
6. **Build Phase 4** (structured editor + live preview)
7. **Build Phase 5** (audit layer)
8. **Build Phase 6** (history/persistence)

Each phase is independently testable. Ship incrementally.