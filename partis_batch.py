"""Batch processing tool for Part-IS (EU 2023/203) — parse & ingest into Neo4j.

Mirrors the CRA batch_tool.py but adapted for Part-IS structure:
  - Articles 1-16
  - IS.AR sections (Annex I — Authority requirements)
  - IS.I.OR sections (Annex II — Organisation requirements)
  - Recitals (1)-(18)
  - Annexes III-IX (amendments to other regulations)
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from google import genai

# ── Paths & config ────────────────────────────────────────────────────
_ENV_PATH = Path(__file__).resolve().parent / "cra_agents" / ".env"
load_dotenv(_ENV_PATH)

BASE_DIR = Path(__file__).resolve().parent
MD_PATH = BASE_DIR / "outputs" / "PartIS_requirements.md"
OUTPUT_DIR = BASE_DIR / "outputs" / "partis_articles"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL = "gemini-2.5-flash-lite"
MIN_INTERVAL = 4.5
_last_call = 0.0

# ── Logging ──────────────────────────────────────────────────────────
LOG_FILE = BASE_DIR / "outputs" / "partis_batch_progress.log"
logger = logging.getLogger("partis_batch")
logger.setLevel(logging.INFO)
_fh = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
_fh.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S"))
logger.addHandler(_fh)
_ch = logging.StreamHandler()
_ch.setFormatter(
    logging.Formatter("%(asctime)s - PARTIS - %(message)s", datefmt="%H:%M:%S")
)
logger.addHandler(_ch)

# ── Gemini client ────────────────────────────────────────────────────
_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY not set")
        _client = genai.Client(api_key=api_key)
    return _client


def _throttle():
    global _last_call
    now = time.time()
    wait = MIN_INTERVAL - (now - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()


def _try_fix_json(text: str) -> dict | list | None:
    t = text.strip()
    if t.startswith("```json"):
        t = t[7:]
    elif t.startswith("```"):
        t = t[3:]
    if t.endswith("```"):
        t = t[:-3]
    t = t.strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        return None


def _retry_call(prompt: str, max_retries: int = 3) -> str | None:
    # Prefer the unified gateway so MODEL_TYPE is honored. Fall back to direct
    # Gemini if the cra_agents package isn't importable (e.g. when this script
    # is run standalone outside the agent container).
    try:
        from cra_agents.tools._llm import generate as _llm_generate

        for attempt in range(max_retries):
            _throttle()
            try:
                return _llm_generate(prompt, model=MODEL)
            except Exception as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err:
                    backoff = 10 * (2**attempt)
                    time.sleep(backoff)
                else:
                    return None
        return None
    except ImportError:
        for attempt in range(max_retries):
            _throttle()
            try:
                response = _get_client().models.generate_content(
                    model=MODEL, contents=prompt
                )
                return response.text
            except Exception as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err:
                    backoff = 10 * (2**attempt)
                    time.sleep(backoff)
                else:
                    return None
        return None


# ── Markdown readers ─────────────────────────────────────────────────


def _read_md() -> str:
    return MD_PATH.read_text(encoding="utf-8")


def _get_article_numbers() -> list[int]:
    text = _read_md()
    return sorted(
        int(m) for m in re.findall(r"^### Article (\d+) —", text, re.MULTILINE)
    )


def _read_article(article_number: int) -> str | None:
    text = _read_md()
    pattern = rf"^### Article {article_number} —"
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        return None
    start = match.start()
    rest = text[match.end() :]
    next_heading = re.search(r"^##?# ", rest, re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(text)
    return text[start:end].strip()


def _get_is_section_ids(annex: str = "I") -> list[str]:
    """Get IS section IDs from given annex. annex='I' → IS.AR, annex='II' → IS.I.OR."""
    text = _read_md()
    if annex == "I":
        prefix = "IS.AR"
    elif annex == "II":
        prefix = "IS.I.OR"
    else:
        return []

    # Find the annex boundary
    annex_pattern = rf"^## ANNEX {re.escape(annex)} —"
    annex_match = re.search(annex_pattern, text, re.MULTILINE)
    if not annex_match:
        return []
    annex_start = annex_match.start()

    # Find next annex
    rest = text[annex_match.end() :]
    next_annex = re.search(r"^## ANNEX ", rest, re.MULTILINE)
    annex_end = annex_match.end() + next_annex.start() if next_annex else len(text)
    annex_text = text[annex_start:annex_end]

    # Find all IS section headings with actual content (skip TOC entries)
    sections = []
    seen = set()
    for m in re.finditer(
        rf"^### ({re.escape(prefix)}\.\d+[A-Z]?) — (.+)$", annex_text, re.MULTILINE
    ):
        section_id = m.group(1)
        # Check if the section has body content (not just a TOC line)
        sec_start = m.end()
        sec_rest = annex_text[sec_start:]
        next_sec = re.search(r"^### ", sec_rest, re.MULTILINE)
        sec_end = sec_start + next_sec.start() if next_sec else len(annex_text)
        body = annex_text[sec_start:sec_end].strip()
        if len(body) > 10 and section_id not in seen:
            sections.append(section_id)
            seen.add(section_id)
    return sections


def _read_is_section(section_id: str) -> str | None:
    """Read a specific IS section (e.g. IS.AR.200, IS.I.OR.205) with its full content."""
    text = _read_md()
    escaped = re.escape(section_id)
    pattern = rf"^### {escaped} — .+$"
    # Find all matches and take the one with actual body content
    matches = list(re.finditer(pattern, text, re.MULTILINE))
    for match in matches:
        start = match.start()
        rest = text[match.end() :]
        next_heading = re.search(r"^### ", rest, re.MULTILINE)
        end = match.end() + next_heading.start() if next_heading else len(text)
        body = text[start:end].strip()
        if len(body) > 50:  # has real content, not just TOC
            return body
    return None


def _get_recital_numbers() -> list[int]:
    text = _read_md()
    return sorted(int(m) for m in re.findall(r"^### \((\d+)\)\s*$", text, re.MULTILINE))


def _read_recital(recital_number: int) -> str | None:
    text = _read_md()
    pattern = rf"^### \({recital_number}\)\s*$"
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        return None
    start = match.start()
    rest = text[match.end() :]
    next_heading = re.search(r"^##?# ", rest, re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(text)
    return text[start:end].strip()


def _get_amendment_annex_ids() -> list[str]:
    """Get annex IDs for amendment annexes (III-IX)."""
    text = _read_md()
    ids = []
    for m in re.finditer(
        r"^## ANNEX (I{2,3}V?|IV|VI{0,3}|VIII?|IX) —", text, re.MULTILINE
    ):
        aid = m.group(1)
        if aid not in ("I", "II"):
            ids.append(aid)
    return ids


def _read_amendment_annex(annex_id: str) -> str | None:
    text = _read_md()
    pattern = rf"^## ANNEX {re.escape(annex_id)} —"
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        return None
    start = match.start()
    rest = text[match.end() :]
    next_annex = re.search(r"^## ANNEX ", rest, re.MULTILINE)
    end = match.end() + next_annex.start() if next_annex else len(text)
    return text[start:end].strip()


# ── Parser prompts ───────────────────────────────────────────────────

ARTICLE_PROMPT = """You are a Legal Knowledge-Graph Parser for EU Implementing Regulation 2023/203 (Part-IS).
This regulation covers information security requirements for aviation organisations and competent authorities.

