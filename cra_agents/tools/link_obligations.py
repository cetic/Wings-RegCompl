"""Obligation-linking tool for the CRA knowledge graph.

Discovers and creates inter-obligation relationships:
  - REFINES:      intra-article, sub-paragraph refines parent paragraph
  - DERIVES_FROM: cross-article, obligation exists because of another article
  - SUPPORTS:     evidence/documentation obligation supports a substantive one
  - COMPLEMENTS:  obligations from different actors towards the same goal

Two modes:
  1. Structural (fast, deterministic) — uses paragraph numbering, cross-refs,
     and shared CRANodes.
  2. Semantic (LLM-assisted) — uses Gemini to classify relationship type for
     top obligation pairs identified structurally.

Also provides a conformity_trace() tool that, given a topic, walks the
obligation graph to show the full chain of obligations relevant to conformity.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

log = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────
_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(_ENV_PATH)

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password123"

MIN_INTERVAL = 4.5
_last_call: float = 0.0

from ._llm import generate as _llm_generate  # noqa: E402

# Relationship types we create
REL_REFINES = "REFINES"
REL_DERIVES = "DERIVES_FROM"
REL_SUPPORTS = "SUPPORTS"
REL_COMPLEMENTS = "COMPLEMENTS"


def _get_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def _throttle():
    global _last_call
    now = time.time()
    wait = MIN_INTERVAL - (now - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()


def _retry_call(prompt: str, max_retries: int = 3) -> str | None:
    for attempt in range(max_retries):
        _throttle()
        try:
            return _llm_generate(prompt)
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                backoff = 10 * (2**attempt)
                log.warning("Rate limited, backing off %ds", backoff)
                time.sleep(backoff)
            else:
                log.error("LLM error: %s", e)
                return None
    return None


# ═══════════════════════════════════════════════════════════════════════
#  STRUCTURAL LINKING (deterministic, fast)
# ═══════════════════════════════════════════════════════════════════════


def _parse_paragraph_ref(ref: str | None) -> tuple[str, str, str]:
    """Parse 'Art. 13(2)(a)' → ('Art. 13', '2', 'a').

    Returns (article_id, paragraph_num, sub_ref).
    """
    if not ref:
        return ("", "", "")
    # Match patterns like Art. 13(2), Art. 13(2)(a), Art. 13(2)(a)(i)
    m = re.match(r"(Art\.\s*\d+)\((\d+)\)(?:\(([a-z]+)\))?", ref)
    if m:
        return (m.group(1), m.group(2), m.group(3) or "")
    # Simpler: just Art. N
    m2 = re.match(r"(Art\.\s*\d+)", ref)
    if m2:
        return (m2.group(1), "", "")
    return ("", "", "")


def _find_intra_article_refines(session) -> list[dict]:
    """Within each article, sub-paragraph obligations REFINE their parent paragraph.

    E.g., Art. 13(2)(a) REFINES Art. 13(2), and Art. 13(2) REFINES Art. 13(1)
    if Art. 13(1) is more general.
    """
    # Get all obligations grouped by article
    recs = session.run(
        "MATCH (a:Article)-[:CONTAINS_OBLIGATION]->(o:Obligation) "
        "RETURN a.article_id AS art, o.id AS oid, o.paragraph_ref AS pref, "
        "o.action AS action ORDER BY a.article_id, o.paragraph_ref"
    ).data()

    # Group by article
    by_article: dict[str, list[dict]] = defaultdict(list)
    for r in recs:
        by_article[r["art"]].append(r)

    links = []
    for art_id, obls in by_article.items():
        # Build a map: paragraph_ref → list of obligations
        by_para: dict[str, list[dict]] = defaultdict(list)
        for o in obls:
            if o["pref"]:
                by_para[o["pref"]].append(o)

        for obl in obls:
            art, para, sub = _parse_paragraph_ref(obl["pref"])
            if not art:
                continue

            # Sub-paragraph REFINES parent paragraph
            if sub and para:
                parent_ref = f"{art}({para})"
                if parent_ref in by_para:
                    for parent_obl in by_para[parent_ref]:
                        if parent_obl["oid"] != obl["oid"]:
                            links.append(
                                {
                                    "source": obl["oid"],
                                    "target": parent_obl["oid"],
                                    "type": REL_REFINES,
                                    "reason": f"sub-paragraph {obl['pref']} refines {parent_ref}",
                                }
                            )

    return links


def _find_cross_article_derives(session) -> list[dict]:
    """Obligations that reference another article DERIVE FROM obligations in that article.

    Uses the existing cross_references (CRANode → ArticleRef) to find which
    article-related nodes point to other articles, then links those obligations.
    """
    # Find obligations whose related CRANodes reference other articles
    recs = session.run(
        "MATCH (o:Obligation)-[:RELATES_TO]->(n:CRANode)-[:REFERENCES]->(ref:ArticleRef) "
        "WHERE ref.ref STARTS WITH 'Art.' "
        "RETURN o.id AS src_obl, o.article_id AS src_art, "
        "ref.ref AS target_art_ref, n.name AS via_node"
    ).data()

    # Normalize target article ref: "Art. 32(1)" → "Art. 32"
    links = []
    seen = set()
    for r in recs:
        tgt_m = re.match(r"(Art\.\s*\d+)", r["target_art_ref"])
        if not tgt_m:
            continue
        tgt_art = tgt_m.group(1)

        # Skip self-references
        if tgt_art == r["src_art"]:
            continue

        # Find obligations in the target article
        tgt_obls = session.run(
            "MATCH (a:Article {article_id: $aid})-[:CONTAINS_OBLIGATION]->(o:Obligation) "
            "RETURN o.id AS oid LIMIT 5",
            aid=tgt_art,
        ).data()

        for tgt in tgt_obls:
            key = (r["src_obl"], tgt["oid"])
            if key not in seen:
                seen.add(key)
                links.append(
                    {
                        "source": r["src_obl"],
                        "target": tgt["oid"],
                        "type": REL_DERIVES,
                        "reason": f"{r['src_art']} refers to {tgt_art} via {r['via_node']}",
                    }
                )

    return links


def _find_supports_links(session) -> list[dict]:
    """Documentation/assessment obligations SUPPORT substantive obligations.

    If obligations from different articles both RELATE_TO the same ComplianceArtifact
    or ConformityAssessment node, the documentation obligation SUPPORTS the
    substantive one.
    """
    recs = session.run(
        "MATCH (o1:Obligation)-[:RELATES_TO]->(ca)<-[:RELATES_TO]-(o2:Obligation) "
        "WHERE o1.article_id <> o2.article_id "
        "AND any(l IN labels(ca) WHERE l IN "
        "['ConformityAssessment','TechnicalDocumentation','CEMarking',"
        "'HarmonisedStandard','ComplianceArtifact']) "
        "AND elementId(o1) < elementId(o2) "
        "RETURN o1.id AS o1_id, o1.article_id AS o1_art, o1.action AS o1_action, "
        "o2.id AS o2_id, o2.article_id AS o2_art, o2.action AS o2_action, "
        "ca.name AS shared, labels(ca) AS ca_labels "
        "ORDER BY shared LIMIT 200"
    ).data()

    # Heuristic: obligations in Art. 13 (essential requirements), Art. 5-12
    # are substantive. Obligations in Art. 24-35 (conformity procedures),
    # Art. 23 (technical docs) SUPPORT them.
    SUBSTANTIVE_ARTS = {f"Art. {n}" for n in range(1, 24)}
    PROCEDURAL_ARTS = {f"Art. {n}" for n in range(24, 72)}

    links = []
    seen = set()
    for r in recs:
        o1_is_subst = r["o1_art"] in SUBSTANTIVE_ARTS
        o2_is_subst = r["o2_art"] in SUBSTANTIVE_ARTS

        if o1_is_subst and not o2_is_subst:
            src, tgt = r["o2_id"], r["o1_id"]
        elif o2_is_subst and not o1_is_subst:
            src, tgt = r["o1_id"], r["o2_id"]
        else:
            continue  # both substantive or both procedural — skip here

        key = (src, tgt)
        if key not in seen:
            seen.add(key)
            links.append(
                {
                    "source": src,
                    "target": tgt,
                    "type": REL_SUPPORTS,
                    "reason": f"procedural obligation supports substantive via shared {r['shared']}",
                }
            )

    return links


def _find_complements_links(session) -> list[dict]:
    """Obligations from different actors on the same topic COMPLEMENT each other.

    If two obligations from different articles + different actors both RELATE_TO
    the same CRANode, they complement each other.
    """
    recs = session.run(
        "MATCH (a1:Actor)-[:HAS_OBLIGATION]->(o1:Obligation)-[:RELATES_TO]->"
        "(n:CRANode)<-[:RELATES_TO]-(o2:Obligation)<-[:HAS_OBLIGATION]-(a2:Actor) "
        "WHERE o1.article_id <> o2.article_id "
        "AND a1.id <> a2.id "
        "AND elementId(o1) < elementId(o2) "
        "RETURN o1.id AS o1_id, a1.name AS a1_name, o1.article_id AS o1_art, "
        "o2.id AS o2_id, a2.name AS a2_name, o2.article_id AS o2_art, "
        "n.name AS shared "
        "ORDER BY shared LIMIT 200"
    ).data()

    links = []
    seen = set()
    for r in recs:
        key = (r["o1_id"], r["o2_id"])
        if key not in seen:
            seen.add(key)
            links.append(
                {
                    "source": r["o1_id"],
                    "target": r["o2_id"],
                    "type": REL_COMPLEMENTS,
                    "reason": f"{r['a1_name']} ({r['o1_art']}) and {r['a2_name']} ({r['o2_art']}) both address {r['shared']}",
                }
            )

    return links


# ═══════════════════════════════════════════════════════════════════════
#  LLM-ASSISTED CLASSIFICATION (optional, slower)
# ═══════════════════════════════════════════════════════════════════════

_CLASSIFY_PROMPT = """You are a legal analyst classifying relationships between EU Cyber Resilience Act obligations.

