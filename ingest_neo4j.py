#!/usr/bin/env python3
"""
Ingest CRA article JSON into Neo4j knowledge graph.

Reads response.json (or any article JSON matching the schema) and:
  1. MERGEs nodes   – keyed on (label, sub_label, id) so duplicates
                      like "Manufacturer" are reused across articles.
  2. MERGEs relationships – keyed on (source_id, target_id, type).
  3. Creates Obligation nodes linked to their actor and related nodes.
  4. Creates CrossReference edges to virtual ArticleRef / AnnexRef nodes.

Usage:
    python ingest_neo4j.py                         # default response.json
    python ingest_neo4j.py article14.json           # specific file
    python ingest_neo4j.py *.json                   # batch multiple articles
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

from neo4j import GraphDatabase

# ── Connection settings ────────────────────────────────────────────────
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password123"


# ── Cypher helpers ─────────────────────────────────────────────────────

CREATE_CONSTRAINTS = """
CREATE CONSTRAINT IF NOT EXISTS FOR (n:CRANode) REQUIRE n.id IS UNIQUE
"""

CREATE_OBLIGATION_CONSTRAINT = """
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Obligation) REQUIRE n.id IS UNIQUE
"""

CREATE_ARTICLE_REF_CONSTRAINT = """
CREATE CONSTRAINT IF NOT EXISTS FOR (n:ArticleRef) REQUIRE n.ref IS UNIQUE
"""

CREATE_COMPLIANCE_ACTION_CONSTRAINT = """
CREATE CONSTRAINT IF NOT EXISTS FOR (n:ComplianceAction) REQUIRE n.id IS UNIQUE
"""

CREATE_ARTICLE_CONSTRAINT = """
CREATE CONSTRAINT IF NOT EXISTS FOR (a:Article) REQUIRE (a.article_id, a.regulation) IS UNIQUE
"""

MERGE_NODE = """
MERGE (n:CRANode {id: $id})
SET n += $props,
    n:`%(label)s`,
    n:`%(sub_label)s`
