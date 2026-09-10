"""
Neo4j client — vector search + graph traversal for the CRA agent.
Embeddings are stored as node properties (e.g. `n.embedding`).
"""

from __future__ import annotations
from typing import Any
from neo4j import GraphDatabase


class Neo4jClient:
    def __init__(self, uri: str, user: str, password: str, embedding_property: str = "embedding"):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.embedding_property = embedding_property

    def close(self):
        self.driver.close()

    # ------------------------------------------------------------------
    # Vector search
    # ------------------------------------------------------------------

    def vector_search(self, query_embedding: list[float], k: int = 5) -> list[dict]:
        """
        Cosine similarity search over all nodes that have an embedding property.
        Returns the top-k most similar nodes with their labels and properties.

        Requires Neo4j 5.11+ for the vector index, or falls back to manual cosine.
        Adjust the index name 'cra_vector_index' to match yours.
        """
        cypher = """
        CALL db.index.vector.queryNodes('cra_vector_index', $k, $embedding)
        YIELD node, score
        RETURN labels(node) AS labels,
               properties(node) AS props,
               score
        ORDER BY score DESC
        """
        try:
            return self._run(cypher, k=k, embedding=query_embedding)
        except Exception:
            # Fallback: manual cosine over nodes with embedding property
            return self._manual_cosine_search(query_embedding, k)

    def _manual_cosine_search(self, query_embedding: list[float], k: int) -> list[dict]:
        """
        Fallback when no vector index exists.
        Loads all node embeddings and computes cosine similarity in Python.
        Fine for small graphs (<50k nodes); for larger graphs, create a vector index.
        """
        import numpy as np

        cypher = f"""
        MATCH (n)
        WHERE n.{self.embedding_property} IS NOT NULL
        RETURN id(n) AS id, labels(n) AS labels,
               properties(n) AS props, n.{self.embedding_property} AS emb
        """
        rows = self._run(cypher)
        if not rows:
            return []

        q = np.array(query_embedding)
        scored = []
        for row in rows:
            v = np.array(row["emb"])
            score = float(np.dot(q, v) / (np.linalg.norm(q) * np.linalg.norm(v) + 1e-10))
            scored.append({"labels": row["labels"], "props": row["props"], "score": score})

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:k]

    # ------------------------------------------------------------------
    # Fixed traversal patterns (mapped to intents)
    # ------------------------------------------------------------------

    def expand_node(self, intent: str, node_props: dict, entities: dict) -> list[dict]:
        """
        Run the fixed Cypher pattern for the given intent.
        Falls back to a generic neighbor expansion if no pattern matches.
        """
        pattern_fn = TRAVERSAL_PATTERNS.get(intent, _generic_expansion)
        return pattern_fn(self, node_props, entities)

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _run(self, cypher: str, **params) -> list[dict]:
        with self.driver.session() as session:
            result = session.run(cypher, **params)
            return [dict(record) for record in result]


# ------------------------------------------------------------------
# Traversal pattern library
# Each function receives (client, seed_node_props, extracted_entities)
# and returns a list of result dicts.
# ------------------------------------------------------------------

def _obligation_lookup(client: Neo4jClient, node: dict, entities: dict) -> list[dict]:
    actor = entities.get("actor", "")
    return client._run("""
        MATCH (a:Actor)-[:HAS_OBLIGATION]->(o:Obligation)
        WHERE toLower(a.name) CONTAINS toLower($actor)
           OR toLower(labels(a)[0]) CONTAINS toLower($actor)
        OPTIONAL MATCH (o)-[:DEFINED_IN]->(art:LegalProvision)
        RETURN a.name AS actor, o.name AS obligation,
               o.description AS description, art.reference AS article
    """, actor=actor)


def _product_classification(client: Neo4jClient, node: dict, entities: dict) -> list[dict]:
    product = entities.get("product", node.get("name", ""))
    return client._run("""
        MATCH (p:ProductWithDigitalElements)
        WHERE toLower(p.name) CONTAINS toLower($product)
        OPTIONAL MATCH (p)-[:mustComplyWith]->(req:EssentialCybersecurityRequirement)
        OPTIONAL MATCH (p)-[:isSubjectTo]->(ca:ConformityAssessment)
        RETURN p.name AS product, labels(p) AS classification,
               collect(DISTINCT req.name) AS requirements,
               collect(DISTINCT ca.name) AS assessments
    """, product=product)


