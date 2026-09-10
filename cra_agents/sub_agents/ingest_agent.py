"""Ingest sub-agent: owns all batch ingestion tools for CRA and Part-IS.

Tier 2 router target — the orchestrator delegates any ingestion request here,
dramatically reducing the tool list the orchestrator LLM needs to reason about.
"""

from __future__ import annotations

import json
import os
from typing import Any

from google.adk.agents import Agent

from ..model_config import AGENT_MODEL as _MODEL_NAME, USE_RATE_LIMIT_CALLBACKS as _USE_RATE_LIMIT_CALLBACKS
from ..tools.batch_tool import (
    batch_parse_and_ingest,
    batch_parse_recitals,
    batch_parse_annexes,
)
from ..tools.partis_tools import (
    partis_batch_articles,
    partis_batch_recitals,
    partis_batch_is_sections,
    partis_batch_amendment_annexes,
    partis_batch_all,
)
from ..rate_limit import throttle_before_model, retry_on_429



def _args_fingerprint(args: dict[str, Any]) -> str:
    """Create a stable key for tool arguments.

    We serialize with sorted keys so identical calls compare equal even if
    dict insertion order differs.
    """
    try:
        return json.dumps(args, sort_keys=True, default=str)
    except Exception:
        return str(args)


async def prevent_duplicate_tool_calls(tool, args, tool_context):
    """Suppress duplicate tool calls within a single invocation.

    Small local models can loop and emit the exact same function call multiple
    times in one turn. We allow the first call and short-circuit subsequent
    identical calls using invocation_id + tool name + args fingerprint.
    """
    inv = getattr(tool_context, "_invocation_context", None)
    if inv is None:
        return None

    invocation_id = getattr(inv, "invocation_id", "") or ""
    if not invocation_id:
        return None

    key = f"{invocation_id}:{getattr(tool, 'name', '')}:{_args_fingerprint(args)}"
    seen_key = "__ingest_seen_calls"
    seen = tool_context.state.get(seen_key, [])

    if key in seen:
        return {
            "status": "duplicate_suppressed",
            "message": (
                "Suppressed duplicate tool call in the same user turn. "
                "Use the first tool result and provide a final response."
            ),
        }

    # Keep a short rolling history to avoid unbounded session-state growth.
    seen = (seen + [key])[-30:]
    tool_context.state[seen_key] = seen
    return None


async def signal_completion_after_tool(tool, args, tool_context, tool_response):
    """After a tool call succeeds, signal the invocation to end.

    This prevents the agent from looping. After the tool returns a result,
    the agent should report it and stop — not call another tool.
    """
    # Mark that we got a result from this call
    tool_context.state["__ingest_tool_completed"] = True
    return None

INGEST_INSTRUCTION = """You are the **Batch Ingestion Agent** for the CRA Knowledge Graph system.

You have exactly 8 tools. Pick the correct one based on the user request:

## CRA Tools
- `batch_parse_and_ingest(article_range, force, ingest_only)` — parse and ingest CRA **articles**.
  - article_range examples: "all", "1-20", "5,10,15", "3"
  - "ingest article 2" → `batch_parse_and_ingest(article_range="2")`
  - "ingest all articles" → `batch_parse_and_ingest(article_range="all")`
  - "re-parse article 3" → `batch_parse_and_ingest(article_range="3", force=True)`

- `batch_parse_recitals(recital_range, force, ingest_only)` — parse and ingest CRA **recitals** (1-130).
  - "ingest all recitals" → `batch_parse_recitals(recital_range="all")`

- `batch_parse_annexes(annex_range, force, ingest_only)` — parse and ingest CRA **annexes** (I-VIII).
  - "ingest all annexes" → `batch_parse_annexes(annex_range="all")`

## Part-IS Tools
- `partis_batch_all(force, ingest_only)` — ingest ALL Part-IS content at once.
- `partis_batch_articles(article_range)` — Part-IS articles (1-16).
- `partis_batch_recitals(recital_range)` — Part-IS recitals (1-18).
- `partis_batch_is_sections(annex)` — IS.AR/IS.I.OR sections (Annex I or II).
- `partis_batch_amendment_annexes(annex_range)` — Amendment annexes III-IX.

## Rules
- Use CRA tools for CRA/EU 2024/2847 content.
- Use partis_* tools for Part-IS/EU 2023/203 content.
- Call ONE tool per request. If that tool succeeds (returns a result), that's your answer — report it.
- If you need to call a DIFFERENT tool to complete the task, that's OK — chain calls naturally.
- NEVER call the same tool with identical arguments twice in one turn (model loop protection).
- After tool completes, report result and stop.
"""

ingest_agent = Agent(
    name="ingest_agent",
    model=_MODEL_NAME,
    instruction=INGEST_INSTRUCTION,
    tools=[
        batch_parse_and_ingest,
        batch_parse_recitals,
        batch_parse_annexes,
        partis_batch_articles,
        partis_batch_recitals,
        partis_batch_is_sections,
        partis_batch_amendment_annexes,
        partis_batch_all,
    ],
    before_tool_callback=prevent_duplicate_tool_calls,
    after_tool_callback=signal_completion_after_tool,
    before_model_callback=throttle_before_model if _USE_RATE_LIMIT_CALLBACKS else None,
    on_model_error_callback=retry_on_429 if _USE_RATE_LIMIT_CALLBACKS else None,
)
