"""Batch processing tool for the ADK agent — parse & ingest multiple articles."""

from __future__ import annotations

import atexit
import json
import logging
import logging.handlers
import os
import queue
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai

# ── Paths & config ────────────────────────────────────────────────────
_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(_ENV_PATH)

BASE_DIR = Path(__file__).resolve().parents[2]
CRA_MD_PATH = BASE_DIR / "outputs" / "CRA_requirements_statemachine.md"
OUTPUT_DIR = BASE_DIR / "outputs" / "articles"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

from ..model_config import BATCH_PARSE_MODEL as MODEL, IS_LOCAL as _IS_LOCAL

MIN_INTERVAL = 4.5
_last_call = 0.0

# ── Logging (real-time to server console + log file) ─────────────────
LOG_FILE = BASE_DIR / "outputs" / "batch_progress.log"
logger = logging.getLogger("batch_tool")
logger.setLevel(logging.INFO)
logger.propagate = False

if not logger.handlers:
    _fmt_console = logging.Formatter(
        "%(asctime)s - BATCH - %(message)s", datefmt="%H:%M:%S"
    )
    _fmt_file = logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S")

    _ch = logging.StreamHandler()
    _ch.setFormatter(_fmt_console)

    _log_queue: queue.SimpleQueue = queue.SimpleQueue()
    # All logger calls go into the queue; a background thread drains it.
    # This avoids concurrent-write lock conflicts on macOS/Docker bind mounts.
    logger.addHandler(logging.handlers.QueueHandler(_log_queue))

    try:
        _fh = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8", delay=True)
        _fh.setFormatter(_fmt_file)
        _listener = logging.handlers.QueueListener(
            _log_queue, _ch, _fh, respect_handler_level=True
        )
    except OSError as _exc:
        # If file-handler setup fails (e.g. volume not mounted), fall back to
        # console-only — no deadlock risk.
        _ch.setFormatter(_fmt_console)
        _listener = logging.handlers.QueueListener(
            _log_queue, _ch, respect_handler_level=True
        )
        logging.getLogger(__name__).warning(
            "File logging disabled for %s: %s", LOG_FILE, _exc
        )

    _listener.start()
    atexit.register(_listener.stop)


# ── Gemini client (lazy init to avoid import-time failures) ──────────
_client = None


def _get_client():
    """Legacy Gemini client used by code paths that still need raw genai access.

    Most call sites should use ``_llm_generate`` from ``._llm`` instead, which
    routes through MODEL_TYPE.
    """
    global _client
    if _client is None:
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY not set")
        _client = genai.Client(api_key=api_key)
    return _client


# Unified LLM gateway (LOCAL=Ollama, OFFLOAD=Gemini)
from ._llm import generate as _llm_generate  # noqa: E402


