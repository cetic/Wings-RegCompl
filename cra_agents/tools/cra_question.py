"""Graph-RAG question-answering tool for the CRA knowledge graph.

Replaces the unsafe `text2cypher` path. Pipeline:

    1. classify  — small LLM call → intent + entities (JSON)
    2. retrieve  — nomic-embed query → vector search over :CRAChunk seeds
    3. expand    — fixed, parameterised Cypher per intent (no NL→Cypher)
    4. synthesise— main LLM call with retrieved context + assessor rules

Why this design (and not text2cypher):
    * deterministic Cypher → no risk of destructive queries
    * single small + single main LLM call → lower latency
    * intent set is small (8) → easy to test, easy to extend
    * directly honours `backend.reflection.format_rules_block` rules so the
      product-memory layer affects retrieval *and* answer phrasing.
"""

from __future__ import annotations

import json
import logging
import re

from ._llm import generate as _llm_generate
from .neo4j_tools import _get_driver
from .vector_tools import _embed_query

log = logging.getLogger(__name__)


# ── Intent definitions ──────────────────────────────────────────────
INTENTS = {
    "obligation_lookup": "Questions about what a specific actor (manufacturer, importer, distributor, steward) must do.",
    "product_classification": "Questions about what category/class a product falls into, or what essential requirements apply to it.",
    "conformity_assessment_path": "Questions about how to assess conformity, which module/procedure applies, whether a notified body is needed.",
    "vulnerability_handling": "Questions about how to handle, disclose, or report vulnerabilities and security incidents.",
    "penalty_lookup": "Questions about fines, penalties, sanctions for non-compliance.",
    "scope_check": "Questions about whether the CRA applies to a product, software type, or use case.",
    "cross_regulation": "Questions about how CRA relates to other EU regulations (AI Act, NIS2, GDPR, MDR…).",
    "timeline_lookup": "Questions about when provisions apply, deadlines, transitional periods.",
}

_INTENT_LIST = "\n".join(f"- {k}: {v}" for k, v in INTENTS.items())

_INTENT_PROMPT = f"""You are an intent classifier for a CRA (Cyber Resilience Act) Q&A system.

Return ONE valid JSON object — no markdown, no explanation — with keys:
- "intent": one of: {", ".join(INTENTS.keys())}
- "actor": one of Manufacturer, Importer, Distributor, AuthorisedRepresentative, OpenSourceSoftwareSteward, or ""
- "product": product name or type if mentioned, else ""
- "article": CRA article number (digits only) if mentioned, else ""
- "regulation": other EU regulation mentioned (AI Act, NIS2, GDPR, MDR…) or ""

Available intents:
{_INTENT_LIST}

If the question matches multiple intents, pick the most specific one.
"""


def _classify(question: str) -> dict:
    raw = _llm_generate(_INTENT_PROMPT + "\n\nQuestion: " + question, temperature=0.0)
    clean = re.sub(r"```(?:json)?|```", "", raw or "").strip()
    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", clean, re.DOTALL)
        parsed = json.loads(m.group()) if m else {}
    defaults = {
        "intent": "obligation_lookup",
        "actor": "",
        "product": "",
        "article": "",
        "regulation": "",
    }
    out = {**defaults, **(parsed if isinstance(parsed, dict) else {})}
    # Coerce types
    for k in defaults:
        if not isinstance(out.get(k), str):
            out[k] = "" if k != "intent" else "obligation_lookup"
    return out


# ── Retrieval ───────────────────────────────────────────────────────
_VECTOR_INDEX = "cra_chunk_embedding"


def _vector_seeds(question: str, k: int = 5) -> list[dict]:
    """Top-k :CRAChunk nodes by cosine similarity to the question."""
    try:
        emb = _embed_query(question)
    except Exception as e:  # noqa: BLE001
        log.warning("Vector embed failed (%s) — proceeding without seeds.", e)
        return []
    cypher = (
        f"CALL db.index.vector.queryNodes('{_VECTOR_INDEX}', $k, $emb) "
        "YIELD node, score "
        "OPTIONAL MATCH (node)-[:EMBEDS]->(target) "
        "RETURN node.chunk_id AS chunk_id, node.section AS section, "
        "       node.title AS title, node.text AS text, "
        "       coalesce(target.article_id, target.recital_id, target.annex_id, '') AS ref, "
        "       score"
    )
    driver = _get_driver()
    try:
        with driver.session() as s:
            return [dict(r) for r in s.run(cypher, k=k, emb=emb)]
    except Exception as e:  # noqa: BLE001
        log.warning("Vector search failed (%s)", e)
        return []
    finally:
        driver.close()


