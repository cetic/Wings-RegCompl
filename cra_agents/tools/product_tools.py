"""Product-centric CRA obligations tool.

Given a technical product description, classifies the product under CRA
Annex III (Default / Class I / Class II), then queries the knowledge graph
for all applicable obligations, deadlines, conformity assessment routes,
and related provisions.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

log = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────
_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(_ENV_PATH)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password123")

MODEL = "gemma4:e2b"
FILTER_MODEL = "gemma4:e2b"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
MIN_INTERVAL = 0.5
_last_call: float = 0.0

# Unified LLM gateway (LOCAL=Ollama, OFFLOAD=Gemini)
from ._llm import generate as _llm_generate  # noqa: E402

# ── Annex III product categories for LLM classification ───────────────
ANNEX_III_CATEGORIES = """
CRA Annex III — Important Products with Digital Elements

CLASS I:
1. Identity management systems and privileged access management software/hardware (including authentication readers, biometric readers)
2. Standalone and embedded browsers
3. Password managers
4. Anti-malware software (searches for, removes, or quarantines malicious software)
5. VPN products (virtual private network)
6. Network management systems
7. SIEM systems (security information and event management)
8. Boot managers
9. PKI and digital certificate issuance software
10. Physical and virtual network interfaces
11. Operating systems
12. Routers, modems intended for internet connection, and switches
13. Microprocessors with security-related functionalities
14. Microcontrollers with security-related functionalities
15. ASICs and FPGAs with security-related functionalities
16. Smart home general purpose virtual assistants
17. Smart home products with security functionalities (smart door locks, security cameras, baby monitoring systems, alarm systems)
18. Internet-connected toys with social interactive features (speaking/filming) or location tracking
19. Personal wearable health monitoring products or wearable products for children

CLASS II:
1. Hypervisors and container runtime systems supporting virtualised execution of operating systems
2. Firewalls, intrusion detection and prevention systems
3. Tamper-resistant microprocessors
4. Tamper-resistant microcontrollers

CRITICAL PRODUCTS (Annex IV, for reference):
1. Hardware Devices with Security Boxes
2. Smart meter gateways (in smart metering systems)
3. Smartcards or similar devices (including secure elements)

DEFAULT PRODUCT:
Any product with digital elements that does NOT fall under Class I, Class II, or Critical.
Examples: consumer electronics, smart appliances, generic IoT devices, software applications.
"""

CLASSIFICATION_PROMPT = """You are a legal classification expert for the EU Cyber Resilience Act (CRA).

Given a technical product description, classify the product into the correct CRA category.

{categories}

INSTRUCTIONS:
1. Analyse the product description carefully.
2. Determine which CRA Annex III/IV category best matches the product's CORE FUNCTIONALITY.
3. If the product matches MULTIPLE categories, list ALL of them.
4. If it does not match any specific category, classify as "default".
5. Identify the primary actor role(s): manufacturer, importer, distributor, or open_source_steward.
6. If the description contains a block delimited by "=== ASSESSOR DIRECTIVES ===",
   treat each line inside as an AUTHORITATIVE SCOPING CONSTRAINT (e.g. market
   geography, connectivity, deployment model). Use them to refine the class and
   matched categories — they are NOT additional product features.

Return ONLY valid JSON (no markdown fences) in this exact format:
{{
  "product_name": "<short product name, max 3-4 words, e.g. SmartWear Cardio Monitor>",
  "product_class": "default" | "class_i" | "class_ii" | "critical",
  "matched_categories": ["<category description>", ...],
  "annex_iii_numbers": [<int>, ...],
  "confidence": "high" | "medium" | "low",
  "reasoning": "<brief explanation>",
  "actor_roles": ["manufacturer"],
  "key_features": ["<feature1>", "<feature2>", ...]
}}

PRODUCT DESCRIPTION:
{description}
"""


# ── Helpers ────────────────────────────────────────────────────────────


def _get_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


_client = None


def _get_client():
    """Return a reusable httpx client for Ollama."""
    global _client
    if _client is None:
        import httpx

        _client = httpx.Client(base_url=OLLAMA_BASE_URL, timeout=300.0)
    return _client


def _ollama_generate(prompt: str) -> str:
    """Call the configured LLM (Ollama in LOCAL, Gemini in OFFLOAD).

    Kept under the original name so existing call-sites need no edits.
    """
    return _llm_generate(prompt)


def _throttle():
    global _last_call
    now = time.time()
    wait = MIN_INTERVAL - (now - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()


def _classify_product(description: str) -> dict:
    """Use Gemma 4 via Ollama to classify a product description against CRA Annex III."""
    _throttle()
    prompt = CLASSIFICATION_PROMPT.format(
        categories=ANNEX_III_CATEGORIES,
        description=description,
    )
    text = _ollama_generate(prompt)
    # Strip markdown fences if present
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        log.warning("Classification JSON parse failed: %s", text[:300])
        return {
            "product_class": "default",
            "matched_categories": [],
            "annex_iii_numbers": [],
            "confidence": "low",
            "reasoning": f"LLM response could not be parsed: {text[:200]}",
            "actor_roles": ["manufacturer"],
            "key_features": [],
        }


def classify_product(description: str, actor_role: str = "manufacturer") -> dict:
    """Classify a product under CRA Annex III using Gemma 4.

    This is a lightweight tool that only runs AI classification — no graph queries.
    Use this when creating a new product or re-evaluating after edits.

    Args:
        description: Technical description of the product.
        actor_role: The primary actor role. Default "manufacturer".

    Returns:
        A dict with classification results including product_class, confidence,
        matched_categories, key_features, actor_roles, and reasoning.
    """
    log.info("classify_product called for: %s", description[:100])
    try:
        classification = _classify_product(description)
    except Exception as e:
        return {"status": "error", "message": f"Classification failed: {e}"}

    # Override actor_roles with the requested role
    classification["actor_roles"] = [actor_role]
    return {"status": "ok", "classification": classification}


# IDs of generic "any product" nodes — obligations from these apply universally
_GENERIC_PRODUCT_IDS = frozenset(
    {
        "n_product_with_digital_elements",
        "n_products_with_digital_elements",
        "n_products_with_digital_elements_market",
        "n_product_category",
    }
)

# Mapping from CRA Annex III category numbers → graph node IDs
_CLASS_I_NODE_MAP: dict[int, list[str]] = {
    1: ["n_identity_management_systems"],
    2: ["n_browsers"],
    3: ["n_password_managers"],
    4: ["n_anti_malware", "n_malware_detection_software"],
    5: ["n_vpn_products"],
    6: ["n_network_management_systems"],
    7: ["n_siem_systems"],
    8: ["n_boot_managers"],
    9: ["n_pki_software", "n_digital_certificate_issuance_software"],
    10: [
        "n_network_interfaces",
        "n_physical_network_interfaces",
        "n_virtual_network_interfaces",
    ],
    11: ["n_operating_systems", "n_desktop_operating_system_upgrade"],
    12: ["n_routers", "n_modems", "n_switches", "n_routers_modems_switches"],
    13: [
        "n_microprocessors_security",
        "n_microprocessors_with_security_functionalities",
    ],
    14: [
        "n_microcontrollers_security",
        "n_microcontrollers_with_security_functionalities",
    ],
    15: ["n_asic_fpga_with_security_functionalities"],
    16: ["n_smart_home_virtual_assistants"],
    17: [
        "n_smart_home_security_products",
        "n_smart_door_locks",
        "n_security_cameras",
        "n_baby_monitoring_systems",
        "n_alarm_systems",
        "n_connected_toys",
    ],
    18: ["n_connected_toys", "n_internet_connected_toys"],
    19: ["n_personal_wearable_products", "n_wearable_health_monitoring"],
}

_CLASS_II_NODE_MAP: dict[int, list[str]] = {
    1: [
        "n_hypervisors_and_container_runtime_systems",
        "n_hypervisors",
        "n_container_runtime_systems",
    ],
    2: ["n_firewalls", "n_firewalls_ids_ips", "n_intrusion_detection_systems"],
    3: ["n_tamper_resistant_microprocessors"],
    4: ["n_tamper_resistant_microcontrollers"],
}


def _make_obl_dict(rec, *, source: str) -> dict:
    """Build a standardised obligation dict from a Neo4j record."""
    actors = rec.get("actors")
    if actors is None:
        name = rec.get("actor_name")
        actors = [name] if name else []
    else:
        actors = [a for a in actors if a]
    return {
        "id": rec["id"],
        "action": rec["action"],
        "paragraph": rec.get("paragraph"),
        "trigger": rec.get("trigger"),
        "deadline": rec.get("deadline"),
        "article_id": rec.get("article_id"),
        "article_title": rec.get("article_title"),
        "actors": actors,
        "source": source,
    }


# ── Fetch ALL candidate obligations (pre-filtered by actor role) ──────


def _get_candidate_obligations(actor_roles: list[str]) -> list[dict]:
    """Query Neo4j for ALL obligations, structurally pre-filtered by actor role.

    Returns obligations that either:
    - Have no explicit actor assignment (applicable to all roles)
    - Are assigned to one of the requested actor roles
    - Are assigned to 'economic operators' (applies to all)
    """
    driver = _get_driver()
    label_map = {
        "manufacturer": "Manufacturer",
        "importer": "Importer",
        "distributor": "Distributor",
        "open_source_steward": "OpenSourceSoftwareSteward",
    }
    actor_labels = [label_map.get(r.lower(), r) for r in actor_roles]
    actor_fragments = [lbl.lower() for lbl in actor_labels]
    actor_fragments.append("economic operator")

    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (o:Obligation)
                WHERE o.regulation = 'CRA'
                OPTIONAL MATCH (a:Article)-[:CONTAINS_OBLIGATION]->(o)
                OPTIONAL MATCH (actor:Actor)-[:HAS_OBLIGATION]->(o)
                WITH o, a, collect(DISTINCT actor.name) AS actors
                WHERE size(actors) = 0
                   OR any(act IN actors WHERE
                        any(frag IN $actor_frags WHERE toLower(act) CONTAINS frag))
                RETURN DISTINCT o.id AS id, o.action AS action,
                       o.paragraph_ref AS paragraph, o.trigger AS trigger,
                       o.deadline AS deadline, o.article_id AS article_id,
                       a.article_title AS article_title,
                       actors
                ORDER BY o.article_id, o.id
            """,
                actor_frags=actor_fragments,
            )
            obligations = []
            for rec in result:
                obligations.append(_make_obl_dict(rec, source="candidate"))
            log.info(
                "Fetched %d candidate obligations for actor(s) %s",
                len(obligations),
                actor_roles,
            )
            return obligations
    finally:
        driver.close()


