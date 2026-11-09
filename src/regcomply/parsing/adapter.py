import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker
from lxml import etree

from .reference import eu_act_pdf_parser, eurlex_fmx_parser, eurlex_html_parser

PARSER_VERSION = "eu-act-parser-v2.6"
SCHEMA_PATH = Path(__file__).parent / "schemas" / "parsed_document.schema.json"
_PARSED_DOCUMENT_SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
_VALIDATOR = Draft202012Validator(
    _PARSED_DOCUMENT_SCHEMA,
    format_checker=FormatChecker(),
)


class ParseFailure(ValueError):
    pass


class ParsedDocumentInvalid(ParseFailure):
    def __init__(self, validation_errors: list[str]) -> None:
        self.validation_errors = validation_errors
        super().__init__("Parsed output does not satisfy the ParsedDocument schema")


def read_pdf_title(source_path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["pdfinfo", "-enc", "UTF-8", str(source_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"(?m)^Title:\s*(.+?)\s*$", result.stdout)
    title = match.group(1).strip() if match else ""
    return title or None


def normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def run_reference_parser(source_path: Path, short_name: str, source_format: str) -> dict[str, Any]:
    if source_format not in {"pdf", "html", "fmx"}:
        raise ParseFailure(f"Unsupported source format: {source_format}")

    with tempfile.TemporaryDirectory(prefix="regcomply-parse-") as temporary_directory:
        temp_path = Path(temporary_directory)
        output_path = temp_path / "parsed.json"
        if source_format == "html":
            _, parser_output = eurlex_html_parser.run(
                str(source_path), short_name, str(output_path)
            )
        elif source_format == "fmx":
            try:
                _, parser_output = eurlex_fmx_parser.run(
                    str(source_path), short_name, str(output_path)
                )
            except (OSError, ValueError, etree.XMLSyntaxError) as error:
                raise ParseFailure(f"Could not parse EUR-Lex Formex XML: {error}") from error
        else:
            text_path = temp_path / "source.txt"
            try:
                subprocess.run(
                    ["pdftotext", "-layout", str(source_path), str(text_path)],
                    check=True,
                    capture_output=True,
                    timeout=300,
                )
            except FileNotFoundError as error:
                raise ParseFailure("pdftotext is unavailable in the parser runtime") from error
            except subprocess.CalledProcessError as error:
                details = error.stderr.decode("utf-8", errors="replace")[:1000]
                raise ParseFailure(f"Could not extract PDF text: {details}") from error
            except subprocess.TimeoutExpired as error:
                raise ParseFailure("PDF text extraction timed out") from error

            _, parser_output = eu_act_pdf_parser.run(
                str(text_path),
                short_name,
                str(output_path),
                str(source_path),
            )

        return cast(dict[str, Any], json.loads(output_path.read_text(encoding="utf-8")))


def build_parsed_document(
    parser_output: dict[str, Any],
    *,
    doc_id: str,
    version_id: str | None,
    short_name: str,
    identifier: str,
    title: str,
    doc_type: str,
    is_binding: bool,
    eli_uri: str | None,
    publication_date: str | None,
    source_format: str,
    source_file: str,
    source_hash: str,
    detected_source_title: str | None = None,
) -> dict[str, Any]:
    report = parser_output.get("report", {})
    canonical_eli = report.get("canonical")
    if eli_uri and canonical_eli and canonical_eli.rstrip("/") != eli_uri.rstrip("/"):
        report.setdefault("errors", []).append(
            "EUR-Lex canonical ELI does not match the declared ELI URI"
        )
    detected_title = detected_source_title or report.get("source_title")
    is_eurlex_file_title = bool(
        detected_title and re.fullmatch(r"L_\d{9}[A-Z]{2}\.\d+\.fmx\.xml", detected_title)
    )
    if (
        detected_title
        and not is_eurlex_file_title
        and normalize_title(title) not in normalize_title(detected_title)
    ):
        report.setdefault("errors", []).append(
            "Source title does not match the declared document title"
        )

    document = {
        "id": doc_id,
        "shortName": short_name,
        "identifier": identifier,
        "title": title,
        "docType": doc_type,
        "isBinding": is_binding,
        "eliUri": eli_uri,
        "publicationDate": publication_date,
        "sourceFormat": source_format,
        "sourceFile": source_file,
        "sourceHash": source_hash,
        "parser": {
            "fmx": "eurlex_fmx_parser",
            "html": "eurlex_html_parser",
            "pdf": "eu_act_pdf_parser",
        }[source_format],
        "parserVersion": PARSER_VERSION,
    }
    if version_id:
        document["versionId"] = version_id
    parsed = {"document": document, **parser_output}
    errors = sorted(_VALIDATOR.iter_errors(parsed), key=lambda error: list(error.absolute_path))
    if errors:
        details = [
            f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
            for error in errors
        ]
        raise ParsedDocumentInvalid(details)
    return parsed


def normalize_text(value: str) -> str:
    value = value.replace("\u00ad", "")
    value = value.translate(str.maketrans("‘’“”–—−", "''\"\"---"))
    value = re.sub(r"\s+", " ", value).strip()
    return re.sub(r"\s*([,;().:])\s*", r"\1", value)


def compare_parsed_documents(
    first: dict[str, Any],
    second: dict[str, Any],
) -> dict[str, Any]:
    first_nodes = {node["citation"]: node for node in first["nodes"]}
    second_nodes = {node["citation"]: node for node in second["nodes"]}
    shared_citations = first_nodes.keys() & second_nodes.keys()

    def normalized_provision_text(node: dict[str, Any]) -> str:
        return normalize_text(" ".join((node.get("heading", ""), node.get("text", ""))))

    def provision_text(node: dict[str, Any]) -> str:
        return " ".join((node.get("heading", ""), node.get("text", ""))).strip()

    identical_text = sum(
        normalized_provision_text(first_nodes[citation])
        == normalized_provision_text(second_nodes[citation])
        for citation in shared_citations
    )
    return {
        "firstSource": first["document"]["sourceFile"],
        "secondSource": second["document"]["sourceFile"],
        "firstNodeCount": len(first_nodes),
        "secondNodeCount": len(second_nodes),
        "sharedNodeCount": len(shared_citations),
        "firstOnly": sorted(first_nodes.keys() - second_nodes.keys()),
        "secondOnly": sorted(second_nodes.keys() - first_nodes.keys()),
        "identicalNormalizedTextCount": identical_text,
        "textDifferences": [
            {
                "citation": citation,
                "firstId": first_nodes[citation]["id"],
                "secondId": second_nodes[citation]["id"],
                "first": provision_text(first_nodes[citation]),
                "second": provision_text(second_nodes[citation]),
            }
            for citation in sorted(shared_citations)
            if normalized_provision_text(first_nodes[citation])
            != normalized_provision_text(second_nodes[citation])
        ],
    }
