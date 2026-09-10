"""Vector indexing and semantic search for the CRA knowledge graph.

Uses Ollama nomic-embed-text (768-dim) for local embeddings and
Neo4j 5.x vector indexes for similarity search.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from urllib.request import Request, urlopen

log = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────
OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_URL = f"{OLLAMA_BASE}/api/embed"
EMBED_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
EMBED_DIM = 768
OLLAMA_TIMEOUT = 60
BATCH_SIZE = 10  # texts per Ollama call

CRA_MD_PATH = (
    Path(__file__).resolve().parents[2] / "outputs" / "CRA_requirements_statemachine.md"
)

# ── Helpers ────────────────────────────────────────────────────────────


def _get_driver():
    """Lazy Neo4j driver import to avoid circular deps."""
    import os
    from neo4j import GraphDatabase

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    pwd = os.getenv("NEO4J_PASSWORD", "password123")
    return GraphDatabase.driver(uri, auth=(user, pwd))


def _embed_texts(texts: list[str]) -> list[list[float]]:
    """Call Ollama to embed a batch of texts. Returns list of 768-dim vectors."""
    # nomic-embed-text performs best with a search_document: prefix for docs
    prefixed = [f"search_document: {t}" for t in texts]
    payload = json.dumps({"model": EMBED_MODEL, "input": prefixed}).encode()
    req = Request(
        OLLAMA_URL,
        method="POST",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = json.loads(urlopen(req, timeout=OLLAMA_TIMEOUT).read())
    return resp["embeddings"]


def _embed_query(text: str) -> list[float]:
    """Embed a single query string (uses search_query prefix for nomic)."""
    payload = json.dumps(
        {
            "model": EMBED_MODEL,
            "input": [f"search_query: {text}"],
        }
    ).encode()
    req = Request(
        OLLAMA_URL,
        method="POST",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = json.loads(urlopen(req, timeout=OLLAMA_TIMEOUT).read())
    return resp["embeddings"][0]


# ── CRA text chunking ─────────────────────────────────────────────────


def _chunk_cra_document() -> list[dict]:
    """Split the CRA markdown into chunks: one per article, recital, and annex.

    Returns list of dicts: {chunk_id, section, title, text}
    """
    text = CRA_MD_PATH.read_text(encoding="utf-8")
    chunks = []

    # ── Articles: ### Article N — Title
    for m in re.finditer(r"^### (Article \d+ — .+)$", text, re.MULTILINE):
        start = m.start()
        rest = text[m.end() :]
        nxt = re.search(r"^###? ", rest, re.MULTILINE)
        end = m.end() + nxt.start() if nxt else len(text)
        body = text[start:end].strip()
        art_num = re.search(r"Article (\d+)", m.group(1)).group(1)
        chunks.append(
            {
                "chunk_id": f"art_{art_num}",
                "section": "article",
                "title": m.group(1),
                "text": body,
            }
        )

    # ── Recitals: ### (N)
    for m in re.finditer(r"^### \((\d+)\)\s*$", text, re.MULTILINE):
        start = m.start()
        rest = text[m.end() :]
        nxt = re.search(r"^###? ", rest, re.MULTILINE)
        end = m.end() + nxt.start() if nxt else len(text)
        body = text[start:end].strip()
        chunks.append(
            {
                "chunk_id": f"recital_{m.group(1)}",
                "section": "recital",
                "title": f"Recital ({m.group(1)})",
                "text": body,
            }
        )

    # ── Annexes: ## ANNEX X — Title
    for m in re.finditer(r"^## (ANNEX [IVXLC]+ — .+)$", text, re.MULTILINE):
        start = m.start()
        rest = text[m.end() :]
        nxt = re.search(r"^## ANNEX ", rest, re.MULTILINE)
        end = m.end() + nxt.start() if nxt else len(text)
        body = text[start:end].strip()
        annex_id = re.search(r"ANNEX ([IVXLC]+)", m.group(1)).group(1)
        chunks.append(
            {
                "chunk_id": f"annex_{annex_id}",
                "section": "annex",
                "title": m.group(1),
                "text": body,
            }
        )

    return chunks


# =====================================================================
# PUBLIC TOOLS — called by the ADK agent
# =====================================================================


def vectorize_graph(sections: str = "all") -> str:
    """Embed CRA text chunks and store vectors on Neo4j nodes for semantic search.

    This creates a :CRAChunk node for each article, recital, and annex with
    the full text and a 768-dim embedding vector, plus a Neo4j vector index.

    Args:
        sections: Which sections to vectorize.
            "all" (default), "articles", "recitals", "annexes",
            or comma-separated like "articles,annexes".

    Returns:
        A progress report showing how many chunks were embedded and indexed.
    """
    # ── 1. Chunk the document ─────────────────────────────────────────
    all_chunks = _chunk_cra_document()
    log.info(f"Total chunks available: {len(all_chunks)}")

    wanted = {s.strip().lower() for s in sections.split(",")}
    if "all" in wanted:
        wanted = {"article", "recital", "annex"}
    # Map plural → singular
    mapping = {"articles": "article", "recitals": "recital", "annexes": "annex"}
    wanted = {mapping.get(w, w) for w in wanted}

    chunks = [c for c in all_chunks if c["section"] in wanted]
    if not chunks:
        return f"No chunks matched sections='{sections}'. Use 'all', 'articles', 'recitals', or 'annexes'."

    log.info(f"Vectorizing {len(chunks)} chunks (sections: {wanted})")

    # ── 2. Embed in batches ───────────────────────────────────────────
    embeddings: list[list[float]] = []
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        # Truncate very long texts for embedding (nomic context = 8192 tokens)
        texts = [c["text"][:6000] for c in batch]
        try:
            vecs = _embed_texts(texts)
            embeddings.extend(vecs)
            log.info(f"  Embedded batch {i // BATCH_SIZE + 1}: {len(batch)} chunks")
        except Exception as e:
            log.error(f"  Embedding failed at batch {i // BATCH_SIZE + 1}: {e}")
            # Fill with None so indexing stays aligned
            embeddings.extend([None] * len(batch))
        time.sleep(0.2)  # gentle on Ollama

    # ── 3. Store in Neo4j ─────────────────────────────────────────────
    driver = _get_driver()
    stored = 0
    skipped = 0

    with driver.session() as session:
        # Create vector index if needed
        session.run("""
            CREATE VECTOR INDEX cra_chunk_embedding IF NOT EXISTS
            FOR (c:CRAChunk) ON (c.embedding)
            OPTIONS {
                indexConfig: {
                    `vector.dimensions`: 768,
                    `vector.similarity_function`: 'cosine'
                }
            }
        """)
        log.info("Vector index cra_chunk_embedding ensured")

        for chunk, vec in zip(chunks, embeddings):
            if vec is None:
                skipped += 1
                continue
            session.run(
                """
                MERGE (c:CRAChunk {chunk_id: $chunk_id})
                SET c.section   = $section,
                    c.title     = $title,
                    c.text      = $text,
                    c.embedding = $embedding
                """,
                chunk_id=chunk["chunk_id"],
                section=chunk["section"],
                title=chunk["title"],
                text=chunk["text"],
                embedding=vec,
            )
            stored += 1

        # ── 4. Link chunks to existing graph nodes ────────────────────
        # Link article chunks to Article nodes
        session.run("""
            MATCH (c:CRAChunk) WHERE c.section = 'article'
            WITH c, 'Art. ' + split(c.chunk_id, '_')[1] AS aid
            MATCH (a:Article {article_id: aid})
            MERGE (c)-[:EMBEDS]->(a)
        """)
        # Link recital chunks to Recital nodes
        session.run("""
            MATCH (c:CRAChunk) WHERE c.section = 'recital'
            WITH c, 'Recital (' + split(c.chunk_id, '_')[1] + ')' AS rid
            MATCH (r:Recital {recital_id: rid})
            MERGE (c)-[:EMBEDS]->(r)
        """)
        # Link annex chunks to Annex nodes
        session.run("""
            MATCH (c:CRAChunk) WHERE c.section = 'annex'
            WITH c, 'Annex ' + split(c.chunk_id, '_')[1] AS aid
            MATCH (a:Annex {annex_id: aid})
            MERGE (c)-[:EMBEDS]->(a)
        """)
        log.info("Linked CRAChunk nodes to Article/Recital/Annex nodes")

    driver.close()

    lines = [
        f"Vectorized {stored} CRA chunks ({skipped} skipped due to errors):",
        f"  - Sections: {', '.join(sorted(wanted))}",
        f"  - Embedding model: {EMBED_MODEL} ({EMBED_DIM}-dim)",
        f"  - Neo4j vector index: cra_chunk_embedding (cosine similarity)",
        f"  - Chunks linked to existing Article/Recital/Annex nodes via :EMBEDS",
        "",
        "You can now use `semantic_search(query)` to find relevant CRA sections.",
    ]
    return "\n".join(lines)


def semantic_search(query: str, top_k: int = 5) -> dict:
    """Search the CRA knowledge graph using semantic similarity.

    Finds the most relevant CRA articles, recitals, and annexes for a
    natural language query using vector embeddings.

    Args:
        query: The natural language question or topic to search for.
            Examples: "supply chain security", "vulnerability disclosure",
            "obligations for open source developers"
        top_k: Number of results to return (default 5, max 20).

    Returns:
        A dict with 'status' and 'report' keys. You MUST relay the 'report'
        field verbatim to the user.
    """
    top_k = min(max(1, top_k), 20)

    # ── 1. Embed the query ────────────────────────────────────────────
    try:
        query_vec = _embed_query(query)
    except Exception as e:
        return {
            "status": "error",
            "report": f"Failed to embed query — {e}. Is Ollama running?",
        }

    # ── 2. Vector search in Neo4j ─────────────────────────────────────
    driver = _get_driver()
    try:
        with driver.session() as session:
            # Check if vector index exists
            indexes = session.run(
                "SHOW INDEXES WHERE name = 'cra_chunk_embedding'"
            ).data()
            if not indexes:
                return {
                    "status": "error",
                    "report": "No vector index found. Run vectorize_graph() first.",
                }

            results = session.run(
                """
                CALL db.index.vector.queryNodes('cra_chunk_embedding', $k, $vec)
                YIELD node, score
                RETURN node.chunk_id AS chunk_id,
                       node.section AS section,
                       node.title AS title,
                       node.text AS text,
                       score
                ORDER BY score DESC
                """,
                k=top_k,
                vec=query_vec,
            ).data()
    finally:
        driver.close()

    if not results:
        return {
            "status": "error",
            "report": "No results found. The vector index may be empty.",
        }

    # ── 3. Build compact results ──────────────────────────────────────
    items = []
    for i, r in enumerate(results, 1):
        score_pct = r["score"] * 100
        preview = r["text"][:250].replace("\n", " ").strip()
        if len(r["text"]) > 250:
            preview += "..."
        items.append(
            {
                "rank": i,
                "section": r["section"],
                "title": r["title"],
                "score": f"{score_pct:.1f}%",
                "excerpt": preview,
            }
        )

    report_lines = [f'Found {len(items)} results for "{query}":\n']
    for it in items:
        report_lines.append(
            f'{it["rank"]}. [{it["section"].upper()}] {it["title"]} — {it["score"]}\n'
            f'   {it["excerpt"]}\n'
        )

    return {
        "status": "ok",
        "result_count": len(items),
        "report": "\n".join(report_lines),
        "results": items,
    }


# =====================================================================
# OBLIGATION-LEVEL VECTOR TOOLS
# =====================================================================


def vectorize_obligations() -> str:
    """Embed all Obligation nodes and create a vector index for semantic obligation search.

    Reads every :Obligation node from Neo4j, builds a text from its
    ``action_full`` (or ``action``) field plus associated actors, embeds it
    with nomic-embed-text, and stores the 768-dim vector on the node.
    Creates the ``cra_obligation_embedding`` cosine-similarity vector index.

    Call this once after ingesting articles (or after a wipe + re-ingest).
    Re-running is safe and idempotent.

    Returns:
        A progress report.
    """
    driver = _get_driver()
    try:
        with driver.session() as session:
            rows = session.run("""
                MATCH (o:Obligation)
                RETURN o.id AS id,
                       o.action AS action,
                       o.action_full AS action_full,
                       o.actors AS actors
                """).data()
    finally:
        driver.close()

    if not rows:
        return (
            "No Obligation nodes found in the graph. "
            "Run batch_parse_and_ingest(article_range='all', force=True) first."
        )

    # Build embedding text for each obligation
    texts: list[str] = []
    for r in rows:
        body = r.get("action_full") or r.get("action") or r["id"]
        actors = r.get("actors") or []
        if isinstance(actors, list) and actors:
            body += f" Actors: {', '.join(actors)}"
        elif isinstance(actors, str) and actors:
            body += f" Actors: {actors}"
        texts.append(body[:4000])

    # Embed in batches
    embeddings: list[list[float] | None] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        try:
            vecs = _embed_texts(batch)
            embeddings.extend(vecs)
            log.info(
                "Embedded obligation batch %d (%d items)",
                i // BATCH_SIZE + 1,
                len(batch),
            )
        except Exception as e:
            log.error(
                "Obligation embedding batch %d failed: %s", i // BATCH_SIZE + 1, e
            )
            embeddings.extend([None] * len(batch))
        time.sleep(0.2)

    # Store vectors + ensure index
    driver = _get_driver()
    stored = skipped = 0
    with driver.session() as session:
        session.run("""
            CREATE VECTOR INDEX cra_obligation_embedding IF NOT EXISTS
            FOR (o:Obligation) ON (o.embedding)
            OPTIONS {
                indexConfig: {
                    `vector.dimensions`: 768,
                    `vector.similarity_function`: 'cosine'
                }
            }
            """)
        for row, vec in zip(rows, embeddings):
            if vec is None:
                skipped += 1
                continue
            session.run(
                "MATCH (o:Obligation {id: $id}) SET o.embedding = $embedding",
                id=row["id"],
                embedding=vec,
            )
            stored += 1
    driver.close()

    return (
        f"Embedded {stored} obligations ({skipped} skipped).\n"
        f"  Model: {EMBED_MODEL} ({EMBED_DIM}-dim)\n"
        f"  Index: cra_obligation_embedding (cosine similarity)\n"
        f"Use search_obligations(query) to find obligations by meaning."
    )


def search_obligations(
    query: str,
    top_k: int = 10,
    mode: str = "hybrid",
) -> dict:
    """Search CRA obligations using semantic similarity, keyword matching, or both.

    Hybrid mode (default) runs a keyword CONTAINS pass and a vector
    similarity pass in parallel, then merges and re-ranks results so that
    obligations matching on both signals rise to the top.

    Args:
        query: Natural-language topic, e.g. "vulnerability disclosure",
               "SBOM requirements", "CE marking", "supply chain security".
        top_k: Maximum results to return (default 10, max 30).
        mode:  "hybrid"   — keyword + semantic combined (recommended).
               "semantic" — vector similarity only (needs vectorize_obligations).
               "keyword"  — CONTAINS text match only (fast, no Ollama needed).

    Returns:
        A dict with 'status', 'report', and 'results' list. You MUST relay
        the 'report' text verbatim to the user.
    """
    top_k = min(max(1, top_k), 30)
    mode = mode.lower().strip()
    if mode not in ("hybrid", "semantic", "keyword"):
        mode = "hybrid"

    driver = _get_driver()
    try:
        driver.verify_connectivity()
    except Exception as e:
        return {"status": "error", "report": f"Cannot connect to Neo4j: {e}"}

    # Shared storage: id → {row data}, id → semantic score
    row_map: dict[str, dict] = {}
    sem_scores: dict[str, float] = {}
    kw_ids: set[str] = set()

    with driver.session() as session:

        # ── Keyword pass ───────────────────────────────────────────────────
        if mode in ("hybrid", "keyword"):
            terms = [
                t.strip().lower()
                for t in re.split(r"\s+", query.strip())
                if len(t.strip()) > 2
            ]
            if terms:
                rows = session.run(
                    """
                    MATCH (o:Obligation)
                    WHERE any(term IN $terms
                              WHERE toLower(coalesce(o.action, '')) CONTAINS term
                                 OR toLower(coalesce(o.action_full, '')) CONTAINS term)
                    OPTIONAL MATCH (a:Article)-[:CONTAINS_OBLIGATION]->(o)
                    RETURN o.id AS id,
                           o.article_id  AS article_id,
                           a.title        AS article_title,
                           o.action       AS action,
                           o.action_full  AS action_full,
                           o.actors       AS actors,
                           o.paragraph_ref AS paragraph_ref
                    LIMIT $limit
                    """,
                    terms=terms,
                    limit=top_k * 3,
                ).data()
                for r in rows:
                    row_map[r["id"]] = r
                    kw_ids.add(r["id"])

        # ── Semantic pass ──────────────────────────────────────────────────
        if mode in ("hybrid", "semantic"):
            idx = session.run(
                "SHOW INDEXES WHERE name = 'cra_obligation_embedding'"
            ).data()
            if not idx:
                if mode == "semantic":
                    driver.close()
                    return {
                        "status": "error",
                        "report": (
                            "No cra_obligation_embedding vector index found. "
                            "Run vectorize_obligations() first, then retry."
                        ),
                    }
                # hybrid fallback: no semantic — continue with keyword-only results
                log.info(
                    "cra_obligation_embedding not found; falling back to keyword-only"
                )
            else:
                try:
                    qvec = _embed_query(query)
                    sem_rows = session.run(
                        """
                        CALL db.index.vector.queryNodes(
                            'cra_obligation_embedding', $k, $vec)
                        YIELD node AS o, score
                        OPTIONAL MATCH (a:Article)-[:CONTAINS_OBLIGATION]->(o)
                        RETURN o.id AS id,
                               o.article_id  AS article_id,
                               a.title        AS article_title,
                               o.action       AS action,
                               o.action_full  AS action_full,
                               o.actors       AS actors,
                               o.paragraph_ref AS paragraph_ref,
                               score
                        ORDER BY score DESC
                        """,
                        k=top_k * 2,
                        vec=qvec,
                    ).data()
                    for r in sem_rows:
                        sem_scores[r["id"]] = r["score"]
                        if r["id"] not in row_map:
                            row_map[r["id"]] = r
                except Exception as e:
                    log.warning("Semantic obligation search failed: %s", e)
                    if mode == "semantic":
                        driver.close()
                        return {
                            "status": "error",
                            "report": (
                                f"Semantic search failed: {e}. "
                                "Is Ollama running? Try mode='keyword' as fallback."
                            ),
                        }

    driver.close()

    if not row_map:
        return {
            "status": "ok",
            "report": (
                f'No obligations found for "{query}".\n'
                "Tips: try broader terms, or use mode='semantic' with vectorize_obligations()."
            ),
            "results": [],
        }

    # ── Merge & rank ──────────────────────────────────────────────────────
    scored: list[dict] = []
    for oid, row in row_map.items():
        s = sem_scores.get(oid, 0.0)
        in_kw = oid in kw_ids

        if mode == "hybrid":
            # Boost obligations that appear in both signals
            combined = s + (0.15 if in_kw else 0.0) if s else (0.55 if in_kw else 0.0)
            match_type = "hybrid" if s and in_kw else ("semantic" if s else "keyword")
        elif mode == "semantic":
            combined = s
            match_type = "semantic"
        else:
            combined = 1.0
            match_type = "keyword"

        full_text = row.get("action_full") or row.get("action") or ""
        preview = full_text[:200].replace("\n", " ").strip()
        if len(full_text) > 200:
            preview += "…"

        actors = row.get("actors") or []
        if isinstance(actors, str):
            actors = [actors] if actors else []

        scored.append(
            {
                "rank": 0,  # assigned below
                "id": oid,
                "article_id": row.get("article_id") or "",
                "article_title": row.get("article_title") or "",
                "action": row.get("action") or "",
                "preview": preview,
                "actors": actors,
                "paragraph_ref": row.get("paragraph_ref") or "",
                "score": round(combined * 100, 1),
                "match_type": match_type,
            }
        )

    scored.sort(key=lambda x: -x["score"])
    results = scored[:top_k]
    for i, r in enumerate(results, 1):
        r["rank"] = i

    # ── Report ────────────────────────────────────────────────────────────
    mode_label = {
        "hybrid": "keyword + semantic",
        "semantic": "semantic only",
        "keyword": "keyword only",
    }
    lines = [
        f'Found {len(results)} obligations matching "{query}" '
        f"[mode: {mode_label.get(mode, mode)}]:\n"
    ]
    for r in results:
        actors_str = ", ".join(r["actors"]) if r["actors"] else "all"
        lines.append(
            f'{r["rank"]}. [{r["article_id"]}] {r["action"]}  '
            f'({r["score"]}% — {r["match_type"]})\n'
            f'   ID: {r["id"]}  |  Actors: {actors_str}\n'
            f'   {r["preview"]}\n'
        )

    return {
        "status": "ok",
        "query": query,
        "mode": mode,
        "result_count": len(results),
        "report": "\n".join(lines),
        "results": results,
    }


def vectorize_actions() -> str:
    """Generates embeddings for ComplianceAction nodes in the Neo4j graph using Ollama.

    This function fetches all ComplianceAction nodes from the graph, computes
    their embeddings using the configured local Ollama model, and updates the
    ComplianceAction nodes with their 'embedding' vector properties.
    Finally, it rebuilds the vector index 'cra_action_embedding' for faster similarity searches.

    Returns:
        A string summarizing the operation, e.g. "Vectorized 42 ComplianceAction nodes!"
    """
    import time

    driver = _get_driver()
    nodes = []

    with driver.session() as session:
        # 1. Fetch
        res = session.run(
            "MATCH (a:ComplianceAction) RETURN a.id AS id, a.text AS text"
        )
        nodes = [(rec["id"], rec["text"]) for rec in res if rec["text"]]

    if not nodes:
        return "No ComplianceAction nodes found to vectorize."

    # 2. Embed
    ids, texts = zip(*nodes)
    embeddings = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = list(texts[i : i + BATCH_SIZE])
        try:
            vecs = _embed_texts(batch)
            embeddings.extend(vecs)
            log.info(
                "Embedded action batch %d (%d items)", i // BATCH_SIZE + 1, len(batch)
            )
        except Exception as e:
            log.error("Action embedding batch %d failed: %s", i // BATCH_SIZE + 1, e)
            embeddings.extend([None] * len(batch))
        time.sleep(0.2)

    # 3. Update
    with driver.session() as session:
        updates = []
        for id_val, emb in zip(ids, embeddings):
            if emb:
                updates.append({"id": id_val, "vec": emb})

        session.run(
            "UNWIND $updates AS upd MATCH (a:ComplianceAction {id: upd.id}) SET a.embedding = upd.vec",
            updates=updates,
        )

        # 4. Create Index
        session.run("DROP INDEX cra_action_embedding IF EXISTS")
        session.run("""
            CREATE VECTOR INDEX cra_action_embedding IF NOT EXISTS
            FOR (a:ComplianceAction) ON (a.embedding)
            OPTIONS {
                indexConfig: {
                    `vector.dimensions`: 768,
                    `vector.similarity_function`: 'cosine'
                }
            }
            """)

    return f"Successfully vectorized {len(updates)} ComplianceAction nodes and updated index 'cra_action_embedding'."
