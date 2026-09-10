# CRA Knowledge Graph Agents

Multi-agent system built with [Google Agent Development Kit (ADK)](https://google.github.io/adk-docs/) that automatically parses EU Cyber Resilience Act articles into a Neo4j knowledge graph.

## Architecture

```
┌─────────────────────────────────────────────────┐
│          cra_orchestrator (root_agent)           │
│         Conversational — routes requests         │
│                                                  │
│  ┌──────────────┐ ┌────────────┐ ┌────────────┐ │
│  │ parser_agent  │ │ ingestion  │ │  query     │ │
│  │              │ │  _agent    │ │  _agent    │ │
│  │ Reads CRA    │ │ Saves JSON │ │ Translates │ │
│  │ article text │ │ & ingests  │ │ questions  │ │
│  │ → structured │ │ into Neo4j │ │ → Cypher   │ │
│  │ JSON         │ │            │ │ → results  │ │
│  └──────┬───────┘ └─────┬──────┘ └─────┬──────┘ │
│         │               │              │         │
│  ┌──────┴───────┐ ┌─────┴──────┐ ┌─────┴──────┐ │
│  │ cra_tools    │ │ neo4j_tools│ │ neo4j_tools│ │
│  │ read_article │ │ save_json  │ │ query_neo4j│ │
│  │ read_annex   │ │ ingest     │ │ get_stats  │ │
│  │ list_articles│ │ get_stats  │ │            │ │
│  └──────────────┘ └────────────┘ └────────────┘ │
└─────────────────────────────────────────────────┘
                         │
                    ┌────┴────┐
                    │  Neo4j  │
                    │  :7687  │
                    └─────────┘
```

## Setup

### 1. Install dependencies

```bash
cd "/Users/tnn/Documents/Documents - lt-cetic-2022/WINGS4/requirement extraction"
source wings4/bin/activate
pip install google-adk python-dotenv neo4j
```

### 2. Configure API key

Edit `cra_agents/.env`:
```
GOOGLE_API_KEY=your-google-api-key-here
```

Get a key at https://aistudio.google.com/apikey

### 3. Start Neo4j

```bash
cd neo4j && docker compose up -d
```

### 4. Run

**Option A — ADK Web UI** (recommended):
```bash
cd "/Users/tnn/Documents/Documents - lt-cetic-2022/WINGS4/requirement extraction"
source wings4/bin/activate
adk web .
```
Then open **http://localhost:8000/dev-ui/** and select **cra_agents** from the app dropdown.

**Option B — CLI**:
```bash
python -m cra_agents
```

## Usage Examples

| Command | What happens |
|---|---|
| "Ingest Article 14" | parser_agent reads Art. 14, extracts JSON → ingestion_agent loads into Neo4j |
| "Ingest Chapter II" | Processes Articles 13–26 one by one |
| "What are the obligations for importers?" | query_agent translates → Cypher → executes → returns table |
| "Show me all actors" | query_agent runs `MATCH (a:Actor) RETURN ...` |
| "Graph stats" | Returns node/relationship counts |

## File Structure

```
cra_agents/
├── __init__.py
├── __main__.py          # CLI entry point
├── agent.py             # Root orchestrator agent
├── .env                 # API key config
├── sub_agents/
│   ├── parser_agent.py  # Article → structured JSON
│   ├── ingestion_agent.py # JSON → Neo4j
│   └── query_agent.py   # Natural language → Cypher
└── tools/
    ├── cra_tools.py     # read_article, list_articles, read_annex
    └── neo4j_tools.py   # save_json, ingest, query, stats
```

## JSON Schema

Each parsed article produces a JSON with:
- **metadata** — article ID, title, chapter, paragraph count
- **nodes** — entities with label/sub_label from CRA ontology (11 top-level classes)
- **relationships** — typed edges with paragraph references
- **obligations** — structured duties per paragraph (actor, action, trigger, deadline)
- **cross_references** — links to other articles/annexes

See `response.json` for a complete example (Article 13).
