#!/usr/bin/env python3
"""
State machine parser to extract the CRA (Cyber Resilience Act) from PDF
into structured Markdown with correct hierarchy.

States:
  PREAMBLE      - Title block, "Having regard to..." clauses
  RECITALS      - "(1) ...", "(2) ...", ... "(130) ..."
  TRANSITION    - "HAVE ADOPTED THIS REGULATION:"
  CHAPTER       - "CHAPTER I", "CHAPTER II", ...
  ARTICLE       - "Article N" heading detected, next line is title
  ARTICLE_BODY  - Paragraph text within an article
  ANNEX         - "ANNEX I", "ANNEX II", ...
  ANNEX_BODY    - Content within an annex

Note: Footnotes and page numbers are ignored.

Hierarchy in Markdown:
  # REGULATION (EU) 2024/2847 — Cyber Resilience Act
  ## Preamble
  ## Recitals
  ### Recital (N)
  ## CHAPTER I — General provisions
  ### Article 1 — Subject matter
  #### 1.  (paragraph)
  ##### (a)  (point)
  ## ANNEX I — ...
"""

import re
import sys
import pdfplumber

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PDF_PATH = "docs/cra.pdf"
OUTPUT_PATH = "outputs/CRA_requirements_statemachine.md"

# Lines matching these patterns are page headers/footers — skip them
SKIP_PATTERNS = [
    re.compile(r"^\s*EN\s*$"),
    re.compile(r"^\s*OJ\s+L,?\s+\d"),
    re.compile(r"^\d+/\d+\s+ELI:"),
    re.compile(r"^ELI:\s*http"),
    re.compile(r"^\s*$"),
]

# Structural patterns
RE_CHAPTER = re.compile(r"^CHAPTER\s+(I{1,3}V?|IV|VI{0,3}|VIII?)\s*$")
RE_ARTICLE = re.compile(r"^Article\s+(\d+)\s*$")
RE_ANNEX = re.compile(r"^ANNEX\s+(I{1,3}V?|IV|VI{0,3}|VIII?)\s*$")
RE_RECITAL = re.compile(r"^\((\d+)\)\s+(.*)")
RE_RECITAL_CONT = re.compile(r"^\((\d+)\)")  # just the number at the start
RE_PARAGRAPH = re.compile(r"^(\d+)\.\s+(.*)")
RE_POINT = re.compile(r"^\(([a-z])\)\s+(.*)")
RE_NUM_POINT = re.compile(r"^\((\d+)\)\s+(.*)")
RE_ROMAN_POINT = re.compile(r"^\(([ivxlc]+)\)\s+(.*)")
RE_SUBPOINT = re.compile(r"^(\d+)\)\s+(.*)")  # numbered sub-points like 1), 2)
RE_HAVE_ADOPTED = re.compile(r"HAVE ADOPTED THIS REGULATION")
RE_ANNEX_PART = re.compile(
    r"^Part\s+(I{1,3}V?|IV|VI{0,3}|VIII?)\s+[A-Z](.*)"
)  # title must start uppercase

# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


