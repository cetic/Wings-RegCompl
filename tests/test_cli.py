from __future__ import annotations

import json
from pathlib import Path

from regcomply.cli_extract import main as extract_main
from regcomply.cli_parse import main as parse_main

FIXTURE = Path(__file__).parent / "fixtures" / "test_act.fmx.xml"


def test_parse_cli_writes_schema_valid_formex_document(tmp_path: Path) -> None:
    output = tmp_path / "parsed.json"

    result = parse_main(
        [
            str(FIXTURE),
            "--short-name",
            "TEST",
            "--identifier",
            "Test act",
            "--title",
            "Test act",
            "--doc-type",
            "Regulation",
            "--output",
            str(output),
        ]
    )

    assert result == 0
    parsed = json.loads(output.read_text(encoding="utf-8"))
    assert parsed["document"]["sourceFormat"] == "fmx"
    assert parsed["document"]["parser"] == "eurlex_fmx_parser"
    assert parsed["report"]["errors"] == []
    assert "test:art_1" in {node["id"] for node in parsed["nodes"]}


def test_extract_plan_only_does_not_require_model_credentials(tmp_path: Path, capsys) -> None:
    parsed_path = tmp_path / "parsed.json"
    assert (
        parse_main(
            [
                str(FIXTURE),
                "--short-name",
                "TEST",
                "--identifier",
                "Test act",
                "--title",
                "Test act",
                "--doc-type",
                "Regulation",
                "--output",
                str(parsed_path),
            ]
        )
        == 0
    )

    result = extract_main(
        [
            str(parsed_path),
            "--output-dir",
            str(tmp_path / "packages"),
            "--phase",
            "all",
            "--plan-only",
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "bootstrap: 1 unit(s)" in output
    assert "test:art_1" in output
    assert "main: 0 unit(s)" in output
