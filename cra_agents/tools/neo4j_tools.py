"""Tools for Neo4j interaction — ingestion and querying."""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

from neo4j import GraphDatabase

# ── Connection settings ────────────────────────────────────────────────
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password123")

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "outputs" / "articles"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _get_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


# ── CRA structure: Article → (Chapter, Section) ───────────────────────
# EU Regulation (EU) 2024/2847 — Cyber Resilience Act
# No explicit sections exist within chapters, so all default to sec1.
_ARTICLE_TO_CHAPTER: dict[int, tuple[int, int]] = {}
_CRA_CHAPTERS = [
    (1, 1, 12),  # Chapter I:   Art. 1-12   (General Provisions)
    (2, 1, 26),  # Chapter II:  Art. 13-26  (Obligations of Economic Operators)
    (3, 1, 34),  # Chapter III: Art. 27-34  (Conformity of the Product)
    (
        4,
        1,
        51,
    ),  # Chapter IV:  Art. 35-51  (Notification of Conformity Assessment Bodies)
    (5, 1, 60),  # Chapter V:   Art. 52-60  (Market Surveillance and Enforcement)
    (6, 1, 62),  # Chapter VI:  Art. 61-62  (Delegated Powers and Committee Procedure)
    (7, 1, 65),  # Chapter VII: Art. 63-65  (Confidentiality and Penalties)
    (8, 1, 71),  # Chapter VIII:Art. 66-71  (Transitional and Final Provisions)
]
_start = 1
for ch_num, sec_num, end_art in _CRA_CHAPTERS:
    for art in range(_start, end_art + 1):
        _ARTICLE_TO_CHAPTER[art] = (ch_num, sec_num)
    _start = end_art + 1


def _build_obligation_id(
    article_id: str,
    paragraph_ref: str,
    obl_index: int,
) -> str:
    """Build a structured obligation ID.

    Format by source:
      - Articles:  ch{N}_sec{S}_art{A}_par{P}_{i}
      - Recitals:  Rec{N}_par{P}_{i}
      - Annexes:   Ann{ROMAN}_Part{ROMAN}_par{P}_{i}  (Part omitted when not specified)

    Args:
        article_id:    e.g. "Art. 13", "Recital (5)", "Annex I"
        paragraph_ref: e.g. "Art. 13(8)", "Annex I, Part II, point 3"
        obl_index:     1-based index of the obligation within its paragraph
    """
    # Extract paragraph number from paragraph_ref like "Art. 13(8)"
    par_match = re.search(r"\((\d+)\)", paragraph_ref) if paragraph_ref else None
    par_num = int(par_match.group(1)) if par_match else 1  # default to par 1

    # Recitals: "Recital (5)" → Rec5_par1_1
    rec_match = (
        re.search(r"Recital\s*\((\d+)\)", article_id, re.IGNORECASE)
        if article_id
        else None
    )
    if rec_match:
        return f"Rec{rec_match.group(1)}_par{par_num}_{obl_index}"

    # Annexes: "Annex I" → AnnI_PartII_par1_1 (with Part) or AnnI_par1_1 (without Part)
    ann_match = (
        re.search(r"Annex\s+(I{1,3}V?|IV|VI{0,3}|VIII?)", article_id, re.IGNORECASE)
        if article_id
        else None
    )
    if ann_match:
        # Extract point number from paragraph_ref like "Annex I, point 3"
        point_match = (
            re.search(r"point\s+(\d+)", paragraph_ref) if paragraph_ref else None
        )
        if point_match and par_num == 1:
            par_num = int(point_match.group(1))
        roman = ann_match.group(1).upper()  # normalise to uppercase Roman numeral
        # Extract Part from paragraph_ref like "Annex I, Part II, point 1"
        part_match = (
            re.search(
                r"Part\s+(I{1,3}V?|IV|VI{0,3}|VIII?)", paragraph_ref, re.IGNORECASE
            )
            if paragraph_ref
            else None
        )
        part_segment = f"_Part{part_match.group(1).upper()}" if part_match else ""
        return f"Ann{roman}{part_segment}_par{par_num}_{obl_index}"

    # Articles: "Art. 13" → ch2_sec1_art13_par8_1
    art_match = re.search(r"(\d+)", article_id)
    art_num = int(art_match.group(1)) if art_match else 0
    ch_num, sec_num = _ARTICLE_TO_CHAPTER.get(art_num, (0, 1))

    return f"ch{ch_num}_sec{sec_num}_art{art_num}_par{par_num}_{obl_index}"


