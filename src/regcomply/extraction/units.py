import hashlib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, cast

Phase = Literal["bootstrap", "main"]
ANNEX_GROUP_TYPES = {"part", "chapter", "section", "annex_chapter"}
BOOTSTRAP_PROFILES_PATH = Path(__file__).with_name("bootstrap_profiles.json")


@lru_cache(maxsize=1)
def _bootstrap_profiles() -> dict[str, dict[str, list[str]]]:
    return cast(
        dict[str, dict[str, list[str]]],
        json.loads(BOOTSTRAP_PROFILES_PATH.read_text(encoding="utf-8")),
    )


@dataclass(frozen=True)
class ExtractionUnit:
    unit_id: str
    root_id: str
    node_ids: tuple[str, ...]
    ordinal: int
    part: int | None = None
    text_overrides: tuple[tuple[str, str], ...] = ()


def _ordered_nodes(
    parsed: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, int], dict[str, int]]:
    nodes = {str(node["id"]): node for node in parsed["nodes"]}
    ordinal_by_id: dict[str, int] = {}
    source_order = {str(node["id"]): index for index, node in enumerate(parsed["nodes"])}
    for parent in nodes.values():
        for ordinal, child_id in enumerate(parent.get("children", [])):
            ordinal_by_id[str(child_id)] = ordinal
    return nodes, ordinal_by_id, source_order


def _subtree_ids(root_id: str, nodes: dict[str, dict[str, Any]]) -> list[str]:
    result: list[str] = []
    pending = [root_id]
    while pending:
        node_id = pending.pop()
        node = nodes.get(node_id)
        if node is None:
            continue
        result.append(node_id)
        pending.extend(reversed([str(child) for child in node.get("children", [])]))
    return result


def _is_annex_target(node: dict[str, Any], targets: set[str]) -> bool:
    local_id = str(node.get("local_id", "")).strip().upper()
    citation = str(node.get("citation", "")).upper()
    return local_id in targets or any(
        re.search(rf"\bANNEX\s+{re.escape(target)}\b", citation) for target in targets
    )


def _partition_subtree(
    root_id: str,
    nodes: dict[str, dict[str, Any]],
    max_chars: int,
) -> list[list[str]]:
    full_ids = _subtree_ids(root_id, nodes)
    full_size = sum(len(str(nodes[node_id].get("text", ""))) for node_id in full_ids)
    child_ids = [str(child) for child in nodes[root_id].get("children", []) if str(child) in nodes]
    if full_size <= max_chars or not child_ids:
        return [full_ids]

    chunks: list[list[str]] = []
    current: list[str] = []
    current_size = len(str(nodes[root_id].get("text", "")))
    for child_id in child_ids:
        for child_chunk in _partition_subtree(child_id, nodes, max_chars):
            child_size = sum(len(str(nodes[item].get("text", ""))) for item in child_chunk)
            if current and current_size + child_size > max_chars:
                chunks.append([root_id, *current])
                current = []
                current_size = len(str(nodes[root_id].get("text", "")))
            current.extend(child_chunk)
            current_size += child_size
    if current:
        chunks.append([root_id, *current])
    return chunks


def _units_for_roots(
    roots: list[str],
    nodes: dict[str, dict[str, Any]],
    ordinals: dict[str, int],
    max_chars: int,
) -> list[ExtractionUnit]:
    units: list[ExtractionUnit] = []
    for root_id in roots:
        partitions = _partition_subtree(root_id, nodes, max_chars)
        if len(partitions) == 1:
            units.append(
                ExtractionUnit(root_id, root_id, tuple(partitions[0]), ordinals.get(root_id, 0))
            )
            continue
        for part, part_ids in enumerate(partitions, start=1):
            membership = hashlib.sha256("\0".join(part_ids).encode()).hexdigest()[:8]
            units.append(
                ExtractionUnit(
                    unit_id=f"{root_id}#part-{part:02d}-{membership}",
                    root_id=root_id,
                    node_ids=tuple(part_ids),
                    ordinal=ordinals.get(root_id, 0),
                    part=part,
                )
            )
    return units


def extraction_units(
    parsed: dict[str, Any],
    phase: Phase,
    *,
    limit: int | None = None,
    max_chars: int = 8_000,
) -> list[ExtractionUnit]:
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    document = parsed["document"]
    short_name = str(document.get("shortName", "")).upper()
    profile = _bootstrap_profiles().get(short_name, {})
    bootstrap_articles = set(profile.get("articles", ["1", "2", "3"]))
    bootstrap_annexes = set(profile.get("annexes", []))
    nodes, ordinals, source_order = _ordered_nodes(parsed)
    article_roots = [node_id for node_id, node in nodes.items() if node.get("ptype") == "article"]
    annex_nodes = [node_id for node_id, node in nodes.items() if node.get("ptype") == "annex"]
    annex_roots: list[str] = []
    annex_subunits: list[str] = []
    targeted_annex_subunits: set[str] = set()
    for annex_id in annex_nodes:
        children = [str(child) for child in nodes[annex_id].get("children", [])]
        grouped_children = [
            child_id
            for child_id in children
            if child_id in nodes and nodes[child_id].get("ptype") in ANNEX_GROUP_TYPES
        ]
        if grouped_children:
            annex_subunits.extend(grouped_children)
            if _is_annex_target(nodes[annex_id], bootstrap_annexes):
                targeted_annex_subunits.update(grouped_children)
        else:
            annex_roots.append(annex_id)
    candidate_roots = sorted(
        article_roots + annex_subunits + annex_roots,
        key=lambda node_id: source_order.get(node_id, 0),
    )

    selected_bootstrap = {
        node_id
        for node_id in candidate_roots
        if (
            nodes[node_id].get("ptype") == "article"
            and str(nodes[node_id].get("local_id", "")) in bootstrap_articles
        )
        or node_id in targeted_annex_subunits
        or (
            nodes[node_id].get("ptype") == "annex"
            and _is_annex_target(nodes[node_id], bootstrap_annexes)
        )
        or "definition" in str(nodes[node_id].get("heading", "")).casefold()
    }
    if phase == "bootstrap":
        selected_roots = [node_id for node_id in candidate_roots if node_id in selected_bootstrap]
    else:
        selected_roots = [
            node_id for node_id in candidate_roots if node_id not in selected_bootstrap
        ]
    units = _units_for_roots(selected_roots, nodes, ordinals, max_chars)
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be positive")
        units = units[:limit]
    return units
