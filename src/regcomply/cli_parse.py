#!/usr/bin/env python3
"""Parse an EU legal source file into a schema-validated parsed-document JSON file."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from .parsing.adapter import (
    ParsedDocumentInvalid,
    ParseFailure,
    build_parsed_document,
    read_pdf_title,
    run_reference_parser,
)

DOC_TYPES = (
    "Regulation",
    "Directive",
    "Decision",
    "DelegatedAct",
    "ImplementingAct",
    "NationalLaw",
    "InternationalStandard",
    "EuropeanStandard",
    "TechnicalSpecification",
    "TechnicalReport",
    "Guidance",
    "CertificationScheme",
    "CommonSpecification",
)
LICENSED_TYPES = {
    "InternationalStandard",
    "EuropeanStandard",
    "TechnicalSpecification",
    "TechnicalReport",
}


def _source_format(source: Path, requested: str | None) -> str:
    if requested:
        return requested
    suffix = source.suffix.casefold()
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix in {".xml", ".fmx"}:
        return "fmx"
    raise ValueError(f"Cannot infer source format from {source.name!r}; use --format")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Input PDF, EUR-Lex HTML, or Formex XML")
    parser.add_argument("--short-name", required=True, help="Document prefix, for example DSA")
    parser.add_argument("--identifier", required=True, help="Official act identifier")
    parser.add_argument("--title", required=True, help="Official document title")
    parser.add_argument("--doc-type", required=True, choices=DOC_TYPES)
    parser.add_argument("--output", required=True, type=Path, help="Parsed JSON output path")
    parser.add_argument(
        "--format", choices=("pdf", "html", "fmx"), help="Override format detection"
    )
    parser.add_argument("--eli-uri", help="Optional ELI URI")
    parser.add_argument("--publication-date", type=date.fromisoformat)
    parser.add_argument("--not-binding", action="store_true", help="Mark the document non-binding")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    source = args.source.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if not source.is_file():
        print(f"Input file does not exist: {source}", file=sys.stderr)
        return 2
    if args.doc_type in LICENSED_TYPES and not _licensed_storage_allowed():
        print(
            "Parsing this document type stores full text. Set "
            "LICENSED_STANDARD_STORAGE_ALLOWED=true only when you have permission.",
            file=sys.stderr,
        )
        return 2
    try:
        source_format = _source_format(source, args.format)
        raw = run_reference_parser(source, args.short_name, source_format)
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        parsed: dict[str, Any] = build_parsed_document(
            raw,
            doc_id=f"kg:{args.short_name.casefold()}",
            version_id=None,
            short_name=args.short_name,
            identifier=args.identifier,
            title=args.title,
            doc_type=args.doc_type,
            is_binding=not args.not_binding,
            eli_uri=args.eli_uri,
            publication_date=args.publication_date.isoformat() if args.publication_date else None,
            source_format=source_format,
            source_file=source.name,
            source_hash=source_hash,
            detected_source_title=read_pdf_title(source) if source_format == "pdf" else None,
        )
    except (ParseFailure, ParsedDocumentInvalid, ValueError, OSError) as error:
        print(f"Parse failed: {error}", file=sys.stderr)
        if isinstance(error, ParsedDocumentInvalid):
            for detail in error.validation_errors:
                print(f"- {detail}", file=sys.stderr)
        return 1

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(parsed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = parsed["report"]
    print(f"Parsed {source.name} as {source_format}: {len(parsed['nodes'])} provisions")
    print(f"Output: {output}")
    print(
        f"Report: {len(report.get('errors', []))} errors, "
        f"{len(report.get('warnings', []))} warnings"
    )
    return 0


def _licensed_storage_allowed() -> bool:
    import os

    return os.environ.get("LICENSED_STANDARD_STORAGE_ALLOWED", "false").casefold() == "true"


if __name__ == "__main__":
    raise SystemExit(main())
