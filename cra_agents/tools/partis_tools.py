"""Thin async wrappers around partis_batch.py tools for the ADK agent.

Prefixed with `partis_` to distinguish from CRA equivalents.
All functions are async so ADK's asyncio.gather() does not block the event
loop on synchronous Neo4j / file I/O, avoiding OSError: [Errno 35].
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure the project root is importable (partis_batch.py lives there).
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import partis_batch  # noqa: E402


async def partis_batch_articles(
    article_range: str = "all", force: bool = False, ingest_only: bool = False
) -> str:
    """Parse and ingest Part-IS articles (1-16) into the Neo4j knowledge graph.

    Args:
        article_range: Which articles to process.
            Examples: "all", "5", "3-10", "1,3,5-10".
        force: If True, re-parse even if a JSON file already exists.
        ingest_only: If True, skip parsing and only ingest existing JSONs.

    Returns:
        A progress report showing which articles succeeded and failed.
    """
    return await asyncio.to_thread(
        partis_batch.batch_parse_articles, article_range, force, ingest_only
    )


async def partis_batch_recitals(
    recital_range: str = "all", force: bool = False, ingest_only: bool = False
) -> str:
    """Parse and ingest Part-IS recitals (1-18) into the Neo4j knowledge graph.

    Args:
        recital_range: Which recitals to process.
            Examples: "all", "5", "3-10", "1,3,5-10".
        force: If True, re-parse even if a JSON file already exists.
        ingest_only: If True, skip parsing and only ingest existing JSONs.

    Returns:
        A progress report showing which recitals succeeded and failed.
    """
    return await asyncio.to_thread(
        partis_batch.batch_parse_recitals, recital_range, force, ingest_only
    )


async def partis_batch_is_sections(
    annex: str = "all", force: bool = False, ingest_only: bool = False
) -> str:
    """Parse and ingest Part-IS IS.AR / IS.I.OR sections (Annexes I and II).

    Args:
        annex: Which annex to process: "all", "I" (IS.AR), or "II" (IS.I.OR).
        force: If True, re-parse even if a JSON file already exists.
        ingest_only: If True, skip parsing and only ingest existing JSONs.

    Returns:
        A progress report showing which sections succeeded and failed.
    """
    return await asyncio.to_thread(
        partis_batch.batch_parse_is_sections, annex, force, ingest_only
    )


async def partis_batch_amendment_annexes(
    annex_range: str = "all", force: bool = False, ingest_only: bool = False
) -> str:
    """Parse and ingest Part-IS amendment annexes (III-IX).

    Args:
        annex_range: Which annexes to process.
            Examples: "all", "III", "III,V,VII".
        force: If True, re-parse even if a JSON file already exists.
        ingest_only: If True, skip parsing and only ingest existing JSONs.

    Returns:
        A progress report showing which annexes succeeded and failed.
    """
    return await asyncio.to_thread(
        partis_batch.batch_parse_amendment_annexes, annex_range, force, ingest_only
    )


async def partis_batch_all(force: bool = False) -> str:
    """Parse and ingest the entire Part-IS regulation (EU 2023/203) into Neo4j.

    Processes in order: articles (1-16), IS.AR sections (Annex I),
    IS.I.OR sections (Annex II), amendment annexes (III-IX), recitals (1-18).

    Args:
        force: If True, re-parse everything even if JSONs already exist.

    Returns:
        A full progress report for all sections.
    """
    return await asyncio.to_thread(partis_batch.batch_parse_all, force)


async def partis_vectorize() -> str:
    """Embed Part-IS text chunks and store vectors in Neo4j.

    Creates CRAChunk nodes with embeddings for all Part-IS articles,
    IS.AR/IS.I.OR sections, recitals, and amendment annexes.
    Requires Ollama running locally with nomic-embed-text model.

    Returns:
        A summary of how many chunks were embedded.
    """
    return await asyncio.to_thread(partis_batch.vectorize_partis)