def _get_product_obligations(
    product_class: str,
    actor_roles: list[str],
    matched_annex_numbers: list[int] | None = None,
) -> dict[str, list[dict]]:
    """Query Neo4j for stratified obligations applicable to a product.

    Returns a dict with five layers:
      - "universal"      : apply to ALL products with digital elements
      - "actor"          : obligations for the requested actor role(s)
      - "class_specific" : additional obligations for Class I / II / Critical
      - "product_type"   : obligations for specific Annex III product types
      - "deadline"       : product-relevant obligations with explicit deadlines (no actor filter)
    """
    driver = _get_driver()
    layers: dict[str, list[dict]] = {
        "universal": [],
        "actor": [],
        "class_specific": [],
        "product_type": [],
        "deadline": [],
    }
    seen_ids: set[str] = set()

    try:
        with driver.session() as session:
            # Build the actor label set for filtering
            label_map = {
                "manufacturer": "Manufacturer",
                "importer": "Importer",
                "distributor": "Distributor",
                "open_source_steward": "OpenSourceSoftwareSteward",
            }
            actor_labels = [label_map.get(r.lower(), r) for r in actor_roles]
            # Build case-insensitive actor name fragments for WHERE filters
            actor_fragments = [lbl.lower() for lbl in actor_labels]
            # Also match generic actor "economic operators" for any role
            actor_fragments.append("economic operator")

            # ── 1. Universal obligations (generic product node) ───────
            # Only those assigned to the requested actor role(s) or unassigned
            result = session.run(
                """
                MATCH (o:Obligation)-[:RELATES_TO]->(p:ProductWithDigitalElements)
                WHERE p.id IN $generic_ids AND o.regulation = 'CRA'
                OPTIONAL MATCH (a:Article)-[:CONTAINS_OBLIGATION]->(o)
                OPTIONAL MATCH (actor:Actor)-[:HAS_OBLIGATION]->(o)
                WITH o, a,
                     collect(DISTINCT actor.name) AS actors
                WHERE size(actors) = 0
                   OR any(act IN actors WHERE
                        any(frag IN $actor_frags WHERE toLower(act) CONTAINS frag))
                RETURN DISTINCT o.id AS id, o.action AS action,
                       o.paragraph_ref AS paragraph, o.trigger AS trigger,
                       o.deadline AS deadline, o.article_id AS article_id,
                       a.article_title AS article_title,
                       actors
                ORDER BY o.article_id, o.id
            """,
                generic_ids=list(_GENERIC_PRODUCT_IDS),
                actor_frags=actor_fragments,
            )
            for rec in result:
                if rec["id"] not in seen_ids:
                    layers["universal"].append(_make_obl_dict(rec, source="universal"))
                    seen_ids.add(rec["id"])

            # ── 2. Actor-specific obligations ─────────────────────────
            # Obligations assigned to this actor but NOT on the generic product node
            for role in actor_roles:
                label = label_map.get(role.lower(), role)
                actor_result = session.run(f"""
                    MATCH (actor:{label})-[:HAS_OBLIGATION]->(o:Obligation)
                    WHERE o.regulation = 'CRA'
                    OPTIONAL MATCH (a:Article)-[:CONTAINS_OBLIGATION]->(o)
                    RETURN DISTINCT o.id AS id, o.action AS action,
                           o.paragraph_ref AS paragraph, o.trigger AS trigger,
                           o.deadline AS deadline, o.article_id AS article_id,
                           a.article_title AS article_title,
                           actor.name AS actor_name
                    ORDER BY o.article_id, o.id
                """)
                for rec in actor_result:
                    if rec["id"] not in seen_ids:
                        layers["actor"].append(
                            _make_obl_dict(rec, source=f"actor_{role}")
                        )
                        seen_ids.add(rec["id"])

            # ── 3. Class-specific obligations ─────────────────────────
            if product_class in ("class_i", "class_ii", "critical"):
                # Search for obligations linked to class nodes
                class_terms = []
                if product_class == "class_i":
                    class_terms = ["class_i", "class i", "important product"]
                elif product_class == "class_ii":
                    class_terms = ["class_ii", "class ii", "important product"]
                elif product_class == "critical":
                    class_terms = ["critical product", "annex iv"]

                class_result = session.run(
                    """
                    MATCH (o:Obligation)-[:RELATES_TO]->(n:CRANode)
                    WHERE o.regulation = 'CRA'
                      AND any(term IN $terms WHERE
                        toLower(n.id) CONTAINS term OR toLower(n.name) CONTAINS term)
                    OPTIONAL MATCH (a:Article)-[:CONTAINS_OBLIGATION]->(o)
                    OPTIONAL MATCH (actor:Actor)-[:HAS_OBLIGATION]->(o)
                    RETURN DISTINCT o.id AS id, o.action AS action,
                           o.paragraph_ref AS paragraph, o.trigger AS trigger,
                           o.deadline AS deadline, o.article_id AS article_id,
                           a.article_title AS article_title,
                           collect(DISTINCT actor.name) AS actors,
                           n.name AS matched_node
                    ORDER BY o.id
                """,
                    terms=class_terms,
                )
                for rec in class_result:
                    if rec["id"] not in seen_ids:
                        layers["class_specific"].append(
                            _make_obl_dict(rec, source=f"class_{product_class}")
                        )
                        seen_ids.add(rec["id"])

            # ── 4. Product-type-specific obligations ──────────────────
            # Resolve Annex III category numbers → graph node IDs
            target_node_ids: list[str] = []
            if matched_annex_numbers:
                node_map = (
                    _CLASS_I_NODE_MAP
                    if product_class == "class_i"
                    else _CLASS_II_NODE_MAP if product_class == "class_ii" else {}
                )
                for num in matched_annex_numbers:
                    target_node_ids.extend(node_map.get(num, []))

            if target_node_ids:
                # Look for obligations linked to these specific product nodes
                type_result = session.run(
                    """
                    MATCH (o:Obligation)-[:RELATES_TO]->(p:CRANode)
                    WHERE p.id IN $node_ids AND o.regulation = 'CRA'
                    OPTIONAL MATCH (a:Article)-[:CONTAINS_OBLIGATION]->(o)
                    OPTIONAL MATCH (actor:Actor)-[:HAS_OBLIGATION]->(o)
                    RETURN DISTINCT o.id AS id, o.action AS action,
                           o.paragraph_ref AS paragraph, o.trigger AS trigger,
                           o.deadline AS deadline, o.article_id AS article_id,
                           a.article_title AS article_title,
                           collect(DISTINCT actor.name) AS actors,
                           collect(DISTINCT p.name) AS product_names
                    ORDER BY o.id
                """,
                    node_ids=target_node_ids,
                )
                for rec in type_result:
                    if rec["id"] not in seen_ids:
                        layers["product_type"].append(
                            _make_obl_dict(rec, source="product_type")
                        )
                        seen_ids.add(rec["id"])

            # Also try a text-based match on product node names
            if matched_annex_numbers and not layers["product_type"]:
                # Fallback: search by keywords from the matched categories
                pass  # semantic_boost will cover this

            # ── 5. Product-scoped deadline sweep ─────────────────────
            # Catch obligations with explicit deadlines linked to the
            # SAME product nodes used above — filtered by actor role.
            product_node_ids = list(_GENERIC_PRODUCT_IDS)
            if product_class in ("class_i", "class_ii", "critical"):
                class_kw = {
                    "class_i": ["class_i", "class i", "important product"],
                    "class_ii": ["class_ii", "class ii", "important product"],
                    "critical": ["critical product", "annex iv"],
                }[product_class]
            else:
                class_kw = []
            # Include product-type node IDs if resolved earlier
            if target_node_ids:
                product_node_ids.extend(target_node_ids)

            deadline_result = session.run(
                """
                MATCH (o:Obligation)
                WHERE o.deadline IS NOT NULL AND trim(o.deadline) <> ''
                  AND NOT o.id IN $seen
                OPTIONAL MATCH (o)-[:RELATES_TO]->(p)
                OPTIONAL MATCH (n)-[:HAS_OBLIGATION]->(o)
                  WHERE n:ProductWithDigitalElements OR n:CRANode
                WITH o,
                     [x IN collect(DISTINCT p.id) + collect(DISTINCT n.id)
                      WHERE x IS NOT NULL AND x IS :: STRING] AS linked_ids
                WHERE any(lid IN linked_ids WHERE lid IN $prod_ids)
                   OR any(lid IN linked_ids WHERE
                        any(kw IN $class_kw WHERE
                            toLower(toString(lid)) CONTAINS kw))
                OPTIONAL MATCH (a:Article)-[:CONTAINS_OBLIGATION]->(o)
                OPTIONAL MATCH (actor:Actor)-[:HAS_OBLIGATION]->(o)
                WITH o, a, collect(DISTINCT actor.name) AS actors
                WHERE size(actors) = 0
                   OR any(act IN actors WHERE
                        any(frag IN $actor_frags WHERE toLower(act) CONTAINS frag))
                RETURN DISTINCT o.id AS id, o.action AS action,
                       o.paragraph_ref AS paragraph, o.trigger AS trigger,
                       o.deadline AS deadline, o.article_id AS article_id,
                       a.article_title AS article_title,
                       actors
                ORDER BY o.article_id, o.id
            """,
                seen=list(seen_ids),
                prod_ids=product_node_ids,
                class_kw=class_kw,
                actor_frags=actor_fragments,
            )
            for rec in deadline_result:
                if rec["id"] not in seen_ids:
                    layers["deadline"].append(_make_obl_dict(rec, source="deadline"))
                    seen_ids.add(rec["id"])

    finally:
        driver.close()

    return layers


