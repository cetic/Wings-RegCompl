# Component maintenance map

The installable RegComply package keeps its parser, extraction rules, schemas, and prompts together under `src/regcomply/`. This map identifies the components that should be reviewed together when changing parser or extraction behavior.

| Component | Related files | Notes |
|---|---|---|
| Deterministic parsers | `parsing/adapter.py`, `parsing/reference/` | HTML, PDF, and Formex parsing share the parsed-document output contract. |
| Parsed-document contract | `parsing/schemas/parsed_document.schema.json` | Validate whenever parser output changes. |
| Extraction context and units | `extraction/context.py`, `extraction/units.py`, `extraction/bootstrap_profiles.json` | Controls model context and provision unit selection. |
| Package contract | `extraction/models.py`, `extraction/schemas/provision_package.schema.json`, `extraction/validate.py` | Keep runtime models and JSON Schema aligned. |
| Model generation | `extraction/agent.py`, `extraction/prompts/` | Prompt version is recorded in generated packages. |
| CLI runtime | `config.py`, `extraction/runtime.py`, `cli_*.py` | Keep the commands independent of a web app or database. |
| RegKG ontology | `ontology/regkg.ttl`, `ontology/regkg-taxonomy.md`, `ontology/generate_taxonomy.py` | Turtle is authoritative; regenerate the Markdown taxonomy with the included script. |

When changing a component, update its related contract, tests, and documentation together. Keep the command-line package independent of services that are not needed for file-based parsing or extraction. Add a row here when introducing a new major component.
