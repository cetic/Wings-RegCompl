from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from typing import Any

from .agent import PROMPT_VERSION
from .models import ProvisionPackage

MAX_GENERATION_ATTEMPTS = 3
REQUIRED_MODALITY = {
    "Obligation": "shall",
    "Prohibition": "shall_not",
    "Permission": "may",
    "Recommendation": "should",
    "LegalEffect": "deemed",
}


def _normalize_question_ids(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"id", "q"} and isinstance(item, str) and item.startswith("kg:question."):
                value[key] = f"kg:q.{item.removeprefix('kg:question.')}"
            else:
                _normalize_question_ids(item)
    elif isinstance(value, list):
        for item in value:
            _normalize_question_ids(item)


def prepare_package(
    generated: dict[str, Any],
    parsed: dict[str, Any],
    unit: Any,
    *,
    model_name: str,
    attempts: int,
) -> dict[str, Any]:
    metadata = generated.setdefault("extraction", {})
    if not isinstance(metadata, dict):
        raise ValueError("extraction metadata must be an object")
    metadata.update(
        {
            "model": model_name,
            "promptVersion": PROMPT_VERSION,
            "timestamp": datetime.now(UTC).isoformat(),
            "attempts": attempts,
        }
    )
    document = parsed["document"]
    generated.setdefault(
        "document",
        {
            "id": document["id"],
            "versionId": document.get("versionId")
            or f"{document['id']}:v-{document['sourceHash'][:16]}",
            "shortName": document["shortName"],
        },
    )
    for key in ("documentScope", "applicability", "askIf"):
        if generated.get(key) is None or generated.get(key) == {}:
            generated.pop(key, None)
    for key in ("statements", "questions", "provisions"):
        for item in generated.get(key, []):
            if isinstance(item, dict):
                for condition_key in ("applicability", "askIf"):
                    if item.get(condition_key) is None or item.get(condition_key) == {}:
                        item.pop(condition_key, None)
    _normalize_question_ids(generated)
    short_name = str(document["shortName"]).casefold()
    for statement in generated.get("statements", []):
        if not isinstance(statement, dict):
            continue
        required_modality = REQUIRED_MODALITY.get(str(statement.get("type", "")))
        if required_modality:
            statement["modality"] = required_modality
        statement_id = statement.get("id")
        prefix = f"{short_name}:"
        if isinstance(statement_id, str) and statement_id.casefold().startswith(prefix):
            rest = statement_id[len(prefix) :]
            statement["id"] = f"{short_name}:{rest if rest.startswith('st.') else 'st.' + rest}"
    return ProvisionPackage.model_validate(generated).model_dump(mode="json", exclude_unset=True)


def propose_unknown_topics(package: dict[str, Any], catalog_ids: set[str]) -> None:
    proposed = package.setdefault("topicsProposed", [])
    proposed_ids = {
        str(item["id"]) for item in proposed if isinstance(item, dict) and item.get("id")
    }
    for statement in package.get("statements", []):
        if not isinstance(statement, dict):
            continue
        for topic_id in statement.get("topics", []):
            if not isinstance(topic_id, str) or topic_id in catalog_ids or topic_id in proposed_ids:
                continue
            namespace, separator, slug = topic_id.partition(":topic.")
            if not separator or not namespace or not re.fullmatch(r"[a-z0-9-]+", slug):
                continue
            proposed.append({"id": topic_id, "label": slug.replace("-", " ").title()})
            proposed_ids.add(topic_id)


def source_provisions(parsed: dict[str, Any], unit: Any) -> list[dict[str, Any]]:
    node_map = {str(node["id"]): node for node in parsed["nodes"]}
    return [node_map[node_id] for node_id in unit.node_ids if node_id in node_map]


def safe_generation_error(error: Exception, parsed: dict[str, Any]) -> str:
    details = str(error).splitlines()[0] if str(error) else "no details provided"
    for node in parsed.get("nodes", []):
        source_text = str(node.get("text", ""))
        if len(source_text) >= 24:
            details = details.replace(source_text, "[source text omitted]")
    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if api_key:
        details = details.replace(api_key, "[credential omitted]")
    return f"generation failed: {type(error).__name__}: {details[:400]}"
