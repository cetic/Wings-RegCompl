"""Root orchestrator agent for the CRA Knowledge Graph system.

This is the main conversational agent that:
1. Routes ingestion requests → ingest_agent (8 tools, focused)
2. Routes analysis/vector/product requests → analysis_agent (12 tools, focused)
3. Routes single-article parse/ingest → parser_agent / ingestion_agent
4. Handles queries and exploration directly (~17 tools)

Tier 1 — fuzzy_resolver: on_tool_error_callback catches hallucinated tool names
         and fuzzy-matches them to the nearest registered tool.
Tier 2 — domain sub-agents: reduces orchestrator tool list from 38 → 17.
"""

from google.adk.agents import Agent
from google.genai import types as _genai_types

from .model_config import (
    AGENT_MODEL_STR as _MODEL_NAME,
    USE_RATE_LIMIT_CALLBACKS as _USE_RATE_LIMIT_CALLBACKS,
    IS_OFFLOAD as _IS_OFFLOAD,
)

from .sub_agents.parser_agent import parser_agent
from .sub_agents.ingestion_agent import ingestion_agent
from .sub_agents.ingest_agent import ingest_agent
from .sub_agents.analysis_agent import analysis_agent
from .tools.cra_tools import (
    list_articles,
    read_article,
    read_annex,
    read_chapter,
    read_recital,
    list_recitals,
    list_annexes,
)
from .tools.neo4j_tools import (
    get_graph_stats,
    get_article_obligations,
    get_all_obligations,
    get_actors,
    get_article_nodes,
    get_deadlines,
    get_verification_actions,
    wipe_graph,
)
from .tools.cra_question import cra_question
from .tools.fuzzy_resolver import on_fuzzy_tool_error, register_tools
from .rate_limit import throttle_before_model, retry_on_429

ROOT_INSTRUCTION = """You are the **Regulatory Knowledge Graph Assistant** — a conversational AI for EU regulation knowledge graphs.

Regulations supported (BOTH are fully supported — never tell the user otherwise):
- **CRA** — Cyber Resilience Act (EU 2024/2847): 71 articles, 130 recitals, 8 annexes
- **Part-IS** — Information Security (EU 2023/203): 16 articles, 18 recitals, IS sections, amendment annexes
  Aliases: "partis", "part-is", "part_is", "part is", "Part IS" all mean Part-IS.

## ROUTING — What to do with each request

### GRAPH SUMMARY / STATS / OVERVIEW (any regulation)
→ Call `get_graph_stats()` DIRECTLY. It returns counts for ALL regulations
  (CRA + Part-IS) in the graph. Never claim a regulation is unsupported
  without first calling this tool.

### INGEST content (parse + load into Neo4j)
→ Call `transfer_to_agent("ingest_agent")`
The ingest_agent will call the appropriate batch tool and return the result.

### ANALYZE / SEARCH / PRODUCT COMPLIANCE / VECTORIZE
→ Call `transfer_to_agent("analysis_agent")`
The analysis_agent will call the appropriate analysis tool and return the result.

### QUERY the knowledge graph (what's already in Neo4j)
Use these tools DIRECTLY — do NOT delegate:
- `cra_question(question)` — **PREFERRED** for any natural-language CRA
  question. Runs a safe graph-RAG pipeline (intent + vector search + fixed
  traversal + grounded synthesis). Use this instead of trying to invent
  Cypher — free-form NL→Cypher generation is disabled for safety.
- `get_article_obligations(article_number)` — obligations from an article
- `get_all_obligations()` — all obligations summary
- `get_actors()` — all actors
- `get_article_nodes(article_number)` — all nodes for an article
- `get_graph_stats()` — node/relationship counts
- `get_deadlines()` — time-sensitive obligations
- `get_verification_actions(article_id)` — verification steps
After any query tool, give a concise human-readable summary. Do NOT dump raw output.

### EXPLORE the regulation text (no Neo4j needed)
Use these tools DIRECTLY:
- `list_articles`, `list_recitals`, `list_annexes`
- `read_article(article_number)`, `read_recital(recital_number)`, `read_annex(annex_id)`, `read_chapter(chapter_number)`

### WIPE GRAPH
- `wipe_graph()` — WARNING: irreversible. Always confirm with user first.

### PARSE A SINGLE ARTICLE (step-by-step)
→ Call `transfer_to_agent("parser_agent")` then `transfer_to_agent("ingestion_agent")`

## Chaining Rules
- If a single tool call completes the user's request, return the result and stop.
- If you need to chain multiple tool calls to fulfill the request, do so naturally.
- AVOID: calling the same tool with identical arguments repeatedly (loop protection active).
- NEVER call `transfer_to_agent("cra_orchestrator")` — that is YOU. Self-transfer is forbidden.
- NEVER fabricate an answer if a tool returned null/empty — call a different tool or report the empty result honestly.
- ALLOW: calling different tools in sequence if needed to answer the user's question.

## Communication Style
- Be concise and professional.
- Display results in tables when appropriate.
- If Neo4j is not running, inform the user to start it.
"""

_ORCHESTRATOR_TOOLS = [
    # Explore CRA text
    list_articles,
    read_article,
    read_annex,
    read_chapter,
    read_recital,
    list_recitals,
    list_annexes,
    # Query graph directly
    get_graph_stats,
    get_article_obligations,
    get_all_obligations,
    get_actors,
    get_article_nodes,
    get_deadlines,
    get_verification_actions,
    wipe_graph,
    cra_question,
]

# Tier 1: register all orchestrator tools in the fuzzy resolver so hallucinated
# names can be matched at error time.
register_tools(_ORCHESTRATOR_TOOLS)

# When using Gemini 2.5 Flash, disable the "thinking" budget. Otherwise the
# model can spend its whole turn on internal thoughts and return an event with
# finish_reason=STOP and zero content parts → the chat UI shows "(no reply)".
_GENERATE_CONFIG = (
    _genai_types.GenerateContentConfig(
        thinking_config=_genai_types.ThinkingConfig(thinking_budget=0),
    )
    if _IS_OFFLOAD
    else None
)

root_agent = Agent(
    name="cra_orchestrator",
    model=_MODEL_NAME,
    instruction=ROOT_INSTRUCTION,
    tools=_ORCHESTRATOR_TOOLS,
    sub_agents=[parser_agent, ingestion_agent, ingest_agent, analysis_agent],
    before_model_callback=throttle_before_model if _USE_RATE_LIMIT_CALLBACKS else None,
    on_model_error_callback=retry_on_429 if _USE_RATE_LIMIT_CALLBACKS else None,
    on_tool_error_callback=on_fuzzy_tool_error,
    generate_content_config=_GENERATE_CONFIG,
)