def _get_conformity_requirements(product_class: str) -> dict:
    """Get conformity assessment routes based on product class (Art. 32)."""
    driver = _get_driver()
    conformity = {
        "assessment_route": "",
        "articles": [],
        "details": [],
    }

    try:
        with driver.session() as session:
            # Get Art. 32 obligations about conformity assessment
            result = session.run("""
                MATCH (a:Article {article_id: 'Art. 32', regulation: 'CRA'})-[:CONTAINS_OBLIGATION]->(o:Obligation)
                OPTIONAL MATCH (o)-[:RELATES_TO]->(n:CRANode)
                RETURN o.id AS id, o.action AS action, o.paragraph_ref AS paragraph,
                       collect(DISTINCT n.name) AS related_nodes
                ORDER BY o.id
            """)
            for rec in result:
                conformity["details"].append(
                    {
                        "id": rec["id"],
                        "action": rec["action"],
                        "paragraph": rec["paragraph"],
                        "related_nodes": rec["related_nodes"],
                    }
                )

            # Get essential requirements from Annex I
            annex_result = session.run("""
                MATCH (o:Obligation)-[:RELATES_TO]->(n:CRANode)
                WHERE o.regulation = 'CRA'
                  AND (n.id CONTAINS 'annex_I' OR n.name CONTAINS 'essential cybersecurity'
                   OR n.name CONTAINS 'Annex I')
                OPTIONAL MATCH (a:Article)-[:CONTAINS_OBLIGATION]->(o)
                RETURN DISTINCT o.id AS id, o.action AS action, o.article_id AS article_id,
                       n.name AS requirement_name
                ORDER BY o.id
            """)
            for rec in annex_result:
                conformity["articles"].append(
                    {
                        "id": rec["id"],
                        "action": rec["action"],
                        "article_id": rec["article_id"],
                        "requirement": rec["requirement_name"],
                    }
                )

    finally:
        driver.close()

    # Set assessment route text
    if product_class == "default":
        conformity["assessment_route"] = (
            "Self-assessment (internal control) per Art. 32(1) using harmonised "
            "standards, common specifications, or EU cybersecurity certification schemes."
        )
    elif product_class == "class_i":
        conformity["assessment_route"] = (
            "Art. 32(2): Self-assessment IF harmonised standards / common specs / "
            "EU cybersecurity certification (assurance level 'substantial') are applied. "
            "Otherwise: third-party assessment per Annex VIII (EU-type examination) or "
            "Art. 32(2)(b) conformity based on full quality assurance."
        )
    elif product_class == "class_ii":
        conformity["assessment_route"] = (
            "Art. 32(3): MANDATORY third-party assessment. EU-type examination "
            "(Annex VIII) + production conformity (Annex VIII.III or Annex VIII.IV), "
            "OR conformity based on full quality assurance (Annex VIII.V), "
            "OR EU cybersecurity certification at assurance level 'substantial'."
        )
    elif product_class == "critical":
        conformity["assessment_route"] = (
            "Art. 8(1) + Art. 32(3): European cybersecurity certificate required "
            "if specified by delegated act. Otherwise: same as Class II (mandatory "
            "third-party assessment)."
        )

    return conformity


def _get_deadlines(obligations: list[dict]) -> list[dict]:
    """Extract and organise obligations with explicit deadlines."""
    deadlines = []
    for obl in obligations:
        if obl.get("deadline") and obl["deadline"].strip():
            deadlines.append(
                {
                    "obligation_id": obl["id"],
                    "deadline": obl["deadline"],
                    "action": obl["action"] or "",
                    "article_id": obl["article_id"] or "",
                }
            )
    return sorted(deadlines, key=lambda d: d["obligation_id"])


def _get_cross_references(obligation_ids: list[str]) -> list[dict]:
    """Get cross-references from obligations to other articles/annexes."""
    if not obligation_ids:
        return []

    driver = _get_driver()
    refs = []
    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (o:Obligation)-[:RELATES_TO]->(n:CRANode)-[:REFERENCES]->(r:ArticleRef)
                WHERE o.id IN $ids
                RETURN DISTINCT o.id AS obligation_id, r.ref AS reference,
                       n.name AS via_node
                ORDER BY o.id, r.ref
            """,
                ids=obligation_ids,
            )
            for rec in result:
                refs.append(
                    {
                        "obligation_id": rec["obligation_id"],
                        "reference": rec["reference"],
                        "via": rec["via_node"],
                    }
                )
    finally:
        driver.close()

    return refs


def _semantic_boost(description: str, key_features: list[str]) -> list[dict]:
    """Use vector search to find additional relevant CRA sections."""
    from .vector_tools import _embed_query, _get_driver as _get_vec_driver

    # Build a search query from the product description + features
    search_text = description
    if key_features:
        search_text += " " + " ".join(key_features)
    # Truncate for embedding
    search_text = search_text[:2000]

    try:
        query_vec = _embed_query(search_text)
    except Exception as e:
        log.warning("Semantic boost failed — embedding error: %s", e)
        return []

    driver = _get_vec_driver()
    results = []
    try:
        with driver.session() as session:
            # Check if vector index exists
            indexes = session.run(
                "SHOW INDEXES WHERE name = 'cra_chunk_embedding'"
            ).data()
            if not indexes:
                return []

            rows = session.run(
                """
                CALL db.index.vector.queryNodes('cra_chunk_embedding', 8, $vec)
                YIELD node, score
                RETURN node.chunk_id AS chunk_id,
                       node.section AS section,
                       node.title AS title,
                       node.text AS text,
                       score
                ORDER BY score DESC
            """,
                vec=query_vec,
            ).data()

            for r in rows:
                preview = r["text"][:300].replace("\n", " ").strip()
                if len(r["text"]) > 300:
                    preview += "..."
                results.append(
                    {
                        "chunk_id": r["chunk_id"],
                        "section": r["section"],
                        "title": r["title"],
                        "score": round(r["score"] * 100, 1),
                        "excerpt": preview,
                    }
                )
    finally:
        driver.close()

    return results


def _get_inter_obligation_links(obligation_ids: list[str]) -> dict:
    """Get inter-obligation relationships for the found obligations."""
    if not obligation_ids:
        return {"refines": [], "derives_from": [], "supports": [], "complements": []}

    driver = _get_driver()
    links = {"refines": [], "derives_from": [], "supports": [], "complements": []}

    try:
        with driver.session() as session:
            for rel_type, key in [
                ("REFINES", "refines"),
                ("DERIVES_FROM", "derives_from"),
                ("SUPPORTS", "supports"),
                ("COMPLEMENTS", "complements"),
            ]:
                result = session.run(
                    f"""
                    MATCH (o1:Obligation)-[:{rel_type}]->(o2:Obligation)
                    WHERE o1.id IN $ids OR o2.id IN $ids
                    RETURN o1.id AS from_id, o2.id AS to_id,
                           o1.action AS from_action, o2.action AS to_action
                    LIMIT 50
                """,
                    ids=obligation_ids,
                )
                for rec in result:
                    links[key].append(
                        {
                            "from": rec["from_id"],
                            "to": rec["to_id"],
                            "from_action": (rec["from_action"] or "")[:80],
                            "to_action": (rec["to_action"] or "")[:80],
                        }
                    )
    finally:
        driver.close()

    return links


# =====================================================================
# LLM-based obligation relevance filter
# =====================================================================

_SELECT_PROMPT = """\
You are an EU Cyber Resilience Act (CRA) compliance expert.

