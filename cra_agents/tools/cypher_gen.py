"""Cypher generation tool using a local Ollama text2cypher model.

Uses neo4j/text-to-cypher-Gemma-3-4B fine-tuned model (GGUF via Ollama)
to translate natural language questions into Cypher queries, then executes them.
"""

from __future__ import annotations

import json
import logging
from urllib.request import Request, urlopen

from .neo4j_tools import query_neo4j, _get_driver

log = logging.getLogger(__name__)

# ── Ollama config ──────────────────────────────────────────────────────
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = (
    "hf.co/mradermacher/text-to-cypher-Gemma-3-4B-Instruct-2025.04.0-GGUF:Q8_0"
)
OLLAMA_TIMEOUT = 120  # seconds (model should be hot after first call)

# ── CRA graph schema for the prompt ───────────────────────────────────
CRA_SCHEMA = """Node labels and properties:
- (:Article) — article_id (STRING, e.g. "Art. 21"), article_title (STRING)
- (:Obligation) — id (STRING, e.g. "Art. 21_obl_1"), article_id (STRING), paragraph_ref (STRING), action (STRING), trigger (STRING), deadline (STRING)
- (:Actor) — id (STRING), name (STRING). IMPORTANT: subtypes are ADDITIONAL LABELS on the same node. Use the label directly: (:Manufacturer), (:Importer), (:Distributor), (:EuropeanCommission), (:ENISA), (:CSIRT), (:MarketSurveillanceAuthority), (:NotifiedBody), (:Consumer), (:OpenSourceSoftwareSteward), (:ConformityAssessmentBody)
- (:ProductWithDigitalElements) — id (STRING), name (STRING). Subtypes as labels: (:DefaultProduct), (:FreeAndOpenSourceSoftware), (:Software), (:Hardware)
- (:CybersecurityConcept) — id (STRING), name (STRING). Subtypes: (:Vulnerability), (:CybersecurityRisk), (:CyberThreat), (:Incident), (:SecurityUpdate)
- (:ComplianceArtifact) — id (STRING), name (STRING). Subtypes: (:ConformityAssessment), (:TechnicalDocumentation), (:CEMarking), (:HarmonisedStandard)
- (:LegalProvision) — id (STRING), name (STRING). Subtypes: (:Penalty), (:SupportPeriod)
- (:MarketActivity) — id (STRING), name (STRING). Subtypes: (:PlacingOnTheMarket), (:Recall), (:Withdrawal), (:SubstantialModification)
- (:ArticleRef) — ref (STRING, e.g. "Art. 28", "Annex VII")
- (:CRANode) — a common label shared by ALL non-Article, non-Obligation nodes

Relationships:
- (:Article)-[:CONTAINS_OBLIGATION]->(:Obligation)
- (:Actor)-[:HAS_OBLIGATION]->(:Obligation)
- (:Obligation)-[:RELATES_TO]->(:CRANode)
- (:Obligation)-[:REFINES]->(:Obligation) — sub-paragraph refines parent
- (:Obligation)-[:DERIVES_FROM]->(:Obligation) — cross-article derivation
- (:Obligation)-[:SUPPORTS]->(:Obligation) — documentation/assessment supports substantive
- (:Obligation)-[:COMPLEMENTS]->(:Obligation) — different actors, same goal
- (:Actor)-[:MANUFACTURES]->(:ProductWithDigitalElements)
- (:Actor)-[:MUST_COMPLY_WITH]->(:LegalProvision)
- (:Actor)-[:MUST_PROVIDE]->(:CRANode)
- (:Actor)-[:MUST_HANDLE]->(:CybersecurityConcept)
- (:Actor)-[:MUST_INFORM]->(:CRANode)
- (:Actor)-[:MUST_UNDERGO]->(:ComplianceArtifact)
- (:Actor)-[:REPORTS_TO]->(:Actor)
- (:CRANode)-[:REFERENCES]->(:ArticleRef)

CRITICAL RULES:
1. Article article_id is STRING with "Art. " prefix: "Art. 21", NOT "21" or 21
2. Subtypes are LABELS, NOT properties. CORRECT: MATCH (m:Manufacturer)  WRONG: MATCH (a:Actor {type: "Manufacturer"})
3. Article->Obligation uses CONTAINS_OBLIGATION. Actor->Obligation uses HAS_OBLIGATION.
4. All entity nodes also have the :CRANode label.
5. ALL relationships go LEFT-to-RIGHT with ->. NEVER use <-. CORRECT: (a)-[:REL]->(b) WRONG: (b)<-[:REL]-(a)

Example queries:
Q: all obligations related to manufacturers
A: MATCH (m:Manufacturer)-[:HAS_OBLIGATION]->(o:Obligation) RETURN m.name, o.id, o.action

Q: obligations in article 21
A: MATCH (a:Article {article_id: "Art. 21"})-[:CONTAINS_OBLIGATION]->(o:Obligation) RETURN o.id, o.action

Q: all penalties
A: MATCH (p:Penalty) RETURN p.id, p.name

Q: what must importers comply with
A: MATCH (i:Importer)-[:MUST_COMPLY_WITH]->(lp:LegalProvision) RETURN i.name, lp.name

Q: actors that report to ENISA
A: MATCH (a:Actor)-[:REPORTS_TO]->(e:ENISA) RETURN a.name

Q: obligations that refine other obligations in article 13
A: MATCH (o1:Obligation)-[:REFINES]->(o2:Obligation) WHERE o1.article_id = "Art. 13" RETURN o1.id, o1.action, o2.id, o2.action

Q: full obligation chain for conformity assessment
A: MATCH path = (o1:Obligation)-[:DERIVES_FROM|SUPPORTS|REFINES*1..3]->(o2:Obligation) WHERE any(l IN labels(o2) WHERE l = "Obligation") RETURN o1.id, o1.action, [r IN relationships(path) | type(r)] AS chain, o2.id, o2.action

Q: obligations related to products with digital elements
A: MATCH (o:Obligation)-[:RELATES_TO]->(p:ProductWithDigitalElements) RETURN o.id, o.action, p.name"""


