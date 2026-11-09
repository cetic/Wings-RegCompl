"""
Deterministic structural parser for EU legal acts — v2.

Changes from v1 (driven by Commission Implementing Regulation (EU) 2023/203, "Part-IS"):
  1. Enacting formula: accepts "HAVE ADOPTED" (EP + Council) and "HAS ADOPTED" (Commission).
  2. Page furniture: ELI footer (2024+) AND legacy OJ header "2.2.2023 EN Official Journal ... L 31/1".
  3. Coded points (EASA style: IS.I.OR.230, ATM/ANS.OR.B.005A, 145.A.200A) as a provision level,
     with de-duplication of the table of contents that precedes them in each annex.
  4. Nesting: a generic MARKER STACK replaces the hard-coded order, so (2)(a) [CRA] and
     (a)(1)(i) [EASA] are both handled by the same rule.
  5. Amendments: quoted text inserted into OTHER acts is not parsed as provisions of this act;
     each instruction becomes an amendment record (target act, target point, operation).
  6. Validation fails loudly: missing enacting terms, zero articles, unclosed quotes.
v2.1 (driven by the GDPR, Regulation (EU) 2016/679):
  7. Letter-spaced headings ("Sec ti on 1") repaired from a character-level re-read (pdfplumber).
  8. Sections in title case; definitions like "'consent' of the data subject means" / "means:".
  9. Pre-2015 act numbers (Directive 95/46/EC); "as defined in point (b) of Article 1(1) of ...".
 10. Orphan-heading detector: a centred line appended to body text is reported as a warning.
v2.2 (driven by NIS2, Directive (EU) 2022/2555):
 11. Table annexes: sector / subsector / entity-type tables read from word coordinates (pdfplumber),
     including rotated (landscape) pages and rows continuing across pages.
 12. Correlation tables (repealed act -> this act) extracted as correlation records.
 13. Definitions with an alternative label ("'domain name system' or 'DNS' means"), kept as alias.
 14. Directive dates: transposition deadline, national measures apply-from, "with effect from", dated tasks.
v2.3 (driven by the Machinery Regulation, Regulation (EU) 2023/1230):
 15. Quotation mode only in amending contexts and never for "'term' means" (annex-level definitions).
 16. "PART A / PART B" groupings (uppercase, lettered).
 17. Multi-level decimal numbering (1.1.1, 3.6.3.1) with one marker level per depth; short decimal
     lines become headings ("1.1.4. Lighting").
 18. Unnumbered subparagraphs: after a completed list, a new capitalised paragraph opens a subparagraph,
     and a following list belongs to it (several lists in one point).
 19. Chapters inside an annex: a numbered heading in capitals ("1. ESSENTIAL HEALTH AND SAFETY ...").
 20. Application dates given as a list ("However, it shall apply as follows: (a) Articles 26 to 42 from ...").
v2.4 (driven by the AI Act, Regulation (EU) 2024/1689):
 21. Sections inside annexes ("Section 1", "Section A. Title", "Section A — Title") grouped like parts.
 22. Robustness: a structural heading without its expected parent is recorded as an error, never a crash.
 23. Once annexes start, a line "Article N" is a wrapped title or a reference, never a new article.
 24. Footnotes citing non-legislative documents (European Council conclusions, EP resolutions, opinions).
 25. Validator accepts numbering that continues across sibling groups (Annex I Sections A 1-12, B 13-20).
 26. Definitions with an inserted qualifier ("'subject', for the purpose of real-world testing, means").
 27. Amending articles: only titles naming ANOTHER act ("Amendment to Regulation (EC) No 300/2008"), not
     internal powers ("Amendments to Annex III"); unnumbered instructions; added (sub)paragraphs; EC numbers.
 28. Lookahead for "(i)" after "(h)": if the next marker is "(ii)", (i)-(iii) are sub-points of (h).
 29. Title cross-check: acts named after "amending" in the title must all have amendment records.
v2.5 (found by differential testing against the EUR-Lex HTML parser):
 30. Act-by-act OJ masthead (2023+) removed from page 1.
 31. Coded points must contain a letter (IS.I.OR.230 yes, "2016/679" no).
 32. Dash lists ("— terrorism,") as list items numbered dash1, dash2, ... (same scheme as the HTML parser).

Usage: python3 eu_act_parser_v2.py <text file from pdftotext -layout> <SHORT> <output.json> [source.pdf]
"""
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field, asdict
import string as st

# --------------------------------------------------------------------------- #
# 1. Cleaning                                                                  #
# --------------------------------------------------------------------------- #
FURNITURE = [
    re.compile(r"^\s*ELI: http\S+\s+\d+/\d+\s*$"),
    re.compile(r"^\s*\d+/\d+\s+ELI: http\S+\s*$"),
    re.compile(r"^\s*(EN\s+)?OJ L, \d+\.\d+\.\d{4}(\s+EN)?\s*$"),
    # legacy OJ header: "2.2.2023   EN   Official Journal of the European Union   L 31/1" (or mirrored)
    re.compile(r"^\s*(\d{1,2}\.\d{1,2}\.\d{4}|L \d+/\d+)\s+EN\s+Official Journal of the European Union\s+(L \d+/\d+|\d{1,2}\.\d{1,2}\.\d{4})\s*$"),
]
FOOTNOTE_START = re.compile(r"^\s{2,}\(\d+\)\s+(Regulation|Directive|Decision|Commission|Council|Recommendation|OJ|https?://|"
                            r"European (?:Council|Parliament|Commission|Data Protection)|Position of|Opinion|Judgment|"
                            r"Communication|Resolution|Agreement|Charter|Interinstitutional)")