Given the article text below, extract ALL entities, relationships, obligations, and cross-references into strict JSON.

OUTPUT RULES:
- Return ONLY valid JSON. No markdown fences, no commentary, no explanation.
- The JSON must follow the exact schema below.

JSON SCHEMA:
{
  "metadata": {
    "regulation": "Implementing Regulation (EU) 2023/203",
    "regulation_short": "Part-IS",
    "article_id": "Art. <N>",
    "article_title": "<title>",
    "paragraph_count": <int>
  },
  "nodes": [
    {
      "id": "n_<snake_case>",
      "label": "<Actor|ProductWithDigitalElements|ProductComponent|TechnicalConcept|CybersecurityConcept|MarketActivity|UseContext|ComplianceArtifact|LegalProvision|Enterprise|LegalFramework>",
      "sub_label": "<specific subclass>",
      "name": "<human-readable name>",
      "properties": {}
    }
  ],
  "relationships": [
    {
      "source_id": "n_...",
      "target_id": "n_...",
      "type": "<RELATIONSHIP_TYPE>",
      "properties": { "paragraph_ref": "Art. N(M)" }
    }
  ],
  "obligations": [
    {
      "id": "obl_<N>",
      "paragraph_ref": "Art. N(M)",
      "actor": "n_<actor_id>",
      "action": "<what the actor must do>",
      "trigger": "<event or null>",
      "deadline": "<deadline or null>",
      "related_nodes": ["n_..."]
    }
  ],
  "cross_references": [
    {
      "source_id": "n_...",
      "target": "<Art. N or Annex X or IS.AR.NNN or IS.I.OR.NNN>",
      "type": "<SPECIFIED_BY|SPECIFIES_PROCESS_FOR|REFERENCES|AMENDS>",
      "context": "<reason for cross-reference>"
    }
  ]
}

RULES:
- Node IDs: n_<snake_case>, consistent across articles.
  Key actors for Part-IS: n_organisation, n_competent_authority, n_easa (the Agency), n_commission
- Every paragraph produces at least one relationship or obligation
- Relationship properties MUST include paragraph_ref
- Cross-reference any mention of IS.AR, IS.I.OR, or IS.D.OR sections
- Cross-reference any mention of other EU regulations (e.g. Regulation (EU) 2018/1139)

ARTICLE TEXT:
"""

IS_SECTION_PROMPT = """You are a Legal Knowledge-Graph Parser for EU Implementing Regulation 2023/203 (Part-IS).
This regulation covers information security requirements for aviation organisations and competent authorities.

Given the IS section text below (from Annex I [Part-IS.AR] or Annex II [Part-IS.I.OR]),
extract ALL entities, relationships, obligations, and cross-references into strict JSON.

These sections contain detailed ISMS requirements — they are the core operative provisions.

OUTPUT RULES:
- Return ONLY valid JSON. No markdown fences, no commentary, no explanation.
- The JSON must follow the exact schema below.