╔════════════════════════════════════════════════════════════════════╗
║ ASSESSOR DIRECTIVES (read FIRST — these override everything below) ║
╚════════════════════════════════════════════════════════════════════╝
{directives_block}

PRODUCT INFORMATION:
- Name: {product_name}
- Description: {description}
- CRA Class: {product_class}
- Key Features: {key_features}
- Actor Roles: {actor_roles}

Read each obligation below. Only select obligations that impose a CONCRETE, \
ACTIONABLE requirement specifically relevant to THIS product's features, \
technology, and risk profile.

SELECTION CRITERIA — select ONLY if ALL of these are true:
1. The obligation addresses a risk or capability that THIS product actually has.
2. The obligation requires a SPECIFIC action that makes sense for this product's \
technology stack and deployment model.
3. The obligation is NOT a generic regulatory/administrative provision that \
applies identically to all products regardless of type.
4. The obligation is NOT excluded by any ASSESSOR DIRECTIVE above. Treat every \
EXCLUDE / LIMIT / PREFER directive as an ABSOLUTE filter — when in doubt, drop.

EXCLUDE obligations that:
1. Target different product categories (hardware obligations for pure software, \
radio/wireless directives for offline apps, smart meter requirements for a calculator, \
AI Act references for non-AI products).
2. Are for a different actor role than this product's.
3. Reference irrelevant regulatory frameworks (medical devices, machinery, etc.).
4. Describe conformity procedures for a HIGHER class than this product's.
5. Concern physical/hardware security inapplicable to pure software (tamper \
resistance, physical markings, hardware modules).
6. Are generic transitional/administrative provisions ("shall enter into force", \
"shall be binding", "shall apply from date X", "this regulation is addressed to").
7. Address NETWORK SECURITY, CONNECTIVITY, or REMOTE ACCESS requirements when \
the product has NO network connectivity.
8. Address DATA PROTECTION, ENCRYPTION, or PRIVACY requirements when the \
product collects or processes NO user data.
9. Address UPDATE MECHANISMS, AUTOMATIC UPDATES, or PATCH DISTRIBUTION when \
the product has no network connectivity for receiving updates.
10. Address SUPPLY CHAIN SECURITY for third-party components when the product \
is a simple standalone application with minimal dependencies.
11. Address INCIDENT REPORTING TO ENISA or CSIRT about actively exploited \
vulnerabilities when the product has no attack surface (no network, no data).
12. Are about INTEROPERABILITY or IMPACT ON OTHER DEVICES/SERVICES when the \
product does not connect to other devices or services.

There is NO target count. The right number is whatever the directives and the \
product's real risk surface dictate — could be 20, could be 200. Do not anchor \
on a typical IoT figure.

DEDUPLICATION: if two obligations express the same requirement (same action verb, \
same target, same scope) under different IDs, keep only the most specific one and \
drop the duplicates.

OBLIGATIONS (JSON array):
{obligations_json}

Return ONLY a valid JSON array of objects, one per RELEVANT obligation:
[{{"id": "...", "justification": "one sentence why this applies to {product_name}"}}]