# ── Graph management ───────────────────────────────────────────────────


def wipe_graph() -> str:
    """Delete ALL nodes and relationships from the Neo4j graph.

    Preserves constraints and indexes. Use this before a full re-ingestion to
    guarantee a clean slate — no stale nodes, no orphaned obligations.

    Returns:
        A confirmation message with the counts of deleted nodes and relationships.
    """
    driver = _get_driver()
    try:
        driver.verify_connectivity()
    except Exception as e:
        return f"ERROR: Cannot connect to Neo4j — {e}"

    try:
        with driver.session() as session:
            # Count before deletion
            before = session.run(
                "MATCH (n) OPTIONAL MATCH (n)-[r]-() "
                "RETURN count(DISTINCT n) AS nodes, count(DISTINCT r) AS rels"
            ).single()
            n_before = before["nodes"]
            r_before = before["rels"]

            # Delete in batches to avoid heap exhaustion on large graphs
            deleted_rels = 0
            deleted_nodes = 0
            while True:
                result = session.run(
                    "MATCH (n) WITH n LIMIT 10000 "
                    "DETACH DELETE n RETURN count(n) AS deleted"
                ).single()
                batch = result["deleted"] if result else 0
                deleted_nodes += batch
                if batch == 0:
                    break

        return (
            f"Graph wiped.\n"
            f"  Deleted: {n_before} nodes, {r_before} relationships.\n"
            f"  The graph is now empty. Re-run batch_parse_and_ingest to repopulate."
        )
    except Exception as e:
        return f"ERROR wiping graph: {e}"
    finally:
        driver.close()


# ── Ingestion ──────────────────────────────────────────────────────────


def save_article_json(article_id: str, json_content: str) -> str:
    """Save a parsed article JSON to disk.

    Args:
        article_id: The article identifier, e.g. 'art_13', 'art_14'.
        json_content: The full JSON string matching the CRA knowledge graph schema.

    Returns:
        The path to the saved file.
    """
    filepath = OUTPUT_DIR / f"{article_id}.json"
    # Validate JSON
    try:
        data = json.loads(json_content)
    except json.JSONDecodeError as e:
        return f"ERROR: Invalid JSON — {e}"

    filepath.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return f"Saved to {filepath}"