def is_letter_spaced(line):
    toks = line.split()
    return len(line) - len(line.lstrip()) >= 20 and len(toks) >= 3 and \
        sum(len(t) <= 4 for t in toks) / len(toks) >= 0.7


def repair_letter_spacing(text, pdf_path):
    """Replace garbled centred lines with the character-level rendering of the same page."""
    if not pdf_path:
        return text, 0
    import pdfplumber
    pages, fixed = text.split("\f"), 0
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pages):
            if i >= len(pdf.pages) or not any(is_letter_spaced(l) for l in page.split("\n")):
                continue
            ref = {re.sub(r"\s+", "", l["text"]).lower(): l["text"]
                   for l in pdf.pages[i].extract_text_lines(keep_blank_chars=True)}
            new = []
            for l in page.split("\n"):
                key = re.sub(r"\s+", "", l).lower()
                if is_letter_spaced(l) and key in ref:
                    indent = len(l) - len(l.lstrip())
                    l = " " * indent + ref[key].strip()
                    fixed += 1
                new.append(l)
            pages[i] = "\n".join(new)
    return "\f".join(pages), fixed


MASTHEAD = re.compile(r"^\s*(Official Journal|of the European Union|L series|\d{4}/\d{1,5}|\d{1,2}\.\d{1,2}\.\d{4})"
                      r"(\s+(EN|L series|\d{4}/\d{1,5}|\d{1,2}\.\d{1,2}\.\d{4}))*\s*$")


