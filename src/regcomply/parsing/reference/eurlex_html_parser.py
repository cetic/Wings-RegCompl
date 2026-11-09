"""
Structural parser for EUR-Lex HTML (the "TXT/HTML" rendering generated from Formex by CONVEX).

Structure comes from the markup, not from layout:
  - chapters / sections / articles: <div class="eli-subdivision" id="cpt_III.sct_2" | "art_14">
  - paragraphs: <div id="014.002"> directly under the article (ids inside quoted amendments belong
    to OTHER acts and are treated as text)
  - recitals: id="rct_N"; annexes: <div class="eli-container" id="anx_III">
  - points: two-cell table rows (marker | content), nested for sub-points
  - annex groupings: <p class="oj-ti-grseq-1">Section A ...</p>
  - footnote calls (<a class="oj-note-tag">) removed from text; notes themselves skipped

Output uses the same Node format and the same extract()/validate() as eu_act_parser_v2,
so results are directly comparable with the PDF pipeline.

Usage: python3 eurlex_html_parser.py <file.html> <SHORT> <output.json>
"""
import json
import re
import sys
from collections import Counter
from dataclasses import asdict

from bs4 import BeautifulSoup, NavigableString, Tag

from .eu_act_pdf_parser import Node, extract, validate, LETTERS

PARA_ID = re.compile(r"^\d{3}\.\d{3}$")
GROUPING = re.compile(r"^(Section|Part|PART|Class)\s+([IVX]+|[A-Z]|\d+)\b\.?\s*[—–-]?\s*(.*)$")


def text_of(el):
    """Visible text without footnote calls."""
    if isinstance(el, NavigableString):
        return str(el)
    el = BeautifulSoup(str(el), "lxml")
    for a in el.select("a.oj-note-tag, span.oj-note-tag"):
        a.decompose()
    return re.sub(r"\s+", " ", el.get_text(" ")).strip()


def _unwrap_browser_source_view(html):
    wrapper = BeautifulSoup(html, "lxml").select_one(".source-container")
    if wrapper is None:
        return html, False
    lines = wrapper.select("td.line-content")
    if not lines:
        return html, False
    return "\n".join(line.get_text() for line in lines), True


def classify_marker(m, prev_letter=None):
    m = m.strip().lstrip("‘'\"")                    # quoted amendment items: "‘(68)"
    if re.fullmatch(r"\(\d+\)", m):
        return "num", m[1:-1]
    if re.fullmatch(r"\((?:i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii)\)", m):
        lab = m[1:-1]
        if prev_letter and len(lab) == 1 and LETTERS.index(lab) == LETTERS.index(prev_letter) + 1:
            return "letter", lab                      # (i) after (h), (v) after (u)
        return "roman", lab
    if re.fullmatch(r"\([a-z]\)", m):
        return "letter", m[1:-1]
    if re.fullmatch(r"\d+(?:\.\d+)+\.?", m):
        return "decimal", m.rstrip(".")
    if re.fullmatch(r"\d+\.", m):
        return "paragraph", m[:-1]
    if m in ("—", "-", "–", "•"):
        return "dash", None
    return "other", m