def ingest_json_to_neo4j(article_id: str) -> str:
    """Ingest a previously saved article JSON file into Neo4j.

    Args:
        article_id: The article identifier matching a saved file, e.g. 'art_13'.

    Returns:
        A summary of what was ingested (node/relationship/obligation counts).
    """
    filepath = OUTPUT_DIR / f"{article_id}.json"
    if not filepath.exists():
        return f"ERROR: File not found: {filepath}"

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Handle double-encoded JSON (string instead of dict)
    if isinstance(data, str):
        data = json.loads(data)

    driver = _get_driver()
    try:
        driver.verify_connectivity()
    except Exception as e:
        return f"ERROR: Cannot connect to Neo4j — {e}"

    results = []
    with driver.session() as session:
        # Constraints
        for query in [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Article) REQUIRE (n.article_id, n.regulation) IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Obligation) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:VerificationAction) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:CRANode) REQUIRE n.id IS UNIQUE",
        ]:
            session.run(query)

        # Metadata
        meta = data.get("metadata", {})
        if meta:
            aid = (
                meta.get("article_id")
                or meta.get("recital_id")
                or meta.get("annex_id")
                or f"unknown-{uuid.uuid4().hex[:8]}"
            )
            props = {
                k: v for k, v in meta.items() if isinstance(v, (str, int, float, bool))
            }
            reg = props.get("regulation_short", "CRA")
            props["regulation"] = reg  # keep MERGE key consistent with SET
            session.run(
                "MERGE (a:Article {article_id: $article_id, regulation: $reg}) SET a += $props",
                article_id=aid,
                reg=reg,
                props=props,
            )
            results.append(f"Metadata for {aid}")

        # Nodes
        nodes = data.get("nodes", [])
        for node in nodes:
            nid = node["id"]
            label = node.get("label", "CRANode")
            sub_label = node.get("sub_label", label)
            props = {"name": node.get("name", "")}
            for k, v in node.get("properties", {}).items():
                if isinstance(v, (str, int, float, bool)):
                    props[k] = v
                elif isinstance(v, list):
                    props[k] = "; ".join(str(i) for i in v)
            query = f"MERGE (n:CRANode {{id: $id}}) SET n += $props, n:`{label}`, n:`{sub_label}`"
            session.run(query, id=nid, props=props)
        results.append(f"Merged {len(nodes)} nodes")

        # Relationships
        rels = data.get("relationships", [])
        for rel in rels:
            rel_type = rel.get("type")
            if not rel_type:
                continue  # skip node-like entries accidentally placed in relationships
            props = {}
            for k, v in rel.get("properties", {}).items():
                if isinstance(v, (str, int, float, bool)):
                    props[k] = v
            src = (
                rel.get("source_id")
                or rel.get("source")
                or rel.get("from")
                or rel.get("id", "")
            )
            tgt = rel.get("target_id") or rel.get("target") or rel.get("to", "")
            if not src or not tgt:
                continue  # skip malformed relationship
            query = f"""
                MATCH (a:CRANode {{id: $source_id}})
                MATCH (b:CRANode {{id: $target_id}})
                MERGE (a)-[r:`{rel_type}`]->(b)
                SET r += $props
            """
            session.run(query, source_id=src, target_id=tgt, props=props)
        results.append(f"Merged {len(rels)} relationships")

        # Obligations
        meta = data.get("metadata", {})
        article_id = (
            meta.get("article_id")
            or meta.get("annex_id")  # "Annex I", "Annex II", …
            or meta.get("recital_id")  # "Recital (5)", …
            or ""
        )
        obls = data.get("obligations", [])
        total_verifs = 0

        # Track per-paragraph obligation counters for unique IDs
        par_counters: dict[str, int] = {}  # key: "par{N}" → count

        for obl in obls:
            raw_id = obl["id"]  # e.g. "obl_5"
            paragraph_ref = obl.get("paragraph_ref", "")  # e.g. "Art. 13(8)"

            # Compute per-paragraph index
            par_match = (
                re.search(r"\((\d+)\)", paragraph_ref) if paragraph_ref else None
            )
            par_key = f"par{par_match.group(1)}" if par_match else "par1"
            par_counters[par_key] = par_counters.get(par_key, 0) + 1
            obl_index = par_counters[par_key]

            # Build structured ID: ch{N}_sec{S}_art{A}_par{P}_{i} / Rec{N}_par{P}_{i} / Ann{X}_par{P}_{i}
            obl_id = _build_obligation_id(article_id, paragraph_ref, obl_index)

            # Keep old-style ID as a property for traceability
            legacy_id = (
                f"{article_id}_{raw_id}" if not raw_id.startswith("Art") else raw_id
            )

            actor_id = obl.get("actor", "")
            props = {"legacy_id": legacy_id}
            for k in ("paragraph_ref", "action", "trigger", "deadline"):
                if obl.get(k) is not None:
                    props[k] = obl[k]
            props["article_id"] = article_id
            props["regulation"] = reg
            session.run(
                "MERGE (o:Obligation {id: $id}) SET o += $props",
                id=obl_id,
                props=props,
            )

            if actor_id:
                session.run(
                    "MATCH (o:Obligation {id: $id}) "
                    "MATCH (actor:CRANode {id: $actor_id}) "
                    "MERGE (actor)-[:HAS_OBLIGATION]->(o)",
                    id=obl_id,
                    actor_id=actor_id,
                )

            # Check if this obligation already has verifications generated
            res = session.run(
                "MATCH (o:Obligation {id: $id})-[:HAS_VERIFICATION]->(v:VerificationAction) "
                "RETURN count(v) AS v_count",
                id=obl_id,
            )
            v_count = res.single()["v_count"] if res else 0

            # Generate and attach verifications if none exist yet
            if v_count == 0 and props.get("action"):
                try:
                    from .verification_generator import (
                        generate_verifications_for_obligation,
                    )

                    verifs = generate_verifications_for_obligation(props["action"])
                    import uuid

                    for v in verifs:
                        desc = v.get("description", "")
                        if not desc:
                            continue

                        # Generate embedding for deduplication
                        try:
                            from .vector_tools import _embed_query

                            embed_vec = _embed_query(desc)
                        except Exception:
                            embed_vec = None

                        existing_id = None
                        if embed_vec:
                            res = session.run(
                                """
                                MATCH (v:VerificationAction)
                                WHERE v.embedding IS NOT NULL
                                WITH v, vector.similarity.cosine(v.embedding, $emb) AS score
                                WHERE score > 0.95
                                RETURN v.id AS id
                                ORDER BY score DESC LIMIT 1
                            """,
                                emb=embed_vec,
                            ).data()
                            if res:
                                existing_id = res[0]["id"]

                        if existing_id:
                            # Link current obligation to the existing unique VerificationAction
                            session.run(
                                "MATCH (o:Obligation {id: $obl_id}) "
                                "MATCH (v:VerificationAction {id: $existing_id}) "
                                "MERGE (o)-[:HAS_VERIFICATION]->(v)",
                                obl_id=obl_id,
                                existing_id=existing_id,
                            )
                        else:
                            # Create a new unique VerificationAction
                            v_id = str(uuid.uuid4())
                            v_props = {
                                "type": v.get("type", "review"),
                                "description": desc,
                                "evidence": v.get("evidence", ""),
                            }

                            if embed_vec:
                                session.run(
                                    "MERGE (v:VerificationAction {id: $id}) "
                                    "SET v += $props, v.embedding = $emb",
                                    id=v_id,
                                    props=v_props,
                                    emb=embed_vec,
                                )
                            else:
                                session.run(
                                    "MERGE (v:VerificationAction {id: $id}) "
                                    "SET v += $props",
                                    id=v_id,
                                    props=v_props,
                                )

                            session.run(
                                "MATCH (o:Obligation {id: $obl_id}) "
                                "MATCH (v:VerificationAction {id: $v_id}) "
                                "MERGE (o)-[:HAS_VERIFICATION]->(v)",
                                obl_id=obl_id,
                                v_id=v_id,
                            )
                        total_verifs += 1
                except Exception as e:
                    print(f"Error generating verifications: {e}")

            # Link obligation to its Article node
            if article_id:
                session.run(
                    "MATCH (a:Article {article_id: $aid}) "
                    "MATCH (o:Obligation {id: $oid}) "
                    "MERGE (a)-[:CONTAINS_OBLIGATION]->(o)",
                    aid=article_id,
                    oid=obl_id,
                )
            for node_id in obl.get("related_nodes", []):
                session.run(
                    "MATCH (o:Obligation {id: $obl_id}) "
                    "MATCH (n:CRANode {id: $node_id}) "
                    "MERGE (o)-[:RELATES_TO]->(n)",
                    obl_id=obl_id,
                    node_id=node_id,
                )

        results.append(f"Merged {len(obls)} obligations")
        if total_verifs > 0:
            results.append(f"Generated {total_verifs} distinct verifications")

        # Cross-references
        crs = data.get("cross_references", [])
        skipped_crs = 0
        for cr in crs:
            target = cr.get("target")
            source_id = cr.get("source_id")
            if not target or not source_id:
                # Malformed entry from the parser — skip rather than abort the ingest.
                skipped_crs += 1
                continue
            session.run(
                "MERGE (r:ArticleRef {ref: $ref}) SET r.type = 'legal_reference'",
                ref=target,
            )
            cr_type = cr.get("type", "REFERENCES")
            context = cr.get("context", "")
            query = f"""
                MATCH (n:CRANode {{id: $source_id}})
                MATCH (r:ArticleRef {{ref: $target}})
                MERGE (n)-[cr:`{cr_type}`]->(r)
                SET cr.context = $context
            """
            session.run(
                query, source_id=source_id, target=target, context=context
            )
        merged_crs = len(crs) - skipped_crs
        if skipped_crs:
            results.append(
                f"Merged {merged_crs} cross-references (skipped {skipped_crs} malformed)"
            )
        else:
            results.append(f"Merged {merged_crs} cross-references")

    driver.close()
    return "Ingestion complete: " + ", ".join(results)