def clean(text):
    out, n_furn, n_foot = [], 0, 0
    for pi, page in enumerate(text.split("\f")):
        kept = []
        for li, ln in enumerate(page.split("\n")):
            if pi == 0 and li < 8 and MASTHEAD.match(ln):
                n_furn += 1
                continue
            if any(p.match(ln) for p in FURNITURE):
                n_furn += 1
                continue
            kept.append(ln)
        cut = len(kept)
        numbered = re.compile(r"^\s{2,}\((\d+)\)\s")
        for i, line in enumerate(kept):
            m = numbered.match(line)
            if not m:
                continue
            n = int(m[1])
            body_before = "\n".join(kept[:i])
            # a footnote call: "(n)" after a word that is NOT a legal cross-reference keyword
            called_inline = re.search(
                rf"(?<!point)(?<!points)(?<!paragraph)(?<!Article)(?<!Annex)(?<!recital)(?<!and)(?<!or)(?<!to)\s\({n}\)",
                body_before) is not None
            block = [l for l in kept[i:] if numbered.match(l)]
            nums = [int(numbered.match(l)[1]) for l in block]
            consecutive = nums == list(range(n, n + len(nums)))
            footnote_like = sum(1 for l in block if FOOTNOTE_START.match(l)) >= max(1, len(block) // 2)
            if called_inline and consecutive and footnote_like:
                cut = i                     # footnote block: called inline above, consecutive to page end
                break
        n_foot += sum(1 for l in kept[cut:] if l.strip())
        out.extend(kept[:cut])
    return out, n_furn, n_foot


# --------------------------------------------------------------------------- #
# 2. Grammar                                                                   #
# --------------------------------------------------------------------------- #
RX = {
    "enacting_start": re.compile(r"\b(HAVE|HAS) ADOPTED THIS (REGULATION|DIRECTIVE|DECISION)"),
    "chapter": re.compile(r"^\s*CHAPTER ([IVXL]+)\s*$"),
    "section": re.compile(r"^\s*(?:SECTION|Section) (\d+)\s*$"),
    "article": re.compile(r"^\s*Article (\d+[a-z]?)\s*$"),
    "annex": re.compile(r"^\s*ANNEX ([IVXL]+)\s*$"),
    "part": re.compile(r"^\s*(Part|PART|Class|Section) ([IVX]+|[A-Z]|\d+)(?!\s+of\b)(?:\s*[.—–-]?\s+([A-Z(].*))?\s*$"),
    # EASA-style coded point: segments separated by . or /, ending in a 3-digit number (+ optional letter)
    "coded": re.compile(r"^\s*((?:[A-Z0-9]{1,6}[./])+?\d{3}[A-Z]?)\s+(\S.*)$"),
    "amending_annex": re.compile(r"\b(is|are) amended as follows\b"),
}
MARKERS = [  # order matters: decimal before paragraph
    ("decimal", re.compile(r"^\s{2,}(\d+(?:\.\d+)+)\.?\s+([A-Z(‘].*)$")),   # uppercase start: avoids "1.5 m from..."
    ("paragraph", re.compile(r"^\s{2,}(\d+)\.\s+(.*)$")),
    ("num", re.compile(r"^\s{2,}\((\d+)\)\s+(.*)$")),
    ("roman", re.compile(r"^\s{2,}\(((?:i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii))\)\s+(.*)$")),
    ("letter", re.compile(r"^\s{2,}\(([a-z])\)\s+(.*)$")),
    ("dash", re.compile(r"^\s{2,}(—)\s+(\S.*)$")),
]
LETTERS = st.ascii_lowercase
AMEND_OPS = [
    ("insert", re.compile(r"(?:point|heading) ([\w./]+) is inserted after (?:point|heading) ([\w./]+)")),
    ("add", re.compile(r"in (?:point|Article) ‘?([\w./]+)(?:\(\d\))?, the following point \((\w+)\) is added")),
    ("add", re.compile(r"[Ii]n ((?:Article|point|Annex|Part) [\w./()]+)[^:]*?,? the following (?:new )?"
                       r"(\w+)\b[^:]*? (?:is|are) (?:added|inserted)")),
    ("delete", re.compile(r"(Articles? \d+[\w()]*(?:(?:,| and) \d+[\w()]*)*) (?:is|are) deleted")),
    ("replace_heading", re.compile(r"the heading(?: of point ([\w./]+))? is replaced by the following")),
    ("replace", re.compile(r"(?:point|Article|paragraph) ?([\w./()]+)(?: of [^,]{0,60}?)? is replaced by the following")),
]
TARGET_ACT = re.compile(r"(?:Regulation|Directive|Decision) (?:\((?:EU|EC|EEC)\) (?:No )?(\d+/\d+)|(\d{2,4}/\d+/(?:EC|EEC|EU)))")
AMENDING_ARTICLE = re.compile(r"^Amendments? (?:to|of) (?:Implementing |Delegated |Commission )?(?:Regulation|Directive|Decision)\b")


def target_act(text):
    m = TARGET_ACT.search(text or "")
    return (m[1] or m[2]) if m else None


@dataclass
class Node:
    id: str
    ptype: str
    local_id: str
    citation: str
    parent: str | None
    heading: str = ""
    text: str = ""
    is_normative: bool = True
    marker: str = ""
    indent: int = 0
    children: list = field(default_factory=list)


class Parser:
    def __init__(self, short):
        self.short = short
        self.nodes, self.amendments, self.ambiguities, self.errors, self.warnings = {}, [], [], [], []
        self.struct = dict.fromkeys(["chapter", "section", "article", "annex", "part", "achapter", "coded"])
        self.markers: list[tuple[str, Node]] = []  # the marker stack
        self.current = None
        self.pending_heading = None
        self.in_quote = False
        self.quote_buffer = []
        self.last_instruction = None
        self.annex_target_act = None
        self.seen_codes = {}
        self.in_signature = False
        self.table_mode = None
        self.correlations = []
        self.subpar_undo = None

    # -- helpers ---------------------------------------------------------------
    def add(self, ptype, local, parent, cite, path, normative=True):
        nid = f"{self.short.lower()}:{path}"
        if nid in self.nodes:
            self.errors.append(f"Duplicate identifier {nid} ({cite}): kept both, second renamed")
            k = 2
            while f"{nid}~{k}" in self.nodes:
                k += 1
            nid = f"{nid}~{k}"
        n = Node(nid, ptype, local, cite, parent.id if parent else None, is_normative=normative)
        self.nodes[nid] = n
        if parent:
            parent.children.append(nid)
        self.current = n
        return n

    def path(self, n):
        return n.id.split(":", 1)[1]

    def container(self):
        s = self.struct
        return s["coded"] or s["article"] or s["achapter"] or s["part"] or s["annex"]

    def set_struct(self, level, node):
        order = ["chapter", "section", "article", "annex", "part", "achapter", "coded"]
        self.struct[level] = node
        for k in order[order.index(level) + 1:]:
            self.struct[k] = None
        if level == "annex":
            self.struct.update(chapter=None, section=None, article=None)
        self.markers = []

    # -- the letter/roman ambiguity --------------------------------------------
    def classify(self, mtype, label):
        if mtype != "roman":
            return mtype
        types = [t for t, _ in self.markers]
        letter = next((n for t, n in reversed(self.markers) if t == "letter"), None)
        if letter and len(label) == 1 and LETTERS.index(label) == LETTERS.index(letter.local_id) + 1:
            self.ambiguities.append(f"'({label})' after '({letter.local_id})' read as a letter in {letter.citation}")
            return "letter"
        if "roman" in types or (self.markers and self.markers[-1][0] in ("letter", "num")):
            return "roman"
        return "letter" if label == "i" and "letter" not in types else "roman"

    # -- the marker stack: same rule for (2)(a) and (a)(1)(i) --------------------
    def push_marker(self, mtype, label, text, indent=0):
        self.maybe_undo_subparagraph(mtype, label)
        mtype = self.classify(mtype, label)
        if mtype == "decimal":
            mtype = f"dec{label.count('.') + 1}"           # one marker level per depth
            depth = label.count(".") + 1
            while self.markers and (self.markers[-1][0] in ("letter", "num", "roman", "dash", "subpar") or
                                    (self.markers[-1][0].startswith("dec") and
                                     int(self.markers[-1][0][3:]) >= depth)):
                self.markers.pop()                         # a decimal heading never sits inside a list
        if mtype == "paragraph" and (self.struct["part"] or self.struct["annex"]) and not self.struct["article"] \
                and re.sub(r"[^A-Za-z]", "", text) and text.upper() == text and len(text) < 120:
            base = self.struct["part"] or self.struct["annex"]
            n = self.add("annex_chapter", label, base, f"{base.citation}, chapter {label}",
                         f"{self.path(base)}.ach_{label}")
            n.heading = text.strip()
            self.set_struct("achapter", n)
            return True
        if mtype == "paragraph":
            self.markers = []
        elif mtype in [t for t, _ in self.markers]:
            while self.markers and self.markers[-1][0] != mtype:
                self.markers.pop()
            self.markers.pop()  # sibling: replace same-type level
        parent = self.markers[-1][1] if self.markers else self.container()
        if parent is None:
            return False
        if mtype == "dash":
            label = f"dash{1 + sum(1 for c in parent.children if self.nodes[c].marker == 'dash')}"
        art = self.struct["article"]
        ptype = "definition" if (mtype == "num" and art is not None and art.heading.lower() == "definitions"
                                 and parent is art) else ("paragraph" if mtype == "paragraph" else "point")
        if parent.ptype in ("article",) and mtype == "paragraph":
            cite = f"{parent.citation}({label})"
        elif parent.ptype in ("annex", "part") and mtype == "paragraph":
            cite = f"{parent.citation}, point {label}"
        elif mtype.startswith("dec"):
            c = self.struct["part"] or self.struct["annex"] or self.container()
            cite = f"{c.citation}, point {label}"
        else:
            cite = f"{parent.citation}({label})"
        n = self.add(ptype, label, parent, cite, f"{self.path(parent)}.{mtype[:3]}_{label.replace('.', '_')}")
        n.text = text
        n.marker = mtype
        n.indent = indent
        if mtype.startswith("dec") and len(text) < 90 and not text.rstrip().endswith((".", ";", ",", ":")):
            n.heading, n.text = text.strip(), ""             # "1.1.4. Lighting"
        self.markers.append((mtype, n))
        return True

    # -- unnumbered subparagraphs ----------------------------------------------
    def open_subparagraph(self, text, indent=0):
        saved = list(self.markers)
        last_item = self.markers[-1][1]
        if indent > last_item.indent + 1:
            pass                                              # indented to the item's text: stays inside it
        else:
            self.markers.pop()                                # aligned with the markers: closes the list
            if self.markers and self.markers[-1][0] == "subpar":
                self.markers.pop()
        parent = self.markers[-1][1] if self.markers else self.container()
        k = 2 + sum(1 for c in parent.children if self.nodes[c].ptype == "subparagraph")
        n = self.add("subparagraph", str(k), parent, f"{parent.citation}, subparagraph {k}",
                     f"{self.path(parent)}.subpar_{k}")
        n.text = text
        n.marker = "subpar"
        self.markers.append(("subpar", n))
        self.subpar_undo = (n, saved, last_item)

    def maybe_undo_subparagraph(self, mtype, label):
        """If the next marker continues the list we just closed, the 'subparagraph' was a false break."""
        if not self.subpar_undo:
            return
        n, saved, last_item = self.subpar_undo
        self.subpar_undo = None
        nxt = lambda l: LETTERS[LETTERS.index(l) + 1] if l in LETTERS[:-1] else None
        cont = (last_item.marker == "letter" and len(label) == 1 and label == nxt(last_item.local_id)) or \
               (last_item.marker in ("num", "paragraph") and label.isdigit() and last_item.local_id.isdigit()
                and int(label) == int(last_item.local_id) + 1) or \
               (last_item.marker == "roman" and mtype == "roman")
        if cont and not n.children:
            last_item.text += " " + n.text
            self.nodes[n.parent].children.remove(n.id)
            del self.nodes[n.id]
            self.markers = saved
            self.ambiguities.append(f"False subparagraph undone after {last_item.citation}")

    # -- amendments ------------------------------------------------------------
    def record_instruction(self, text):
        for op, rx in AMEND_OPS:
            if m := rx.search(text):
                target = m.group(1)
                if target is None and self.current is not None and self.current.parent:
                    pm = re.search(r"point ([\w./]+) is amended", self.nodes[self.current.parent].text)
                    target = pm[1] if pm else None    # inherit from the parent instruction
                rec = {"in": self.current.citation if self.current else None, "operation": op,
                       "target_act": self.annex_target_act, "target": target, "detail": m.groups()[1:] if len(m.groups()) > 1 else (),
                       "inserted_text": ""}
                self.amendments.append(rec)
                self.last_instruction = rec
                return

    # -- main loop -------------------------------------------------------------
    def parse(self, lines):
        in_enacting = False
        pre = self.add("preamble", "pre", None, f"{self.short} Preamble", "preamble", normative=False)
        prev_text = ""
        blank_before = False
        for raw in lines:
            line = raw.rstrip()
            s = line.strip()
            if not s:
                blank_before = True
                continue
            was_blank, blank_before = blank_before, False

            # ---- quoted text (amendments): never parsed as provisions of this act
            if (self.in_enacting_quote_start(s, prev_text) and self.amending_context()
                    and not re.match(r"^‘[^’]+’\s+means?\b", s)) or self.in_quote:
                if not self.in_quote:
                    self.in_quote = True
                    self.quote_buffer = []
                self.quote_buffer.append(s)
                if re.search(r"’\s*[;.,]?\s*$", s) and not re.search(r"‘[^’]*’\s*[;.,]?\s*$", s[1:]) or s.endswith(("’;", "’.", "’")):
                    self.in_quote = False
                    if self.last_instruction is not None:
                        self.last_instruction["inserted_text"] = " ".join(self.quote_buffer)[:300]
                        self.last_instruction = None
                prev_text = s
                continue

            if not in_enacting:
                if RX["enacting_start"].search(line):
                    in_enacting = True
                    continue
                if m := MARKERS[2][1].match(line):
                    self.add("recital", m[1], pre, f"{self.short} Recital ({m[1]})", f"rec_{m[1]}", normative=False).text = m[2]
                elif self.current:
                    self.current.text += " " + s
                continue

            if re.match(r"^Done at \w+", s):          # signature block until the next annex
                self.in_signature = True
                continue
            if self.in_signature:
                if RX["annex"].match(line):
                    self.in_signature = False
                else:
                    continue

            if self.table_mode == "entity" and not RX["annex"].match(line):
                continue                                  # handled by read_entity_tables()
            if self.table_mode == "correlation" and not RX["annex"].match(line):
                if m := CORR_ROW.match(line):
                    old, new = m[1].strip(), m[2].strip()
                    self.correlations.append({"repealed": old, "this_act": None if new in "-–" else new})
                continue
            if RX["annex"].match(line):
                self.table_mode = None

            if self.pending_heading is not None and self.pending_heading.ptype == "part" and \
                    any(rx.match(line) for _, rx in MARKERS):
                self.pending_heading = None               # "Class I" followed directly by "1. ..."
            if self.pending_heading is not None:
                h = self.pending_heading
                h.heading = s
                self.pending_heading = None
                if h.ptype == "annex" and s.upper() == "CORRELATION TABLE":
                    h.ptype = "correlation_annex"; self.table_mode = "correlation"
                if h.ptype == "article" and AMENDING_ARTICLE.match(s):
                    self.annex_target_act = target_act(s)  # "Amendment to Regulation (EC) No 300/2008"
                if h.ptype == "annex" and RX["amending_annex"].search(s):
                    h.ptype = "amending_annex"          # no title: the heading IS the amending sentence
                    if t := target_act(s):
                        self.annex_target_act = t
                prev_text = s
                continue

            if m := RX["chapter"].match(line):
                n = self.add("chapter", m[1], None, f"{self.short} Chapter {m[1]}", f"chap_{m[1]}")
                self.set_struct("chapter", n); self.pending_heading = n
            elif not self.struct["annex"] and (m := RX["section"].match(line)):
                ch = self.struct["chapter"]
                if ch is None:
                    self.errors.append(f"Section {m[1]} found outside any chapter: '{s}'")
                    continue
                n = self.add("section", m[1], ch, f"{ch.citation} Section {m[1]}", f"{self.path(ch)}.sec_{m[1]}")
                self.set_struct("section", n); self.pending_heading = n
            elif not self.struct["annex"] and (m := RX["article"].match(line)):
                n = self.add("article", m[1], self.struct["section"] or self.struct["chapter"],
                             f"{self.short} Art. {m[1]}", f"art_{m[1]}")
                self.set_struct("article", n); self.pending_heading = n
                self.annex_target_act = None
            elif m := RX["annex"].match(line):
                n = self.add("annex", m[1], None, f"{self.short} Annex {m[1]}", f"anx_{m[1]}")
                self.set_struct("annex", n); self.pending_heading = n
                self.seen_codes = {}; self.annex_target_act = None
            elif self.struct["annex"] and (m := RX["part"].match(line)):
                a = self.struct["annex"]
                kind, num = m[1].capitalize(), m[2]
                n = self.add("part", num, a, f"{a.citation}, {kind} {num}", f"{self.path(a)}.{kind.lower()}_{num}")
                n.heading = m[3] or ""; self.set_struct("part", n)
                if not n.heading:
                    self.pending_heading = n           # title on the next line ("General principles")
            elif self.struct["annex"] and self.struct["annex"].ptype == "annex" and (m := RX["coded"].match(line)) \
                    and re.search(r"[A-Z]", m[1]):
                code, title = m[1], m[2].strip()
                a = self.struct["annex"]
                if code in self.seen_codes:  # 2nd occurrence: the 1st was a table-of-contents entry
                    old = self.seen_codes.pop(code)
                    if not old.text.strip():
                        a.children.remove(old.id); del self.nodes[old.id]
                n = self.add("coded_point", code, a, code, f"{self.path(a)}.{code.replace('/', '_')}")
                n.heading = title
                self.seen_codes[code] = n
                self.set_struct("coded", n)
            elif any(rx.match(line) for _, rx in MARKERS) and self.container() is not None:
                mtype, m = next((t, rx.match(line)) for t, rx in MARKERS if rx.match(line))
                self.push_marker(mtype, m[1], m[2], len(line) - len(line.lstrip()))
                if self.amending_context():
                    self.record_instruction(m[2])
            elif self.current is not None and self.current.ptype in ("article", "section", "chapter") \
                    and not self.current.children and not self.current.text and self.current.heading \
                    and len(line) - len(line.lstrip()) >= 20:
                self.current.heading += " " + s           # wrapped heading (e.g. GDPR Art. 12)
            elif self.struct["annex"] is not None and not self.struct["annex"].children and \
                    re.match(r"^Sector\s+Subsector\s+Type of entity$", re.sub(r"\s+", " ", s)):
                self.struct["annex"].ptype = "table_annex"; self.table_mode = "entity"
            elif self.struct["annex"] is not None and s.upper() == "CORRELATION TABLE":
                self.struct["annex"].heading = (self.struct["annex"].heading + " " + s).strip()
                self.struct["annex"].ptype = "correlation_annex"; self.table_mode = "correlation"
            elif self.current is not None and self.current.ptype == "annex" and not self.current.children:
                h = self.current                      # wrapped annex heading: keep accumulating
                h.heading += " " + s
                if RX["amending_annex"].search(h.heading):
                    h.ptype = "amending_annex"
                    if t := target_act(h.heading):
                        self.annex_target_act = t
            elif self.current is not None and was_blank and self.markers and \
                    self.markers[-1][0] in ("letter", "num", "roman", "dash") and s[:1].isupper() and \
                    self.current.text.rstrip().endswith((".", ":")) and not self.amending_context():
                self.open_subparagraph(s, len(line) - len(line.lstrip()))   # text after a completed list
            elif self.current:
                if len(line) - len(line.lstrip()) >= 30 and len(s) < 90 and not s.endswith((".", ";", ",", ":")):
                    self.warnings.append(f"Centred line appended to {self.current.citation}: '{s[:60]}' (missed heading?)")
                self.current.text += " " + s
                if self.amending_context() and (s.endswith(":") or re.search(r"\bdeleted\b", s)):
                    self.record_instruction(self.current.text)
            prev_text = s
        if self.in_quote:
            self.errors.append("Unclosed quotation at end of document")
        if not in_enacting:
            self.errors.append("Enacting formula ('HAS/HAVE ADOPTED THIS ...') never found: only the preamble was parsed")
        return self

    def amending_context(self):
        a, art = self.struct["annex"], self.struct["article"]
        return (a is not None and a.ptype == "amending_annex") or \
            (art is not None and AMENDING_ARTICLE.match(art.heading or "") is not None)

    @staticmethod
    def in_enacting_quote_start(s, prev_text):
        return s.startswith("‘") and prev_text.rstrip().endswith(":")


# --------------------------------------------------------------------------- #
# 2b. Table readers                                                            #
# --------------------------------------------------------------------------- #
FURN_WORDS = re.compile(r"^(EN|\d{1,2}\.\d{1,2}\.\d{4}|L|\d+/\d+|Official|Journal|of|the|European|Union)$")


def read_entity_tables(pdf_path):
    """Sector / Subsector / Type-of-entity tables (e.g. NIS2 Annexes I and II).
    Returns {annex_number: [ {sector, subsectors: [ {subsector, entities: [...]}, ... ]}, ... ]}"""
    import pdfplumber
    out, annex, sector, sub, ent = {}, None, None, None, None
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            text_line = " ".join(w["text"] for w in words[:40])
            if m := re.search(r"\bANNEX ([IVX]+)\b", text_line):
                annex = m[1]
                if not any(w["text"] == "Subsector" for w in words):
                    annex = None                       # an annex that is not an entity table
                    continue
                out[annex], sector, sub, ent = [], None, None, None
            if annex is None or not words:
                continue
            # body words only: drop the running-header strip on the outer edge
            body = [w for w in words if not (w["x0"] > page.width * 0.9 and FURN_WORDS.match(w["text"]))]
            hdr = next((w for w in body if w["text"] == "Subsector"), None)
            start = hdr["bottom"] if hdr else 0
            # column boundaries: the table's vertical rules first, item markers as fallback
            rules = []
            for x in sorted(e["x0"] for e in page.edges if e["orientation"] == "v" and e["x0"] < page.width * 0.9):
                if not rules or x - rules[-1] > 3:
                    rules.append(x)
            if len(rules) >= 3:
                x_sub, x_type = rules[1] - 1, rules[2] - 1
            else:
                subs = [w["x0"] for w in body if re.match(r"^\([a-z]\)$", w["text"]) and w["top"] > start]
                dashes = [w["x0"] for w in body if w["text"] == "—" and w["top"] > start]
                if not dashes:
                    continue
                x_type = min(dashes) - 2
                x_sub = min(subs) - 2 if subs else x_type - 90
            lines = {}
            for w in body:
                if w["top"] > start:
                    lines.setdefault(round(w["top"]), []).append(w)
            for top in sorted(lines):
                ws = sorted(lines[top], key=lambda w: w["x0"])
                col = lambda a, b: " ".join(w["text"] for w in ws if a <= w["x0"] < b).strip()
                c_sec, c_sub, c_typ = col(0, x_sub), col(x_sub, x_type), col(x_type, 1e9)
                if re.match(r"^\(\d+\)", c_sec):
                    break                              # footnote zone reached
                if m := re.match(r"^(\d+)\.\s*(.*)$", c_sec):
                    sector = {"number": m[1], "name": m[2], "subsectors": []}
                    out[annex].append(sector); sub = None
                elif c_sec and sector is not None:
                    sector["name"] = (sector["name"] + " " + c_sec).strip()
                if m := re.match(r"^\(([a-z])\)\s*(.*)$", c_sub):
                    sub = {"letter": m[1], "name": m[2], "entities": []}
                    sector["subsectors"].append(sub)
                elif c_sub and sub is not None:
                    sub["name"] = (sub["name"] + " " + c_sub).strip()
                if c_typ:
                    if sector is not None and sub is None:   # sector without subsectors
                        sub = {"letter": None, "name": "", "entities": []}
                        sector["subsectors"].append(sub)
                    if c_typ.startswith("—") or ent is None or sub is not None and not sub["entities"]:
                        ent = c_typ.lstrip("— ").strip()
                        sub["entities"].append(ent)
                    else:
                        sub["entities"][-1] = (sub["entities"][-1] + " " + c_typ).strip()
    return out


CORR_ROW = re.compile(r"^\s{2,}((?:Article|Articles|Annex)\s.+?)\s{3,}((?:Article|Articles|Annex)\s.+|[-–])\s*$")


# --------------------------------------------------------------------------- #
# 3. Rule-based extraction (signals for the LLM layer)                         #
# --------------------------------------------------------------------------- #
DEF_RX = re.compile(r"^‘([^’]+)’(?:,\s*‘[^’]+’)*(?:\s+and\s+‘[^’]+’)?(?:\s+or\s+‘([^’]+)’)?(?:\s+of the [\w ]+?)?"
                    r"(?:,\s*[^‘’,]{3,80},)?\s+means?:?\s*(.*)$", re.S)
BYREF_RX = re.compile(r"(?:as defined in|pursuant to|listed in) ((?:points? \(\w+\) of )?(?:Article|Annex) [\w\s(),]+?(?:of|to) (?:Regulation|Directive|Decision|Recommendation) (?:\((?:EU|EC)\))?(?: No)? ?\d+/\d+)")
XREF_EXT = re.compile(r"(Regulation|Directive|Decision) (?:\((EU|EC|EEC|Euratom)\)(?: No)? (\d+/\d+)|(\d{2,4}/\d+)/(EC|EEC|EU))")
MODAL_RX = re.compile(r"\b(shall not|shall|may not|may|should)\b")
DURATION_RX = re.compile(r"\b(within|no later than|after|exceeding|at least(?: until)?|for at least)\s+(\d+|one|two|three|six)\s+(hours?|days?|months?|years?)\b")
DATE = r"(\d{1,2} (?:January|February|March|April|May|June|July|August|September|October|November|December) \d{4})"
DATE_EVENTS = [
    ("transposition_deadline", re.compile(r"(?:[Bb]y " + DATE + r",? Member States shall adopt and publish|adopt and publish,? by " + DATE + r")")),
    ("national_measures_apply_from", re.compile(r"apply those measures from " + DATE)),
    ("with_effect_from", re.compile(r"with effect from " + DATE)),
    ("dated_task", re.compile(r"\b[Bb]y " + DATE)),
]
APPLY_RX = re.compile(r"(Article \d+|Chapter [IVX]+(?: \(Articles \d+ to \d+\))?|This Regulation|It|it) shall apply from (\d{1,2} \w+ \d{4})")


def extract(nodes):
    defs, xext, modals, durations, applies = [], Counter(), Counter(), [], []
    for n in nodes.values():
        t = re.sub(r"\s+", " ", n.text).strip()
        if n.ptype == "definition" and (m := DEF_RX.match(t)):
            br = BYREF_RX.search(m[3])
            defs.append({"provision": n.citation, "term": m[1], "alias": m[2], "by_reference": br[1] if br else None})
        for m in XREF_EXT.finditer(t):
            xext[f"{m[1]} ({m[2]}) {m[3]}" if m[2] else f"{m[1]} {m[4]}/{m[5]}"] += 1
        if n.is_normative:
            for m in MODAL_RX.finditer(t):
                modals[m[1]] += 1
            for m in DURATION_RX.finditer(t):
                durations.append({"provision": n.citation, "match": m[0]})
        seen_dates = set()
        for kind, rx in DATE_EVENTS:
            for m in rx.finditer(t):
                date = next(g for g in m.groups() if g)
                if any(d == date and abs(m.end() - e) < 80 for d, e in seen_dates):
                    continue
                seen_dates.add((date, m.end()))
                applies.append({"kind": kind, "date": date, "provision": n.citation,
                                "context": t[max(0, m.start() - 80):m.start()]})
        parent = nodes.get(n.parent) if n.parent else None
        if n.marker in ("letter", "num") and parent is not None and "shall apply" in parent.text:
            if m := re.match(r"^((?:Articles?|Chapters?|Annex(?:es)?|Points?|Sections?)\b.*?) from " + DATE, t):
                applies.append({"kind": "applies_from", "scope": re.sub(r"\s+shall apply$", "", m[1]), "date": m[2],
                                "provision": n.citation,
                                "context": "list in " + parent.citation})
        for m in APPLY_RX.finditer(t):
            scope = "This Regulation" if m[1].lower() == "it" else m[1]
            applies.append({"kind": "applies_from", "scope": scope, "date": m[2], "provision": n.citation,
                            "context": t[max(0, m.start() - 90):m.start()]})
    return defs, xext, modals, durations, applies


# --------------------------------------------------------------------------- #
# 4. Validation                                                                #
# --------------------------------------------------------------------------- #
def roman_to_int(s):
    v = {"I": 1, "V": 5, "X": 10, "L": 50}
    return sum(-v[c] if i + 1 < len(s) and v[c] < v[s[i + 1]] else v[c] for i, c in enumerate(s))


def validate(nodes, errors):
    r = {"errors": list(errors)}
    arts = sorted(int(re.match(r"\d+", n.local_id)[0]) for n in nodes.values() if n.ptype == "article")
    if not arts:
        r["errors"].append("No articles found")
    r["articles_found"] = len(arts)
    r["article_gaps"] = sorted(set(range(1, max(arts) + 1)) - set(arts)) if arts else []
    anx = sorted(roman_to_int(n.local_id) for n in nodes.values() if n.ptype in ("annex", "amending_annex", "table_annex", "correlation_annex"))
    r["annexes_found"] = len(anx)
    r["annex_gaps"] = sorted(set(range(1, max(anx) + 1)) - set(anx)) if anx else []
    rec = sorted(int(n.local_id) for n in nodes.values() if n.ptype == "recital")
    r["recitals_found"] = len(rec)
    r["recital_gaps"] = sorted(set(range(1, max(rec) + 1)) - set(rec))[:10] if rec else []
    seq = []
    for n in nodes.values():
        kids = [nodes[c] for c in n.children]
        ls = [k.local_id for k in kids if k.marker == "letter"]
        if ls and ls != list(LETTERS[:len(ls)]):
            seq.append(f"{n.citation}: letters ({')('.join(ls)})")
        ps = [int(k.local_id) for k in kids if k.ptype == "paragraph" and k.local_id.isdigit()]
        start = 1
        if ps and n.parent and n.ptype == "part":           # numbering may continue from the previous group
            sib = [nodes[c] for c in nodes[n.parent].children]
            i = sib.index(n)
            prev = [int(k.local_id) for s_ in sib[:i] if s_.ptype == "part"
                    for k in (nodes[c] for c in s_.children) if k.ptype == "paragraph" and k.local_id.isdigit()]
            if prev and ps[0] == max(prev) + 1:
                start = ps[0]
        if ps and ps != list(range(start, start + len(ps))):
            seq.append(f"{n.citation}: paragraphs {ps}")
        secs = [int(k.local_id) for k in kids if k.ptype == "section"]
        if secs and secs != list(range(1, len(secs) + 1)):
            seq.append(f"{n.citation}: sections {secs}")
    r["sequence_errors"] = seq
    r["articles_without_heading"] = [n.citation for n in nodes.values() if n.ptype == "article" and not n.heading]
    return r


def fix_roman_lists(p):
    for n in list(p.nodes.values()):
        if n.marker == "letter" and n.local_id == "i":
            kids = [p.nodes[c] for c in n.children]
            if kids and kids[0].marker == "roman" and kids[0].local_id == "ii":
                parent = p.nodes[n.parent]
                idx = parent.children.index(n.id)
                n.marker = "roman"
                for k in kids:
                    n.children.remove(k.id)
                    k.parent = parent.id
                    k.citation = k.citation.replace(f"{n.citation}", parent.citation, 1)
                    idx += 1
                    parent.children.insert(idx, k.id)
                p.ambiguities.append(f"'(i)' re-read as roman (list continues with (ii)) in {parent.citation}")
                # if (i) followed (h), the romans are sub-points of (h)
                sib = parent.children
                j = sib.index(n.id)
                if j > 0 and p.nodes[sib[j - 1]].marker == "letter" and p.nodes[sib[j - 1]].local_id == "h":
                    h = p.nodes[sib[j - 1]]
                    run_ = []
                    for cid in sib[j:]:
                        if p.nodes[cid].marker == "roman":
                            run_.append(cid)
                        else:
                            break
                    for cid in run_:
                        parent.children.remove(cid)
                        c = p.nodes[cid]
                        c.parent = h.id
                        c.citation = f"{h.citation}({c.local_id})"
                        h.children.append(cid)


def title_amended_acts(text):
    """Acts listed after 'amending' in the title (first page, before 'THE EUROPEAN ...' / 'Having regard')."""
    head = re.split(r"THE EUROPEAN PARLIAMENT AND THE COUNCIL OF THE EUROPEAN UNION,|THE EUROPEAN COMMISSION,|"
                    r"Having regard", text, maxsplit=1)[0]
    head = re.sub(r"\s+", " ", head)
    m = re.search(r"\bamending (.*?)(?:\band repealing\b|\(Text with|\(Artificial|\(Cyber|$)", head)
    if not m:
        return set()
    seg = m[1]
    acts = set(re.findall(r"\b(\d{2,4}/\d+/(?:EC|EEC|EU))\b", seg))
    acts |= set(re.findall(r"(?:\((?:EU|EC|EEC)\)|,|and)\s*(?:No\s*)?(\d{2,4}/\d{1,4})\b(?!/)", seg))
    return acts


def run(src, short, out_path, pdf_path=None):
    raw_text = open(src, encoding="utf-8").read()
    text, n_fixed = repair_letter_spacing(raw_text, pdf_path)
    lines, n_furn, n_foot = clean(text)
    p = Parser(short).parse(lines)
    fix_roman_lists(p)
    tables = read_entity_tables(pdf_path) if pdf_path and any(
        n.ptype == "table_annex" for n in p.nodes.values()) else {}
    dehyph = lambda t: re.sub(r"\u00ad\s*", "", t or "")
    for num, sectors in tables.items():
        a = p.nodes.get(f"{short.lower()}:anx_{num}")
        if a is None:
            continue
        for sec in sectors:
            sn = p.add("sector", sec["number"], a, f"{a.citation}, point {sec['number']}", f"{p.path(a)}.sec_{sec['number']}")
            sn.heading = dehyph(sec["name"])
            for sub in sec["subsectors"]:
                parent = sn
                if sub["letter"]:
                    parent = p.add("subsector", sub["letter"], sn, f"{sn.citation}({sub['letter']})",
                                   f"{p.path(sn)}.sub_{sub['letter']}")
                    parent.heading = dehyph(sub["name"])
                for k, e in enumerate(sub["entities"], 1):
                    p.add("entity_type", str(k), parent, f"{parent.citation}, entity {k}",
                          f"{p.path(parent)}.ent_{k}").text = dehyph(e)
    defs, xext, modals, durations, applies = extract(p.nodes)
    rep = validate(p.nodes, p.errors)
    in_title = title_amended_acts(raw_text)
    recorded = {a["target_act"] for a in p.amendments}
    rep["title_amended_acts"] = sorted(in_title)
    if re.search(r"\bamending\b", re.sub(r"\s+", " ", raw_text[:3000])) and not in_title:
        rep["errors"].append("Title mentions 'amending' but no amended act could be extracted from it")
    if in_title - recorded:
        rep["errors"].append(f"Acts amended per the title but without amendment records: {sorted(in_title - recorded)}")
    rep.update(table_sectors={k: len(v) for k, v in tables.items()}, correlation_rows=len(p.correlations),
               letter_spaced_lines_repaired=n_fixed, warnings=p.warnings, furniture_lines_removed=n_furn, footnote_lines_removed=n_foot, ambiguities=p.ambiguities,
               node_types=Counter(n.ptype for n in p.nodes.values()))
    out = {"report": rep, "definitions": defs, "external_refs": xext.most_common(), "modals": modals,
           "durations": durations, "application_dates": applies, "amendments": p.amendments,
           "correlations": p.correlations}
    json.dump({"nodes": [asdict(n) for n in p.nodes.values()], **out}, open(out_path, "w"),
              ensure_ascii=False, indent=1, default=list)
    return p, out


if __name__ == "__main__":
    src, short, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    _, out = run(src, short, out_path, sys.argv[4] if len(sys.argv) > 4 else None)
    print(json.dumps(out["report"], ensure_ascii=False, indent=1, default=list))
