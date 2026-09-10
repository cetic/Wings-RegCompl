"""
Intent classifier for CRA questions.

The LLM's only job here is to:
  1. Pick one of 8 intents
  2. Extract named entities (actor, product, article, regulation)

This is much simpler and more reliable than generating Cypher.
Swap `call_llm()` with your actual LLM call.
"""

from __future__ import annotations
import json
import re


# ------------------------------------------------------------------
# Intent definitions
# ------------------------------------------------------------------

INTENTS = {
    "obligation_lookup":          "Questions about what a specific actor (manufacturer, importer, distributor, steward) must do",
    "product_classification":     "Questions about what category/class a product falls into, or what requirements apply to it",
    "conformity_assessment_path": "Questions about how to assess conformity, which module/procedure applies, whether a notified body is needed",
    "vulnerability_handling":     "Questions about how to handle, disclose, or report vulnerabilities and security incidents",
    "penalty_lookup":             "Questions about fines, penalties, sanctions for non-compliance",
    "scope_check":                "Questions about whether the CRA applies to a product, software type, or use case",
    "cross_regulation":           "Questions about how CRA relates to other EU regulations (AI Act, NIS2, GDPR, MDR...)",
    "timeline_lookup":            "Questions about when provisions apply, deadlines, transitional periods",
}

INTENT_LIST = "\n".join(f"- {k}: {v}" for k, v in INTENTS.items())

SYSTEM_PROMPT = """You are an intent classifier for a CRA (Cyber Resilience Act) question-answering system.

Given a user question, return a JSON object with:
- "intent": one of the intents listed below
- "actor": the economic operator mentioned (Manufacturer, Importer, Distributor, AuthorisedRepresentative, OpenSourceSoftwareSteward) or ""
- "product": the product type or name mentioned, or ""
- "product_class": the product classification if mentioned (DefaultProduct, ImportantProduct_ClassI, ImportantProduct_ClassII, CriticalProduct) or ""
- "article": the CRA article number if mentioned, or ""
- "regulation": another EU regulation mentioned (AI Act, NIS2, GDPR, MDR...) or ""

Available intents:
{intent_list}

Rules:
- Return ONLY valid JSON, no markdown, no explanation.
- If the question matches multiple intents, pick the most specific one.
- For actor names, use the exact ontology label (e.g. "Manufacturer" not "maker").
""".format(intent_list=INTENT_LIST)


# ------------------------------------------------------------------
# Main classifier
# ------------------------------------------------------------------

def classify_intent(question: str, llm_fn) -> dict:
    """
    Classify the intent and extract entities from a CRA question.

    Args:
        question: The user's question.
        llm_fn:   Your LLM callable. Signature:
                  llm_fn(system: str, user: str) -> str

    Returns a dict like:
        {
          "intent": "obligation_lookup",
          "actor": "Manufacturer",
          "product": "",
          "product_class": "",
          "article": "13",
          "regulation": ""
        }
    """
    raw = llm_fn(system=SYSTEM_PROMPT, user=question)
    return _parse_json(raw)


def _parse_json(raw: str) -> dict:
    """Safely parse the LLM's JSON response."""
    # Strip any markdown fences the model may add
    clean = re.sub(r"```(?:json)?|```", "", raw).strip()
    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError:
        # Last-resort: try to extract JSON object with regex
        match = re.search(r"\{.*\}", clean, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
            except json.JSONDecodeError:
                parsed = {}
        else:
            parsed = {}

    # Ensure all expected keys are present
    defaults = {
        "intent": "obligation_lookup",
        "actor": "",
        "product": "",
        "product_class": "",
        "article": "",
        "regulation": "",
    }
    return {**defaults, **parsed}
