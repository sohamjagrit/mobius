"""Anthropic API wrapper for Mobius pipeline stages.

Single entry point: `call_claude(system_prompt, user_prompt)`. The client is
created lazily so importing this module is cheap and side-effect-free until
the first call.

Prompt caching: the system prompt is cached by default (`cache_control:
ephemeral`). The system prompts in the Mobius pipeline are stable across
runs, so cache hits drop input cost to ~10% on repeat calls within 5 min.
Pass `cache_system=False` to disable.
"""
import os
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 8000

_client: Anthropic | None = None

LAST_USAGE: dict = {}

# USD per token. Cache writes bill at 1.25x base input; cache reads at 0.1x.
PRICING = {
    "sonnet": {"input": 3 / 1e6, "output": 15 / 1e6, "cache_write": 3.75 / 1e6, "cache_read": 0.30 / 1e6},
    "haiku":  {"input": 1 / 1e6, "output":  5 / 1e6, "cache_write": 1.25 / 1e6, "cache_read": 0.10 / 1e6},
}


def cost_usd(usage: dict) -> float:
    """Dollar cost of one call from a LAST_USAGE-shaped dict."""
    model = usage.get("model", "")
    rates = PRICING["haiku"] if "haiku" in model else PRICING["sonnet"]
    return (
        usage.get("input_tokens", 0)                * rates["input"]
        + usage.get("output_tokens", 0)             * rates["output"]
        + usage.get("cache_creation_input_tokens", 0) * rates["cache_write"]
        + usage.get("cache_read_input_tokens", 0)     * rates["cache_read"]
    )


def get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def call_claude(
    system_prompt: str,
    user_prompt: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    cache_system: bool = True,
    output_schema: dict | None = None,
) -> str:
    """Single-turn message call. Returns the assistant's text response."""
    system_block = (
        [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]
        if cache_system
        else system_prompt
    )
    kwargs: dict = {}
    if output_schema is not None:
        kwargs["output_config"] = {"format": {"type": "json_schema", "schema": output_schema}}
    response = get_client().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_block,
        messages=[{"role": "user", "content": user_prompt}],
        **kwargs,
    )
    LAST_USAGE.clear()
    LAST_USAGE.update({
        "model": model,
        "input_tokens":               getattr(response.usage, "input_tokens", 0),
        "output_tokens":              getattr(response.usage, "output_tokens", 0),
        "cache_creation_input_tokens": getattr(response.usage, "cache_creation_input_tokens", 0),
        "cache_read_input_tokens":     getattr(response.usage, "cache_read_input_tokens", 0),
    })
    return response.content[0].text