JSON SCHEMA:
{
  "metadata": {
    "regulation": "Implementing Regulation (EU) 2023/203",
    "regulation_short": "Part-IS",
    "article_id": "<IS.AR.NNN or IS.I.OR.NNN>",
    "article_title": "<section title>",
    "annex": "<Annex I or Annex II>",
    "paragraph_count": <int>
  },
  "nodes": [
    {
      "id": "n_<snake_case>",
      "label": "<Actor|ProductWithDigitalElements|ProductComponent|TechnicalConcept|CybersecurityConcept|MarketActivity|UseContext|ComplianceArtifact|LegalProvision|Enterprise|LegalFramework>",
      "sub_label": "<specific subclass>",
      "name": "<human-readable name>",
      "properties": {}
    }
  ],
  "relationships": [
    {
      "source_id": "n_...",
      "target_id": "n_...",
      "type": "<RELATIONSHIP_TYPE>",
      "properties": { "section_ref": "<IS.AR.NNN(a)(1) or IS.I.OR.NNN(a)(1)>" }
    }
  ],
  "obligations": [
    {
      "id": "obl_<N>",
      "paragraph_ref": "<IS.AR.NNN(a)(1) or IS.I.OR.NNN(a)(1)>",
      "actor": "n_<actor_id>",
      "action": "<what the actor must do>",
      "trigger": "<event or null>",
      "deadline": "<deadline or null>",
      "related_nodes": ["n_..."]
    }
  ],
  "cross_references": [
    {
      "source_id": "n_...",
      "target": "<IS.AR.NNN or IS.I.OR.NNN or Art. N or Annex X>",
      "type": "<SPECIFIED_BY|SPECIFIES_PROCESS_FOR|REFERENCES|AMENDS>",
      "context": "<reason for cross-reference>"
    }
  ]
}

RULES:
- Node IDs: n_<snake_case>, consistent across sections.
  Key actors: n_organisation (for IS.I.OR), n_competent_authority (for IS.AR), n_easa, n_commission
  Key concepts: n_isms, n_risk_assessment, n_risk_treatment, n_incident_response, n_reporting_scheme
- Extract EVERY obligation: each lettered point (a), (b), (c) and sub-point (1), (2) is typically a distinct obligation
- Capture rich cross-references between IS sections (e.g. "in accordance with point IS.I.OR.210")
- paragraph_ref format: IS.I.OR.200(a)(1) — use point notation matching the regulation's structure

IS SECTION TEXT:
"""

RECITAL_PROMPT = """You are a Legal Knowledge-Graph Parser for EU Implementing Regulation 2023/203 (Part-IS).
This regulation covers information security requirements for aviation organisations and competent authorities.

Given the recital text below, extract ALL entities, relationships, and cross-references into strict JSON.
Recitals provide interpretive context — they do NOT create legal obligations.

OUTPUT RULES:
- Return ONLY valid JSON. No markdown fences, no commentary, no explanation.

JSON SCHEMA:
{
  "metadata": {
    "regulation": "Implementing Regulation (EU) 2023/203",
    "regulation_short": "Part-IS",
    "recital_id": "Recital (<N>)",
    "section": "Recitals"
  },
  "nodes": [
    {
      "id": "n_<snake_case>",
      "label": "<Actor|ProductWithDigitalElements|ProductComponent|TechnicalConcept|CybersecurityConcept|MarketActivity|UseContext|ComplianceArtifact|LegalProvision|Enterprise|LegalFramework>",
      "sub_label": "<specific subclass>",
      "name": "<human-readable name>",
      "properties": {}
    }
  ],
  "relationships": [
    {
      "source_id": "n_...",
      "target_id": "n_...",
      "type": "<RELATIONSHIP_TYPE>",
      "properties": { "recital_ref": "Recital (<N>)" }
    }
  ],
  "obligations": [],
  "cross_references": [
    {
      "source_id": "n_...",
      "target": "<Art. N or Annex X or Directive/Regulation ref>",
      "type": "<REFERENCES|MOTIVATES|INTERPRETS|AMENDS>",
      "context": "<reason for cross-reference>"
    }
  ]
}

RULES:
- Node IDs: n_<snake_case>, consistent with article/section nodes
- Recitals have NO legal obligations — leave the obligations array empty
- Extract all cross-references to Part-IS articles, IS sections, and external EU legislation
- Key actors: n_organisation, n_competent_authority, n_easa, n_commission

RECITAL TEXT:
"""

AMENDMENT_ANNEX_PROMPT = """You are a Legal Knowledge-Graph Parser for EU Implementing Regulation 2023/203 (Part-IS).

Given the amendment annex text below, extract the key amendments, affected regulations, obligations and cross-references into strict JSON.
Amendment annexes modify other EU aviation regulations to introduce information security requirements.

OUTPUT RULES:
- Return ONLY valid JSON. No markdown fences, no commentary, no explanation.

JSON SCHEMA:
{
  "metadata": {
    "regulation": "Implementing Regulation (EU) 2023/203",
    "regulation_short": "Part-IS",
    "annex_id": "Annex <ROMAN>",
    "annex_title": "<title>",
    "section": "Annexes"
  },
  "nodes": [
    {
      "id": "n_<snake_case>",
      "label": "<Actor|ProductWithDigitalElements|ProductComponent|TechnicalConcept|CybersecurityConcept|MarketActivity|UseContext|ComplianceArtifact|LegalProvision|Enterprise|LegalFramework>",
      "sub_label": "<specific subclass>",
      "name": "<human-readable name>",
      "properties": {}
    }
  ],
  "relationships": [
    {
      "source_id": "n_...",
      "target_id": "n_...",
      "type": "<RELATIONSHIP_TYPE>",
      "properties": { "annex_ref": "Annex <ROMAN>" }
    }
  ],
  "obligations": [
    {
      "id": "obl_<N>",
      "paragraph_ref": "Annex <ROMAN>, point <N>",
      "actor": "n_<actor_id>",
      "action": "<what the actor must do>",
      "trigger": "<event or null>",
      "deadline": "<deadline or null>",
      "related_nodes": ["n_..."]
    }
  ],
  "cross_references": [
    {
      "source_id": "n_...",
      "target": "<Art. N or IS.AR.NNN or IS.I.OR.NNN or Regulation ref>",
      "type": "<SPECIFIED_BY|SPECIFIES_PROCESS_FOR|REFERENCES|AMENDS>",
      "context": "<reason for cross-reference>"
    }
  ]
}

