# Contributing

Contributions are welcome, including parser fixes, format support, extraction improvements, tests, and documentation.

## Development setup

From the project root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
```

## Pull requests

- For a substantial change, open an issue first to discuss the behavior and approach.
- Keep changes focused and add or update offline tests for behavior changes.
- Run the test and lint commands above before submitting.
- Update the README when changing CLI arguments, supported formats, or setup requirements.
- If changing a vendored parser, schema, or extraction prompt, update `UPSTREAM.md` and the related tests.
- Never include API keys, licensed source documents, private documents, generated parsed files, or model output containing protected text.
- Do not commit `.env`, virtual environments, caches, or build outputs.

The maintainers will review contributions for correctness, reproducibility, licensing, and compatibility with supported Python versions.
