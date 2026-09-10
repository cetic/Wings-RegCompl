"""Tools for reading CRA articles from the extracted markdown."""

from __future__ import annotations

import re
from pathlib import Path

# Path to the extracted CRA markdown
CRA_MD_PATH = (
    Path(__file__).resolve().parents[2] / "outputs" / "CRA_requirements_statemachine.md"
)


def list_articles() -> str:
    """List all articles and annexes available in the CRA regulation.
    Returns a numbered list of article titles."""
    text = CRA_MD_PATH.read_text(encoding="utf-8")
    articles = re.findall(r"^### (Article \d+.*|Part .*)$", text, re.MULTILINE)
    chapters = re.findall(r"^## (CHAPTER .+|ANNEX .+)$", text, re.MULTILINE)
    lines = []
    for ch in chapters:
        lines.append(f"\n## {ch}")
    for art in articles:
        lines.append(f"  - {art}")
    # Rebuild with structure
    result = []
    text_lines = text.split("\n")
    for line in text_lines:
        if line.startswith("## CHAPTER") or line.startswith("## ANNEX"):
            result.append(f"\n{line}")
        elif line.startswith("### Article") or line.startswith("### Part"):
            result.append(f"  {line.replace('### ', '- ')}")
    return "\n".join(result) if result else "No articles found."


def read_article(article_number: int) -> str:
    """Read the full text of a specific CRA article by its number.

    Args:
        article_number: The article number to read (e.g. 13 for Article 13).

    Returns:
        The full text of the article, including title and all paragraphs.
    """
    text = CRA_MD_PATH.read_text(encoding="utf-8")
    # Find the start of the requested article
    pattern = rf"^### Article {article_number} —"
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        return f"Article {article_number} not found in the CRA document."

    start = match.start()
    # Find the next article or chapter or annex heading
    rest = text[match.end() :]
    next_heading = re.search(r"^###? ", rest, re.MULTILINE)
    if next_heading:
        end = match.end() + next_heading.start()
    else:
        end = len(text)

    return text[start:end].strip()


def read_annex(annex_id: str) -> str:
    """Read the full text of a CRA annex.

    Args:
        annex_id: The annex identifier, e.g. 'I', 'II', 'III', 'IV', etc.

    Returns:
        The full text of the annex including all parts.
    """
    text = CRA_MD_PATH.read_text(encoding="utf-8")
    # Map Roman numerals
    pattern = rf"^## ANNEX {re.escape(annex_id)} —"
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        return f"Annex {annex_id} not found in the CRA document."

    start = match.start()
    rest = text[match.end() :]
    next_annex = re.search(r"^## ANNEX ", rest, re.MULTILINE)
    if next_annex:
        end = match.end() + next_annex.start()
    else:
        end = len(text)

    return text[start:end].strip()


def read_chapter(chapter_number: int) -> str:
    """Read all articles within a CRA chapter.

    Args:
        chapter_number: The chapter number in Roman numerals mapping:
            1=I, 2=II, 3=III, 4=IV, 5=V, 6=VI, 7=VII, 8=VIII

    Returns:
        The full text of all articles in the chapter.
    """
    roman_map = {
        1: "I",
        2: "II",
        3: "III",
        4: "IV",
        5: "V",
        6: "VI",
        7: "VII",
        8: "VIII",
    }
    roman = roman_map.get(chapter_number, str(chapter_number))

    text = CRA_MD_PATH.read_text(encoding="utf-8")
    pattern = rf"^## CHAPTER {roman} —"
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        return f"Chapter {chapter_number} not found."

    start = match.start()
    rest = text[match.end() :]
    next_chapter = re.search(r"^## (CHAPTER|ANNEX) ", rest, re.MULTILINE)
    if next_chapter:
        end = match.end() + next_chapter.start()
    else:
        end = len(text)

    return text[start:end].strip()


def read_recital(recital_number: int) -> str:
    """Read the full text of a specific CRA recital by its number.

    Args:
        recital_number: The recital number (1-130).

    Returns:
        The full text of the recital.
    """
    text = CRA_MD_PATH.read_text(encoding="utf-8")
    pattern = rf"^### \({recital_number}\)\s*$"
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        return f"Recital ({recital_number}) not found in the CRA document."

    start = match.start()
    rest = text[match.end() :]
    next_heading = re.search(r"^###? ", rest, re.MULTILINE)
    if next_heading:
        end = match.end() + next_heading.start()
    else:
        end = len(text)

    return text[start:end].strip()


def list_recitals() -> str:
    """List all recitals available in the CRA regulation.

    Returns:
        A numbered list of recital identifiers (1 through 130).
    """
    text = CRA_MD_PATH.read_text(encoding="utf-8")
    numbers = re.findall(r"^### \((\d+)\)\s*$", text, re.MULTILINE)
    if not numbers:
        return "No recitals found."
    return f"CRA contains {len(numbers)} recitals: (1) through ({numbers[-1]})"


def list_annexes() -> str:
    """List all annexes available in the CRA regulation.

    Returns:
        A list of annex identifiers and their titles.
    """
    text = CRA_MD_PATH.read_text(encoding="utf-8")
    annexes = re.findall(r"^## (ANNEX .+)$", text, re.MULTILINE)
    if not annexes:
        return "No annexes found."
    lines = [f"CRA contains {len(annexes)} annexes:"]
    for a in annexes:
        lines.append(f"  - {a}")
    return "\n".join(lines)
