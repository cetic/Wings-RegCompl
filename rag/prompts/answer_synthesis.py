"""
Prompts for the CRA answer synthesis step.
"""

ANSWER_SYSTEM_PROMPT = """You are a precise legal-technical assistant specialised in the EU Cyber Resilience Act (Regulation (EU) 2024/2847).

Your role is to answer questions about the CRA based exclusively on the graph context provided.

Rules:
- Be precise and reference the relevant article numbers when available in the context.
- If the context is insufficient to answer fully, say so clearly and indicate which article the user should consult.
- Do not invent obligations, penalties, or deadlines not present in the context.
- Structure your answer clearly: start with the direct answer, then provide supporting detail.
- If the question involves a specific actor (manufacturer, importer...), focus on their specific obligations.
- Use plain language where possible, avoiding unnecessary legal jargon.
"""

ANSWER_USER_TEMPLATE = """Question: {question}

Relevant CRA graph context:
{context}

Please answer the question based on the context above."""


def format_context(graph_results: list[dict]) -> str:
    """
    Convert raw Neo4j result dicts into a readable context string for the LLM.
    Deduplicates and truncates to avoid token overflow.
    """
    if not graph_results:
        return "No specific graph data retrieved. Answer based on general CRA knowledge."

    seen = set()
    lines = []
    for row in graph_results:
        # Build a human-readable line from each result dict
        parts = []
        for k, v in row.items():
            if v is None or v == "" or v == []:
                continue
            if isinstance(v, list):
                v = ", ".join(str(x) for x in v if x)
            parts.append(f"{k}: {v}")
        line = " | ".join(parts)
        if line and line not in seen:
            seen.add(line)
            lines.append(line)

    # Cap at 60 lines to stay within context limits
    if len(lines) > 60:
        lines = lines[:60]
        lines.append("... [context truncated]")

    return "\n".join(lines)


def build_answer_prompt(question: str, graph_results: list[dict]) -> tuple[str, str]:
    """
    Returns (system_prompt, user_prompt) ready to pass to your LLM.
    """
    context = format_context(graph_results)
    user = ANSWER_USER_TEMPLATE.format(question=question, context=context)
    return ANSWER_SYSTEM_PROMPT, user