# ── Querying ───────────────────────────────────────────────────────────


def query_neo4j(cypher_query: str) -> str:
    """Execute a Cypher query against the Neo4j CRA knowledge graph and return results.

    Args:
        cypher_query: A valid Cypher query string.

    Returns:
        The query results as a formatted string.
    """
    driver = _get_driver()
    try:
        driver.verify_connectivity()
    except Exception as e:
        return f"ERROR: Cannot connect to Neo4j — {e}"

    try:
        with driver.session() as session:
            result = session.run(cypher_query)
            records = [dict(record) for record in result]

        if not records:
            return "No results found."

        # Format results
        lines = []
        keys = list(records[0].keys())
        # Header
        lines.append(" | ".join(keys))
        lines.append("-|-".join(["---"] * len(keys)))
        # Rows
        for rec in records:
            row = []
            for k in keys:
                val = rec[k]
                if hasattr(val, "get"):  # Node
                    row.append(str(dict(val)))
                elif isinstance(val, list):
                    row.append(str(val))
                else:
                    row.append(str(val) if val is not None else "—")
            lines.append(" | ".join(row))

        return "\n".join(lines)
    except Exception as e:
        return f"ERROR executing query: {e}"
    finally:
        driver.close()


def get_graph_stats() -> str:
    """Get summary statistics of the current Neo4j knowledge graph.

    Covers ALL regulations present (CRA, Part-IS, etc.). Returns total
    counts plus a per-regulation breakdown.

    Returns:
        Node counts by label, relationship counts by type, totals, and
        per-regulation node counts.
    """
    driver = _get_driver()
    try:
        driver.verify_connectivity()
    except Exception as e:
        return f"ERROR: Cannot connect to Neo4j — {e}"

    try:
        with driver.session() as session:
            # Node counts by label
            node_result = session.run(
                "MATCH (n) UNWIND labels(n) AS lbl "
                "RETURN lbl AS label, count(*) AS count ORDER BY count DESC"
            )
            node_counts = [(r["label"], r["count"]) for r in node_result]

            # Relationship counts
            rel_result = session.run(
                "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count ORDER BY count DESC"
            )
            rel_counts = [(r["type"], r["count"]) for r in rel_result]

            # Per-regulation breakdown (label x regulation)
            reg_result = session.run(
                "MATCH (n) WHERE n.regulation IS NOT NULL "
                "RETURN n.regulation AS reg, labels(n)[0] AS lbl, count(*) AS c "
                "ORDER BY reg, c DESC"
            )
            reg_rows = [(r["reg"], r["lbl"], r["c"]) for r in reg_result]

            # Totals
            total_result = session.run(
                "MATCH (n) WITH count(n) AS nodes "
                "MATCH ()-[r]->() RETURN nodes, count(r) AS rels"
            )
            totals = total_result.single()

        lines = [f"=== Neo4j Knowledge Graph Stats ==="]
        lines.append(
            f"Total nodes: {totals['nodes']}, Total relationships: {totals['rels']}"
        )
        lines.append(f"\nNodes by label:")
        for lbl, cnt in node_counts:
            lines.append(f"  {lbl}: {cnt}")
        lines.append(f"\nRelationships by type:")
        for typ, cnt in rel_counts:
            lines.append(f"  {typ}: {cnt}")
        if reg_rows:
            lines.append(f"\nNodes by regulation:")
            current_reg = None
            for reg, lbl, c in reg_rows:
                if reg != current_reg:
                    lines.append(f"  [{reg}]")
                    current_reg = reg
                lines.append(f"    {lbl}: {c}")
        return "\n".join(lines)
    except Exception as e:
        return f"ERROR: {e}"
    finally:
        driver.close()


