import json
from typing import Any

from .units import ExtractionUnit


def build_extraction_context(
    parsed: dict[str, Any],
    unit: ExtractionUnit,
    *,
    catalog: dict[str, list[dict[str, Any]]] | None = None,
) -> str:
    document = parsed["document"]
    all_nodes = {str(node["id"]): node for node in parsed["nodes"]}
    selected_ids = set(unit.node_ids)
    node_rows: list[dict[str, Any]] = []
    for node_id in unit.node_ids:
        node = all_nodes[node_id]
        node_rows.append(
            {
                "id": node_id,
                "citation": node.get("citation", ""),
                "ptype": node.get("ptype", ""),
                "localId": node.get("local_id", ""),
                "parent": node.get("parent") if node.get("parent") in selected_ids else None,
                "heading": node.get("heading", ""),
                "text": node.get("text", ""),
                "isNormative": bool(node.get("is_normative", False)),
                "children": [
                    str(child) for child in node.get("children", []) if str(child) in selected_ids
                ],
            }
        )
    citations = {
        str(all_nodes[node_id].get("citation", ""))
        for node_id in selected_ids
        if node_id in all_nodes
    }
    application_dates = [
        item
        for item in parsed.get("application_dates", [])
        if str(item.get("provision", "")) in citations
        or str(item.get("provision", "")) in selected_ids
    ]
    unit_node = all_nodes[unit.root_id]
    context = {
        "document": {
            "id": document["id"],
            "versionId": document.get("versionId")
            or f"{document['id']}:v-{document['sourceHash'][:16]}",
            "shortName": document["shortName"],
            "identifier": document.get("identifier", ""),
            "title": document.get("title", ""),
            "docType": document.get("docType", ""),
            "isBinding": document.get("isBinding", False),
            "publicationDate": document.get("publicationDate"),
        },
        "unit": {
            "provisionId": unit.root_id,
            "unitId": unit.unit_id,
            "citation": unit_node.get("citation", ""),
            "ptype": unit_node.get("ptype", ""),
            "heading": unit_node.get("heading", ""),
            "part": unit.part,
        },
        "provisions": node_rows,
        "definitionsInScope": (catalog or {}).get("definitions", []),
        "roles": (catalog or {}).get("roles", []),
        "questions": (catalog or {}).get("questions", []),
        "events": (catalog or {}).get("events", []),
        "artefacts": (catalog or {}).get("artefacts", []),
        "topics": (catalog or {}).get("topics", []),
        "applicationDates": application_dates,
    }
    return json.dumps(context, ensure_ascii=False, separators=(",", ":"))
