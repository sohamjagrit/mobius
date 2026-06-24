"""Mobius pipeline prompts — one module per stage.

Single source of truth for both the Streamlit app and the R&D notebook.
Edit the per-stage file; both surfaces pick up the change on next run.
"""

from .stage0_profile import S0_SYSTEM, S0_USER_TMPL, S0_SCHEMA
from .stage1_keywords import S1_SYSTEM, S1_USER_TMPL, S1_SCHEMA
from .stage2_tailor import S2_SYSTEM, S2_USER_TMPL, S2_SCHEMA
from .stage_outreach import build_so_system, SO_USER_TMPL, SO_SCHEMA, LINKEDIN_TEMPLATES

__all__ = [
    "S0_SYSTEM", "S0_USER_TMPL", "S0_SCHEMA",
    "S1_SYSTEM", "S1_USER_TMPL", "S1_SCHEMA",
    "S2_SYSTEM", "S2_USER_TMPL", "S2_SCHEMA",
    "build_so_system", "SO_USER_TMPL", "SO_SCHEMA", "LINKEDIN_TEMPLATES",
]