# ── High-level query helpers ───────────────────────────────────────────


def get_article_obligations(article_number: int) -> str:
    """Get all obligations from a specific CRA article.

    Args:
        article_number: The article number (e.g. 21 for Article 21).

    Returns:
        A formatted list of obligations with their details.
    """
    article_id = f"Art. {article_number}"
    driver = _get_driver()
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (a:Article {article_id: $aid, regulation: 'CRA'})-[:CONTAINS_OBLIGATION]->(o:Obligation) "
                "OPTIONAL MATCH (actor)-[:HAS_OBLIGATION]->(o) "
                "RETURN o.id AS id, o.action AS action, o.paragraph_ref AS paragraph, "
                "o.trigger AS trigger, o.deadline AS deadline, "
                "collect(DISTINCT actor.name) AS actors "
                "ORDER BY o.id",
                aid=article_id,
            )
            records = [dict(r) for r in result]

        if not records:
            # Check if article exists
            with driver.session() as session:
                art = session.run(
                    "MATCH (a:Article {article_id: $aid}) RETURN a.article_title AS title",
                    aid=article_id,
                ).single()
            if not art:
                return f"Article {article_number} not found in the graph. Use get_graph_stats to see what's ingested."
            return f"Article {article_number} ('{art['title']}') has no obligations in the graph."

        lines = [f"Obligations in Article {article_number} ({len(records)} found):\n"]
        for rec in records:
            lines.append(f"**{rec['id']}**")
            if rec["action"]:
                lines.append(f"  Action: {rec['action']}")
            if rec["paragraph"]:
                lines.append(f"  Paragraph: {rec['paragraph']}")
            if rec["trigger"]:
                lines.append(f"  Trigger: {rec['trigger']}")
            if rec["deadline"]:
                lines.append(f"  Deadline: {rec['deadline']}")
            actors = [a for a in (rec["actors"] or []) if a]
            if actors:
                lines.append(f"  Actors: {', '.join(actors)}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"ERROR: {e}"
    finally:
        driver.close()


def get_all_obligations() -> str:
    """Get a summary of all obligations across all CRA articles.

    Returns:
        A summary listing obligation counts per article and total count.
    """
    driver = _get_driver()
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (a:Article {regulation: 'CRA'})-[:CONTAINS_OBLIGATION]->(o:Obligation) "
                "RETURN a.article_id AS article, count(o) AS count "
                "ORDER BY a.article_id"
            )
            records = [dict(r) for r in result]

            total = session.run(
                "MATCH (o:Obligation {regulation: 'CRA'}) RETURN count(o) AS total"
            ).single()

        if not records:
            return "No obligations found in the graph."

        lines = [
            f"Obligations summary ({total['total']} total across {len(records)} articles):\n"
        ]
        for rec in records:
            lines.append(f"  {rec['article']}: {rec['count']} obligations")
        return "\n".join(lines)
    except Exception as e:
        return f"ERROR: {e}"
    finally:
        driver.close()


