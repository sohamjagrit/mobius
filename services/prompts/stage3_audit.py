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

<examples>
CASE 1 — passes (faithful rewrite; all claims trace to source material)

  Pair:
  {
    "pair_id": "experience[0].bullets[0]",
    "source": "rewrite",
    "text": "Built REST APIs in Flask and PostgreSQL powering internal data pipelines for the analytics team",
    "original": "Built APIs using Flask and PostgreSQL for internal data ingestion workflows",
    "support": [],
    "skill_tags": ["Flask", "PostgreSQL", "REST API", "data pipelines"],
    "domain_tags": ["backend", "data engineering"]
  }

  Result:
  {
    "pair_id": "experience[0].bullets[0]",
    "ok": true,
    "novel_claims": []
  }

  Reasoning: "REST API" is in skill_tags; "data pipelines" is in skill_tags; "analytics team" is a reasonable paraphrase of "internal data ingestion workflows". Flask and PostgreSQL appear verbatim in the original. Nothing invented.

---

CASE 2 — flagged (subtle fabrication: invented metric, tools not in source, verb inflation)

  Pair:
  {
    "pair_id": "experience[1].bullets[2]",
    "source": "rewrite",
    "text": "Led model training pipeline achieving 15% accuracy improvement using PyTorch and MLflow",
    "original": "Contributed to model training scripts in Python",
    "support": [],
    "skill_tags": ["Python", "machine learning"],
    "domain_tags": ["ML", "modeling"]
  }

  Result:
  {
    "pair_id": "experience[1].bullets[2]",
    "ok": false,
    "novel_claims": ["15% accuracy improvement", "PyTorch", "MLflow", "Led"]
  }

  Reasoning: The original says "Contributed to" — "Led" inflates the role. "15% accuracy improvement" appears nowhere in the source. "PyTorch" and "MLflow" are not in original, support, skill_tags, or domain_tags. All four are novel claims.
</examples>

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