def _call_ollama(question: str, error_feedback: str | None = None) -> str:
    """Call the local Ollama text2cypher model to generate a Cypher query."""
    user_content = f"Schema:\n{CRA_SCHEMA}\n\nQuestion: {question}"
    if error_feedback:
        user_content += (
            f"\n\nYour previous Cypher query caused this error:\n{error_feedback}\n"
            "Generate a CORRECTED query. Remember: subtypes are LABELS not properties."
        )
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a Neo4j Cypher expert. Given a graph schema and a "
                    "user question, generate ONLY a valid Cypher query. "
                    "Output ONLY the Cypher query, no explanation, no markdown. "
                    "Subtypes are NODE LABELS, not properties. "
                    "CORRECT: MATCH (m:Manufacturer) WRONG: MATCH (a {type: 'Manufacturer'})"
                ),
            },
            {
                "role": "user",
                "content": user_content,
            },
        ],
    }
    req = Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    resp = urlopen(req, timeout=OLLAMA_TIMEOUT)
    result = json.loads(resp.read())
    cypher = result["message"]["content"].strip()
    # Clean up: remove markdown fences if present
    if cypher.startswith("```"):
        lines = cypher.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        cypher = "\n".join(lines).strip()
    # Fix escaped newlines
    cypher = cypher.replace("\\n", "\n")
    # Fix reversed arrows: <-[:REL]-( → )-[:REL]->(
    import re

    cypher = re.sub(r"\)<-\[:([A-Z_]+)\]-\(", r")-[:\1]->(", cypher)
    return cypher


def ask_graph(question: str) -> str:
    """Ask a natural language question about the CRA knowledge graph.

    Uses a specialized local AI model (text2cypher) to translate your question
    into a Cypher query, then executes it against Neo4j and returns the results.

    Args:
        question: A natural language question about the CRA, e.g.
                  "What are the obligations in article 21?",
                  "Show me all manufacturers",
                  "What must importers comply with?"

    Returns:
        The query results formatted as a table, or an error message.
    """
    try:
        # Step 1: Generate Cypher
        log.info("text2cypher → generating Cypher for: %s", question)
        cypher = _call_ollama(question)
        log.info("text2cypher → generated: %s", cypher)

        # Step 2: Execute the Cypher
        result = query_neo4j(cypher)

        # Step 3: If error, retry once with error feedback
        if result.startswith("ERROR"):
            log.warning("text2cypher → first attempt failed: %s", result)
            cypher2 = _call_ollama(question, error_feedback=f"{cypher}\n→ {result}")
            log.info("text2cypher → retry generated: %s", cypher2)
            result2 = query_neo4j(cypher2)
            return f"Generated Cypher:\n{cypher2}\n\nResults:\n{result2}"

        # Return both the query and results for transparency
        return f"Generated Cypher:\n{cypher}\n\nResults:\n{result}"

    except Exception as e:
        log.error("text2cypher error: %s", e)
        return f"ERROR generating/executing Cypher: {e}"