def get_actors() -> str:
    """Get all actors in the CRA knowledge graph.

    Returns:
        A list of all actor nodes with their labels and names.
    """
    driver = _get_driver()
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (a:Actor) "
                "RETURN a.id AS id, a.name AS name, "
                "[l IN labels(a) WHERE l <> 'Actor' AND l <> 'CRANode'] AS types "
                "ORDER BY a.name"
            )
            records = [dict(r) for r in result]

        if not records:
            return "No actors found in the graph."

        lines = [f"Actors in the CRA graph ({len(records)} found):\n"]
        for rec in records:
            types = ", ".join(rec["types"]) if rec["types"] else "Actor"
            lines.append(f"  - {rec['name']} ({types})")
        return "\n".join(lines)
    except Exception as e:
        return f"ERROR: {e}"
    finally:
        driver.close()


def get_article_nodes(article_number: int) -> str:
    """Get all nodes and relationships from a specific CRA article.

    Args:
        article_number: The article number (e.g. 13 for Article 13).

    Returns:
        A summary of all nodes and relationships ingested from that article.
    """
    article_id = f"Art. {article_number}"
    driver = _get_driver()
    try:
        with driver.session() as session:
            # Check article exists
            art = session.run(
                "MATCH (a:Article {article_id: $aid}) RETURN a.article_title AS title",
                aid=article_id,
            ).single()
            if not art:
                return f"Article {article_number} not found in the graph."

            # Get nodes
            nodes_result = session.run(
                "MATCH (n:CRANode) WHERE n.article_ref CONTAINS $aid OR n.id CONTAINS $prefix "
                "RETURN n.id AS id, n.name AS name, "
                "[l IN labels(n) WHERE l <> 'CRANode'] AS labels "
                "ORDER BY n.id",
                aid=article_id,
                prefix=f"art{article_number}_",
            )
            nodes = [dict(r) for r in nodes_result]

            # Get obligations
            obl_result = session.run(
                "MATCH (a:Article {article_id: $aid, regulation: 'CRA'})-[:CONTAINS_OBLIGATION]->(o:Obligation) "
                "RETURN o.id AS id, o.action AS action",
                aid=article_id,
            )
            obligations = [dict(r) for r in obl_result]

        lines = [f"Article {article_number}: '{art['title']}'"]
        lines.append(f"\nNodes ({len(nodes)}):")
        for n in nodes:
            lbls = ", ".join(n["labels"]) if n["labels"] else "?"
            lines.append(f"  [{lbls}] {n['id']}: {n['name']}")
        lines.append(f"\nObligations ({len(obligations)}):")
        for o in obligations:
            lines.append(f"  {o['id']}: {o['action'] or '(no action)'}")
        return "\n".join(lines)
    except Exception as e:
        return f"ERROR: {e}"
    finally:
        driver.close()


