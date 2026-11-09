# RegComply

File-based command-line tools for parsing EU regulatory sources and extracting structured requirements. The project runs independently and does not require a web service, database, or container stack.

## Features

- Parse EUR-Lex HTML, browser-saved EUR-Lex source-view HTML, Formex XML, and PDF into schema-validated parsed-document JSON.
- Extract bootstrap and main provision packages from parsed JSON.
- Validate package structure, evidence quotes, references, and applicability conditions.
- Use Gemini for cloud extraction or Ollama for local extraction.
- Run an extraction plan without making model calls.

## Requirements

- Python 3.12, 3.13, or 3.14.
- Poppler command-line tools (`pdftotext` and `pdfinfo`) for PDF parsing. On macOS: `brew install poppler`.
- For cloud extraction, a Google API key and network access.
- For local extraction, Ollama running and the selected model already downloaded.

## Install

From this directory:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev]'
```

The install adds `regcomply-parse` and `regcomply-extract` commands. You can also use the Python modules directly or invoke the wrapper scripts in this directory.

For environment configuration, copy `.env.example` to `.env`, edit it locally, then load it into the shell before running commands:

```sh
cp .env.example .env
set -a
. ./.env
set +a
```

The project intentionally does not auto-load `.env`; credentials stay under the operator's control. Never commit `.env` or API keys.

## Ontology

The RegKG ontology is included under `ontology/`. `regkg.ttl` is authoritative; `regkg-taxonomy.md` is a generated human-readable reference and should not be edited directly. To regenerate it, install the optional ontology dependency and run:

```sh
.venv/bin/python -m pip install -e '.[ontology]'
cd ontology && ../.venv/bin/python generate_taxonomy.py
```

The ontology describes the domain model. The current CLI parser and extraction workflow do not require it at runtime.

## Parse

```sh
regcomply-parse ./sources/dsa.html \
  --short-name DSA \
  --identifier '(EU) 2022/2065' \
  --title 'Digital Services Act' \
  --doc-type Regulation \
  --output ./work/dsa.parsed.json
```

The input format is inferred from `.pdf`, `.html` / `.htm`, or `.xml` / `.fmx`. Override it with `--format` when necessary. Parsed output includes the source hash, parser report, and schema metadata.

Parsing licensed standards stores their full text in the parsed JSON. It is blocked by default. Set `LICENSED_STANDARD_STORAGE_ALLOWED=true` only when you have permission to store that content.

## Extract

Inspect planned units without invoking a model:

```sh
regcomply-extract ./work/dsa.parsed.json \
  --output-dir ./work/dsa-packages \
  --phase all \
  --limit 3 \
  --plan-only
```

Run extraction after reviewing the plan:

```sh
regcomply-extract ./work/dsa.parsed.json \
  --output-dir ./work/dsa-packages \
  --phase all \
  --route auto
```

Phases are `bootstrap`, `main`, or `all`. Routes are `auto`, `local`, or `cloud`. Auto uses cloud extraction for non-standard regulations when `GOOGLE_API_KEY` is set; otherwise it selects local Ollama. Licensed standard types always use local extraction. `--limit` applies separately to each selected phase. `--model` overrides the model name.

Each unit is written to its own JSON file. Invalid units are written as `.invalid.json` and contain validation errors plus the last generated package, when available. Valid packages in the output directory are reused as catalogs on later runs. Review all generated material before relying on it; model output is not legal advice.

## Tests and lint

```sh
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
```

PDF parser tests require Poppler. CI runs offline unit tests using a synthetic Formex XML fixture; it does not fetch or include licensed source documents.

## Project contents

- `src/regcomply/`: installable CLI and parser/extraction implementation.
- `ontology/`: RegKG ontology source, generated taxonomy, and generator.
- `tests/`: offline tests for CLI behavior and package/unit planning.
- `UPSTREAM.md`: component map and maintenance notes.

Contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow. This project is licensed under Apache-2.0; see [LICENSE](LICENSE) and [NOTICE](NOTICE). Redistributors must preserve applicable copyright and attribution notices as described in the license.

## Acknowledgements

Contributors: Thierry Noundou Njike and Abiola Paterne Chokki.

This project was funded by the WINGS4 project.