RULES:
- Node IDs: n_<snake_case>, consistent across articles
- Key actors: n_competent_authority, n_organisation, n_easa
- Extract the ISMS obligations introduced by the amendments
- Cross-reference back to IS.AR, IS.I.OR sections and Part-IS articles

AMENDMENT ANNEX TEXT:
"""


# ── Obligation ID builder for Part-IS ────────────────────────────────


def _build_obligation_id(article_id: str, paragraph_ref: str, obl_index: int) -> str:
    """Build a structured obligation ID for Part-IS.

    Formats:
      - Articles:     art{N}_par{P}_{i}
      - Recitals:     Rec{N}_par{P}_{i}
      - IS.AR:        IS_AR_{NNN}_par{a}_{i}
      - IS.I.OR:      IS_I_OR_{NNN}_par{a}_{i}
      - Annexes:      AnnN_par{P}_{i}
    """
    # Extract paragraph number
    par_match = re.search(r"\((\w+)\)", paragraph_ref) if paragraph_ref else None
    par_id = par_match.group(1) if par_match else "1"

    # Recitals
    rec_match = (
        re.search(r"Recital\s*\((\d+)\)", article_id, re.IGNORECASE)
        if article_id
        else None
    )
    if rec_match:
        return f"Rec{rec_match.group(1)}_par{par_id}_{obl_index}"

    # IS.AR sections: IS.AR.200 → IS_AR_200
    is_ar_match = re.search(r"IS\.AR\.(\d+[A-Z]?)", article_id) if article_id else None
    if is_ar_match:
        sec_num = is_ar_match.group(1)
        return f"IS_AR_{sec_num}_par{par_id}_{obl_index}"

    # IS.I.OR sections: IS.I.OR.200 → IS_I_OR_200
    is_ior_match = (
        re.search(r"IS\.I\.OR\.(\d+[A-Z]?)", article_id) if article_id else None
    )
    if is_ior_match:
        sec_num = is_ior_match.group(1)
        return f"IS_I_OR_{sec_num}_par{par_id}_{obl_index}"

    # Annexes
    ann_match = (
        re.search(r"Annex\s+(I{1,3}V?|IV|VI{0,3}|VIII?|IX)", article_id, re.IGNORECASE)
        if article_id
        else None
    )
    if ann_match:
        roman = ann_match.group(1).upper()
        return f"Ann{roman}_par{par_id}_{obl_index}"

    # Articles: "Art. 4" → art4_par1_1
    art_match = re.search(r"(\d+)", article_id) if article_id else None
    art_num = art_match.group(1) if art_match else "0"
    return f"art{art_num}_par{par_id}_{obl_index}"


# ── Neo4j ingestion ─────────────────────────────────────────────────


def _get_driver():
    import os
    from neo4j import GraphDatabase

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password123")
    return GraphDatabase.driver(uri, auth=(user, password))


def _ingest_json(file_id: str) -> str:
    """Ingest a Part-IS JSON file into Neo4j."""
    filepath = OUTPUT_DIR / f"{file_id}.json"
    if not filepath.exists():
        return f"ERROR: File not found: {filepath}"

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
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

        # Metadata → Article node
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
            props["regulation"] = "Part-IS"
            session.run(
                "MERGE (a:Article {article_id: $article_id, regulation: $reg}) SET a += $props",
                article_id=aid,
                reg="Part-IS",
                props=props,
            )
            results.append(f"Metadata for {aid}")

        # Nodes → CRANode (shared ontology across regulations)
        nodes = data.get("nodes", [])
        for node in nodes:
            nid = node["id"]
            label = node.get("label", "CRANode")
            sub_label = node.get("sub_label", label)
            props = {"name": node.get("name", ""), "regulation": "Part-IS"}
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
                continue
            props = {}
            for k, v in rel.get("properties", {}).items():
                if isinstance(v, (str, int, float, bool)):
                    props[k] = v
            src = rel.get("source_id") or rel.get("source") or rel.get("from", "")
            tgt = rel.get("target_id") or rel.get("target") or rel.get("to", "")
            if not src or not tgt:
                continue
            query = f"""
                MATCH (a:CRANode {{id: $source_id}})
                MATCH (b:CRANode {{id: $target_id}})
                MERGE (a)-[r:`{rel_type}`]->(b)
                SET r += $props
            """
            session.run(query, source_id=src, target_id=tgt, props=props)
        results.append(f"Merged {len(rels)} relationships")

        # Obligations
        article_id = (
            meta.get("article_id")
            or meta.get("annex_id")
            or meta.get("recital_id")
            or ""
        )
        obls = data.get("obligations", [])
        total_verifs = 0
        par_counters: dict[str, int] = {}

        for obl in obls:
            raw_id = obl["id"]
            paragraph_ref = obl.get("paragraph_ref", "")

            par_match = (
                re.search(r"\((\w+)\)", paragraph_ref) if paragraph_ref else None
            )
            par_key = f"par{par_match.group(1)}" if par_match else "par1"
            par_counters[par_key] = par_counters.get(par_key, 0) + 1
            obl_index = par_counters[par_key]

            obl_id = _build_obligation_id(article_id, paragraph_ref, obl_index)
            legacy_id = (
                f"{article_id}_{raw_id}" if not raw_id.startswith("Art") else raw_id
            )

            actor_id = obl.get("actor", "")
            props = {"legacy_id": legacy_id, "regulation": "Part-IS"}
            for k in ("paragraph_ref", "action", "trigger", "deadline"):
                if obl.get(k) is not None:
                    props[k] = obl[k]
            props["article_id"] = article_id
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

            # Verification actions
            res = session.run(
                "MATCH (o:Obligation {id: $id})-[:HAS_VERIFICATION]->(v:VerificationAction) "
                "RETURN count(v) AS v_count",
                id=obl_id,
            )
            v_count = res.single()["v_count"] if res else 0

            if v_count == 0 and props.get("action"):
                try:
                    from cra_agents.tools.verification_generator import (
                        generate_verifications_for_obligation,
                    )
                    from cra_agents.tools.vector_tools import _embed_query

                    verifs = generate_verifications_for_obligation(props["action"])
                    for v in verifs:
                        desc = v.get("description", "")
                        if not desc:
                            continue
                        try:
                            embed_vec = _embed_query(desc)
                        except Exception:
                            embed_vec = None

                        existing_id = None
                        if embed_vec:
                            dup_res = session.run(
                                "MATCH (v:VerificationAction) "
                                "WHERE v.embedding IS NOT NULL "
                                "WITH v, vector.similarity.cosine(v.embedding, $emb) AS score "
                                "WHERE score > 0.95 "
                                "RETURN v.id AS id ORDER BY score DESC LIMIT 1",
                                emb=embed_vec,
                            ).data()
                            if dup_res:
                                existing_id = dup_res[0]["id"]

                        if existing_id:
                            session.run(
                                "MATCH (o:Obligation {id: $obl_id}) "
                                "MATCH (v:VerificationAction {id: $existing_id}) "
                                "MERGE (o)-[:HAS_VERIFICATION]->(v)",
                                obl_id=obl_id,
                                existing_id=existing_id,
                            )
                        else:
                            v_id = str(uuid.uuid4())
                            v_props = {
                                "type": v.get("type", "review"),
                                "description": desc,
                                "evidence": v.get("evidence", ""),
                                "regulation": "Part-IS",
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
                                    "MERGE (v:VerificationAction {id: $id}) SET v += $props",
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

            # Link obligation to Article node
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
            results.append(f"Generated {total_verifs} verifications")

        # Cross-references
        crs = data.get("cross_references", [])
        for cr in crs:
            target = cr["target"]
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
                query, source_id=cr["source_id"], target=target, context=context
            )
        results.append(f"Merged {len(crs)} cross-references")

    driver.close()
    return "Ingestion complete: " + ", ".join(results)


# ── Parsers ──────────────────────────────────────────────────────────


def _parse_raw(prompt: str, text: str, label: str) -> dict | None:
    raw = _retry_call(prompt + text)
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(f"{label} — raw JSON invalid, attempting auto-repair…")
        repaired = _try_fix_json(raw)
        if repaired is not None:
            logger.info(f"{label} — auto-repair succeeded")
            return repaired
        (OUTPUT_DIR / f"{label}_raw.txt").write_text(raw, encoding="utf-8")
        return None


# ── Batch processing functions ───────────────────────────────────────


def batch_parse_articles(
    article_range: str = "all", force: bool = False, ingest_only: bool = False
) -> str:
    """Parse and ingest Part-IS articles."""
    all_articles = _get_article_numbers()
    if article_range.strip().lower() == "all":
        targets = all_articles
    else:
        targets = [n for n in _parse_range(article_range) if n in all_articles]

    if not targets:
        return f"No valid articles. Available: {all_articles}"

    logger.info(f"=== ARTICLES START: {len(targets)} ===")
    lines = [f"Processing {len(targets)} articles"]
    success, failed = 0, []

    for i, num in enumerate(targets, 1):
        file_id = f"art_{num}"
        json_path = OUTPUT_DIR / f"{file_id}.json"

        if not ingest_only:
            if json_path.exists() and not force:
                lines.append(f"[{i}/{len(targets)}] Art. {num} — skipped")
                logger.info(f"[{i}/{len(targets)}] Art. {num} — skipped")
            else:
                logger.info(f"[{i}/{len(targets)}] Art. {num} — parsing…")
                text = _read_article(num)
                if not text:
                    lines.append(f"[{i}/{len(targets)}] Art. {num} — NOT FOUND")
                    failed.append(num)
                    continue
                data = _parse_raw(ARTICLE_PROMPT, text, f"art_{num}")
                if data is None:
                    lines.append(f"[{i}/{len(targets)}] Art. {num} — PARSE FAILED")
                    failed.append(num)
                    continue
                json_path.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                n = len(data.get("nodes", []))
                o = len(data.get("obligations", []))
                lines.append(f"[{i}/{len(targets)}] Art. {num} — parsed: {n}N {o}O")
                logger.info(f"[{i}/{len(targets)}] Art. {num} — parsed: {n}N {o}O")

        if not json_path.exists():
            failed.append(num)
            continue

        logger.info(f"[{i}/{len(targets)}] Art. {num} — ingesting…")
        result = _ingest_json(file_id)
        if result.startswith("ERROR"):
            lines.append(f"[{i}/{len(targets)}] Art. {num} — INGEST FAILED: {result}")
            failed.append(num)
        else:
            lines.append(f"[{i}/{len(targets)}] Art. {num} — {result}")
            success += 1

    lines.append(f"\nDone: {success}/{len(targets)} articles succeeded.")
    if failed:
        lines.append(f"Failed: {failed}")
    return "\n".join(lines)


def batch_parse_is_sections(
    annex: str = "all", force: bool = False, ingest_only: bool = False
) -> str:
    """Parse and ingest IS.AR / IS.I.OR sections from Annexes I and II."""
    annexes_to_process = []
    if annex.strip().lower() == "all":
        annexes_to_process = ["I", "II"]
    elif annex.strip().upper() in ("I", "II"):
        annexes_to_process = [annex.strip().upper()]
    else:
        return f"Invalid annex: {annex}. Use 'I', 'II', or 'all'."

    all_sections = []
    for a in annexes_to_process:
        for sid in _get_is_section_ids(a):
            all_sections.append((a, sid))

    if not all_sections:
        return "No IS sections found."

    logger.info(f"=== IS SECTIONS START: {len(all_sections)} ===")
    lines = [f"Processing {len(all_sections)} IS sections"]
    success, failed = 0, []

    for i, (annex_id, section_id) in enumerate(all_sections, 1):
        file_id = section_id.replace(".", "_")  # IS.AR.200 → IS_AR_200
        json_path = OUTPUT_DIR / f"{file_id}.json"

        if not ingest_only:
            if json_path.exists() and not force:
                lines.append(f"[{i}/{len(all_sections)}] {section_id} — skipped")
                logger.info(f"[{i}/{len(all_sections)}] {section_id} — skipped")
            else:
                logger.info(f"[{i}/{len(all_sections)}] {section_id} — parsing…")
                text = _read_is_section(section_id)
                if not text:
                    lines.append(f"[{i}/{len(all_sections)}] {section_id} — NOT FOUND")
                    failed.append(section_id)
                    continue
                data = _parse_raw(IS_SECTION_PROMPT, text, file_id)
                if data is None:
                    lines.append(
                        f"[{i}/{len(all_sections)}] {section_id} — PARSE FAILED"
                    )
                    failed.append(section_id)
                    continue
                json_path.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                n = len(data.get("nodes", []))
                o = len(data.get("obligations", []))
                lines.append(
                    f"[{i}/{len(all_sections)}] {section_id} — parsed: {n}N {o}O"
                )
                logger.info(
                    f"[{i}/{len(all_sections)}] {section_id} — parsed: {n}N {o}O"
                )

        if not json_path.exists():
            failed.append(section_id)
            continue

        logger.info(f"[{i}/{len(all_sections)}] {section_id} — ingesting…")
        result = _ingest_json(file_id)
        if result.startswith("ERROR"):
            lines.append(
                f"[{i}/{len(all_sections)}] {section_id} — INGEST FAILED: {result}"
            )
            failed.append(section_id)
        else:
            lines.append(f"[{i}/{len(all_sections)}] {section_id} — {result}")
            success += 1

    lines.append(f"\nDone: {success}/{len(all_sections)} IS sections succeeded.")
    if failed:
        lines.append(f"Failed: {failed}")
    return "\n".join(lines)


def batch_parse_recitals(
    recital_range: str = "all", force: bool = False, ingest_only: bool = False
) -> str:
    """Parse and ingest Part-IS recitals."""
    all_recitals = _get_recital_numbers()
    if recital_range.strip().lower() == "all":
        targets = all_recitals
    else:
        targets = [n for n in _parse_range(recital_range) if n in all_recitals]

    if not targets:
        return f"No valid recitals. Available: {all_recitals}"

    logger.info(f"=== RECITALS START: {len(targets)} ===")
    lines = [f"Processing {len(targets)} recitals"]
    success, failed = 0, []

    for i, num in enumerate(targets, 1):
        file_id = f"recital_{num}"
        json_path = OUTPUT_DIR / f"{file_id}.json"

        if not ingest_only:
            if json_path.exists() and not force:
                lines.append(f"[{i}/{len(targets)}] Recital ({num}) — skipped")
                logger.info(f"[{i}/{len(targets)}] Recital ({num}) — skipped")
            else:
                logger.info(f"[{i}/{len(targets)}] Recital ({num}) — parsing…")
                text = _read_recital(num)
                if not text:
                    lines.append(f"[{i}/{len(targets)}] Recital ({num}) — NOT FOUND")
                    failed.append(num)
                    continue
                data = _parse_raw(RECITAL_PROMPT, text, file_id)
                if data is None:
                    lines.append(f"[{i}/{len(targets)}] Recital ({num}) — PARSE FAILED")
                    failed.append(num)
                    continue
                json_path.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                n = len(data.get("nodes", []))
                x = len(data.get("cross_references", []))
                lines.append(
                    f"[{i}/{len(targets)}] Recital ({num}) — parsed: {n}N {x}X"
                )
                logger.info(f"[{i}/{len(targets)}] Recital ({num}) — parsed: {n}N {x}X")

        if not json_path.exists():
            failed.append(num)
            continue

        logger.info(f"[{i}/{len(targets)}] Recital ({num}) — ingesting…")
        result = _ingest_json(file_id)
        if result.startswith("ERROR"):
            lines.append(
                f"[{i}/{len(targets)}] Recital ({num}) — INGEST FAILED: {result}"
            )
            failed.append(num)
        else:
            lines.append(f"[{i}/{len(targets)}] Recital ({num}) — {result}")
            success += 1

    lines.append(f"\nDone: {success}/{len(targets)} recitals succeeded.")
    if failed:
        lines.append(f"Failed: {failed}")
    return "\n".join(lines)


def batch_parse_amendment_annexes(
    annex_range: str = "all", force: bool = False, ingest_only: bool = False
) -> str:
    """Parse and ingest amendment annexes (III-IX)."""
    all_annexes = _get_amendment_annex_ids()
    if annex_range.strip().lower() == "all":
        targets = all_annexes
    else:
        targets = [a for a in annex_range.split(",") if a.strip() in all_annexes]

    if not targets:
        return f"No valid amendment annexes. Available: {all_annexes}"

    logger.info(f"=== AMENDMENT ANNEXES START: {len(targets)} ===")
    lines = [f"Processing {len(targets)} amendment annexes: {', '.join(targets)}"]
    success, failed = 0, []

    for i, aid in enumerate(targets, 1):
        file_id = f"annex_{aid}"
        json_path = OUTPUT_DIR / f"{file_id}.json"

        if not ingest_only:
            if json_path.exists() and not force:
                lines.append(f"[{i}/{len(targets)}] Annex {aid} — skipped")
                logger.info(f"[{i}/{len(targets)}] Annex {aid} — skipped")
            else:
                logger.info(f"[{i}/{len(targets)}] Annex {aid} — parsing…")
                text = _read_amendment_annex(aid)
                if not text:
                    lines.append(f"[{i}/{len(targets)}] Annex {aid} — NOT FOUND")
                    failed.append(aid)
                    continue
                data = _parse_raw(AMENDMENT_ANNEX_PROMPT, text, file_id)
                if data is None:
                    lines.append(f"[{i}/{len(targets)}] Annex {aid} — PARSE FAILED")
                    failed.append(aid)
                    continue
                json_path.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                n = len(data.get("nodes", []))
                o = len(data.get("obligations", []))
                lines.append(f"[{i}/{len(targets)}] Annex {aid} — parsed: {n}N {o}O")
                logger.info(f"[{i}/{len(targets)}] Annex {aid} — parsed: {n}N {o}O")

        if not json_path.exists():
            failed.append(aid)
            continue

        logger.info(f"[{i}/{len(targets)}] Annex {aid} — ingesting…")
        result = _ingest_json(file_id)
        if result.startswith("ERROR"):
            lines.append(f"[{i}/{len(targets)}] Annex {aid} — INGEST FAILED: {result}")
            failed.append(aid)
        else:
            lines.append(f"[{i}/{len(targets)}] Annex {aid} — {result}")
            success += 1

    lines.append(f"\nDone: {success}/{len(targets)} amendment annexes succeeded.")
    if failed:
        lines.append(f"Failed: {failed}")
    return "\n".join(lines)


# ── Range parser ─────────────────────────────────────────────────────


def _parse_range(range_str: str) -> list[int]:
    numbers = []
    for part in range_str.split(","):
        part = part.strip()
        if "-" in part:
            s, e = part.split("-", 1)
            numbers.extend(range(int(s), int(e) + 1))
        else:
            numbers.append(int(part))
    return sorted(set(numbers))


# ── Master function ──────────────────────────────────────────────────


def batch_parse_all(force: bool = False) -> str:
    """Parse and ingest the entire Part-IS regulation into Neo4j.

    Processes in order: articles, IS.AR sections, IS.I.OR sections,
    amendment annexes, recitals.
    """
    results = []

    logger.info("=" * 60)
    logger.info("PART-IS FULL INGESTION STARTED")
    logger.info("=" * 60)

    # 1. Articles 1-16
    logger.info("--- Phase 1: Articles ---")
    r = batch_parse_articles("all", force=force)
    results.append(r)

    # 2. IS.AR sections (Annex I)
    logger.info("--- Phase 2: IS.AR sections (Annex I) ---")
    r = batch_parse_is_sections("I", force=force)
    results.append(r)

    # 3. IS.I.OR sections (Annex II)
    logger.info("--- Phase 3: IS.I.OR sections (Annex II) ---")
    r = batch_parse_is_sections("II", force=force)
    results.append(r)

    # 4. Amendment annexes (III-IX)
    logger.info("--- Phase 4: Amendment annexes ---")
    r = batch_parse_amendment_annexes("all", force=force)
    results.append(r)

    # 5. Recitals
    logger.info("--- Phase 5: Recitals ---")
    r = batch_parse_recitals("all", force=force)
    results.append(r)

    logger.info("=" * 60)
    logger.info("PART-IS FULL INGESTION COMPLETE")
    logger.info("=" * 60)

    return "\n\n".join(results)


# ── Vector embeddings ────────────────────────────────────────────────

import os as _os

OLLAMA_URL = (
    _os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/") + "/api/embed"
)
EMBED_MODEL = "nomic-embed-text"
EMBED_DIM = 768
EMBED_BATCH = 10


def _embed_texts(texts: list[str]) -> list[list[float]]:
    from urllib.request import Request, urlopen

    prefixed = [f"search_document: {t}" for t in texts]
    payload = json.dumps({"model": EMBED_MODEL, "input": prefixed}).encode()
    req = Request(
        OLLAMA_URL,
        method="POST",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = json.loads(urlopen(req, timeout=60).read())
    return resp["embeddings"]


def _chunk_partis_document() -> list[dict]:
    """Split the Part-IS markdown into chunks for embedding."""
    text = _read_md()
    chunks = []

    # Articles
    for m in re.finditer(r"^### (Article \d+ — .+)$", text, re.MULTILINE):
        start = m.start()
        rest = text[m.end() :]
        nxt = re.search(r"^###? ", rest, re.MULTILINE)
        end = m.end() + nxt.start() if nxt else len(text)
        body = text[start:end].strip()
        art_num = re.search(r"Article (\d+)", m.group(1)).group(1)
        chunks.append(
            {
                "chunk_id": f"partis_art_{art_num}",
                "section": "article",
                "title": m.group(1),
                "text": body,
                "regulation": "Part-IS",
            }
        )

    # IS sections (IS.AR.NNN and IS.I.OR.NNN)
    for m in re.finditer(
        r"^### (IS\.\w+(?:\.\w+)*\.\d+[A-Z]?) — (.+)$", text, re.MULTILINE
    ):
        start = m.start()
        rest = text[m.end() :]
        nxt = re.search(r"^### ", rest, re.MULTILINE)
        end = m.end() + nxt.start() if nxt else len(text)
        body = text[start:end].strip()
        if len(body) < 50:
            continue  # skip TOC-only entries
        sec_id = m.group(1)
        chunks.append(
            {
                "chunk_id": f"partis_{sec_id.replace('.', '_')}",
                "section": "is_section",
                "title": f"{sec_id} — {m.group(2)}",
                "text": body,
                "regulation": "Part-IS",
            }
        )

    # Recitals
    for m in re.finditer(r"^### \((\d+)\)\s*$", text, re.MULTILINE):
        start = m.start()
        rest = text[m.end() :]
        nxt = re.search(r"^###? ", rest, re.MULTILINE)
        end = m.end() + nxt.start() if nxt else len(text)
        body = text[start:end].strip()
        chunks.append(
            {
                "chunk_id": f"partis_recital_{m.group(1)}",
                "section": "recital",
                "title": f"Recital ({m.group(1)})",
                "text": body,
                "regulation": "Part-IS",
            }
        )

    # Amendment Annexes
    for m in re.finditer(r"^## (ANNEX [IVXLC]+ — .+)$", text, re.MULTILINE):
        annex_id = re.search(r"ANNEX ([IVXLC]+)", m.group(1)).group(1)
        if annex_id in ("I", "II"):
            continue  # handled via IS sections
        start = m.start()
        rest = text[m.end() :]
        nxt = re.search(r"^## ANNEX ", rest, re.MULTILINE)
        end = m.end() + nxt.start() if nxt else len(text)
        body = text[start:end].strip()
        chunks.append(
            {
                "chunk_id": f"partis_annex_{annex_id}",
                "section": "annex",
                "title": m.group(1),
                "text": body,
                "regulation": "Part-IS",
            }
        )

    return chunks


def vectorize_partis() -> str:
    """Embed Part-IS text chunks and store vectors in Neo4j."""
    chunks = _chunk_partis_document()
    if not chunks:
        return "No chunks found in Part-IS markdown."

    logger.info(f"Vectorizing {len(chunks)} Part-IS chunks")

    embeddings: list[list[float] | None] = []
    for i in range(0, len(chunks), EMBED_BATCH):
        batch = chunks[i : i + EMBED_BATCH]
        texts = [c["text"][:6000] for c in batch]
        try:
            vecs = _embed_texts(texts)
            embeddings.extend(vecs)
            logger.info(f"  Embedded batch {i // EMBED_BATCH + 1}: {len(batch)} chunks")
        except Exception as e:
            logger.error(f"  Embedding failed at batch {i // EMBED_BATCH + 1}: {e}")
            embeddings.extend([None] * len(batch))
        time.sleep(0.2)

    driver = _get_driver()
    stored, skipped = 0, 0

    with driver.session() as session:
        session.run("""
            CREATE VECTOR INDEX partis_chunk_embedding IF NOT EXISTS
            FOR (c:CRAChunk) ON (c.embedding)
            OPTIONS {
                indexConfig: {
                    `vector.dimensions`: 768,
                    `vector.similarity_function`: 'cosine'
                }
            }
        """)
        logger.info("Vector index partis_chunk_embedding ensured")

        for chunk, vec in zip(chunks, embeddings):
            if vec is None:
                skipped += 1
                continue
            session.run(
                """
                MERGE (c:CRAChunk {chunk_id: $chunk_id})
                SET c.section    = $section,
                    c.title      = $title,
                    c.text       = $text,
                    c.regulation = $regulation,
                    c.embedding  = $embedding
            """,
                chunk_id=chunk["chunk_id"],
                section=chunk["section"],
                title=chunk["title"],
                text=chunk["text"],
                regulation=chunk["regulation"],
                embedding=vec,
            )
            stored += 1

        # Link article chunks to Article nodes
        session.run("""
            MATCH (c:CRAChunk) WHERE c.regulation = 'Part-IS' AND c.section = 'article'
            WITH c, 'Art. ' + split(c.chunk_id, '_')[2] AS aid
            MATCH (a:Article {article_id: aid, regulation: 'Part-IS'})
            MERGE (c)-[:EMBEDS]->(a)
        """)

    driver.close()

    lines = [
        f"Vectorized {stored} Part-IS chunks ({skipped} skipped):",
        f"  - Sections: articles, IS sections, recitals, amendment annexes",
        f"  - Model: {EMBED_MODEL} ({EMBED_DIM}-dim)",
        f"  - Neo4j vector index: partis_chunk_embedding (cosine)",
    ]
    return "\n".join(lines)


# ── CLI entry point ──────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    args = sys.argv[1:]

    if not args or args[0] == "all":
        print(batch_parse_all(force="--force" in args))
    elif args[0] == "articles":
        r = args[1] if len(args) > 1 else "all"
        print(batch_parse_articles(r, force="--force" in args))
    elif args[0] == "sections":
        a = args[1] if len(args) > 1 else "all"
        print(batch_parse_is_sections(a, force="--force" in args))
    elif args[0] == "recitals":
        r = args[1] if len(args) > 1 else "all"
        print(batch_parse_recitals(r, force="--force" in args))
    elif args[0] == "annexes":
        r = args[1] if len(args) > 1 else "all"
        print(batch_parse_amendment_annexes(r, force="--force" in args))
    elif args[0] == "vectorize":
        print(vectorize_partis())
    else:
        print(
            "Usage: python partis_batch.py [all|articles|sections|recitals|annexes|vectorize] [range] [--force]"
        )