def get_deadlines() -> str:
    """Get all CRA obligations that have an explicit deadline.

    Returns:
        A formatted table of obligations with their deadlines, grouped by article.
    """
    driver = _get_driver()
    try:
        driver.verify_connectivity()
    except Exception as e:
        return f"ERROR: Cannot connect to Neo4j — {e}"

    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (o:Obligation) "
                "WHERE o.regulation = 'CRA' AND o.deadline IS NOT NULL AND trim(o.deadline) <> '' "
                "OPTIONAL MATCH (actor:Actor)-[:HAS_OBLIGATION]->(o) "
                "RETURN o.id AS id, o.article_id AS article, "
                "o.action AS action, o.deadline AS deadline, "
                "o.trigger AS trigger, "
                "collect(DISTINCT actor.name) AS actors "
                "ORDER BY o.article_id, o.id"
            )
            records = [dict(r) for r in result]

        if not records:
            return "No obligations with deadlines found in the graph."

        lines = [f"Obligations with deadlines ({len(records)} found):\n"]
        current_article = None
        for rec in records:
            art = rec.get("article") or "General"
            if art != current_article:
                current_article = art
                lines.append(f"\n## {art}")
            lines.append(f"  **{rec['id']}**")
            action = rec.get("action") or ""
            if len(action) > 150:
                action = action[:150] + "…"
            lines.append(f"    Action: {action}")
            lines.append(f"    Deadline: {rec['deadline']}")
            if rec.get("trigger"):
                trigger = rec["trigger"]
                if len(trigger) > 120:
                    trigger = trigger[:120] + "…"
                lines.append(f"    Trigger: {trigger}")
            actors = [a for a in (rec.get("actors") or []) if a]
            if actors:
                lines.append(f"    Actors: {', '.join(actors)}")
            lines.append("")

        return "\n".join(lines)
    except Exception as e:
        return f"ERROR: {e}"
    finally:
        driver.close()


def get_verification_actions(article_id: str = "") -> str:
    """Get the VerificationAction nodes linked to obligations.

    Each VerificationAction is a concrete compliance verification step
    (inspection, review, testcase, or waiver) generated during ingestion.

    Args:
        article_id: An article ID like ``"Art. 13"`` to filter verifications
            for that article only. Pass an empty string (default) to retrieve
            verifications for ALL obligations.

    Returns:
        A formatted list of verification actions grouped by obligation.
    """
    driver = _get_driver()
    try:
        driver.verify_connectivity()
    except Exception as e:
        return f"ERROR: Cannot connect to Neo4j — {e}"

    try:
        with driver.session() as session:
            if article_id:
                result = session.run(
                    "MATCH (o:Obligation {article_id: $aid})-[:HAS_VERIFICATION]->(v:VerificationAction) "
                    "RETURN o.id AS obligation_id, o.action AS obligation, "
                    "v.id AS verification_id, v.type AS type, "
                    "v.description AS description, v.evidence AS evidence "
                    "ORDER BY o.id, v.type, v.id",
                    aid=article_id,
                )
            else:
                result = session.run(
                    "MATCH (o:Obligation)-[:HAS_VERIFICATION]->(v:VerificationAction) "
                    "RETURN o.id AS obligation_id, o.action AS obligation, "
                    "v.id AS verification_id, v.type AS type, "
                    "v.description AS description, v.evidence AS evidence "
                    "ORDER BY o.id, v.type, v.id"
                )
            records = [dict(r) for r in result]

        if not records:
            msg = "No VerificationAction nodes found"
            if article_id:
                msg += f" for article '{article_id}'"
            msg += ". Run ingestion to generate them automatically."
            return msg

        lines = [f"VerificationActions ({len(records)} found):\n"]
        current_obl = None
        for rec in records:
            if rec["obligation_id"] != current_obl:
                current_obl = rec["obligation_id"]
                obl_text = (rec.get("obligation") or "")[:80]
                lines.append(f"\n**{current_obl}** — {obl_text}")
            type_tag = f"[{rec['type']}]" if rec.get("type") else ""
            desc = rec.get("description") or ""
            evidence = rec.get("evidence") or ""
            lines.append(f"  • {type_tag} {desc}")
            if evidence:
                lines.append(f"    → Evidence: {evidence}")

        return "\n".join(lines)
    except Exception as e:
        return f"ERROR: {e}"
    finally:
        driver.close()
