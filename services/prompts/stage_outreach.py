"""Outreach stage — profile + tailored delta + JD -> LinkedIn note + cold email."""

# --- LinkedIn note templates -------------------------------------------------
# Each template defines the exact flow for the LinkedIn connection note.
# The email is always generated fresh (template-independent).

LINKEDIN_TEMPLATES = {
    "new_joiner": {
        "label": "They recently joined the company",
        "description": "Warm note acknowledging their recent join, asking for insights on applying.",
        "structure": (
            "Hi [recruiter_name or 'there'],\n"
            "Hope you're doing well! I saw you joined [company] in the last year — hope the experience has been amazing.\n"
            "I came across the [role] role and would love your insights on how to apply.\n"
            "Thanks!"
        ),
        "rules": (
            "Follow this exact flow — do not deviate:\n"
            "  1. Greeting: 'Hi [name],' (use recruiter name if provided, else 'Hi there,')\n"
            "  2. Wellbeing: 'Hope you're doing well!'\n"
            "  3. Acknowledgement: 'I saw you joined [company] in the last year — hope the experience has been amazing.'\n"
            "  4. Ask: 'I came across the [role] role and would love your insights on how to apply.'\n"
            "  5. Sign-off: 'Thanks!'\n"
            "Write it as one flowing message, ≤300 characters. No credential pitching. Warm and human."
        ),
    },
}

# Default template used when no template is selected (original behavior)
_DEFAULT_LINKEDIN_RULES = (
    "  - Open with something specific to the company or role — a product they ship, a market they operate in, "
    "something concrete from the JD. Not 'I saw your job posting.'\n"
    "  - State ONE concrete credential or achievement from the candidate's background directly relevant to this role.\n"
    "  - End with a soft, frictionless ask. 'Would love to connect.' is acceptable.\n"
    "  - No emoji. No 'I'm very interested in the [role] position' opener — too generic."
)

# --- system prompt (template-aware) ------------------------------------------

_SO_SYSTEM_TMPL = """
<role>
You are an expert career coach and cold outreach specialist.
</role>

<task>
Given a candidate's background, their target role, company, and the raw JD, produce:
  1. A LinkedIn connection note (≤300 characters — hard limit, every character counts)
  2. A cold email with subject line and body (body ≤150 words)
</task>

<rules>
  LINKEDIN NOTE (≤300 characters — enforced):
{linkedin_rules}

  COLD EMAIL SUBJECT:
  - 6–10 words. Specific. Includes company name or role.
  - Not clickbait. Not "Quick question" or "Following up."
  - Example: "ML engineer with production LLM experience — [Company]"

  COLD EMAIL BODY (≤150 words):
  - Salutation: "Hi [recruiter_name]," if provided; "Hi [Company] team," otherwise.
  - Paragraph 1 (1–2 sentences): Why THIS company — something real from the JD, not generic praise.
  - Paragraph 2 (2–3 sentences): Your fit — two specific credentials from the candidate's background that map to the JD.
  - Closing (1 sentence): Low-friction CTA. "Happy to share my resume — would a 15-minute chat work?" is fine.
  - Sign-off: "Best,\\n[Candidate name]"
  - No bullet points. No headers. Plain prose.
  - Total body ≤150 words.

  GROUNDING:
  - Every claim about the candidate MUST trace to the provided profile summary or tailored bullets.
  - Do not invent metrics, titles, companies, or technologies not present in the data.
  - If company name is blank, extract it from the JD or use "your company."

  TONE:
  - Confident, not boastful. Specific, not vague. Human, not templated.
</rules>
""".strip()


def build_so_system(template_key: str | None = None) -> str:
    if template_key and template_key in LINKEDIN_TEMPLATES:
        linkedin_rules = "  " + LINKEDIN_TEMPLATES[template_key]["rules"].replace("\n", "\n  ")
    else:
        linkedin_rules = _DEFAULT_LINKEDIN_RULES
    return _SO_SYSTEM_TMPL.format(linkedin_rules=linkedin_rules)


SO_USER_TMPL = """
<candidate>
Name: {name}
Target role: {target_role}
Company: {company}
Recruiter name: {recruiter_name}

Top experience:
{experience_summary}

Skills: {skills_summary}
</candidate>

<jd>
{jd_text}
</jd>
""".strip()

SO_SCHEMA = {
    "type": "object",
    "properties": {
        "linkedin_note": {"type": "string"},
        "email_subject": {"type": "string"},
        "email_body":    {"type": "string"},
    },
    "required": ["linkedin_note", "email_subject", "email_body"],
    "additionalProperties": False,
}