Given two obligations, classify their relationship as EXACTLY ONE of:
- REFINES: obligation A provides more specific detail on the general requirement in B
- DERIVES_FROM: obligation A exists because of a mandate in B (cross-article derivation)
- SUPPORTS: obligation A provides evidence, documentation, or assessment to demonstrate compliance with B
- COMPLEMENTS: obligations A and B together achieve the same goal, from different actors or perspectives
- NONE: no meaningful relationship

Return ONLY a JSON object: {"relationship": "<type>", "confidence": <0.0-1.0>, "reason": "<one sentence>"}

Obligation A:
  ID: {a_id}
  Article: {a_art}
  Paragraph: {a_para}
  Action: {a_action}

Obligation B:
  ID: {b_id}
  Article: {b_art}
  Paragraph: {b_para}
  Action: {b_action}

Shared context: {context}
"""


def _classify_pair_llm(obl_a: dict, obl_b: dict, context: str) -> dict | None:
    """Use Gemini to classify the relationship between two obligations."""
    prompt = _CLASSIFY_PROMPT.format(
        a_id=obl_a["id"],
        a_art=obl_a.get("article_id", "?"),
        a_para=obl_a.get("paragraph_ref", "?"),
        a_action=obl_a.get("action", "?"),
        b_id=obl_b["id"],
        b_art=obl_b.get("article_id", "?"),
        b_para=obl_b.get("paragraph_ref", "?"),
        b_action=obl_b.get("action", "?"),
        context=context,
    )
    raw = _retry_call(prompt)
    if not raw:
        return None

    # Parse JSON from response
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        raw = "\n".join(lines).strip()

    try:
        result = json.loads(raw)
        rel = result.get("relationship", "NONE")
        if rel not in (REL_REFINES, REL_DERIVES, REL_SUPPORTS, REL_COMPLEMENTS, "NONE"):
            rel = "NONE"
        return {
            "relationship": rel,
            "confidence": float(result.get("confidence", 0.5)),
            "reason": result.get("reason", ""),
        }
    except (json.JSONDecodeError, ValueError):
        return None


# ═══════════════════════════════════════════════════════════════════════
#  PUBLIC TOOLS
# ═══════════════════════════════════════════════════════════════════════


def link_obligations(mode: str = "structural", max_llm_pairs: int = 50) -> dict:
    """Discover and create inter-obligation relationships in the CRA knowledge graph.

    Analyzes the 461 obligations to find how they relate to each other:
    - REFINES: sub-paragraph obligations that detail a parent obligation
    - DERIVES_FROM: obligations that exist because of another article's mandate
    - SUPPORTS: documentation/assessment obligations that support substantive ones
    - COMPLEMENTS: obligations from different actors towards the same goal

    Args:
        mode: "structural" (fast, deterministic) or "full" (structural + LLM
              classification for top pairs). Default "structural".
        max_llm_pairs: Maximum obligation pairs to classify with LLM in "full"
              mode. Default 50.

    Returns:
        Summary of discovered and created relationships with counts by type.
    """
    driver = _get_driver()
    try:
        driver.verify_connectivity()
    except Exception as e:
        return {"status": "error", "report": f"Cannot connect to Neo4j: {e}"}

    stats = {REL_REFINES: 0, REL_DERIVES: 0, REL_SUPPORTS: 0, REL_COMPLEMENTS: 0}
    all_links: list[dict] = []

    with driver.session() as session:
        # Check current state
        existing = session.run(
            "MATCH (o1:Obligation)-[r]->(o2:Obligation) "
            "WHERE type(r) IN ['REFINES','DERIVES_FROM','SUPPORTS','COMPLEMENTS'] "
            "RETURN count(r) AS cnt"
        ).single()["cnt"]

        log.info("link_obligations: mode=%s, existing links=%d", mode, existing)

        # ── Phase 1: Structural discovery ─────────────────────────────
        log.info("Phase 1a: intra-article REFINES...")
        refines = _find_intra_article_refines(session)
        all_links.extend(refines)
        log.info("  Found %d REFINES links", len(refines))

        log.info("Phase 1b: cross-article DERIVES_FROM...")
        derives = _find_cross_article_derives(session)
        all_links.extend(derives)
        log.info("  Found %d DERIVES_FROM links", len(derives))

        log.info("Phase 1c: SUPPORTS links...")
        supports = _find_supports_links(session)
        all_links.extend(supports)
        log.info("  Found %d SUPPORTS links", len(supports))

        log.info("Phase 1d: COMPLEMENTS links...")
        complements = _find_complements_links(session)
        all_links.extend(complements)
        log.info("  Found %d COMPLEMENTS links", len(complements))

        # ── Phase 2: LLM classification (optional) ───────────────────
        llm_classified = 0
        if mode == "full" and max_llm_pairs > 0:
            log.info(
                "Phase 2: LLM classification of top %d ambiguous pairs...",
                max_llm_pairs,
            )
            # Find obligation pairs sharing CRANodes that weren't already linked
            linked_pairs = {(l["source"], l["target"]) for l in all_links}
            linked_pairs.update({(l["target"], l["source"]) for l in all_links})

            candidates = session.run(
                "MATCH (o1:Obligation)-[:RELATES_TO]->(n:CRANode)<-[:RELATES_TO]-(o2:Obligation) "
                "WHERE o1.article_id <> o2.article_id "
                "AND elementId(o1) < elementId(o2) "
                "RETURN o1 AS o1_node, o2 AS o2_node, "
                "collect(n.name)[0..3] AS shared_names "
                "LIMIT 500"
            ).data()

            pairs_to_classify = []
            for c in candidates:
                o1p = dict(c["o1_node"])
                o2p = dict(c["o2_node"])
                if (o1p["id"], o2p["id"]) in linked_pairs:
                    continue
                pairs_to_classify.append((o1p, o2p, ", ".join(c["shared_names"])))
                if len(pairs_to_classify) >= max_llm_pairs:
                    break

            for i, (o1p, o2p, ctx) in enumerate(pairs_to_classify):
                result = _classify_pair_llm(o1p, o2p, ctx)
                if (
                    result
                    and result["relationship"] != "NONE"
                    and result["confidence"] >= 0.6
                ):
                    all_links.append(
                        {
                            "source": o1p["id"],
                            "target": o2p["id"],
                            "type": result["relationship"],
                            "reason": f"LLM ({result['confidence']:.0%}): {result['reason']}",
                        }
                    )
                    llm_classified += 1
                if (i + 1) % 10 == 0:
                    log.info(
                        "  LLM classified %d/%d pairs", i + 1, len(pairs_to_classify)
                    )

            log.info("  LLM added %d links", llm_classified)

        # ── Phase 3: Write links to Neo4j ─────────────────────────────
        log.info("Phase 3: Writing %d links to Neo4j...", len(all_links))
        created = 0
        for link in all_links:
            rel_type = link["type"]
            result = session.run(
                f"MATCH (o1:Obligation {{id: $src}}) "
                f"MATCH (o2:Obligation {{id: $tgt}}) "
                f"MERGE (o1)-[r:`{rel_type}`]->(o2) "
                f"ON CREATE SET r.reason = $reason, r.method = $method "
                f"RETURN count(r) AS cnt",
                src=link["source"],
                tgt=link["target"],
                reason=link["reason"],
                method="llm" if link["reason"].startswith("LLM") else "structural",
            ).single()
            if result and result["cnt"] > 0:
                stats[rel_type] = stats.get(rel_type, 0) + 1
                created += 1

        # Final count
        final = session.run(
            "MATCH (o1:Obligation)-[r]->(o2:Obligation) "
            "WHERE type(r) IN ['REFINES','DERIVES_FROM','SUPPORTS','COMPLEMENTS'] "
            "RETURN type(r) AS t, count(r) AS c ORDER BY t"
        ).data()

    driver.close()

    # Build report
    final_map = {r["t"]: r["c"] for r in final}
    report_lines = [
        f"Obligation linking complete (mode: {mode})",
        f"Previously existing: {existing} links",
        f"Newly discovered: {len(all_links)} candidate links",
        f"Written to Neo4j: {created} relationships",
        "",
        "Relationship counts in graph:",
    ]
    for rel_type in [REL_REFINES, REL_DERIVES, REL_SUPPORTS, REL_COMPLEMENTS]:
        cnt = final_map.get(rel_type, 0)
        report_lines.append(f"  {rel_type}: {cnt}")
    total = sum(final_map.values())
    report_lines.append(f"  TOTAL: {total}")

    if mode == "full":
        report_lines.append(f"\nLLM-classified pairs: {llm_classified}")

    report = "\n".join(report_lines)
    log.info(report)

    return {
        "status": "ok",
        "report": report,
        "counts": final_map,
        "total_links": total,
    }


def conformity_trace(topic: str, max_depth: int = 3) -> dict:
    """Trace the full chain of obligations relevant to a conformity topic.

    Starting from obligations matching a topic (e.g., "vulnerability handling",
    "CE marking", "technical documentation"), walks the inter-obligation
    graph (REFINES, DERIVES_FROM, SUPPORTS, COMPLEMENTS) to build a complete
    conformity traceability chain.

    Args:
        topic: The conformity topic to trace, e.g. "vulnerability handling",
               "essential cybersecurity requirements", "CE marking",
               "software bill of materials".
        max_depth: Maximum hops to follow in the obligation graph (default 3).

    Returns:
        A traceability report showing the obligation chain with relationship
        types, actors, articles, and actions.
    """
    driver = _get_driver()
    try:
        driver.verify_connectivity()
    except Exception as e:
        return {"status": "error", "report": f"Cannot connect to Neo4j: {e}"}

    with driver.session() as session:
        # Check if inter-obligation links exist
        link_count = session.run(
            "MATCH (:Obligation)-[r]->(:Obligation) "
            "WHERE type(r) IN ['REFINES','DERIVES_FROM','SUPPORTS','COMPLEMENTS'] "
            "RETURN count(r) AS cnt"
        ).single()["cnt"]

        if link_count == 0:
            return {
                "status": "error",
                "report": "No inter-obligation links found. Run link_obligations() first to discover relationships between obligations.",
            }

        # Step 1: Find seed obligations matching the topic
        # ── Keyword pass: action text ──────────────────────────────────
        seeds = session.run(
            "MATCH (o:Obligation) "
            "WHERE toLower(coalesce(o.action,'')) CONTAINS toLower($topic) "
            "   OR toLower(coalesce(o.action_full,'')) CONTAINS toLower($topic) "
            "RETURN o.id AS oid, o.article_id AS art, o.action AS action, "
            "o.paragraph_ref AS pref "
            "LIMIT 10",
            topic=topic,
        ).data()

        # ── Keyword pass: related CRANodes ─────────────────────────────
        node_seeds = session.run(
            "MATCH (o:Obligation)-[:RELATES_TO]->(n:CRANode) "
            "WHERE toLower(n.name) CONTAINS toLower($topic) "
            "RETURN DISTINCT o.id AS oid, o.article_id AS art, "
            "o.action AS action, o.paragraph_ref AS pref "
            "LIMIT 10",
            topic=topic,
        ).data()

        # Merge keyword seeds
        seen_ids = {s["oid"] for s in seeds}
        for ns in node_seeds:
            if ns["oid"] not in seen_ids:
                seeds.append(ns)
                seen_ids.add(ns["oid"])

        # ── Semantic pass: vector similarity on Obligation.embedding ───
        obl_idx = session.run(
            "SHOW INDEXES WHERE name = 'cra_obligation_embedding'"
        ).data()
        if obl_idx:
            try:
                from .vector_tools import _embed_query as _vt_embed

                qvec = _vt_embed(topic)
                sem_seeds = session.run(
                    """
                    CALL db.index.vector.queryNodes(
                        'cra_obligation_embedding', 8, $vec)
                    YIELD node AS o, score
                    WHERE score > 0.65
                    RETURN o.id AS oid, o.article_id AS art,
                           o.action AS action, o.paragraph_ref AS pref
                    """,
                    vec=qvec,
                ).data()
                for ss in sem_seeds:
                    if ss["oid"] not in seen_ids:
                        seeds.append(ss)
                        seen_ids.add(ss["oid"])
                log.debug("Semantic seeds added: %d", len(sem_seeds))
            except Exception as e:
                log.warning("Semantic seed search failed in conformity_trace: %s", e)

        if not seeds:
            return {
                "status": "ok",
                "report": (
                    f'No obligations found matching topic "{topic}". '
                    "Try a different term, or run vectorize_obligations() to enable "
                    "semantic matching."
                ),
                "chain": [],
            }

        # Step 2: Walk the obligation graph from seeds
        seed_ids = [s["oid"] for s in seeds]

        # Use Neo4j variable-length path traversal
        chain_recs = session.run(
            "UNWIND $seeds AS seed_id "
            "MATCH (start:Obligation {id: seed_id}) "
            "OPTIONAL MATCH path = (start)-[r*1.."
            + str(max_depth)
            + "]-(linked:Obligation) "
            "WHERE ALL(rel IN r WHERE type(rel) IN "
            "['REFINES','DERIVES_FROM','SUPPORTS','COMPLEMENTS']) "
            "WITH start, linked, r "
            "OPTIONAL MATCH (actor)-[:HAS_OBLIGATION]->(linked) "
            "RETURN start.id AS seed_id, start.article_id AS seed_art, "
            "start.action AS seed_action, "
            "linked.id AS linked_id, linked.article_id AS linked_art, "
            "linked.action AS linked_action, linked.paragraph_ref AS linked_pref, "
            "[rel IN r | type(rel)] AS rel_types, "
            "collect(DISTINCT actor.name) AS actors "
            "ORDER BY seed_id, linked_art",
            seeds=seed_ids,
        ).data()

        # Step 3: Build the trace report
        # Group by seed
        trace: dict[str, list] = defaultdict(list)
        for rec in chain_recs:
            sid = rec["seed_id"]
            if rec["linked_id"]:
                trace[sid].append(
                    {
                        "obligation": rec["linked_id"],
                        "article": rec["linked_art"],
                        "paragraph": rec["linked_pref"],
                        "action": rec["linked_action"],
                        "relationship_chain": rec["rel_types"],
                        "actors": [a for a in rec["actors"] if a],
                    }
                )
            elif sid not in trace:
                trace[sid] = []

        # Also get actors for seeds
        seed_actors_recs = session.run(
            "UNWIND $seeds AS seed_id "
            "MATCH (start:Obligation {id: seed_id}) "
            "OPTIONAL MATCH (actor)-[:HAS_OBLIGATION]->(start) "
            "RETURN start.id AS oid, start.article_id AS art, "
            "start.action AS action, start.paragraph_ref AS pref, "
            "collect(DISTINCT actor.name) AS actors",
            seeds=seed_ids,
        ).data()
        seed_info = {r["oid"]: r for r in seed_actors_recs}

    driver.close()

    # Format report
    report_lines = [
        f'Conformity trace for "{topic}" — {len(seeds)} seed obligations, '
        f"{sum(len(v) for v in trace.values())} linked obligations:\n"
    ]

    chain_items = []
    for seed in seeds:
        sid = seed["oid"]
        si = seed_info.get(sid, {})
        actors = ", ".join(a for a in si.get("actors", []) if a) or "unknown"
        report_lines.append(f"## SEED: {sid} ({seed['art']})")
        report_lines.append(f"   Action: {seed['action']}")
        report_lines.append(f"   Actor(s): {actors}")
        report_lines.append(f"   Paragraph: {seed.get('pref', '?')}")

        chain_items.append(
            {
                "role": "seed",
                "obligation": sid,
                "article": seed["art"],
                "action": seed["action"],
                "actors": si.get("actors", []),
            }
        )

        linked = trace.get(sid, [])
        if linked:
            # Deduplicate
            seen_linked = set()
            for lnk in linked:
                if lnk["obligation"] in seen_linked:
                    continue
                seen_linked.add(lnk["obligation"])
                rel_chain = (
                    " → ".join(lnk["relationship_chain"])
                    if lnk["relationship_chain"]
                    else "?"
                )
                actors_str = ", ".join(lnk["actors"]) if lnk["actors"] else "?"
                report_lines.append(
                    f"   └─[{rel_chain}]─> {lnk['obligation']} ({lnk['article']})"
                )
                report_lines.append(f"      Action: {lnk['action']}")
                report_lines.append(f"      Actor(s): {actors_str}")

                chain_items.append(
                    {
                        "role": "linked",
                        "obligation": lnk["obligation"],
                        "article": lnk["article"],
                        "action": lnk["action"],
                        "relationship": rel_chain,
                        "actors": lnk["actors"],
                    }
                )
        else:
            report_lines.append("   (no linked obligations)")
        report_lines.append("")

    report = "\n".join(report_lines)

    return {
        "status": "ok",
        "report": report,
        "seed_count": len(seeds),
        "linked_count": sum(len(v) for v in trace.values()),
        "chain": chain_items,
    }


# ═══════════════════════════════════════════════════════════════════════
#  COMPLIANCE IMPACT — "if I comply with X, what else am I compliant with?"
# ═══════════════════════════════════════════════════════════════════════

# Propagation rules per relationship type and direction:
#
# Relationship      Direction of compliance propagation
# ────────────────  ──────────────────────────────────────────────────
# REFINES           child→parent: complying with child PARTIALLY covers parent
#                   parent→child: does NOT propagate (parent is general)
#
# DERIVES_FROM      A→B: A derived from B. Complying with A fulfills what B
#                   required in that context → COVERS B partially.
#                   B→A: does NOT propagate (B created A but didn't fulfil it)
#
# SUPPORTS          procedural→substantive: complying with procedural provides
#                   EVIDENCE for substantive → EVIDENCE contribution.
#                   substantive→procedural: does NOT propagate.
#
# COMPLEMENTS       bidirectional but weaker: complying with A CONTRIBUTES
#                   toward the same goal as B. Not full coverage.

_PROPAGATION_RULES = {
    # (rel_type, direction): (impact_level, description)
    # direction: "outgoing" = we follow source→target, "incoming" = target→source
    (REL_REFINES, "outgoing"): ("partial", "refines (more specific detail of)"),
    (REL_REFINES, "incoming"): (None, None),  # parent doesn't cover child
    (REL_DERIVES, "outgoing"): ("partial", "fulfills the mandate from"),
    (REL_DERIVES, "incoming"): (None, None),  # source doesn't fulfil derived
    (REL_SUPPORTS, "outgoing"): ("evidence", "provides supporting evidence for"),
    (REL_SUPPORTS, "incoming"): (None, None),  # substantive doesn't cover procedural
    (REL_COMPLEMENTS, "outgoing"): ("contributes", "contributes to the same goal as"),
    (REL_COMPLEMENTS, "incoming"): (
        "contributes",
        "receives contribution toward same goal",
    ),
}

# Impact levels ordered by strength
_IMPACT_ORDER = {"full": 0, "partial": 1, "evidence": 2, "contributes": 3}


def compliance_impact(obligation_ids: list[str], max_depth: int = 2) -> dict:
    """Given obligations you are compliant with, show what other obligations
    are fully or partially covered.

    Walks the inter-obligation graph following compliance propagation rules:
    - **FULLY COVERED**: all refinements of a parent → parent is fully covered
    - **PARTIALLY COVERED**: your obligation refines or derives from another
    - **EVIDENCE PROVIDED**: your procedural obligation supports a substantive one
    - **CONTRIBUTES TO**: your obligation complements another (different actor, same goal)

    Args:
        obligation_ids: List of obligation IDs you are compliant with.
            Examples: ["Art. 13_obl_12"], ["Art. 13_obl_6", "Art. 13_obl_8"],
            or a single article like ["Art. 13"] to select all its obligations.
        max_depth: Maximum hops to propagate (default 2).

    Returns:
        A compliance impact report showing which other obligations are covered,
        partially covered, or receive evidence from your compliance.
    """
    driver = _get_driver()
    try:
        driver.verify_connectivity()
    except Exception as e:
        return {"status": "error", "report": f"Cannot connect to Neo4j: {e}"}

    with driver.session() as session:
        # Check inter-obligation links exist
        link_count = session.run(
            "MATCH (:Obligation)-[r]->(:Obligation) "
            "WHERE type(r) IN ['REFINES','DERIVES_FROM','SUPPORTS','COMPLEMENTS'] "
            "RETURN count(r) AS cnt"
        ).single()["cnt"]

        if link_count == 0:
            return {
                "status": "error",
                "report": "No inter-obligation links found. Run link_obligations() first.",
            }

        # Resolve obligation IDs — expand article-level references
        resolved_ids: set[str] = set()
        for oid in obligation_ids:
            oid = oid.strip()
            # Check if it's an article reference like "Art. 13" (no _obl_)
            if re.match(r"^Art\.\s*\d+$", oid):
                art_obls = session.run(
                    "MATCH (a:Article {article_id: $aid})-[:CONTAINS_OBLIGATION]->(o:Obligation) "
                    "RETURN o.id AS oid",
                    aid=oid,
                ).data()
                for r in art_obls:
                    resolved_ids.add(r["oid"])
            else:
                # Verify it exists
                exists = session.run(
                    "MATCH (o:Obligation {id: $oid}) RETURN o.id AS oid",
                    oid=oid,
                ).data()
                if exists:
                    resolved_ids.add(oid)

        if not resolved_ids:
            return {
                "status": "error",
                "report": f"No obligations found for IDs: {obligation_ids}. "
                "Use format like 'Art. 13_obl_12' or 'Art. 13' for all of an article.",
            }

        # Fetch details for compliant obligations
        compliant_details: dict[str, dict] = {}
        for oid in resolved_ids:
            rec = session.run(
                "MATCH (o:Obligation {id: $oid}) "
                "OPTIONAL MATCH (actor)-[:HAS_OBLIGATION]->(o) "
                "RETURN o.id AS id, o.article_id AS art, o.action AS action, "
                "o.paragraph_ref AS pref, collect(DISTINCT actor.name) AS actors",
                oid=oid,
            ).single()
            if rec:
                compliant_details[oid] = dict(rec)

        # ── BFS propagation following compliance rules ────────────────
        # impact_map: obligation_id -> {level, reason, via, depth}
        impact_map: dict[str, dict] = {}
        queue: list[tuple[str, int]] = [(oid, 0) for oid in resolved_ids]
        visited: set[str] = set(resolved_ids)

        while queue:
            current_id, depth = queue.pop(0)
            if depth >= max_depth:
                continue

            # Get all inter-obligation neighbors
            neighbors = session.run(
                "MATCH (o:Obligation {id: $oid})-[r]-(other:Obligation) "
                "WHERE type(r) IN ['REFINES','DERIVES_FROM','SUPPORTS','COMPLEMENTS'] "
                "RETURN other.id AS other_id, other.article_id AS other_art, "
                "other.action AS other_action, other.paragraph_ref AS other_pref, "
                "type(r) AS rtype, "
                "CASE WHEN startNode(r) = o THEN 'outgoing' ELSE 'incoming' END AS dir",
                oid=current_id,
            ).data()

            for nb in neighbors:
                other_id = nb["other_id"]
                if other_id in resolved_ids:
                    continue  # already compliant, skip

                rtype = nb["rtype"]
                direction = nb["dir"]

                rule_key = (rtype, direction)
                impact_level, description = _PROPAGATION_RULES.get(
                    rule_key, (None, None)
                )

                if impact_level is None:
                    continue  # no propagation in this direction

                # Check if we already have a stronger impact for this obligation
                if other_id in impact_map:
                    existing_level = impact_map[other_id]["level"]
                    if _IMPACT_ORDER.get(existing_level, 99) <= _IMPACT_ORDER.get(
                        impact_level, 99
                    ):
                        continue  # existing is stronger or equal

                impact_map[other_id] = {
                    "level": impact_level,
                    "reason": f"Your compliance with {current_id} {description} {other_id}",
                    "via": current_id,
                    "rtype": rtype,
                    "direction": direction,
                    "depth": depth + 1,
                    "article": nb["other_art"],
                    "action": nb["other_action"],
                    "paragraph": nb["other_pref"],
                }

                if other_id not in visited:
                    visited.add(other_id)
                    queue.append((other_id, depth + 1))

        # ── Check for FULL coverage via REFINES ───────────────────────
        # A parent obligation is FULLY covered if ALL its refinements are
        # in the compliant set
        parents_in_impact = {
            oid
            for oid, info in impact_map.items()
            if info["rtype"] == REL_REFINES and info["direction"] == "outgoing"
        }
        for parent_id in parents_in_impact:
            # Get all children that REFINE this parent
            children = session.run(
                "MATCH (child:Obligation)-[:REFINES]->(parent:Obligation {id: $pid}) "
                "RETURN child.id AS cid",
                pid=parent_id,
            ).data()
            child_ids = {c["cid"] for c in children}

            if child_ids and child_ids.issubset(resolved_ids):
                # All refinements are compliant → parent is fully covered
                impact_map[parent_id]["level"] = "full"
                impact_map[parent_id]["reason"] = (
                    f"ALL {len(child_ids)} refinements are compliant → "
                    f"{parent_id} is fully covered"
                )

    driver.close()

    # ── Group results by impact level ─────────────────────────────────
    grouped: dict[str, list[dict]] = {
        "full": [],
        "partial": [],
        "evidence": [],
        "contributes": [],
    }
    for oid, info in sorted(
        impact_map.items(), key=lambda x: (_IMPACT_ORDER.get(x[1]["level"], 99), x[0])
    ):
        grouped[info["level"]].append({"obligation": oid, **info})

    # ── Build report ──────────────────────────────────────────────────
    report_lines = [
        f"Compliance Impact Analysis",
        f"{'=' * 50}",
        f"You declared compliance with {len(resolved_ids)} obligation(s):",
    ]
    for oid in sorted(resolved_ids):
        d = compliant_details.get(oid, {})
        actors = ", ".join(a for a in d.get("actors", []) if a) or "?"
        action = (d.get("action") or "?")[:100]
        report_lines.append(f"  - {oid} ({d.get('art', '?')}) [{actors}]: {action}")

    report_lines.append(
        f"\nImpact on other obligations ({len(impact_map)} affected):\n"
    )

    # Full coverage
    full = grouped["full"]
    if full:
        report_lines.append(f"FULLY COVERED ({len(full)}):")
        for item in full:
            report_lines.append(f"  [FULL] {item['obligation']} ({item['article']})")
            report_lines.append(f"    {item['reason']}")
            action = (item.get("action") or "?")[:120]
            report_lines.append(f"    Action: {action}")
        report_lines.append("")

    # Partial coverage
    partial = grouped["partial"]
    if partial:
        report_lines.append(f"PARTIALLY COVERED ({len(partial)}):")
        for item in partial:
            report_lines.append(f"  [PARTIAL] {item['obligation']} ({item['article']})")
            report_lines.append(f"    {item['reason']}")
            action = (item.get("action") or "?")[:120]
            report_lines.append(f"    Action: {action}")
        report_lines.append("")

    # Evidence
    evidence = grouped["evidence"]
    if evidence:
        report_lines.append(f"EVIDENCE PROVIDED FOR ({len(evidence)}):")
        for item in evidence:
            report_lines.append(
                f"  [EVIDENCE] {item['obligation']} ({item['article']})"
            )
            report_lines.append(f"    {item['reason']}")
            action = (item.get("action") or "?")[:120]
            report_lines.append(f"    Action: {action}")
        report_lines.append("")

    # Contributes
    contrib = grouped["contributes"]
    if contrib:
        report_lines.append(f"CONTRIBUTES TO ({len(contrib)}):")
        for item in contrib:
            report_lines.append(
                f"  [CONTRIBUTES] {item['obligation']} ({item['article']})"
            )
            report_lines.append(f"    {item['reason']}")
            action = (item.get("action") or "?")[:120]
            report_lines.append(f"    Action: {action}")
        report_lines.append("")

    if not impact_map:
        report_lines.append("  No compliance impact found for these obligations.")
        report_lines.append(
            "  This may mean they are isolated or link_obligations() needs to be re-run."
        )

    # Summary
    report_lines.append(f"\nSUMMARY:")
    report_lines.append(f"  Compliant with: {len(resolved_ids)} obligations")
    report_lines.append(f"  Fully covered:  {len(full)}")
    report_lines.append(f"  Partially covered: {len(partial)}")
    report_lines.append(f"  Evidence provided: {len(evidence)}")
    report_lines.append(f"  Contributes to: {len(contrib)}")
    report_lines.append(f"  Total impacted: {len(impact_map)}")

    report = "\n".join(report_lines)

    return {
        "status": "ok",
        "report": report,
        "compliant_count": len(resolved_ids),
        "impact_count": len(impact_map),
        "full": len(full),
        "partial": len(partial),
        "evidence": len(evidence),
        "contributes": len(contrib),
        "details": grouped,
    }