def _conformity_assessment_path(client: Neo4jClient, node: dict, entities: dict) -> list[dict]:
    product_class = entities.get("product_class", entities.get("product", ""))
    return client._run("""
        MATCH (p:ProductWithDigitalElements)-[:isSubjectTo]->(ca:ConformityAssessment)
        WHERE toLower(labels(p)[0]) CONTAINS toLower($product_class)
           OR toLower(p.name) CONTAINS toLower($product_class)
        OPTIONAL MATCH (ca)<-[:performsAssessment]-(nb:NotifiedBody)
        RETURN p.name AS product, labels(p)[0] AS product_class,
               ca.name AS assessment_type, ca.module AS module,
               nb.name AS notified_body
    """, product_class=product_class)


def _vulnerability_handling(client: Neo4jClient, node: dict, entities: dict) -> list[dict]:
    return client._run("""
        MATCH (req:VulnerabilityHandlingRequirement)
        OPTIONAL MATCH (v:Vulnerability)-[:addressedBy]->(su:SecurityUpdate)
        OPTIONAL MATCH (m:Manufacturer)-[:reportsTo]->(c:CSIRT)
        OPTIONAL MATCH (m)-[:reportsToENISA]->(e:ENISA)
        RETURN req.reference AS requirement_ref,
               req.description AS requirement,
               su.description AS security_update_rule,
               c.name AS csirt,
               e.name AS enisa
        LIMIT 20
    """)


def _penalty_lookup(client: Neo4jClient, node: dict, entities: dict) -> list[dict]:
    return client._run("""
        MATCH (pen:Penalty)
        OPTIONAL MATCH (pen)-[:TRIGGERED_BY]->(ob:Obligation)
        RETURN pen.tier AS tier,
               pen.max_fine AS max_fine,
               pen.turnover_percentage AS turnover_pct,
               pen.trigger AS trigger,
               collect(ob.name) AS obligations
        ORDER BY pen.tier
    """)


def _scope_check(client: Neo4jClient, node: dict, entities: dict) -> list[dict]:
    return client._run("""
        MATCH (p:ProductWithDigitalElements)
        OPTIONAL MATCH (p)-[:hasComponent]->(c:ProductComponent)
        OPTIONAL MATCH (exc:LegalFramework)-[:EXCLUDES]->(p)
        RETURN p.name AS product, labels(p) AS type,
               collect(DISTINCT c.name) AS components,
               collect(DISTINCT exc.name) AS exclusions
        LIMIT 20
    """)


def _cross_regulation(client: Neo4jClient, node: dict, entities: dict) -> list[dict]:
    regulation = entities.get("regulation", "")
    return client._run("""
        MATCH (lf:LegalFramework)
        WHERE $regulation = '' OR toLower(lf.name) CONTAINS toLower($regulation)
        OPTIONAL MATCH (lf)-[:RELATED_TO]->(prov:LegalProvision)
        RETURN lf.name AS regulation, lf.description AS relationship,
               collect(prov.reference) AS cra_provisions
    """, regulation=regulation)


def _timeline_lookup(client: Neo4jClient, node: dict, entities: dict) -> list[dict]:
    return client._run("""
        MATCH (ev:LegalProvision)
        WHERE ev.effectiveDate IS NOT NULL
        RETURN ev.reference AS article, ev.name AS description,
               ev.effectiveDate AS date
        ORDER BY ev.effectiveDate
    """)


def _generic_expansion(client: Neo4jClient, node: dict, entities: dict) -> list[dict]:
    """Fallback: return the seed node's direct neighbors (1 hop)."""
    node_id = node.get("id") or node.get("name", "")
    return client._run("""
        MATCH (n)-[r]-(neighbor)
        WHERE n.name = $node_id OR id(n) = toInteger($node_id)
        RETURN n.name AS source, type(r) AS relationship,
               neighbor.name AS neighbor, labels(neighbor) AS neighbor_labels,
               neighbor.description AS description
        LIMIT 30
    """, node_id=str(node_id))


TRAVERSAL_PATTERNS: dict[str, Any] = {
    "obligation_lookup":          _obligation_lookup,
    "product_classification":     _product_classification,
    "conformity_assessment_path": _conformity_assessment_path,
    "vulnerability_handling":     _vulnerability_handling,
    "penalty_lookup":             _penalty_lookup,
    "scope_check":                _scope_check,
    "cross_regulation":           _cross_regulation,
    "timeline_lookup":            _timeline_lookup,
}