class HtmlParser:
    def __init__(self, short):
        self.short = short
        self.nodes = {}
        self.errors, self.warnings, self.ambiguities = [], [], []

    def add(self, ptype, local, parent, cite, path, normative=True):
        nid = f"{self.short.lower()}:{path}"
        if nid in self.nodes:
            self.errors.append(f"Duplicate identifier {nid} ({cite})")
            k = 2
            while f"{nid}~{k}" in self.nodes:
                k += 1
            nid = f"{nid}~{k}"
        n = Node(nid, ptype, local, cite, parent.id if parent else None, is_normative=normative)
        self.nodes[nid] = n
        if parent:
            parent.children.append(nid)
        return n

    @staticmethod
    def path(n):
        return n.id.split(":", 1)[1]

    # ---- content of a container: paragraphs of text, lists (tables), quoted divs --------------
    def walk(self, el, target, base, is_definitions=False, dash_count=None):
        """el: element whose children are content; target: node receiving text/children;
        base: node used for annex-style citations ('point N')."""
        current = target
        seen_list = False
        dash_count = dash_count if dash_count is not None else [0]
        prev_letter = None
        for ch in el.children:
            if not isinstance(ch, Tag):
                continue
            cls = ch.get("class") or []
            if ch.name == "p" and ("oj-normal" in cls or not cls):
                t = text_of(ch)
                if not t:
                    continue
                if not target.text and not target.children:
                    target.text = t
                elif seen_list:                     # text after a list: unnumbered subparagraph
                    k = 2 + sum(1 for c in target.children if self.nodes[c].ptype == "subparagraph")
                    current = self.add("subparagraph", str(k), target, f"{target.citation}, subparagraph {k}",
                                       f"{self.path(target)}.subpar_{k}")
                    current.text, current.marker = t, "subpar"
                    seen_list = False
                else:
                    current.text = (current.text + " " + t).strip()
            elif ch.name == "table":
                seen_list = True
                for tr in ch.find_all("tr", recursive=False) or ch.select(":scope > tbody > tr"):
                    tds = tr.find_all("td", recursive=False)
                    if len(tds) < 2:
                        continue
                    # content = last cell; marker = last non-empty cell before it (indent cells are empty)
                    marks = [text_of(td) for td in tds[:-1] if text_of(td)]
                    mtype, label = classify_marker(marks[-1] if marks else "", prev_letter)
                    if mtype == "letter":
                        prev_letter = label
                    if mtype == "dash":
                        dash_count[0] += 1
                        label = f"dash{dash_count[0]}"
                    if mtype == "other":
                        self.warnings.append(f"Unknown list marker '{label}' in {current.citation}")
                        label = re.sub(r"\W+", "_", label)[:12] or "x"
                    if mtype == "paragraph" and current.ptype in ("annex", "part"):
                        cite = f"{current.citation}, point {label}"
                    elif mtype == "decimal":
                        cite = f"{base.citation}, point {label}"
                    else:
                        cite = f"{current.citation}({label})"
                    ptype = "definition" if (is_definitions and mtype == "num" and current is target) else (
                        "paragraph" if mtype == "paragraph" else "point")
                    n = self.add(ptype, label, current, cite,
                                 f"{self.path(current)}.{mtype[:3]}_{str(label).replace('.', '_')}")
                    n.marker = mtype if mtype != "paragraph" else "paragraph"
                    self.walk(tds[-1], n, base)
            elif ch.name == "div" and PARA_ID.match(ch.get("id", "")):
                # a paragraph id NOT directly under an article: quoted text of another act
                current.text = (current.text + " " + text_of(ch)).strip()
            elif ch.name == "div" and "eli-title" in cls:
                continue
            elif ch.name == "div" and "oj-enumeration-spacing" in cls and \
                    (m := re.match(r"^(\d+(?:\.\d+)*)\.\s+(.*)$", text_of(ch))):
                seen_list = True                          # numbered point without a table (Annex VI)
                label = m[1]
                dec = "." in label
                cite = f"{base.citation}, point {label}" if (dec or target.ptype in ("annex", "part")) \
                    else f"{target.citation}({label})"
                n = self.add("point" if dec else "paragraph", label, target, cite,
                             f"{self.path(target)}.{'dec' if dec else 'par'}_{label.replace('.', '_')}")
                n.text, n.marker = m[2], ("decimal" if dec else "paragraph")
            elif ch.name == "div":
                self.walk(ch, current, base, is_definitions, dash_count)
            elif ch.name == "p" and "oj-note" in cls:
                continue
            elif ch.name == "span" and text_of(ch):          # bare text in a cell (Annex I entries)
                current.text = (current.text + " " + text_of(ch)).strip()

    # ---- main -----------------------------------------------------------------------------------
    def parse(self, html):
        soup = BeautifulSoup(html, "lxml")
        pre = self.add("preamble", "pre", None, f"{self.short} Preamble", "preamble", normative=False)
        for r in soup.find_all("div", id=re.compile(r"^rct_\d+$")):
            num = r["id"].split("_")[1]
            tds = r.find_all("td")
            body = text_of(tds[1]) if len(tds) >= 2 else re.sub(r"^\(\d+\)\s*", "", text_of(r))
            self.add("recital", num, pre, f"{self.short} Recital ({num})", f"rec_{num}", normative=False).text = body

        def title_of(div, idx):
            t = div.find("div", class_="eli-title", recursive=False)
            ps = t.find_all("p") if t else []
            return text_of(ps[idx]) if len(ps) > idx else ""

        for div in soup.find_all("div", id=re.compile(r"^cpt_[IVXL]+$")):
            ch_id = div["id"].split("_")[1]
            ch = self.add("chapter", ch_id, None, f"{self.short} Chapter {ch_id}", f"chap_{ch_id}")
            ch.heading = title_of(div, -1)
            for sdiv in div.find_all("div", id=re.compile(rf"^cpt_{ch_id}\.sct_\d+$"), recursive=False):
                sn = sdiv["id"].split("_")[-1]
                sec = self.add("section", sn, ch, f"{ch.citation} Section {sn}", f"{self.path(ch)}.sec_{sn}")
                sec.heading = title_of(sdiv, -1)
                for adiv in sdiv.find_all("div", id=re.compile(r"^art_\d+$"), recursive=False):
                    self.article(adiv, sec)
            for adiv in div.find_all("div", id=re.compile(r"^art_\d+$"), recursive=False):
                self.article(adiv, ch)

        for adiv in soup.find_all("div", class_="eli-container", id=re.compile(r"^anx_[IVXL]+$")):
            self.annex(adiv)
        return self

    def article(self, adiv, parent):
        num = adiv["id"].split("_")[1]
        art = self.add("article", num, parent, f"{self.short} Art. {num}", f"art_{num}")
        t = adiv.find("div", class_="eli-title", recursive=False)
        art.heading = text_of(t) if t else ""
        is_def = art.heading.lower() == "definitions"
        paras = [d for d in adiv.find_all("div", recursive=False) if PARA_ID.match(d.get("id", ""))]
        if paras:
            for d in paras:
                pn = str(int(d["id"].split(".")[1]))
                par = self.add("paragraph", pn, art, f"{art.citation}({pn})", f"art_{num}.par_{pn}")
                par.marker = "paragraph"
                # strip the leading "2." marker paragraph text
                self.walk(d, par, par, is_def)
                par.text = re.sub(r"^\d+\.\s*", "", par.text)
        else:
            self.walk(adiv, art, art, is_def)

    def annex(self, adiv):
        num = adiv["id"].split("_")[1]
        a = self.add("annex", num, None, f"{self.short} Annex {num}", f"anx_{num}")
        heads = [text_of(p) for p in adiv.find_all("p", class_="oj-doc-ti", recursive=False)]
        a.heading = " ".join(heads[1:]) if len(heads) > 1 else ""
        if "correlation table" in a.heading.lower():
            a.ptype = "correlation_annex"
        # split the annex body at grouping headings (Section / Part)
        target, buffer = a, []
        group_parent = a

        def flush():
            if buffer:
                wrapper = BeautifulSoup("<div></div>", "lxml").div
                for el in buffer:
                    wrapper.append(el)
                self.walk(wrapper, target, group_parent)      # decimals cite the annex / part
                buffer.clear()

        children = [c for c in adiv.children if isinstance(c, Tag)]
        i = 0
        while i < len(children):
            c = children[i]
            cls = c.get("class") or []
            if c.name == "p" and "oj-doc-ti" in cls:
                i += 1
                continue
            if c.name == "p" and "oj-ti-grseq-1" in cls and (m := GROUPING.match(text_of(c))):
                flush()
                kind, gnum, title = m[1].capitalize(), m[2], m[3]
                target = self.add("part", gnum, a, f"{a.citation}, {kind} {gnum}",
                                  f"{self.path(a)}.{kind.lower()}_{gnum}")
                group_parent = target
                if not title and i + 1 < len(children) and "oj-ti-grseq-1" in (children[i + 1].get("class") or []):
                    title = text_of(children[i + 1]); i += 1
                target.heading = title
            elif c.name == "p" and "oj-ti-grseq-1" in cls and (m := re.match(r"^(\d+)\.\s+(.+)$", text_of(c))):
                flush()                                   # numbered group heading ("1. Schengen ...")
                target = self.add("paragraph", m[1], group_parent, f"{group_parent.citation}, point {m[1]}",
                                  f"{self.path(group_parent)}.par_{m[1]}")
                target.heading, target.marker = m[2], "paragraph"
            else:
                buffer.append(c.__copy__() if hasattr(c, "__copy__") else c)
            i += 1
        flush()


def run(src, short, out_path):
    html = open(src, encoding="utf-8").read()
    html, recovered_source_view = _unwrap_browser_source_view(html)
    soup_title = re.search(r"<title>(.*?)</title>", html)
    canon = re.search(r'rel="canonical" href="([^"]+)"', html)
    p = HtmlParser(short).parse(html)
    defs, xext, modals, durations, applies = extract(p.nodes)
    rep = validate(p.nodes, p.errors)
    rep.update(source_title=soup_title[1] if soup_title else None, canonical=canon[1] if canon else None,
               warnings=p.warnings, node_types=Counter(n.ptype for n in p.nodes.values()))
    if recovered_source_view:
        rep["warnings"].append("Recovered EUR-Lex markup from browser-saved source view")
    out = {"report": rep, "definitions": defs, "external_refs": xext.most_common(), "modals": modals,
           "durations": durations, "application_dates": applies}
    json.dump({"nodes": [asdict(n) for n in p.nodes.values()], **out}, open(out_path, "w"),
              ensure_ascii=False, indent=1, default=list)
    return p, out


if __name__ == "__main__":
    _, out = run(sys.argv[1], sys.argv[2], sys.argv[3])
    print(json.dumps(out["report"], ensure_ascii=False, indent=1, default=list))