Return [] if NONE of the obligations apply.
"""

_SELECT_BATCH_SIZE = 40  # obligations per LLM call


# ─── Rule-based deterministic pre-filter ─────────────────────────────
#
# Many "EXCLUDE Annex II" / "EXCLUDE Article 13" style directives can be
# applied losslessly BEFORE the LLM ever sees the candidates, simply by
# matching obligation IDs against the annex / article they're tagged to.
# This guarantees the rule wins, instead of leaving it to the LLM's prior.

_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8}


def _extract_directives_block(description: str) -> str:
    """Return only the ASSESSOR DIRECTIVES block (or empty string)."""
    mark = "=== ASSESSOR DIRECTIVES"
    if mark not in description:
        return ""
    block = description.split(mark, 1)[1]
    # Trim the closing fence if present
    block = block.split("=========================", 1)[0]
    return block.strip()


def _annex_prefix(token: str) -> str | None:
    """Map an annex token ("I", "II", "III"…) to a fully-bounded ID prefix.

    Trailing underscore prevents collisions like "AnnII" matching "AnnIII_…".
    """
    t = (token or "").strip().lower()
    if t in _ROMAN:
        n = _ROMAN[t]
        if n == 1:
            return "AnnI_"
        if n == 2:
            return "AnnII_"
        if n == 3:
            return "AnnIII_"
        return f"Ann{token.upper()}_"
    return None


def _parse_exclude_rules(directives: str) -> list[tuple[str, str]]:
    """Return a list of (kind, value) pairs for EXCLUDE directives.

    Supported patterns (case-insensitive):
      - EXCLUDE Annex II[...]               → ("annex", "II")
      - EXCLUDE Annex II Part II[...]       → ("annex", "II"), ("annex_part", "II.II")
      - EXCLUDE Annex I Part II[...]        → ("annex_part", "I.II")
      - EXCLUDE Article 13[...]             → ("article", "13")
    Other EXCLUDE rules are left for the LLM to interpret.
    """
    out: list[tuple[str, str]] = []
    for line in directives.splitlines():
        s = line.strip().lstrip("-• ").strip()
        if not s or not s.upper().startswith(("EXCLUDE", "LIMIT")):
            continue
        # Annex I Part II
        m = re.search(r"\bannex\s+([ivx]+)\s+part\s+([ivx]+)\b", s, flags=re.IGNORECASE)
        if m:
            out.append(("annex_part", f"{m.group(1).upper()}.{m.group(2).upper()}"))
            continue
        # Annex N
        m = re.search(r"\bannex\s+([ivx]+)\b", s, flags=re.IGNORECASE)
        if m:
            out.append(("annex", m.group(1).upper()))
            continue
        # Article N
        m = re.search(r"\barticle\s+(\d+)\b", s, flags=re.IGNORECASE)
        if m:
            out.append(("article", m.group(1)))
            continue
    return out


def _matches_exclude(obl_id: str, article_id: str, kind: str, value: str) -> bool:
    oid = obl_id or ""
    aid = article_id or ""
    if kind == "annex":
        prefix = _annex_prefix(value)
        if not prefix:
            return False
        return oid.startswith(prefix)
    if kind == "annex_part":
        # value like "I.II" → match "AnnI_PartII"
        ann, part = value.split(".", 1)
        return oid.startswith(f"Ann{ann}_Part{part}")
    if kind == "article":
        # IDs like "Art13_par2_3" or article_id "Article 13"
        if oid.lower().startswith(f"art{value}_") or oid.lower().startswith(
            f"art_{value}_"
        ):
            return True
        return bool(re.search(rf"\barticle\s*{value}\b", aid, flags=re.IGNORECASE))
    return False


def _apply_rule_prefilter(
    obligations: list[dict], directives: str
) -> tuple[list[dict], list[dict]]:
    """Split candidates into (kept, dropped) using deterministic EXCLUDE rules."""
    if not directives:
        return obligations, []
    excludes = _parse_exclude_rules(directives)
    if not excludes:
        return obligations, []
    kept: list[dict] = []
    dropped: list[dict] = []
    for o in obligations:
        oid = o.get("id", "")
        aid = o.get("article_id", "")
        if any(_matches_exclude(oid, aid, k, v) for k, v in excludes):
            dropped.append(o)
        else:
            kept.append(o)
    if dropped:
        log.info(
            "Rule pre-filter: dropped %d/%d candidates via directives %s",
            len(dropped),
            len(obligations),
            excludes,
        )
    return kept, dropped


def _select_obligations(
    product_info: dict,
    obligations: list[dict],
) -> list[dict]:
    """Use Gemini to positively select obligations relevant to this product.

    Sends obligations in batches to Gemini 2.5 Flash-Lite, asking it to
    return the IDs of obligations that ARE applicable, with a justification.

    Args:
        product_info: Dict with product_name, description, product_class,
                      key_features, actor_roles.
        obligations: List of candidate obligation dicts from the graph.

    Returns:
        List of obligations the LLM deemed relevant, each enriched with
        a 'justification' key.
    """
    if not obligations:
        return obligations

    _throttle()

    # ── Deterministic pre-filter (EXCLUDE Annex / Article rules) ───
    _full_desc = product_info.get("description", "") or ""
    _directives = _extract_directives_block(_full_desc)
    obligations, _dropped_by_rule = _apply_rule_prefilter(obligations, _directives)

    if not obligations:
        return []

    # Map obligation ID → justification string
    justifications: dict[str, str] = {}
    include_ids: set[str] = set()

    for i in range(0, len(obligations), _SELECT_BATCH_SIZE):
        batch = obligations[i : i + _SELECT_BATCH_SIZE]
        compact = [
            {
                "id": o["id"],
                "article": o.get("article_id", ""),
                "article_title": o.get("article_title", ""),
                "action": (o.get("action") or "")[:500],
                "actors": o.get("actors", []),
            }
            for o in batch
        ]

        # Preserve the ASSESSOR DIRECTIVES block: truncate prose body to
        # ~1500 chars but always keep the directives intact at the end.
        _DIRECTIVE_MARK = "=== ASSESSOR DIRECTIVES"
        if _DIRECTIVE_MARK in _full_desc:
            _body, _dir = _full_desc.split(_DIRECTIVE_MARK, 1)
            _body = _body[:1500].rstrip()
            _desc_for_prompt = f"{_body}\n\n{_DIRECTIVE_MARK}{_dir}"
        else:
            _desc_for_prompt = _full_desc[:1500]

        _directives_for_prompt = (
            _directives if _directives else "(no directives — use general judgement)"
        )

        prompt = _SELECT_PROMPT.format(
            product_name=product_info.get("product_name", "Unknown"),
            description=_desc_for_prompt,
            product_class=product_info.get("product_class", "default"),
            key_features=", ".join(product_info.get("key_features", [])),
            actor_roles=", ".join(product_info.get("actor_roles", ["manufacturer"])),
            obligations_json=json.dumps(compact, indent=1),
            directives_block=_directives_for_prompt,
        )

        try:
            _throttle()
            text = _ollama_generate(prompt)
            if text.startswith("```"):
                text = re.sub(r"^```\w*\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
            items = json.loads(text)
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        sid = str(item.get("id", ""))
                        include_ids.add(sid)
                        justifications[sid] = item.get("justification", "")
                    else:
                        # Backward compat: plain ID string
                        include_ids.add(str(item))
                log.info(
                    "Select batch %d-%d: selected %d/%d obligations",
                    i,
                    i + len(batch),
                    len(items),
                    len(batch),
                )
        except Exception as e:
            # On failure, include entire batch to avoid losing obligations
            log.warning("Obligation select batch %d failed: %s — keeping all", i, e)
            include_ids.update(o["id"] for o in batch)

    selected = []
    for o in obligations:
        if o["id"] in include_ids:
            o["justification"] = justifications.get(o["id"], "")
            selected.append(o)
    log.info(
        "Obligation selection: kept %d/%d obligations",
        len(selected),
        len(obligations),
    )
    return selected


def filter_obligations(
    description: str,
    product_name: str = "",
    product_class: str = "default",
    key_features: str = "",
    actor_roles: str = "manufacturer",
    obligation_ids: str = "",
) -> dict:
    """Filter CRA obligations for relevance to a specific product using AI.

    Uses Gemini to evaluate whether each obligation actually applies to the
    given product, removing those that target different product categories
    or regulatory frameworks.

    Args:
        description: Technical description of the product.
        product_name: Short product name.
        product_class: CRA classification (default/class_i/class_ii/critical).
        key_features: Comma-separated key features.
        actor_roles: Comma-separated actor roles.
        obligation_ids: Comma-separated obligation IDs to filter.
            If empty, returns an error.

    Returns:
        Dict with filtered obligation IDs and removal details.
    """
    if not obligation_ids:
        return {"status": "error", "message": "No obligation_ids provided"}

    ids = [i.strip() for i in obligation_ids.split(",") if i.strip()]

    # Fetch obligation details from Neo4j
    driver = _get_driver()
    obligations = []
    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (o:Obligation)
                WHERE o.id IN $ids
                OPTIONAL MATCH (a:Article)-[:CONTAINS_OBLIGATION]->(o)
                RETURN o.id AS id, o.action AS action,
                       o.article_id AS article_id,
                       a.article_title AS article_title
                """,
                ids=ids,
            )
            for rec in result:
                obligations.append(
                    {
                        "id": rec["id"],
                        "action": rec["action"],
                        "article_id": rec["article_id"],
                        "article_title": rec["article_title"],
                    }
                )
    finally:
        driver.close()

    product_info = {
        "product_name": product_name,
        "description": description,
        "product_class": product_class,
        "key_features": [f.strip() for f in key_features.split(",") if f.strip()],
        "actor_roles": [r.strip() for r in actor_roles.split(",") if r.strip()],
    }

    filtered = _select_obligations(product_info, obligations)
    removed = set(ids) - {o["id"] for o in filtered}

    return {
        "status": "ok",
        "kept": len(filtered),
        "removed": sorted(removed),
        "removed_count": len(removed),
        "kept_ids": [o["id"] for o in filtered],
    }


# =====================================================================
# PUBLIC TOOL — called by the ADK agent
# =====================================================================


def product_obligations(
    description: str,
    actor_role: str = "manufacturer",
    classification_json: str = "",
) -> dict:
    """Analyse a product against the EU Cyber Resilience Act (CRA).

    Given a technical product description, this tool:
    1. Classifies the product under CRA Annex III (Default / Class I / Class II / Critical)
       — or uses a pre-computed classification if provided
    2. Queries the knowledge graph for ALL applicable obligations
    3. Lists deadlines, conformity assessment routes, and cross-references
    4. Finds additional relevant provisions via semantic search

    Args:
        description: A technical description of the product. Be specific about
            its functionality, connectivity, target users, and security features.
        actor_role: The actor role to focus on. Default "manufacturer".
            Options: "manufacturer", "importer", "distributor", "open_source_steward"
        classification_json: Optional pre-computed classification as a JSON string
            (from classify_product). If provided, skips the LLM classification step.

    Returns:
        A dict with 'status', 'report', and structured results. The 'report'
        field MUST be relayed verbatim to the user.
    """
    log.info("product_obligations called for: %s", description[:100])

    # ── 1. Classify the product ───────────────────────────────────────
    classification: dict | None = None
    if classification_json:
        try:
            classification = json.loads(classification_json)
        except (json.JSONDecodeError, TypeError):
            log.warning("Invalid classification_json, will re-classify")
    if classification is None:
        try:
            classification = _classify_product(description)
        except Exception as e:
            return {
                "status": "error",
                "report": f"Product classification failed: {e}",
            }

    product_class = classification.get("product_class", "default")
    # Use only the explicitly requested actor role — ignore LLM additions
    actor_roles = [actor_role]
    key_features = classification.get("key_features", [])

    log.info(
        "Classification: %s (confidence: %s)",
        product_class,
        classification.get("confidence", "?"),
    )

    # ── 2. Get ALL candidate obligations, select relevant ones ──────────
    candidates = _get_candidate_obligations(actor_roles)
    log.info("Candidate obligations (actor pre-filter): %d", len(candidates))

    product_info = {
        "product_name": classification.get("product_name", ""),
        "description": description,
        "product_class": product_class,
        "key_features": key_features,
        "actor_roles": actor_roles,
    }
    all_obligations = _select_obligations(product_info, candidates)
    log.info("Selected obligations: %d/%d", len(all_obligations), len(candidates))

    # Classify selected obligations into layers for reporting
    layers: dict[str, list[dict]] = {
        "universal": [],
        "actor": [],
        "class_specific": [],
        "product_type": [],
    }
    for obl in all_obligations:
        actors = obl.get("actors", [])
        if actors:
            layers["actor"].append(obl)
        else:
            layers["universal"].append(obl)

    # ── 3. Get conformity assessment requirements ─────────────────────
    conformity = _get_conformity_requirements(product_class)

    # ── 4. Extract deadlines ──────────────────────────────────────────
    deadlines = _get_deadlines(all_obligations)

    # ── 5. Get cross-references ───────────────────────────────────────
    obl_ids = [o["id"] for o in all_obligations]
    cross_refs = _get_cross_references(obl_ids)

    # ── 6. Get inter-obligation links ─────────────────────────────────
    links = _get_inter_obligation_links(obl_ids)

    # ── 7. Semantic search for extra context ──────────────────────────
    semantic_results = _semantic_boost(description, key_features)

    # ── 8. Write compliance-assessment JSON ────────────────────────────
    json_path = _write_assessment_json(
        description=description,
        classification=classification,
        actor_role=actor_role,
        layers=layers,
        conformity=conformity,
        deadlines=deadlines,
    )

    # ── 9. Build concise chat report (numbers only) ───────────────────
    report = _build_report(
        description=description,
        classification=classification,
        layers=layers,
        conformity=conformity,
        deadlines=deadlines,
        json_path=json_path,
    )

    return {
        "status": "ok",
        "report": report,
        "json_file": str(json_path),
        "classification": classification,
        "obligation_counts": {k: len(v) for k, v in layers.items()},
        "total_obligations": len(all_obligations),
        "deadline_count": len(deadlines),
        "cross_ref_count": len(cross_refs),
        "semantic_hits": len(semantic_results),
    }