"""

MERGE_RELATIONSHIP = """
MATCH (a:CRANode {id: $source_id})
MATCH (b:CRANode {id: $target_id})
CALL apoc.merge.relationship(a, $rel_type, {}, $props, b, {}) YIELD rel
RETURN rel
"""

# Fallback when APOC is not installed – one query per relationship type
# is not ideal but works without plugins.
MERGE_RELATIONSHIP_PLAIN = """
MATCH (a:CRANode {id: $source_id})
MATCH (b:CRANode {id: $target_id})
MERGE (a)-[r:`%(rel_type)s`]->(b)
SET r += $props
"""

MERGE_OBLIGATION = """
MERGE (o:Obligation {id: $id})
SET o += $props
WITH o
MATCH (actor:CRANode {id: $actor_id})
MERGE (actor)-[:HAS_OBLIGATION]->(o)
"""

LINK_OBLIGATION_TO_NODE = """
MATCH (o:Obligation {id: $obl_id})
MATCH (n:CRANode {id: $node_id})
MERGE (o)-[:RELATES_TO]->(n)
"""

MERGE_ARTICLE_REF = """
MERGE (r:ArticleRef {ref: $ref})
SET r.type = 'legal_reference'
"""

MERGE_CROSS_REFERENCE = """
MATCH (n:CRANode {id: $source_id})
MATCH (r:ArticleRef {ref: $target})
MERGE (n)-[cr:`%(cr_type)s`]->(r)
SET cr.context = $context
"""

MERGE_COMPLIANCE_ACTION = """
MERGE (a:ComplianceAction {id: $id})
SET a += $props
"""

LINK_OBLIGATION_TO_ACTION = """
MATCH (o:Obligation {id: $obl_id})
MATCH (a:ComplianceAction {id: $act_id})
MERGE (o)-[:HAS_ACTION]->(a)
"""

MERGE_METADATA = """
MERGE (a:Article {article_id: $article_id, regulation: $regulation})
SET a += $props
"""


# ── Ingestion logic ───────────────────────────────────────────────────


def has_apoc(session) -> bool:
    """Check whether APOC plugin is available."""
    try:
        result = session.run("RETURN apoc.version() AS v")
        result.single()
        return True
    except Exception:
        return False


def ensure_constraints(session):
    """Create uniqueness constraints (idempotent)."""
    for stmt in (
        CREATE_CONSTRAINTS,
        CREATE_OBLIGATION_CONSTRAINT,
        CREATE_ARTICLE_REF_CONSTRAINT,
        CREATE_COMPLIANCE_ACTION_CONSTRAINT,
        CREATE_ARTICLE_CONSTRAINT,
    ):
        session.run(stmt)


def ingest_metadata(session, metadata: dict):
    """MERGE the Article node carrying the metadata envelope."""
    article_id = (
        metadata.get("article_id")
        or metadata.get("recital_id")
        or metadata.get("annex_id")
        or f"unknown-{uuid.uuid4().hex[:8]}"
    )
    regulation = metadata.get("regulation_short", "CRA")
    props = {
        k: v for k, v in metadata.items() if isinstance(v, (str, int, float, bool))
    }
    props["regulation"] = regulation
    session.run(
        MERGE_METADATA, article_id=article_id, regulation=regulation, props=props
    )


def ingest_nodes(session, nodes: list[dict]):
    """MERGE each node with its primary + secondary label."""
    for node in nodes:
        nid = node["id"]
        label = node.get("label", "CRANode")
        sub_label = node.get("sub_label", label)
        props = {
            "name": node.get("name", ""),
        }
        # Flatten simple properties
        for k, v in node.get("properties", {}).items():
            if isinstance(v, (str, int, float, bool)):
                props[k] = v
            elif isinstance(v, list):
                # Store lists as semicolon-joined strings for Neo4j compatibility
                props[k] = "; ".join(str(i) for i in v)

        query = MERGE_NODE % {"label": label, "sub_label": sub_label}
        session.run(query, id=nid, props=props)

    print(f"  ✓ Merged {len(nodes)} nodes")


def ingest_relationships(session, relationships: list[dict], use_apoc: bool):
    """MERGE each relationship between two CRANode nodes."""
    count = 0
    for rel in relationships:
        source_id = rel["source_id"]
        target_id = rel["target_id"]
        rel_type = rel["type"]
        props = {}
        for k, v in rel.get("properties", {}).items():
            if isinstance(v, (str, int, float, bool)):
                props[k] = v

        if use_apoc:
            session.run(
                MERGE_RELATIONSHIP,
                source_id=source_id,
                target_id=target_id,
                rel_type=rel_type,
                props=props,
            )
        else:
            query = MERGE_RELATIONSHIP_PLAIN % {"rel_type": rel_type}
            session.run(query, source_id=source_id, target_id=target_id, props=props)
        count += 1

    print(f"  ✓ Merged {count} relationships")


def ingest_obligations(session, obligations: list[dict]):
    """Create Obligation nodes and link them to their actor and related nodes."""
    if not obligations:
        return
    count = 0
    for obl in obligations:
        obl_id = obl["id"]
        actor_id = obl.get("actor", "")
        props = {}
        for k in ("paragraph_ref", "action", "trigger", "deadline"):
            if obl.get(k) is not None:
                props[k] = obl[k]

        session.run(MERGE_OBLIGATION, id=obl_id, props=props, actor_id=actor_id)

        for node_id in obl.get("related_nodes", []):
            session.run(LINK_OBLIGATION_TO_NODE, obl_id=obl_id, node_id=node_id)

        # ComplianceAction nodes — short, executable steps for this obligation
        for act_idx, act in enumerate(obl.get("actions", []), start=1):
            act_id = f"{obl_id}_act_{act_idx}"
            act_props = {
                "text": act.get("text", ""),
                "category": act.get("category", ""),
                "priority": act.get("priority", "medium"),
                "obligation_id": obl_id,
            }
            session.run(MERGE_COMPLIANCE_ACTION, id=act_id, props=act_props)
            session.run(LINK_OBLIGATION_TO_ACTION, obl_id=obl_id, act_id=act_id)

        count += 1

    print(f"  ✓ Merged {count} obligations")


def ingest_cross_references(session, cross_refs: list[dict]):
    """Create ArticleRef nodes and link source CRANodes to them."""
    if not cross_refs:
        return
    count = 0
    for cr in cross_refs:
        target = cr["target"]
        session.run(MERGE_ARTICLE_REF, ref=target)

        cr_type = cr.get("type", "REFERENCES")
        context = cr.get("context", "")
        query = MERGE_CROSS_REFERENCE % {"cr_type": cr_type}
        session.run(query, source_id=cr["source_id"], target=target, context=context)
        count += 1

    print(f"  ✓ Merged {count} cross-references")


def ingest_file(driver, filepath: Path):
    """Process a single JSON file."""
    print(f"\n{'─'*60}")
    print(f"Ingesting: {filepath.name}")
    print(f"{'─'*60}")

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    with driver.session() as session:
        ensure_constraints(session)
        use_apoc = has_apoc(session)
        if use_apoc:
            print("  ℹ  APOC detected — using apoc.merge.relationship")
        else:
            print("  ℹ  APOC not found — using per-type MERGE fallback")

        # 1. Metadata
        if "metadata" in data:
            ingest_metadata(session, data["metadata"])
            art = data["metadata"].get("article_id", "?")
            print(f"  ✓ Metadata for {art}")

        # 2. Nodes
        ingest_nodes(session, data.get("nodes", []))

        # 3. Relationships
        ingest_relationships(session, data.get("relationships", []), use_apoc)

        # 4. Obligations
        ingest_obligations(session, data.get("obligations", []))

        # 5. Cross-references
        ingest_cross_references(session, data.get("cross_references", []))


# ── Main ──────────────────────────────────────────────────────────────


def main():
    files = (
        [Path(p) for p in sys.argv[1:]]
        if len(sys.argv) > 1
        else [Path("response.json")]
    )

    for f in files:
        if not f.exists():
            print(f"⚠  File not found: {f}")
            sys.exit(1)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    # Verify connectivity
    try:
        driver.verify_connectivity()
        print("Connected to Neo4j ✓")
    except Exception as e:
        print(f"✗ Cannot connect to Neo4j at {NEO4J_URI}: {e}")
        sys.exit(1)

    try:
        for f in files:
            ingest_file(driver, f)
    finally:
        driver.close()

    print(f"\n{'═'*60}")
    print(f"Done — {len(files)} file(s) ingested.")
    print(f"Open http://localhost:7474 to explore the graph.")
    print(f"{'═'*60}")


if __name__ == "__main__":
    main()