# ── Intent-specific traversals (parameterised, read-only) ──────────
_TRAVERSALS = {
    "obligation_lookup": (
        "MATCH (a:Actor)-[:HAS_OBLIGATION]->(o:Obligation) "
        "WHERE $actor = '' OR toLower(a.name) CONTAINS toLower($actor) "
        "   OR any(l IN labels(a) WHERE toLower(l) CONTAINS toLower($actor)) "
        "OPTIONAL MATCH (art:Article)-[:CONTAINS_OBLIGATION]->(o) "
        "RETURN a.name AS actor, o.id AS id, o.action AS action, "
        "       art.article_id AS article LIMIT 40"
    ),
    "vulnerability_handling": (
        "MATCH (a:Article)-[:CONTAINS_OBLIGATION]->(o:Obligation) "
        "WHERE toLower(o.action) CONTAINS 'vulnerab' "
        "   OR toLower(o.action) CONTAINS 'incident' "
        "   OR toLower(o.action) CONTAINS 'csirt' "
        "   OR toLower(o.action) CONTAINS 'security update' "
        "RETURN a.article_id AS article, o.id AS id, o.action AS action LIMIT 40"
    ),
    "penalty_lookup": (
        "MATCH (a:Article)-[:CONTAINS_OBLIGATION]->(o:Obligation) "
        "WHERE toLower(coalesce(a.article_title,'')) CONTAINS 'penalt' "
        "   OR toLower(o.action) CONTAINS 'fine' "
        "   OR toLower(o.action) CONTAINS 'penalt' "
        "RETURN a.article_id AS article, a.article_title AS title, "
        "       o.id AS id, o.action AS action LIMIT 30"
    ),
    "timeline_lookup": (
        "MATCH (a:Article)-[:CONTAINS_OBLIGATION]->(o:Obligation) "
        "WHERE o.deadline IS NOT NULL AND o.deadline <> '' "
        "RETURN a.article_id AS article, o.id AS id, o.action AS action, "
        "       o.deadline AS deadline LIMIT 40"
    ),
    "conformity_assessment_path": (
        "MATCH (a:Article)-[:CONTAINS_OBLIGATION]->(o:Obligation) "
        "WHERE toLower(o.action) CONTAINS 'conformity' "
        "   OR toLower(o.action) CONTAINS 'notified body' "
        "   OR toLower(o.action) CONTAINS 'module' "
        "RETURN a.article_id AS article, o.id AS id, o.action AS action LIMIT 40"
    ),
    "scope_check": (
        "MATCH (a:Article)-[:CONTAINS_OBLIGATION]->(o:Obligation) "
        "WHERE toLower(coalesce(a.article_title,'')) CONTAINS 'scope' "
        "   OR a.article_id IN ['Art. 2','Art. 3'] "
        "RETURN a.article_id AS article, a.article_title AS title, "
        "       o.id AS id, o.action AS action LIMIT 30"
    ),
    "cross_regulation": (
        "MATCH (a:Article)-[:CONTAINS_OBLIGATION]->(o:Obligation) "
        "WHERE ($regulation <> '' AND toLower(o.action) CONTAINS toLower($regulation)) "
        "   OR toLower(o.action) CONTAINS 'nis2' "
        "   OR toLower(o.action) CONTAINS 'gdpr' "
        "   OR toLower(o.action) CONTAINS 'ai act' "
        "RETURN a.article_id AS article, o.id AS id, o.action AS action LIMIT 30"
    ),
    "product_classification": (
        "MATCH (a:Article)-[:CONTAINS_OBLIGATION]->(o:Obligation) "
        "WHERE toLower(coalesce(a.article_title,'')) CONTAINS 'classif' "
        "   OR toLower(o.action) CONTAINS 'class i' "
        "   OR toLower(o.action) CONTAINS 'class ii' "
        "   OR toLower(o.action) CONTAINS 'important product' "
        "   OR toLower(o.action) CONTAINS 'critical product' "
        "RETURN a.article_id AS article, o.id AS id, o.action AS action LIMIT 30"
    ),
}


def _traverse(intent: str, entities: dict) -> list[dict]:
    cypher = _TRAVERSALS.get(intent)
    if not cypher:
        return []
    params = {
        "actor": entities.get("actor", ""),
        "regulation": entities.get("regulation", ""),
        "article": entities.get("article", ""),
    }
    driver = _get_driver()
    try:
        with driver.session() as s:
            return [dict(r) for r in s.run(cypher, **params)]
    except Exception as e:  # noqa: BLE001
        log.warning("Traversal for intent %s failed: %s", intent, e)
        return []
    finally:
        driver.close()