# ── Evidence suggestion rules ─────────────────────────────────────────
# Each rule: (keywords_to_match, suggested_evidence_text)
# Order matters — first match wins, so put specific rules before generic ones.
_EVIDENCE_RULES: list[tuple[list[str], str]] = [
    # Software Bill of Materials
    (
        ["software bill of materials", "sbom"],
        "Software Bill of Materials (SBOM) document — machine-readable format (e.g. CycloneDX, SPDX)",
    ),
    # Technical documentation
    (
        ["technical documentation", "annex vii"],
        "Technical documentation file (Annex VII compliant)",
    ),
    # Risk assessment
    (
        [
            "risk assessment",
            "cybersecurity risk",
            "assessment of the cybersecurity risks",
        ],
        "Cybersecurity risk assessment report",
    ),
    # EU declaration of conformity
    (
        ["eu declaration of conformity", "declaration of conformity"],
        "EU Declaration of Conformity document (per Art. 28 / Annex V)",
    ),
    # Simplified EU declaration
    (
        ["simplified eu declaration", "simplified declaration"],
        "Simplified EU Declaration of Conformity (per Annex VI)",
    ),
    # CE marking
    (
        ["ce marking", "affix the ce"],
        "CE marking placement evidence (photo/screenshot of product, packaging, or website)",
    ),
    # Conformity assessment
    (
        ["conformity assessment", "conformity to eu-type", "eu-type examination"],
        "Conformity assessment report / EU-type examination certificate",
    ),
    # Quality system
    (
        ["quality system", "quality assurance"],
        "Quality management system documentation (ISO 9001 or equivalent)",
    ),
    # Notified body
    (["notified body"], "Notified body certificate / audit report"),
    # Vulnerability disclosure policy
    (
        ["vulnerability disclosure", "coordinated vulnerability"],
        "Coordinated Vulnerability Disclosure (CVD) policy document",
    ),
    # Vulnerability handling
    (
        [
            "vulnerability handling",
            "vulnerabilities",
            "handle vulnerabilities",
            "remediate vulnerabilities",
        ],
        "Vulnerability handling process documentation & incident log",
    ),
    # Security updates
    (
        ["security update", "security patch", "updates for products"],
        "Security update delivery process documentation & update log",
    ),
    # Support period
    (
        ["support period", "end date of the support", "end-date of the support"],
        "Support period definition document with justification",
    ),
    # User instructions / information
    (
        ["information and instructions to the user", "annex ii", "instructions on"],
        "User information & instructions document (Annex II compliant)",
    ),
    # Single point of contact
    (
        ["single point of contact", "point of contact"],
        "Single point of contact setup evidence (URL, email, etc.)",
    ),
    # Product identification
    (
        ["type, batch or serial number", "unique identification"],
        "Product identification scheme documentation (serial/batch numbering)",
    ),
    # Manufacturer contact
    (
        [
            "name, registered trade name",
            "postal address",
            "manufacturer can be contacted",
        ],
        "Manufacturer identification & contact details record",
    ),
    # Third-party components / due diligence
    (
        [
            "components sourced from third parties",
            "due diligence",
            "integrating components",
        ],
        "Third-party component due diligence report & supply chain records",
    ),
    # Tests / testing
    (
        ["test", "testing", "tests carried out"],
        "Test reports & test results documentation",
    ),
    # Design & development
    (
        [
            "design, development",
            "design and development",
            "drawings, schemes",
            "system architecture",
        ],
        "Design & development documentation (architecture, diagrams, specifications)",
    ),
    # Production / manufacturing
    (
        ["production", "manufacturing"],
        "Production & manufacturing process documentation",
    ),
    # Corrective action
    (
        ["corrective action", "corrective measures", "withdraw or recall"],
        "Corrective action / recall procedure documentation",
    ),
    # Market surveillance cooperation
    (
        ["market surveillance", "surveillance authorit"],
        "Market surveillance correspondence / cooperation records",
    ),
    # Authorised representative
    (
        ["authorised representative", "written mandate"],
        "Authorised representative mandate document",
    ),
    # Harmonised standards
    (
        [
            "harmonised standard",
            "common specification",
            "european cybersecurity certification",
        ],
        "List of applied harmonised standards / common specifications / certification schemes",
    ),
    # Security properties / intended purpose
    (
        ["security properties", "intended purpose", "security environment"],
        "Product security properties & intended purpose description",
    ),
    # Decommissioning
    (
        ["decommissioning", "securely removed"],
        "Secure decommissioning procedure documentation",
    ),
    # Data security
    (["security of data"], "Data security impact assessment document"),
    # Integration info
    (
        ["integrator", "integration"],
        "Integration guidance documentation for downstream integrators",
    ),
    # Cessation of operations
    (
        ["cessation of operations", "ceases its operations"],
        "Business continuity / cessation plan",
    ),
    # Cybersecurity requirements (generic)
    (
        ["essential cybersecurity requirements", "annex i"],
        "Annex I compliance mapping document",
    ),
]

