#!/usr/bin/env python3
"""Extract regulation packages from parsed JSON without the API or database job queue."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from pydantic import ValidationError  # noqa: E402

from .config import settings
from .extraction.agent import ADKPackageGenerator
from .extraction.context import build_extraction_context
from .extraction.runtime import (
    MAX_GENERATION_ATTEMPTS,
    prepare_package,
    propose_unknown_topics,
    safe_generation_error,
    source_provisions,
)
from .extraction.units import Phase, extraction_units
from .extraction.validate import validate_package

LICENSED_TYPES = {
    "InternationalStandard",
    "EuropeanStandard",
    "TechnicalSpecification",
    "TechnicalReport",
}
CATALOG_FIELDS = {
    "definitions": "definitions",
    "roles": "roles",
    "events": "events",
    "artefacts": "artefacts",
    "topicsProposed": "topics",
    "questions": "questions",
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("parsed_document", type=Path, help="Schema-valid parsed-document JSON")
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="Directory for package JSON files"
    )
    parser.add_argument("--phase", choices=("bootstrap", "main", "all"), default="all")
    parser.add_argument("--limit", type=int, help="Maximum units per phase")
    parser.add_argument("--max-unit-chars", type=int, default=settings.extraction_max_unit_chars)
    parser.add_argument("--route", choices=("auto", "local", "cloud"), default="auto")
    parser.add_argument("--model", help="Override the configured local or cloud model")
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="List extraction units without calling a model",
    )
    return parser


def _catalog(
    packages: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], set[str], dict[str, dict[str, Any]]]:
    catalog: dict[str, list[dict[str, Any]]] = defaultdict(list)
    catalog_ids: set[str] = set()
    for package in packages:
        for field, group in CATALOG_FIELDS.items():
            for item in package.get(field, []):
                if item not in catalog[group]:
                    catalog[group].append(item)
                if isinstance(item, dict):
                    for key in ("id", "termId"):
                        if item.get(key):
                            catalog_ids.add(str(item[key]))
    questions = {
        str(item["id"]): dict(item)
        for item in catalog.get("questions", [])
        if isinstance(item, dict) and item.get("id")
    }
    return dict(catalog), catalog_ids, questions


def _load_existing_packages(directory: Path) -> list[dict[str, Any]]:
    packages: list[dict[str, Any]] = []
    for path in directory.glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(item, dict) and item.get("packageVersion") == "1.0":
            packages.append(item)
    return packages


def _route(document_type: str, requested: str) -> tuple[bool, str]:
    licensed = document_type in LICENSED_TYPES
    if requested == "cloud" and licensed:
        raise ValueError("Licensed standards must use local extraction")
    local_only = requested == "local" or licensed
    if requested == "auto" and not licensed:
        local_only = not bool(os.environ.get("GOOGLE_API_KEY"))
    model = settings.local_llm_model if local_only else settings.gemini_model
    return local_only, model


def _unit_filename(short_name: str, phase: str, unit_id: str) -> str:
    safe_unit = re.sub(r"[^A-Za-z0-9._-]+", "_", unit_id)
    return f"{short_name.casefold()}-{phase}-{safe_unit}.json"


def _extract_phase(
    parsed: dict[str, Any],
    phase: Phase,
    *,
    output_dir: Path,
    limit: int | None,
    max_unit_chars: int,
    generator: ADKPackageGenerator,
    model_name: str,
    local_only: bool,
    packages: list[dict[str, Any]],
) -> tuple[int, int]:
    units = extraction_units(parsed, phase, limit=limit, max_chars=max_unit_chars)
    valid_count = 0
    invalid_count = 0
    for index, unit in enumerate(units, start=1):
        catalog, catalog_ids, catalog_questions = _catalog(packages)
        context = build_extraction_context(parsed, unit, catalog=catalog)
        feedback: list[str] = []
        package: dict[str, Any] | None = None
        errors: list[str] = []
        for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
            try:
                generated = generator.generate(
                    context,
                    model_name=model_name,
                    local_only=local_only,
                    validation_feedback=feedback,
                )
                package = prepare_package(
                    generated,
                    parsed,
                    unit,
                    model_name=model_name,
                    attempts=attempt,
                )
                propose_unknown_topics(package, catalog_ids)
                if package["document"]["id"] != parsed["document"]["id"]:
                    errors = ["document.id does not match the parsed source"]
                elif package["unit"]["provisionId"] != unit.root_id:
                    errors = ["unit.provisionId does not match the selected unit"]
                else:
                    expected_ids = set(unit.node_ids)
                    actual_ids = {item["id"] for item in package["provisions"]}
                    if actual_ids != expected_ids or len(package["provisions"]) != len(
                        expected_ids
                    ):
                        errors = ["provisions must include exactly the selected unit nodes"]
                    else:
                        errors = validate_package(
                            package,
                            source_provisions(parsed, unit),
                            catalog_ids=catalog_ids,
                            catalog_questions=catalog_questions,
                        )
            except ValidationError as error:
                errors = [
                    "output schema: "
                    + "; ".join(
                        f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
                        for item in error.errors(include_url=False)
                    )
                ]
            except Exception as error:
                errors = [safe_generation_error(error, parsed)]
            if not errors:
                break
            feedback = errors

        if errors or package is None:
            invalid_count += 1
            result = {
                "status": "invalid",
                "phase": phase,
                "unitId": unit.unit_id,
                "errors": errors or ["No package returned"],
                "package": package,
            }
            target = output_dir / _unit_filename(
                str(parsed["document"]["shortName"]), phase, unit.unit_id
            )
            target = target.with_suffix(".invalid.json")
            target.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            detail = errors[-1] if errors else "no package"
            print(f"[{phase} {index}/{len(units)}] INVALID {unit.unit_id}: {detail}")
            continue

        valid_count += 1
        packages.append(package)
        target = output_dir / _unit_filename(
            str(parsed["document"]["shortName"]), phase, unit.unit_id
        )
        target.write_text(
            json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"[{phase} {index}/{len(units)}] OK {unit.unit_id}")
    return valid_count, invalid_count


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    parsed_path = args.parsed_document.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    try:
        parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"Could not read parsed document: {error}", file=sys.stderr)
        return 2
    if not isinstance(parsed, dict) or not isinstance(parsed.get("document"), dict):
        print("Input is not a parsed-document JSON object", file=sys.stderr)
        return 2

    document_type = str(parsed["document"].get("docType", ""))
    phases: list[Phase] = ["bootstrap", "main"] if args.phase == "all" else [args.phase]
    if args.plan_only:
        for phase in phases:
            units = extraction_units(
                parsed,
                phase,
                limit=args.limit,
                max_chars=args.max_unit_chars,
            )
            print(f"{phase}: {len(units)} unit(s)")
            for unit in units:
                print(f"  {unit.unit_id} ({len(unit.node_ids)} provisions)")
        return 0

    try:
        local_only, default_model = _route(document_type, args.route)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    model_name = args.model or default_model
    generator = ADKPackageGenerator()
    try:
        generator.preflight(model_name, local_only=local_only)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    packages = _load_existing_packages(output_dir)
    valid_total = 0
    invalid_total = 0
    for phase in phases:
        valid, invalid = _extract_phase(
            parsed,
            phase,
            output_dir=output_dir,
            limit=args.limit,
            max_unit_chars=args.max_unit_chars,
            generator=generator,
            model_name=model_name,
            local_only=local_only,
            packages=packages,
        )
        valid_total += valid
        invalid_total += invalid
    print(f"Finished: {valid_total} valid packages, {invalid_total} invalid packages")
    print(f"Output: {output_dir}")
    return 1 if invalid_total else 0


if __name__ == "__main__":
    raise SystemExit(main())
