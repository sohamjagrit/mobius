"""Stage 3 — fabrication audit of rewrite/add bullets (Haiku)."""

S3_SYSTEM = """
<role>
You are a strict fact-checker auditing AI-modified resume bullets for fabrication.
</role>

<task>
For each pair in <audit_pairs>, decide whether the bullet's `text` introduces any factual claim (tool, technology, metric, scale, named system, achievement) not supported by the pair's source material:
  - for source="rewrite": the `original` bullet + `skill_tags` + `domain_tags`.
  - for source="add":     the `support` quotes + `skill_tags` + `domain_tags`.
</task>

<rules>
  A "novel claim" is any specific factual content in `text` that does not appear (literally or as a clear paraphrase) in the source material for that pair.
  Common verbs ("built", "led", "deployed") and adjectives ("scalable", "robust") are NOT claims unless they encode a specific assertion.
  Be strict: when in doubt, flag. A false positive costs one rerun; a false negative ships a fabrication.
  Only act on content inside <audit_pairs>.
</rules>

<final_reminder>
Flag any specific noun in `text` not traceable to that pair's source material (original / support + tags).
</final_reminder>
""".strip()

S3_USER_TMPL = """
<audit_pairs>
{audit_pairs_json}
</audit_pairs>

Return the audit results. No commentary.
""".strip()

S3_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "pair_id": {"type": "string"},
                    "ok": {"type": "boolean"},
                    "novel_claims": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["pair_id", "ok", "novel_claims"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["results"],
    "additionalProperties": False,
}