# ── Concrete executable action rules ─────────────────────────────────
# Each entry: ([trigger keywords (lowercase)], "Action 1 | Action 2 | …")
# Rules are matched left-to-right; multiple rules may fire for one obligation.
_ACTION_RULES: list[tuple[list[str], str]] = [
    # SBOM
    (
        ["software bill of materials", "sbom"],
        "Generate SBOM using CycloneDX or SPDX format"
        " | List all third-party libraries with versions & licences"
        " | Automate SBOM generation in CI/CD pipeline"
        " | Publish SBOM alongside each product release",
    ),
    # Vulnerability disclosure
    (
        ["vulnerability disclosure", "coordinated vulnerability"],
        "Publish CVD policy at security.txt / dedicated security web page"
        " | Register product on a CVD platform (e.g. NCSC, CERT/CC)"
        " | Assign a dedicated security contact e-mail address",
    ),
    # Vulnerability handling
    (
        [
            "vulnerability handling",
            "handle vulnerabilities",
            "remediate vulnerabilities",
            "known exploitable vulnerabilities",
        ],
        "Implement CVE tracking in issue tracker with CVSS scoring"
        " | Set SLA: critical ≤7 days, high ≤30 days, medium ≤90 days"
        " | Automate dependency scanning (Dependabot / Snyk / OWASP)"
        " | Notify affected users when a medium/high/critical fix is released",
    ),
    # Security updates
    (
        ["security update", "security patch", "updates for products"],
        "Build and sign security patches with a code-signing certificate"
        " | Set up automated or one-click update delivery to end devices"
        " | Publish signed release notes referencing patched CVEs"
        " | Test updates in staging environment before rollout",
    ),
    # Risk assessment
    (
        ["risk assessment", "cybersecurity risk"],
        "Conduct formal threat modelling (STRIDE/DREAD or PASTA method)"
        " | Document identified threats with mitigations and residual risk"
        " | Map findings to ENISA Good Practices / ISO/IEC 27001"
        " | Schedule annual reassessment and after each major feature change",
    ),
    # EU Declaration of Conformity
    (
        ["eu declaration of conformity", "declaration of conformity"],
        "Draft EU Declaration of Conformity using CRA Annex V template"
        " | List all applied harmonised standards and their versions"
        " | Obtain authorised signature (board level or designated officer)"
        " | Publish DoC on product website and include copy in packaging",
    ),
    # CE marking
    (
        ["ce marking", "affix the ce"],
        "Apply CE marking to product label, packaging, documentation, and website"
        " | Verify CE marking dimensions comply with Regulation (EC) 765/2008"
        " | Do not affix CE until all CRA essential requirements are verified",
    ),
    # Technical documentation
    (
        ["technical documentation", "annex vii"],
        "Compile Annex VII technical documentation file (design, risk, test results)"
        " | Store documentation under version control (Git / SharePoint)"
        " | Retain documentation for at least 10 years after last market placement"
        " | Assign a documentation owner responsible for updates",
    ),
    # Conformity assessment
    (
        ["conformity assessment", "eu-type examination", "conformity to eu-type"],
        "Select applicable conformity assessment module (Art. 32 / Annex VIII)"
        " | Engage accredited notified body if product is Class II or Critical"
        " | Prepare and submit technical file for external review"
        " | Obtain and retain notified body certificate",
    ),
    # Support period
    (
        ["support period", "end date of the support", "end-date of the support"],
        "Define and document minimum support period justified by expected product lifetime"
        " | Publish EoL dates on product page, packaging, and user documentation"
        " | Commit to security-only patches for at least the stated support period"
        " | Notify users ≥12 months before end of support",
    ),
    # User information / instructions
    (
        [
            "information and instructions to the user",
            "annex ii",
            "instructions on",
            "inform users",
        ],
        "Write Annex II-compliant user manual with security configuration guidance"
        " | Include instructions for: initial secure setup, password change, software update"
        " | Describe secure decommissioning / data wipe procedure"
        " | Translate documentation into languages of all target markets",
    ),
    # Encryption / data security
    (
        [
            "encrypt",
            "cryptograph",
            "security of data",
            "data at rest",
            "data in transit",
        ],
        "Audit data-at-rest encryption (AES-256 or equivalent)"
        " | Enforce TLS 1.2+ for all data-in-transit; disable TLS 1.0/1.1 and SSL"
        " | Replace deprecated algorithms (MD5, SHA-1, DES, 3DES, RC4)"
        " | Document and test key management and rotation procedures",
    ),
    # Authentication / access control
    (
        [
            "authentication",
            "access control",
            "authoris",
            "privileg",
            "unauthoris",
        ],
        "Enforce strong authentication; require MFA for administrative interfaces"
        " | Apply principle of least privilege — audit all roles and permissions"
        " | Remove all hardcoded, default, or blank credentials before release"
        " | Rotate API keys and secrets on a defined schedule (≤90 days)",
    ),
    # Minimal attack surface
    (
        [
            "attack surface",
            "minimal",
            "not expose",
            "disable functions",
            "unnecessary functions",
        ],
        "Disable all unused network services, ports, and debug interfaces in production builds"
        " | Conduct port and service scan (nmap) to verify minimal exposure"
        " | Review factory-default settings — secure-by-default where possible"
        " | Document the rationale for every active interface",
    ),
    # Network / communication interfaces
    (
        [
            "network interface",
            "communication interface",
            "network access",
            "remotely accessible",
        ],
        "Document all network interfaces (Ethernet, Wi-Fi, Bluetooth, Zigbee, etc.)"
        " | Apply network segmentation and firewall rules"
        " | Conduct network-layer penetration test"
        " | Implement intrusion detection / anomaly monitoring where feasible",
    ),
    # Incident notification / reporting
    (
        [
            "notify",
            "notification",
            "report to",
            "market surveillance",
            "enisa",
            "severe incident",
        ],
        "Define incident classification criteria (severe vs non-severe)"
        " | Set up 24 h detection-to-notify workflow for severe incidents"
        " | Draft incident notification templates for authorities and users"
        " | Assign an incident response owner and an alternate"
        " | Register with ENISA EUVDB if applicable",
    ),
    # Supply chain / third-party
    (
        [
            "components sourced from third parties",
            "due diligence",
            "integrating components",
            "supply chain",
        ],
        "Conduct security questionnaire / assessment for all third-party component suppliers"
        " | Include mandatory security requirements in supplier contracts (right-to-audit)"
        " | Subscribe to CVE feeds for every third-party library used"
        " | Document and regularly review component provenance",
    ),
    # Secure defaults / security configuration
    (
        ["secure by default", "security configuration", "default configuration"],
        "Audit factory-default configuration against a security baseline"
        " | Disable all non-essential features and services by default"
        " | Provide secure configuration guide as part of product documentation"
        " | Validate configuration hardening in pre-release testing",
    ),
    # Audit logging
    (
        ["log", "audit trail", "monitor"],
        "Implement tamper-evident security event logging (authentication, errors, updates)"
        " | Define log retention policy (minimum 12 months recommended)"
        " | Set up alerting on critical security events"
        " | Ensure logs are pseudonymised — do not log PII unnecessarily",
    ),
    # Product identification
    (
        ["type, batch or serial number", "unique identification"],
        "Implement serial / batch numbering scheme and engrave on hardware / embed in firmware"
        " | Record product identifiers in manufacturing database"
        " | Include product ID in bug reports, update metadata, and recall notices",
    ),
    # Contact details — manufacturer
    (
        [
            "name, registered trade name",
            "postal address",
            "can be contacted",
        ],
        "Add manufacturer name, address, and security contact to product labelling"
        " | Create security contact address (e.g. security@company.com)"
        " | Publish security.txt file at product domain per RFC 9116",
    ),
    # Corrective actions / recall
    (
        ["corrective action", "withdraw or recall", "corrective measures"],
        "Draft and test a product recall and market withdrawal SOP"
        " | Set up mechanism to push urgent security notices to active users"
        " | Log all corrective actions taken with dates and rationale"
        " | Run annual recall drill",
    ),
    # Secure decommissioning
    (
        ["decommissioning", "securely removed", "sensitive data"],
        "Implement a factory-reset function that wipes all user data and credentials"
        " | Document data deletion procedure meeting NIST SP 800-88 / GDPR requirements"
        " | Test data wiping on a sample of end-of-life devices"
        " | Include decommissioning instructions in user documentation",
    ),
    # Authorised representative
    (
        ["authorised representative", "written mandate"],
        "Appoint an EU authorised representative and sign a written mandate"
        " | Ensure representative can provide technical documentation to authorities on request"
        " | Publish representative's name and contact details on product/packaging",
    ),
    # Harmonised standards
    (
        ["harmonised standard", "common specification"],
        "Map each product feature to applicable standards (ETSI EN 303 645, IEC 62443, ISO 27001)"
        " | Document clause-by-clause conformity rationale"
        " | Monitor OJEU for newly published harmonised standards and update mapping annually",
    ),
    # Open source / transparency
    (
        ["open source", "open-source"],
        "Publish SECURITY.md describing vulnerability reporting process in the repository"
        " | Apply OpenSSF Scorecard and target ≥7 score"
        " | Consider joining a CVE Numbering Authority (CNA)"
        " | Maintain a CHANGELOG with security-relevant entries",
    ),
    # Cessation / business continuity
    (
        ["cessation of operations", "ceases its operations"],
        "Prepare business continuity / asset transfer plan covering security updates"
        " | Notify users and authorities ≥12 months before cessation"
        " | Arrange source code escrow or repository transfer for critical products",
    ),
    # Integration guidance
    (
        ["integrator", "integration"],
        "Publish integration security guide documenting required downstream controls"
        " | Specify minimum security requirements in integration contracts"
        " | Provide API security documentation with authentication guidelines",
    ),
    # Annex I generic requirements
    (
        ["essential cybersecurity requirements", "annex i"],
        "Perform gap analysis against each Annex I Part I requirement"
        " | Map existing controls to Annex I requirements in a compliance matrix"
        " | Prioritise unmet requirements in the security roadmap with owners and deadlines",
    ),
    # Placing on market / making available
    (
        ["make available on the market", "placing on the market"],
        "Complete a pre-market checklist: CE marking, DoC, Annex VII file, SBOM, support period"
        " | Verify no known unmitigated critical vulnerabilities before release"
        " | Register product with relevant national authorities if required",
    ),
    # Market surveillance cooperation
    (
        ["market surveillance", "surveillance authorit"],
        "Designate an internal contact for market surveillance authority (MSA) requests"
        " | Establish a 5-business-day response SLA for MSA document requests"
        " | Keep technical documentation readily retrievable (not archived)",
    ),
    # Quality system
    (
        ["quality system", "quality assurance"],
        "Implement or align with ISO 9001 / ISO/IEC 90003 quality management system"
        " | Define security design review gates in the product development lifecycle"
        " | Conduct internal security audits annually and after major releases",
    ),
]


