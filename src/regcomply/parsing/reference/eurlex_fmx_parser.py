"""Structural parser for EUR-Lex Formex XML acts."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from lxml import etree

from .eu_act_pdf_parser import Node, extract, validate

STRUCTURAL_TAGS = {
    "ACT", "ARTICLE", "ANNEX", "CHAPTER", "ITEM", "LIST", "PARAG",
    "PART", "RECITAL", "SECTION", "SUBPARAG",
}
INLINE_MARKERS = {
    "NO.ANNEX", "NO.ART", "NO.CHAPTER", "NO.PARAG", "NO.POINT", "NO.SECTION",
}


def _name(element: etree._Element) -> str:
    return etree.QName(element).localname.upper()


def _text(element: etree._Element, stop: set[str] | None = None) -> str:
    stop_tags = STRUCTURAL_TAGS | INLINE_MARKERS | (stop or set())
    parts: list[str] = []

    def visit(current: etree._Element) -> None:
        if current.text:
            parts.append(current.text)
        for child in current:
            if not isinstance(child.tag, str):
                continue
            if _name(child) not in stop_tags:
                visit(child)
            if child.tail:
                parts.append(child.tail)

    visit(element)
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def _direct_text(element: etree._Element, tag_names: set[str]) -> str:
    for child in element:
        if isinstance(child.tag, str) and _name(child) in tag_names:
            value = " ".join(child.itertext()).strip()
            if value:
                return re.sub(r"\s+", " ", value)
    return ""


def _number(element: etree._Element, tag_names: set[str], fallback: int | str) -> str:
    value = ""
    for child in element.iter():
        if isinstance(child.tag, str) and _name(child) in tag_names:
            value = " ".join(child.itertext()).strip()
            if value:
                break
    value = value or element.get("IDENTIFIER", "")
    value = value.strip().rstrip(".")
    if re.fullmatch(r"\([A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*\)", value):
        return value[1:-1]
    matches = re.findall(r"[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*", value)
    return matches[-1] if matches else str(fallback)


def _marker(value: str) -> str:
    if re.fullmatch(r"[a-z]", value):
        return "letter"
    if value.isdigit():
        return "num"
    if re.fullmatch(r"(?:i|ii|iii|iv|v|vi|vii|viii|ix|x)", value):
        return "roman"
    return ""


class FormexParser:
    def __init__(self, short_name: str) -> None:
        self.short_name = short_name
        self.nodes: dict[str, Node] = {}
        self.errors: list[str] = []

    def add(
        self,
        ptype: str,
        local_id: str,
        parent: Node | None,
        citation: str,
        path: str,
        *,
        normative: bool = True,
    ) -> Node:
        node_id = f"{self.short_name.lower()}:{path}"
        if node_id in self.nodes:
            self.errors.append(f"Duplicate identifier {node_id} ({citation})")
            return self.nodes[node_id]
        node = Node(
            node_id,
            ptype,
            local_id,
            citation,
            parent.id if parent else None,
            is_normative=normative,
        )
        self.nodes[node_id] = node
        if parent is not None:
            parent.children.append(node_id)
        return node

    def _add_items(self, container: etree._Element, parent: Node, base_path: str) -> None:
        items = [child for child in container if isinstance(child.tag, str) and _name(child) == "ITEM"]
        for index, item in enumerate(items, start=1):
            label = _number(item, {"NO.POINT", "NO.ITEM"}, index)
            path = f"{base_path}.point_{label.replace('.', '_')}"
            node = self.add("point", label, parent, f"{parent.citation}({label})", path)
            node.marker = _marker(label)
            node.text = _text(item, {"ITEM", "LIST"})
            for child in item:
                if isinstance(child.tag, str) and _name(child) == "LIST":
                    self._add_items(child, node, path)

    def _article_parent(self, element: etree._Element, preamble: Node) -> Node:
        group_types = {
            "CHAPTER": ("chapter", "chap", "NO.CHAPTER", "Chapter"),
            "SECTION": ("section", "sec", "NO.SECTION", "Section"),
            "PART": ("part", "part", "NO.PART", "Part"),
        }
        ancestors = [
            ancestor
            for ancestor in element.iterancestors()
            if isinstance(ancestor.tag, str) and _name(ancestor) in group_types
        ]
        parent = preamble
        for ancestor in reversed(ancestors):
            tag = _name(ancestor)
            ptype, path_prefix, number_tag, label = group_types[tag]
            siblings = [
                sibling
                for sibling in ancestor.getparent()
                if isinstance(sibling.tag, str) and _name(sibling) == tag
            ] if ancestor.getparent() is not None else [ancestor]
            fallback = siblings.index(ancestor) + 1
            number = _number(ancestor, {number_tag}, fallback)
            path = f"{parent.id.split(':', 1)[1]}.{path_prefix}_{number}"
            if parent is preamble:
                path = f"{path_prefix}_{number}"
            node_id = f"{self.short_name.lower()}:{path}"
            group = self.nodes.get(node_id)
            if group is None:
                group = self.add(
                    ptype,
                    number,
                    parent,
                    f"{parent.citation} {label} {number}" if parent is not preamble
                    else f"{self.short_name} {label} {number}",
                    path,
                )
                title = next(
                    (
                        child
                        for child in ancestor.iter()
                        if child is not ancestor and isinstance(child.tag, str) and _name(child) == "TI"
                    ),
                    None,
                )
                group.heading = " ".join(title.itertext()).strip() if title is not None else ""
            parent = group
        return parent

    def _article(self, element: etree._Element, parent: Node) -> None:
        number = _number(element, {"NO.ART"}, len(self.nodes) + 1).split(".", 1)[0]
        path = f"art_{number}"
        article = self.add("article", number, parent, f"{self.short_name} Art. {number}", path)
        article_title = next(
            (
                child
                for child in element.iter()
                if isinstance(child.tag, str) and _name(child) == "TI"
            ),
            None,
        )
        article.heading = " ".join(article_title.itertext()).strip() if article_title is not None else ""
        paragraphs = [child for child in element if isinstance(child.tag, str) and _name(child) == "PARAG"]
        if not paragraphs:
            article.text = _text(element)
            return
        for index, paragraph_element in enumerate(paragraphs, start=1):
            paragraph_number = _number(paragraph_element, {"NO.PARAG"}, index).split(".", 1)[0]
            paragraph_path = f"{path}.par_{paragraph_number}"
            paragraph = self.add(
                "paragraph", paragraph_number, article,
                f"{article.citation}({paragraph_number})", paragraph_path,
            )
            paragraph.marker = "paragraph"
            paragraph.text = _text(paragraph_element)
            for child in paragraph_element:
                if isinstance(child.tag, str) and _name(child) == "LIST":
                    self._add_items(child, paragraph, paragraph_path)

    def parse(self, root: etree._Element) -> FormexParser:
        if _name(root) != "ACT":
            raise ValueError("XML root must be a EUR-Lex Formex ACT element")
        preamble = self.add(
            "preamble", "pre", None, f"{self.short_name} Preamble", "preamble", normative=False
        )
        for index, element in enumerate(root.iter(), start=1):
            if not isinstance(element.tag, str) or _name(element) != "RECITAL":
                continue
            number = _number(element, {"NO.RECITAL", "NO.RCT"}, index)
            recital = self.add(
                "recital", number, preamble, f"{self.short_name} Recital ({number})",
                f"rec_{number}", normative=False,
            )
            recital.text = _text(element)
        for element in root.iter():
            if isinstance(element.tag, str) and _name(element) == "ARTICLE":
                self._article(element, self._article_parent(element, preamble))
        annexes = [element for element in root.iter() if isinstance(element.tag, str) and _name(element) == "ANNEX"]
        for index, element in enumerate(annexes, start=1):
            number = _number(element, {"NO.ANNEX"}, index)
            path = f"anx_{number}"
            annex = self.add("annex", number, preamble, f"{self.short_name} Annex {number}", path)
            annex.heading = _direct_text(element, {"TI.ANNEX", "TITLE"})
            annex.text = _text(element)
            for child in element:
                if isinstance(child.tag, str) and _name(child) == "LIST":
                    self._add_items(child, annex, path)
        return self


def run(src: str, short_name: str, out_path: str) -> tuple[FormexParser, dict[str, Any]]:
    xml_parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        remove_comments=True,
        huge_tree=False,
    )
    root = etree.parse(src, xml_parser).getroot()
    formex = FormexParser(short_name).parse(root)
    definitions, external_refs, modals, durations, application_dates = extract(formex.nodes)
    report = validate(formex.nodes, formex.errors)
    report.update(
        source_title=_direct_text(root, {"TI.DOC", "TI.ACT"}) or None,
        canonical=None,
        warnings=[],
        node_types=Counter(node.ptype for node in formex.nodes.values()),
    )
    output = {
        "report": report,
        "definitions": definitions,
        "external_refs": external_refs.most_common(),
        "modals": modals,
        "durations": durations,
        "application_dates": application_dates,
    }
    with open(out_path, "w", encoding="utf-8") as output_file:
        json.dump(
            {"nodes": [asdict(node) for node in formex.nodes.values()], **output},
            output_file,
            ensure_ascii=False,
            indent=1,
            default=list,
        )
    return formex, output


if __name__ == "__main__":
    _, result = run(sys.argv[1], sys.argv[2], sys.argv[3])
    print(json.dumps(result["report"], ensure_ascii=False, indent=1, default=list))