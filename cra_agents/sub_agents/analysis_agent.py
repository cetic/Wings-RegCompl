"""Analysis sub-agent: owns vector search, obligation linking, and product tools.

Tier 2 router target — keeps semantic/vector/product tools out of the
orchestrator's context, leaving it with a short, focused tool list.
"""

from __future__ import annotations

import os

from google.adk.agents import Agent

from ..tools.vector_tools import (
    vectorize_graph,
    vectorize_obligations,
    semantic_search,
    search_obligations,
)
from ..tools.link_obligations import (
    link_obligations,
    conformity_trace,
    compliance_impact,
)
from ..tools.product_tools import (
    product_obligations,
    classify_product,
    filter_obligations,
)
from ..tools.excel_export import export_assessment_to_excel
from ..tools.partis_tools import partis_vectorize
from ..rate_limit import throttle_before_model, retry_on_429
from ..model_config import AGENT_MODEL as _MODEL_NAME, USE_RATE_LIMIT_CALLBACKS as _USE_RATE_LIMIT_CALLBACKS


ANALYSIS_INSTRUCTION = """You are the **Analysis Agent** for the CRA Knowledge Graph system.

You handle semantic search, obligation linking, product compliance analysis, and vectorization.

## Tools

### Vectorization (run once after ingestion)
- `vectorize_graph(sections)` — embed CRA text chunks. sections: "all", "articles", "recitals", "annexes"
- `vectorize_obligations()` — embed individual obligation nodes.
- `partis_vectorize()` — embed Part-IS text chunks.

### Semantic Search
- `semantic_search(query)` — article-level semantic search. Relay the "report" field verbatim.
- `search_obligations(query, top_k, mode)` — obligation-level search.
  - mode: "hybrid" (default), "semantic", "keyword"
  - Relay the "report" field verbatim.

### Obligation Linking
- `link_obligations(mode)` — discover relationships between obligations.
  - mode: "structural" (fast) or "full" (structural + LLM)
  - Run once; re-run to update.
- `conformity_trace(topic)` — trace obligation chains for a compliance topic.
- `compliance_impact(obligation_ids)` — propagate compliance through the obligation graph.

### Product Compliance
- `product_obligations(description, actor_role)` — get all CRA obligations for a product.
  - actor_role: "manufacturer" (default), "importer", "distributor", "open_source_steward"
  - In the chat, show ONLY the summary and json_file path. Do NOT list individual obligations.
- `classify_product(description)` — classify a product under CRA Annex III categories.
- `filter_obligations(filters)` — filter obligations by actor, article, deadline, etc.
- `export_assessment_to_excel(json_file)` — export a product assessment JSON to Excel.

## Rules
- Call exactly ONE tool per step.
- Always relay the "report" field from semantic_search and search_obligations responses verbatim.
- After export_assessment_to_excel, show the path to the generated .xlsx file.
"""

analysis_agent = Agent(
    name="analysis_agent",
    model=_MODEL_NAME,
    instruction=ANALYSIS_INSTRUCTION,
    tools=[
        vectorize_graph,
        vectorize_obligations,
        semantic_search,
        search_obligations,
        link_obligations,
        conformity_trace,
        compliance_impact,
        product_obligations,
        classify_product,
        filter_obligations,
        export_assessment_to_excel,
        partis_vectorize,
    ],
    before_model_callback=throttle_before_model if _USE_RATE_LIMIT_CALLBACKS else None,
    on_model_error_callback=retry_on_429 if _USE_RATE_LIMIT_CALLBACKS else None,
)