# ── Article-specific shortcut (when classifier extracted an article #) ─


def _article_obligations(article_num: str) -> list[dict]:
    if not article_num:
        return []
    aid = f"Art. {article_num}"
    cypher = (
        "MATCH (a:Article {article_id: $aid})-[:CONTAINS_OBLIGATION]->(o:Obligation) "
        "OPTIONAL MATCH (actor:Actor)-[:HAS_OBLIGATION]->(o) "
        "RETURN a.article_id AS article, a.article_title AS title, "
        "       o.id AS id, o.action AS action, "
        "       collect(DISTINCT actor.name) AS actors LIMIT 40"
    )
    driver = _get_driver()
    try:
        with driver.session() as s:
            return [dict(r) for r in s.run(cypher, aid=aid)]
    finally:
        driver.close()


# ── Context formatter ──────────────────────────────────────────────


def _format_context(seeds: list[dict], rows: list[dict]) -> str:
    lines: list[str] = []
    seen: set[str] = set()

    if seeds:
        lines.append("## Most-relevant CRA text chunks (top vector hits):")
        for s in seeds[:5]:
            ref = s.get("ref") or s.get("chunk_id") or ""
            title = (s.get("title") or "").strip()
            text = (s.get("text") or "").strip()
            if not text:
                continue
            snippet = text[:600] + ("…" if len(text) > 600 else "")
            key = f"{ref}::{title}"
            if key in seen:
                continue
            seen.add(key)
            head = f"[{ref}] {title}".strip(" []") or "(chunk)"
            lines.append(f"- **{head}**\n  {snippet}")

    if rows:
        lines.append("\n## Graph traversal results:")
        for row in rows:
            parts = []
            for k, v in row.items():
                if v in (None, "", []):
                    continue
                if isinstance(v, list):
                    v = ", ".join(str(x) for x in v if x)
                parts.append(f"{k}: {v}")
            line = " | ".join(parts)
            if line and line not in seen:
                seen.add(line)
                lines.append(f"- {line}")

    return "\n".join(lines) if lines else "(No relevant graph data was found.)"


# ── Answer synthesis ───────────────────────────────────────────────


_ANSWER_PROMPT = """You are a precise legal-technical assistant for the EU Cyber Resilience Act (Regulation (EU) 2024/2847).

Answer the user's question using ONLY the graph context below. Rules:
- Cite article numbers (e.g. "Art. 13") whenever the context provides one.
- If the context is insufficient to answer fully, say so and indicate which article(s) the user should consult.
- Do NOT invent obligations, penalties, or deadlines that are not in the context.
- Structure the answer: short direct answer first, then supporting detail.
- Use plain language; avoid unnecessary legalese.
{rules_block}

Detected intent: {intent}

Graph context:
{context}

Question: {question}

Answer:"""


def cra_question(question: str, feedback_rules: list[str] | None = None) -> str:
    """Answer a natural-language CRA question via the graph-RAG pipeline.

    Args:
        question: The user's question, e.g. "What are the obligations of a
            manufacturer for vulnerability handling?".
        feedback_rules: Optional list of assessor-feedback rules (typically
            distilled by `backend.reflection`) to inject into the prompt.

    Returns:
        A grounded, citation-aware answer string.
    """
    q = (question or "").strip()
    if not q:
        return "Please provide a non-empty question about the CRA."

    entities = _classify(q)
    intent = entities.get("intent", "obligation_lookup")
    log.info("cra_question: intent=%s entities=%s", intent, entities)

    seeds = _vector_seeds(q, k=5)
    rows = _traverse(intent, entities)

    # If the classifier pulled out an explicit article, give it more weight.
    if entities.get("article"):
        rows = _article_obligations(entities["article"]) + rows

    context = _format_context(seeds, rows)

    rules_block = ""
    if feedback_rules:
        bullets = "\n".join(f"- {r}" for r in feedback_rules if r and r.strip())
        if bullets:
            rules_block = "\n\n## Assessor feedback rules (always apply):\n" + bullets

    prompt = _ANSWER_PROMPT.format(
        rules_block=rules_block,
        intent=intent,
        context=context,
        question=q,
    )
    try:
        return _llm_generate(prompt, temperature=0.2)
    except Exception as e:  # noqa: BLE001
        log.error("cra_question synthesis failed: %s", e)
        return f"(Sorry, the answer step failed: {e})"
