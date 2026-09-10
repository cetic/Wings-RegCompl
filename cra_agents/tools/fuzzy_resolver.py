"""Tier 1: Fuzzy tool-name resolver for ADK on_tool_error_callback.

When a local LLM hallucinates a tool name (e.g. `part_data` instead of
`batch_parse_and_ingest`), ADK raises ValueError and calls this callback.
We fuzzy-match the hallucinated name against all registered callables and,
if confidence is high enough, execute the real tool and return its result —
transparently, as if the correct name had been used.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Callable, Optional

from rapidfuzz import fuzz, process

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Registry — populated by register_tools() called from agent.py after all
# tool functions are imported.  Keyed by exact Python function name.
# ---------------------------------------------------------------------------
TOOL_REGISTRY: dict[str, Callable] = {}

FUZZY_THRESHOLD = 72  # minimum token_sort_ratio score to accept a match


def register_tools(tools: list[Callable]) -> None:
    """Populate TOOL_REGISTRY from the agent's tool list."""
    TOOL_REGISTRY.clear()
    for fn in tools:
        name = getattr(fn, "__name__", None) or getattr(fn, "name", None)
        if name:
            TOOL_REGISTRY[name] = fn
    log.info("fuzzy_resolver: registered %d tools", len(TOOL_REGISTRY))


def resolve_tool_name(hallucinated: str, threshold: int = FUZZY_THRESHOLD) -> Optional[str]:
    """Return the nearest registered tool name, or None if below threshold."""
    if not TOOL_REGISTRY:
        return None
    match, score, _ = process.extractOne(
        hallucinated,
        TOOL_REGISTRY.keys(),
        scorer=fuzz.token_sort_ratio,
    )
    log.info(
        "fuzzy_resolver: '%s' → '%s' (score=%d, threshold=%d)",
        hallucinated,
        match,
        score,
        threshold,
    )
    if score >= threshold:
        return match
    return None


async def on_fuzzy_tool_error(
    tool: Any,
    args: dict[str, Any],
    tool_context: Any,
    error: Exception,
) -> Optional[dict]:
    """ADK on_tool_error_callback — intercepts 'Tool not found' errors.

    If the error is a name-not-found ValueError, fuzzy-match the hallucinated
    name, call the real tool, and return its result so ADK can carry on.
    Returns None for any other error (lets ADK propagate it normally).
    """
    err_str = str(error)
    if "not found" not in err_str.lower():
        return None  # not our concern — let ADK handle it

    hallucinated_name: str = getattr(tool, "name", "") or ""
    if not hallucinated_name:
        return None

    resolved = resolve_tool_name(hallucinated_name)
    if resolved is None:
        log.warning(
            "fuzzy_resolver: no match above threshold for '%s'. Giving up.",
            hallucinated_name,
        )
        return {
            "error": (
                f"Tool '{hallucinated_name}' not found and no close match "
                f"was found. Available tools: {', '.join(sorted(TOOL_REGISTRY))}"
            )
        }

    log.info("fuzzy_resolver: dispatching '%s' → '%s'", hallucinated_name, resolved)
    real_fn = TOOL_REGISTRY[resolved]

    try:
        result = real_fn(**args)
        if inspect.isawaitable(result):
            result = await result
        # ADK expects a dict as the tool response
        if isinstance(result, dict):
            return result
        return {"result": result}
    except Exception as exec_err:
        log.error("fuzzy_resolver: error calling '%s': %s", resolved, exec_err)
        return {"error": f"Resolved tool '{resolved}' raised: {exec_err}"}