# ── Rate limiting ─────────────────────────────────────────────────────
def _throttle():
    global _last_call
    now = time.time()
    wait = MIN_INTERVAL - (now - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()


def _try_fix_json(text: str) -> dict | list | None:
    """Strip markdown formatting from LLM JSON output and parse it."""
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


# ── CRA reader ───────────────────────────────────────────────────────
def _get_article_numbers() -> list[int]:
    text = CRA_MD_PATH.read_text(encoding="utf-8")
    return sorted(
        int(m) for m in re.findall(r"^### Article (\d+) —", text, re.MULTILINE)
    )


def _read_article(article_number: int) -> str | None:
    text = CRA_MD_PATH.read_text(encoding="utf-8")
    pattern = rf"^### Article {article_number} —"
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        return None
    start = match.start()
    rest = text[match.end() :]
    next_heading = re.search(r"^###? ", rest, re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(text)
    return text[start:end].strip()


# ── Recital reader ───────────────────────────────────────────────────
def _get_recital_numbers() -> list[int]:
    text = CRA_MD_PATH.read_text(encoding="utf-8")
    return sorted(int(m) for m in re.findall(r"^### \((\d+)\)\s*$", text, re.MULTILINE))


def _read_recital(recital_number: int) -> str | None:
    text = CRA_MD_PATH.read_text(encoding="utf-8")
    pattern = rf"^### \({recital_number}\)\s*$"
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        return None
    start = match.start()
    rest = text[match.end() :]
    next_heading = re.search(r"^###? ", rest, re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(text)
    return text[start:end].strip()


# ── Annex reader ─────────────────────────────────────────────────────
_ANNEX_IDS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]


def _get_annex_ids() -> list[str]:
    text = CRA_MD_PATH.read_text(encoding="utf-8")
    return [m for m in re.findall(r"^## ANNEX ([IVXLC]+) —", text, re.MULTILINE)]


def _read_annex(annex_id: str) -> str | None:
    text = CRA_MD_PATH.read_text(encoding="utf-8")
    pattern = rf"^## ANNEX {re.escape(annex_id)} —"
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        return None
    start = match.start()
    rest = text[match.end() :]
    next_annex = re.search(r"^## ANNEX ", rest, re.MULTILINE)
    end = match.end() + next_annex.start() if next_annex else len(text)
    return text[start:end].strip()


# ── Parser prompt ────────────────────────────────────────────────────
PARSER_PROMPT = """You are a Legal Knowledge-Graph Parser for the EU Cyber Resilience Act (CRA).

Given the article text below, extract ALL entities, relationships, obligations, and cross-references into strict JSON.

OUTPUT RULES:
- Return ONLY valid JSON. No markdown fences, no commentary, no explanation.
- The JSON must follow the exact schema below.

JSON SCHEMA:
{
  "metadata": {
    "regulation": "Regulation (EU) 2024/2847",
    "regulation_short": "CRA",
    "article_id": "Art. <N>",
    "article_title": "<title>",
    "chapter": "<chapter heading or null>",
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
      "target": "<Art. N or Annex X>",
      "type": "<SPECIFIED_BY|SPECIFIES_PROCESS_FOR|REFERENCES|AMENDS>",
      "context": "<reason for cross-reference>"
    }
  ]
}

RULES:
- Node IDs: n_<snake_case>, consistent across articles (e.g. n_manufacturer, n_enisa)
- Every paragraph produces at least one relationship or obligation
- Relationship properties MUST include paragraph_ref
- Include cra_definition_id in node properties when referencing defined terms

ARTICLE TEXT:
"""

# ── Recital parser prompt ────────────────────────────────────────────
RECITAL_PARSER_PROMPT = """You are a Legal Knowledge-Graph Parser for the EU Cyber Resilience Act (CRA).

Given the recital text below, extract ALL entities, relationships, and cross-references into strict JSON.
Recitals are explanatory/motivational paragraphs — they do NOT create legal obligations but provide
interpretive context, rationale, and cross-references to articles and other EU legislation.

OUTPUT RULES:
- Return ONLY valid JSON. No markdown fences, no commentary, no explanation.
- The JSON must follow the exact schema below.

JSON SCHEMA:
{
  "metadata": {
    "regulation": "Regulation (EU) 2024/2847",
    "regulation_short": "CRA",
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
- Node IDs: n_<snake_case>, consistent with article nodes (e.g. n_manufacturer, n_enisa)
- Recitals have NO legal obligations — leave the obligations array empty
- Extract all cross-references to CRA articles, annexes, and external EU legislation
- Capture the key concepts and actors mentioned in the recital

RECITAL TEXT:
"""

# ── Annex parser prompt ──────────────────────────────────────────────
ANNEX_PARSER_PROMPT = """You are a Legal Knowledge-Graph Parser for the EU Cyber Resilience Act (CRA).

Given the annex text below, extract ALL entities, relationships, requirements, and cross-references into strict JSON.
Annexes contain technical requirements, product lists, conformity assessment procedures, or documentation templates.

OUTPUT RULES:
- Return ONLY valid JSON. No markdown fences, no commentary, no explanation.
- The JSON must follow the exact schema below.

JSON SCHEMA:
{
  "metadata": {
    "regulation": "Regulation (EU) 2024/2847",
    "regulation_short": "CRA",
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
      "target": "<Art. N or Annex X>",
      "type": "<SPECIFIED_BY|SPECIFIES_PROCESS_FOR|REFERENCES|AMENDS>",
      "context": "<reason for cross-reference>"
    }
  ]
}

RULES:
- Node IDs: n_<snake_case>, consistent with article nodes (e.g. n_manufacturer, n_enisa)
- Extract all requirements, product categories, or procedures listed in the annex
- Relationship properties MUST include annex_ref
- Include cra_definition_id in node properties when referencing defined terms
- For product lists (Annex III, IV), create a node for each product category

ANNEX TEXT:
"""


# ── Neo4j ingestion ──────────────────────────────────────────────────
def _ingest_json_to_neo4j(article_id: str) -> str:
    from .neo4j_tools import ingest_json_to_neo4j

    return ingest_json_to_neo4j(article_id)


def _run_sync_in_thread(fn, *args, **kwargs):
    """Run a blocking synchronous function in a thread-pool executor.

    ADK runs tool calls via asyncio.gather() on the event loop. Any blocking
    I/O (Neo4j driver, time.sleep, file writes) inside a tool will stall the
    loop and trigger OSError: [Errno 35] Resource deadlock avoided on macOS.
    Offloading to a thread executor keeps the event loop free.
    """
    import asyncio
    import functools

    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, functools.partial(fn, *args, **kwargs))


def _parse_one(article_number: int) -> dict | None:
    article_text = _read_article(article_number)
    if not article_text:
        return None
    raw = _retry_call(PARSER_PROMPT + article_text)
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(
            f"Art. {article_number} — raw JSON invalid, attempting auto-repair…"
        )
        repaired = _try_fix_json(raw)
        if repaired is not None:
            logger.info(f"Art. {article_number} — auto-repair succeeded")
            return repaired
        (OUTPUT_DIR / f"art_{article_number}_raw.txt").write_text(raw, encoding="utf-8")
        return None


def _parse_one_recital(recital_number: int) -> dict | None:
    recital_text = _read_recital(recital_number)
    if not recital_text:
        return None
    raw = _retry_call(RECITAL_PARSER_PROMPT + recital_text)
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(
            f"Recital ({recital_number}) — raw JSON invalid, attempting auto-repair…"
        )
        repaired = _try_fix_json(raw)
        if repaired is not None:
            logger.info(f"Recital ({recital_number}) — auto-repair succeeded")
            return repaired
        (OUTPUT_DIR / f"recital_{recital_number}_raw.txt").write_text(
            raw, encoding="utf-8"
        )
        return None


def _parse_one_annex(annex_id: str) -> dict | None:
    annex_text = _read_annex(annex_id)
    if not annex_text:
        return None
    raw = _retry_call(ANNEX_PARSER_PROMPT + annex_text)
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(f"Annex {annex_id} — raw JSON invalid, attempting auto-repair…")
        repaired = _try_fix_json(raw)
        if repaired is not None:
            logger.info(f"Annex {annex_id} — auto-repair succeeded")
            return repaired
        (OUTPUT_DIR / f"annex_{annex_id}_raw.txt").write_text(raw, encoding="utf-8")
        return None


# ── Helper to parse range strings ────────────────────────────────────
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


# =====================================================================
# IMPLEMENTATION (sync) — wrapped by async public tools below
# =====================================================================


def _batch_parse_and_ingest_impl(
    article_range: str, force: bool = False, ingest_only: bool = False
) -> str:
    """Parse and ingest a range of CRA articles into the Neo4j knowledge graph.

    This tool processes multiple articles in a single call — use it when the
    user asks to process more than one article at once (e.g. "ingest articles
    1 through 20" or "process all articles").

    Args:
        article_range: Which articles to process.
            Examples: "all", "5", "3-10", "1,3,5-10".
            Use "all" to process every article in the CRA (1-71).
        force: If True, re-parse articles even if a JSON file already exists.
            Default is False (skip already-parsed articles).
        ingest_only: If True, skip the Gemini parsing step and only ingest
            existing JSON files into Neo4j. Default is False.

    Returns:
        A progress report showing which articles succeeded and failed.
    """
    all_articles = _get_article_numbers()

    if article_range.strip().lower() == "all":
        targets = all_articles
    else:
        targets = [n for n in _parse_range(article_range) if n in all_articles]

    if not targets:
        return f"No valid articles in range '{article_range}'. Available: {all_articles[0]}-{all_articles[-1]}"

    logger.info(
        f"=== BATCH START: {len(targets)} articles ({targets[0]}-{targets[-1]}) ==="
    )
    lines = [f"Processing {len(targets)} articles: {targets[0]}-{targets[-1]}"]
    success = 0
    failed = []

    for i, num in enumerate(targets, 1):
        art_id = f"art_{num}"
        json_path = OUTPUT_DIR / f"{art_id}.json"

        # ── Parse ─────────────────────────────────────────────
        if not ingest_only:
            if json_path.exists() and not force:
                msg = f"[{i}/{len(targets)}] Art. {num} — skipped (already parsed)"
                logger.info(msg)
                lines.append(msg)
            else:
                logger.info(f"[{i}/{len(targets)}] Art. {num} — parsing via Gemini…")
                data = _parse_one(num)
                if data is None:
                    msg = f"[{i}/{len(targets)}] Art. {num} — PARSE FAILED"
                    logger.warning(msg)
                    lines.append(msg)
                    failed.append(num)
                    continue
                json_path.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                n = len(data.get("nodes", []))
                r = len(data.get("relationships", []))
                o = len(data.get("obligations", []))
                x = len(data.get("cross_references", []))
                msg = f"[{i}/{len(targets)}] Art. {num} — parsed: {n}N {r}R {o}O {x}X"
                logger.info(msg)
                lines.append(msg)

        # ── Ingest ────────────────────────────────────────────
        if not json_path.exists():
            msg = f"[{i}/{len(targets)}] Art. {num} — no JSON, skipping ingest"
            logger.warning(msg)
            lines.append(msg)
            failed.append(num)
            continue

        logger.info(f"[{i}/{len(targets)}] Art. {num} — ingesting into Neo4j…")
        result = _ingest_json_to_neo4j(art_id)
        if result.startswith("ERROR"):
            msg = f"[{i}/{len(targets)}] Art. {num} — INGEST FAILED: {result}"
            logger.error(msg)
            lines.append(msg)
            failed.append(num)
        else:
            msg = f"[{i}/{len(targets)}] Art. {num} — ingested: {result}"
            logger.info(msg)
            lines.append(msg)
            success += 1

    logger.info(f"=== BATCH DONE: {success}/{len(targets)} succeeded ===")
    lines.append(f"\nDone: {success}/{len(targets)} succeeded.")
    if failed:
        lines.append(f"Failed: {failed}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────


def _batch_parse_recitals_impl(
    recital_range: str, force: bool = False, ingest_only: bool = False
) -> str:
    """Parse and ingest a range of CRA recitals into the Neo4j knowledge graph.

    Recitals provide interpretive context and rationale for the CRA.
    They do not create obligations but contain cross-references and key concepts.

    Args:
        recital_range: Which recitals to process.
            Examples: "all", "5", "3-10", "1,3,5-10".
            Use "all" to process all 130 recitals.
        force: If True, re-parse even if a JSON file already exists.
        ingest_only: If True, skip parsing and only ingest existing JSONs.

    Returns:
        A progress report showing which recitals succeeded and failed.
    """
    all_recitals = _get_recital_numbers()

    if recital_range.strip().lower() == "all":
        targets = all_recitals
    else:
        targets = [n for n in _parse_range(recital_range) if n in all_recitals]

    if not targets:
        return f"No valid recitals in range '{recital_range}'. Available: 1-{all_recitals[-1] if all_recitals else '?'}"

    logger.info(f"=== BATCH RECITALS START: {len(targets)} recitals ===")
    lines = [f"Processing {len(targets)} recitals"]
    success = 0
    failed = []

    for i, num in enumerate(targets, 1):
        rec_id = f"recital_{num}"
        json_path = OUTPUT_DIR / f"{rec_id}.json"

        # ── Parse ─────────────────────────────────────────────
        if not ingest_only:
            if json_path.exists() and not force:
                msg = f"[{i}/{len(targets)}] Recital ({num}) — skipped (already parsed)"
                logger.info(msg)
                lines.append(msg)
            else:
                logger.info(
                    f"[{i}/{len(targets)}] Recital ({num}) — parsing via Gemini…"
                )
                data = _parse_one_recital(num)
                if data is None:
                    msg = f"[{i}/{len(targets)}] Recital ({num}) — PARSE FAILED"
                    logger.warning(msg)
                    lines.append(msg)
                    failed.append(num)
                    continue
                json_path.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                n = len(data.get("nodes", []))
                r = len(data.get("relationships", []))
                x = len(data.get("cross_references", []))
                msg = f"[{i}/{len(targets)}] Recital ({num}) — parsed: {n}N {r}R {x}X"
                logger.info(msg)
                lines.append(msg)

        # ── Ingest ────────────────────────────────────────────
        if not json_path.exists():
            msg = f"[{i}/{len(targets)}] Recital ({num}) — no JSON, skipping ingest"
            logger.warning(msg)
            lines.append(msg)
            failed.append(num)
            continue

        logger.info(f"[{i}/{len(targets)}] Recital ({num}) — ingesting into Neo4j…")
        result = _ingest_json_to_neo4j(rec_id)
        if result.startswith("ERROR"):
            msg = f"[{i}/{len(targets)}] Recital ({num}) — INGEST FAILED: {result}"
            logger.error(msg)
            lines.append(msg)
            failed.append(num)
        else:
            msg = f"[{i}/{len(targets)}] Recital ({num}) — ingested: {result}"
            logger.info(msg)
            lines.append(msg)
            success += 1

    logger.info(f"=== BATCH RECITALS DONE: {success}/{len(targets)} succeeded ===")
    lines.append(f"\nDone: {success}/{len(targets)} recitals succeeded.")
    if failed:
        lines.append(f"Failed: {failed}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────


def _batch_parse_annexes_impl(
    annex_range: str = "all", force: bool = False, ingest_only: bool = False
) -> str:
    """Parse and ingest CRA annexes into the Neo4j knowledge graph.

    Annexes contain essential cybersecurity requirements, product lists,
    conformity assessment procedures, and documentation templates.

    Args:
        annex_range: Which annexes to process.
            Examples: "all", "I", "I,III,V", "I-IV".
            Use "all" to process all 8 annexes (I through VIII).
            Accepts Roman numerals (I-VIII) or numbers (1-8).
        force: If True, re-parse even if a JSON file already exists.
        ingest_only: If True, skip parsing and only ingest existing JSONs.

    Returns:
        A progress report showing which annexes succeeded and failed.
    """
    all_annexes = _get_annex_ids()
    roman_to_int = {
        "I": 1,
        "II": 2,
        "III": 3,
        "IV": 4,
        "V": 5,
        "VI": 6,
        "VII": 7,
        "VIII": 8,
    }
    int_to_roman = {v: k for k, v in roman_to_int.items()}

    if annex_range.strip().lower() == "all":
        targets = all_annexes
    else:
        # Support both Roman and numeric input
        targets = []
        for part in annex_range.split(","):
            part = part.strip()
            if "-" in part:
                s, e = part.split("-", 1)
                s_int = roman_to_int.get(
                    s.strip(), int(s.strip()) if s.strip().isdigit() else 0
                )
                e_int = roman_to_int.get(
                    e.strip(), int(e.strip()) if e.strip().isdigit() else 0
                )
                for n in range(s_int, e_int + 1):
                    r = int_to_roman.get(n)
                    if r and r in all_annexes:
                        targets.append(r)
            else:
                # Direct Roman numeral or int
                if part in all_annexes:
                    targets.append(part)
                elif part.isdigit():
                    r = int_to_roman.get(int(part))
                    if r and r in all_annexes:
                        targets.append(r)

    if not targets:
        return f"No valid annexes in range '{annex_range}'. Available: {all_annexes}"

    logger.info(
        f"=== BATCH ANNEXES START: {len(targets)} annexes ({', '.join(targets)}) ==="
    )
    lines = [f"Processing {len(targets)} annexes: {', '.join(targets)}"]
    success = 0
    failed = []

    for i, aid in enumerate(targets, 1):
        annex_file_id = f"annex_{aid}"
        json_path = OUTPUT_DIR / f"{annex_file_id}.json"

        # ── Parse ─────────────────────────────────────────────
        if not ingest_only:
            if json_path.exists() and not force:
                msg = f"[{i}/{len(targets)}] Annex {aid} — skipped (already parsed)"
                logger.info(msg)
                lines.append(msg)
            else:
                logger.info(f"[{i}/{len(targets)}] Annex {aid} — parsing via Gemini…")
                data = _parse_one_annex(aid)
                if data is None:
                    msg = f"[{i}/{len(targets)}] Annex {aid} — PARSE FAILED"
                    logger.warning(msg)
                    lines.append(msg)
                    failed.append(aid)
                    continue
                json_path.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                n = len(data.get("nodes", []))
                r = len(data.get("relationships", []))
                o = len(data.get("obligations", []))
                x = len(data.get("cross_references", []))
                msg = f"[{i}/{len(targets)}] Annex {aid} — parsed: {n}N {r}R {o}O {x}X"
                logger.info(msg)
                lines.append(msg)

        # ── Ingest ────────────────────────────────────────────
        if not json_path.exists():
            msg = f"[{i}/{len(targets)}] Annex {aid} — no JSON, skipping ingest"
            logger.warning(msg)
            lines.append(msg)
            failed.append(aid)
            continue

        logger.info(f"[{i}/{len(targets)}] Annex {aid} — ingesting into Neo4j…")
        result = _ingest_json_to_neo4j(annex_file_id)
        if result.startswith("ERROR"):
            msg = f"[{i}/{len(targets)}] Annex {aid} — INGEST FAILED: {result}"
            logger.error(msg)
            lines.append(msg)
            failed.append(aid)
        else:
            msg = f"[{i}/{len(targets)}] Annex {aid} — ingested: {result}"
            logger.info(msg)
            lines.append(msg)
            success += 1

    logger.info(f"=== BATCH ANNEXES DONE: {success}/{len(targets)} succeeded ===")
    lines.append(f"\nDone: {success}/{len(targets)} annexes succeeded.")
    if failed:
        lines.append(f"Failed: {failed}")
    return "\n".join(lines)


# =====================================================================
# PUBLIC ASYNC TOOLS — called by the ADK agent
#
# ADK runs tool calls via asyncio.gather(). The synchronous batch
# implementations block on Neo4j I/O and Gemini HTTP calls, which
# stalls the event loop and triggers OSError: [Errno 35] on macOS.
# asyncio.to_thread() offloads each blocking call to a thread-pool
# worker, keeping the event loop free.
# =====================================================================

import asyncio as _asyncio


async def batch_parse_and_ingest(
    article_range: str, force: bool = False, ingest_only: bool = False
) -> str:
    """Parse and ingest a range of CRA articles into the Neo4j knowledge graph.

    Args:
        article_range: Which articles to process.
            Examples: "all", "5", "3-10", "1,3,5-10".
            Use "all" to process every article in the CRA (1-71).
        force: If True, re-parse articles even if a JSON file already exists.
        ingest_only: If True, skip parsing and only ingest existing JSONs.

    Returns:
        A progress report showing which articles succeeded and failed.
    """
    return await _asyncio.to_thread(
        _batch_parse_and_ingest_impl, article_range, force, ingest_only
    )


async def batch_parse_recitals(
    recital_range: str, force: bool = False, ingest_only: bool = False
) -> str:
    """Parse and ingest a range of CRA recitals into the Neo4j knowledge graph.

    Args:
        recital_range: Which recitals to process.
            Examples: "all", "5", "3-10", "1,3,5-10".
            Use "all" to process all 130 recitals.
        force: If True, re-parse even if a JSON file already exists.
        ingest_only: If True, skip parsing and only ingest existing JSONs.

    Returns:
        A progress report showing which recitals succeeded and failed.
    """
    return await _asyncio.to_thread(
        _batch_parse_recitals_impl, recital_range, force, ingest_only
    )


async def batch_parse_annexes(
    annex_range: str, force: bool = False, ingest_only: bool = False
) -> str:
    """Parse and ingest a range of CRA annexes into the Neo4j knowledge graph.

    Args:
        annex_range: Which annexes to process.
            Examples: "all", "I", "I-III", "I,III,V".
            Use "all" to process all 8 annexes (I-VIII).
        force: If True, re-parse even if a JSON file already exists.
        ingest_only: If True, skip parsing and only ingest existing JSONs.

    Returns:
        A progress report showing which annexes succeeded and failed.
    """
    return await _asyncio.to_thread(
        _batch_parse_annexes_impl, annex_range, force, ingest_only
    )