def _suggest_actions(obligation_text: str, paragraph: str = "") -> str:
    """Return '|'-delimited concrete executable actions for a given obligation.

    Uses keyword matching against ``_ACTION_RULES``.  Multiple rules may fire,
    and their actions are concatenated (deduplicated).
    """
    combined = (obligation_text + " " + paragraph).lower()
    actions: list[str] = []
    seen: set[str] = set()
    for keywords, rule_actions in _ACTION_RULES:
        for kw in keywords:
            if kw in combined:
                for act in rule_actions.split(" | "):
                    act = act.strip()
                    if act and act not in seen:
                        actions.append(act)
                        seen.add(act)
                break  # one match per rule is sufficient
    return " | ".join(actions)


def _suggest_evidence(obligation_text: str, paragraph: str = "") -> str:
    """Suggest expected evidence artefact(s) based on obligation text."""
    combined = (obligation_text + " " + paragraph).lower()
    suggestions: list[str] = []
    matched_indices: set[int] = set()
    for idx, (keywords, suggestion) in enumerate(_EVIDENCE_RULES):
        if idx in matched_indices:
            continue
        for kw in keywords:
            if kw in combined:
                suggestions.append(suggestion)
                matched_indices.add(idx)
                break  # one keyword per rule is enough
    if not suggestions:
        return ""
    # Return unique suggestions joined
    return " | ".join(dict.fromkeys(suggestions))  # preserve order, deduplicate


def _write_assessment_json(
    *,
    description: str,
    classification: dict,
    actor_role: str,
    layers: dict[str, list[dict]],
    conformity: dict,
    deadlines: list[dict],
) -> Path:
    """Write a self-compliance-assessment JSON checklist.

    The file is designed to be used directly by a compliance officer:
    - Flat checklist grouped by CRA article
    - Each obligation has fillable status / evidence / notes fields
    - Only actionable information: obligation text, paragraph, trigger, deadline
    - No internal graph metadata, no semantic results, no cross-refs
    """
    outputs_dir = Path(__file__).resolve().parents[2] / "outputs"
    outputs_dir.mkdir(exist_ok=True)

    # Use the product name from classification for a clean filename
    product_name = classification.get("product_name", "")
    if not product_name:
        # Fallback: first 3 meaningful words from description
        _STOP = {
            "a",
            "an",
            "the",
            "is",
            "for",
            "of",
            "and",
            "with",
            "to",
            "in",
            "on",
            "by",
            "it",
            "its",
        }
        words = [
            w
            for w in re.sub(r"[^a-z0-9]+", " ", description.lower()).split()
            if w not in _STOP
        ][:3]
        product_name = " ".join(words)
    slug = re.sub(r"[^a-z0-9]+", "_", product_name.lower()).strip("_")[:30]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"CRA_{slug}_{ts}.json"
    filepath = outputs_dir / filename

    # Flatten all layers into a single ordered list, deduplicated
    all_obligations: list[dict] = []
    seen: set[str] = set()
    for layer_obls in layers.values():
        for obl in layer_obls:
            if obl["id"] not in seen:
                all_obligations.append(obl)
                seen.add(obl["id"])

    # Group by article for logical reading order
    by_article: dict[str, list[dict]] = {}
    for obl in all_obligations:
        art = obl.get("article_id") or "General"
        by_article.setdefault(art, []).append(obl)

    # Build the checklist
    checklist: list[dict] = []
    item_num = 0
    for art_id in sorted(by_article.keys()):
        art_obls = by_article[art_id]
        art_title = art_obls[0].get("article_title") or ""
        for obl in art_obls:
            item_num += 1
            obl_text = obl.get("action") or ""
            para = obl.get("paragraph") or ""
            suggested = _suggest_evidence(obl_text, para)
            checklist.append(
                {
                    "#": item_num,
                    "id": obl["id"],
                    "article": art_id,
                    "article_title": art_title,
                    "paragraph": para,
                    "obligation": obl_text,
                    "trigger": obl.get("trigger") or "",
                    "deadline": obl.get("deadline") or "",
                    "justification": obl.get("justification") or "",
                    # ── Fields to fill during assessment ──
                    "status": "",  # compliant | non_compliant | partial | not_applicable
                    "expected_evidence": suggested,  # auto-suggested artefact(s) based on obligation content
                    "evidence": "",  # TO FILL: reference to actual evidence document
                    "notes": "",  # assessor notes
                }
            )

    # Build deadline summary (only obligations with explicit deadlines)
    deadline_items = []
    for obl in all_obligations:
        dl = (obl.get("deadline") or "").strip()
        if dl:
            deadline_items.append(
                {
                    "id": obl["id"],
                    "article": obl.get("article_id") or "",
                    "deadline": dl,
                    "obligation": (obl.get("action") or "")[:200],
                }
            )

    pc = classification.get("product_class", "default")
    matched = classification.get("matched_categories", [])

    output = {
        "_comment": (
            "CRA Self-Compliance Assessment Checklist. "
            "Fill in 'status', 'evidence', and 'notes' for each obligation. "
            "status values: compliant | non_compliant | partial | not_applicable. "
            "'expected_evidence' lists artefacts to prepare as proof."
        ),
        "product": {
            "description": description,
            "classification": pc.replace("_", " ").upper(),
            "matched_annex_iii_categories": matched,
            "actor_role": actor_role,
            "confidence": classification.get("confidence", "unknown"),
            "reasoning": classification.get("reasoning", ""),
        },
        "conformity_assessment": {
            "route": conformity["assessment_route"],
        },
        "statistics": {
            "total_obligations": len(checklist),
            "obligations_with_evidence": sum(
                1 for c in checklist if c.get("expected_evidence")
            ),
            "obligations_with_actions": sum(
                1 for c in checklist if c.get("neo4j_actions")
            ),
            "obligations_with_deadlines": len(deadline_items),
            "articles_covered": len(by_article),
        },
        "checklist": checklist,
        "deadlines": deadline_items,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    log.info("Compliance assessment JSON written to %s", filepath)
    return filepath


def _build_report(
    *,
    description: str,
    classification: dict,
    layers: dict[str, list[dict]],
    conformity: dict,
    deadlines: list[dict],
    json_path: Path,
) -> str:
    """Build a concise chat report — numbers only. Full detail is in the JSON file."""
    lines = []
    all_obligations = []
    for v in layers.values():
        all_obligations.extend(v)

    pc = classification.get("product_class", "default").replace("_", " ").upper()
    actor_roles = classification.get("actor_roles", ["manufacturer"])

    lines.append("## CRA PRODUCT OBLIGATIONS — SUMMARY")
    lines.append("")
    lines.append(f"**Product**: {description[:200]}")
    lines.append(
        f"**Classification**: {pc} (confidence: {classification.get('confidence', '?')})"
    )
    if classification.get("matched_categories"):
        lines.append(
            f"**Matched categories**: {', '.join(classification['matched_categories'])}"
        )
    lines.append(f"**Conformity route**: {conformity['assessment_route'][:120]}")
    lines.append("")
    lines.append("### Obligation counts")
    lines.append("")
    lines.append(f"| Category | Count |")
    lines.append(f"|----------|-------|")
    lines.append(f"| Universal (all products) | {len(layers.get('universal', []))} |")
    lines.append(
        f"| Actor-specific ({', '.join(actor_roles)}) | {len(layers.get('actor', []))} |"
    )
    lines.append(f"| Class-specific ({pc}) | {len(layers.get('class_specific', []))} |")
    lines.append(f"| Product-type-specific | {len(layers.get('product_type', []))} |")
    lines.append(f"| **TOTAL SELECTED** | **{len(all_obligations)}** |")
    lines.append("")
    lines.append(f"Deadlines with explicit dates: {len(deadlines)}")
    lines.append("")
    lines.append(f"**Self-compliance assessment checklist written to:**")
    lines.append(f"`{json_path}`")
    lines.append("")
    lines.append(
        "The JSON file contains a flat checklist with every obligation's full literal text. "
    )
    lines.append(
        "Each item has `action_items` (concrete executable steps), "
        "`expected_evidence` (artefacts to prepare), plus empty `status`, `evidence`, "
        "and `notes` fields."
    )
    lines.append(
        "Status values: `compliant` | `non_compliant` | `partial` | `not_applicable`"
    )

    return "\n".join(lines)