class CRAParser:
    """State machine parser for the CRA regulation PDF."""

    STATES = (
        "PREAMBLE",
        "RECITALS",
        "TRANSITION",
        "CHAPTER_HEAD",
        "ARTICLE_HEAD",
        "ARTICLE_BODY",
        "ANNEX_HEAD",
        "ANNEX_BODY",
    )

    def __init__(self):
        self.state = "PREAMBLE"
        self.lines_out: list[str] = []
        self.current_chapter = ""
        self.current_chapter_title = ""
        self.current_article = ""
        self.current_article_title = ""
        self.current_annex = ""
        self.current_annex_title = ""
        self.current_recital = 0
        self.pending_text = ""  # accumulates multi-line text

    # ---- output helpers ----
    def emit(self, text: str):
        self.lines_out.append(text)

    def emit_blank(self):
        if self.lines_out and self.lines_out[-1] != "":
            self.lines_out.append("")

    def flush_pending(self):
        """Write any accumulated pending text."""
        if self.pending_text.strip():
            self.emit(self.pending_text.strip())
            self.emit_blank()
        self.pending_text = ""

    # ---- line classification ----
    def should_skip(self, line: str) -> bool:
        for pat in SKIP_PATTERNS:
            if pat.match(line):
                return True
        return False

    # ---- state handlers ----
    def handle_line(self, line: str):
        """Route a single line to the appropriate state handler."""
        stripped = line.strip()

        # Global skip
        if self.should_skip(stripped):
            return

        # Global transitions that can happen from any state
        if RE_HAVE_ADOPTED.search(stripped):
            self.flush_pending()
            self.emit_blank()
            self.emit("---")
            self.emit_blank()
            self.emit("**HAVE ADOPTED THIS REGULATION:**")
            self.emit_blank()
            self.state = "TRANSITION"
            return

        m_chap = RE_CHAPTER.match(stripped)
        if m_chap and self.state not in ("PREAMBLE",):
            self.flush_pending()
            self.current_chapter = m_chap.group(1)
            self.current_chapter_title = ""
            self.state = "CHAPTER_HEAD"
            return

        m_annex = RE_ANNEX.match(stripped)
        if m_annex:
            self.flush_pending()
            self.current_annex = m_annex.group(1)
            self.current_annex_title = ""
            self.state = "ANNEX_HEAD"
            return

        m_art = RE_ARTICLE.match(stripped)
        if m_art and self.state in (
            "TRANSITION",
            "CHAPTER_HEAD",
            "ARTICLE_BODY",
            "ARTICLE_HEAD",
        ):
            self.flush_pending()
            self.current_article = m_art.group(1)
            self.current_article_title = ""
            self.state = "ARTICLE_HEAD"
            return

        # Dispatch to current state
        handler = getattr(self, f"state_{self.state}", None)
        if handler:
            handler(stripped)

    # ---- PREAMBLE ----
    def state_PREAMBLE(self, line: str):
        m = RE_RECITAL.match(line)
        if m:
            # First recital — transition
            self.flush_pending()
            self.emit_blank()
            self.emit("## Recitals")
            self.emit_blank()
            self.state = "RECITALS"
            self.state_RECITALS(line)
            return

        # Check for "Whereas:" as a marker
        if line.strip() == "Whereas:":
            self.flush_pending()
            self.emit_blank()
            self.emit("*Whereas:*")
            self.emit_blank()
            return

        # Accumulate preamble text
        self.pending_text += " " + line if self.pending_text else line

    # ---- RECITALS ----
    def state_RECITALS(self, line: str):
        m = RE_RECITAL.match(line)
        if m:
            num = int(m.group(1))
            rest = m.group(2)

            # New recital — flush previous
            self.flush_pending()
            self.current_recital = num
            self.emit(f"### ({num})")
            self.emit_blank()
            self.pending_text = rest
            return

        # Continuation of current recital
        self.pending_text += " " + line if self.pending_text else line

    # ---- TRANSITION ----
    def state_TRANSITION(self, line: str):
        # Waiting for a CHAPTER or Article — anything else is ignored or part of transition
        pass

    # ---- CHAPTER_HEAD ----
    def state_CHAPTER_HEAD(self, line: str):
        """Expecting the chapter title on the next non-empty line."""
        if not self.current_chapter_title:
            self.current_chapter_title = line
        else:
            # Multi-line chapter title
            self.current_chapter_title += " " + line
            return

        # Emit the chapter heading and stay in this state until an Article appears
        self.emit_blank()
        self.emit(f"## CHAPTER {self.current_chapter} — {self.current_chapter_title}")
        self.emit_blank()

    # ---- ARTICLE_HEAD ----
    def state_ARTICLE_HEAD(self, line: str):
        """Expecting the article title on the next non-empty line after 'Article N'."""
        if not self.current_article_title:
            self.current_article_title = line
            self.emit(
                f"### Article {self.current_article} — {self.current_article_title}"
            )
            self.emit_blank()
            self.state = "ARTICLE_BODY"
            return

    # ---- ARTICLE_BODY ----
    def state_ARTICLE_BODY(self, line: str):
        """Parse paragraphs, points, and free text within an article."""
        # Check for numbered paragraph: "1. ...", "2. ..."
        m_para = RE_PARAGRAPH.match(line)
        if m_para:
            self.flush_pending()
            num = m_para.group(1)
            rest = m_para.group(2)
            self.emit(f"**{num}.** {rest}")
            self.pending_text = ""
            # Don't start pending_text — the rest may continue on next lines
            # Actually let's accumulate the rest in pending_text
            self.pending_text = f"**{num}.** {rest}"
            # Replace what we just emitted
            self.lines_out.pop()
            return

        # Check for lettered point: "(a) ...", "(b) ..."
        m_pt = RE_POINT.match(line)
        if m_pt:
            self.flush_pending()
            letter = m_pt.group(1)
            rest = m_pt.group(2)
            self.pending_text = f"- ({letter}) {rest}"
            return

        # Check for roman numeral point: "(i) ...", "(ii) ..."
        m_rom = RE_ROMAN_POINT.match(line)
        if m_rom:
            self.flush_pending()
            numeral = m_rom.group(1)
            rest = m_rom.group(2)
            self.pending_text = f"  - ({numeral}) {rest}"
            return

        # Check for numbered point: "(1) ...", "(2) ..." (e.g. Article 3 definitions)
        m_npt = RE_NUM_POINT.match(line)
        if m_npt:
            self.flush_pending()
            num = m_npt.group(1)
            rest = m_npt.group(2)
            self.pending_text = f"- ({num}) {rest}"
            return

        # Check for sub-points: "1) ...", "2) ..."
        m_sub = RE_SUBPOINT.match(line)
        if m_sub:
            self.flush_pending()
            num = m_sub.group(1)
            rest = m_sub.group(2)
            self.pending_text = f"  - {num}) {rest}"
            return

        # Continuation text
        if self.pending_text:
            self.pending_text += " " + line
        else:
            self.pending_text = line

    # ---- ANNEX_HEAD ----
    def state_ANNEX_HEAD(self, line: str):
        """Expecting the annex title on the next non-empty line(s)."""
        if not self.current_annex_title:
            self.current_annex_title = line
            self.emit_blank()
            self.emit(f"## ANNEX {self.current_annex} — {self.current_annex_title}")
            self.emit_blank()
            self.state = "ANNEX_BODY"
            return

    # ---- ANNEX_BODY ----
    def state_ANNEX_BODY(self, line: str):
        """Parse annex content — Parts, numbered items, points, free text."""
        # Part heading within annex (must have a proper title starting with uppercase)
        m_part = RE_ANNEX_PART.match(line)
        if m_part:
            self.flush_pending()
            part_num = m_part.group(1)
            # re-extract the full title after "Part N "
            title = re.sub(r"^Part\s+\S+\s+", "", line)
            self.emit(f"### Part {part_num} — {title}")
            self.emit_blank()
            return

        # Numbered paragraph
        m_para = RE_PARAGRAPH.match(line)
        if m_para:
            self.flush_pending()
            num = m_para.group(1)
            rest = m_para.group(2)
            self.pending_text = f"**{num}.** {rest}"
            return

        # Lettered point
        m_pt = RE_POINT.match(line)
        if m_pt:
            self.flush_pending()
            letter = m_pt.group(1)
            rest = m_pt.group(2)
            self.pending_text = f"- ({letter}) {rest}"
            return

        # Roman numeral point
        m_rom = RE_ROMAN_POINT.match(line)
        if m_rom:
            self.flush_pending()
            numeral = m_rom.group(1)
            rest = m_rom.group(2)
            self.pending_text = f"  - ({numeral}) {rest}"
            return

        # Numbered point: (1), (2), ... (e.g. definitions)
        m_npt = RE_NUM_POINT.match(line)
        if m_npt:
            self.flush_pending()
            num = m_npt.group(1)
            rest = m_npt.group(2)
            self.pending_text = f"- ({num}) {rest}"
            return

        # Sub-points
        m_sub = RE_SUBPOINT.match(line)
        if m_sub:
            self.flush_pending()
            num = m_sub.group(1)
            rest = m_sub.group(2)
            self.pending_text = f"  - {num}) {rest}"
            return

        # Check for "Class I" / "Class II" headings in ANNEX III/IV
        if re.match(r"^Class\s+(I{1,2}V?|IV)\s*$", line):
            self.flush_pending()
            self.emit(f"### {line}")
            self.emit_blank()
            return

        # Continuation text
        if self.pending_text:
            self.pending_text += " " + line
        else:
            self.pending_text = line

    # ---- page text extraction (with footnote cropping) ----
    @staticmethod
    def _extract_body_text(page) -> str:
        """Extract text from a PDF page, cropping out the footnote zone.

        Footnotes in EU OJ PDFs appear at the bottom of each page and are
        preceded by a superscript number (font size < 6).  We detect
        the y-position of the first such superscript marker at the left
        margin and crop the page above it.
        """
        chars = page.chars
        # Superscript digits at left margin, in the bottom 40% of the page
        # (excludes inline superscript footnote refs within body text)
        fn_markers = [
            c
            for c in chars
            if c.get("size", 10) < 6
            and c["text"].isdigit()
            and c["x0"] < 120
            and c["top"] > page.height * 0.6
        ]
        if fn_markers:
            footnote_y = min(c["top"] for c in fn_markers)
            # Crop page: keep only the area above the footnote zone
            cropped = page.crop((0, 0, page.width, footnote_y - 1))
            text = cropped.extract_text()
        else:
            text = page.extract_text()
        return text or ""

    # ---- main parse ----
    def parse_pdf(self, pdf_path: str) -> str:
        """Extract text from PDF and run the state machine."""
        pdf = pdfplumber.open(pdf_path)

        # Emit document title
        self.emit("# REGULATION (EU) 2024/2847 — Cyber Resilience Act")
        self.emit_blank()
        self.emit("## Preamble")
        self.emit_blank()

        for page_num, page in enumerate(pdf.pages, 1):
            text = self._extract_body_text(page)
            if not text:
                continue
            for line in text.split("\n"):
                self.handle_line(line)

        # Flush any remaining text
        self.flush_pending()

        pdf.close()
        return "\n".join(self.lines_out)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = CRAParser()
    result = parser.parse_pdf(PDF_PATH)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(result)

    # Print summary statistics
    chapters = result.count("\n## CHAPTER")
    articles = result.count("\n### Article")
    annexes = result.count("\n## ANNEX")
    recitals = result.count("\n### (")
    print(f"Extracted CRA to {OUTPUT_PATH}")
    print(f"  Chapters:  {chapters}")
    print(f"  Articles:  {articles}")
    print(f"  Recitals:  {recitals}")
    print(f"  Annexes:   {annexes}")
    print(f"  Total lines: {len(parser.lines_out)}")


if __name__ == "__main__":
    main()
