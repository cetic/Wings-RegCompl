# RegComply

RegComply turns the EU Cyber Resilience Act (CRA) into a Neo4j knowledge
graph and uses it to generate product-specific compliance assessments.

The project currently supports **only the Cyber Resilience Act**, Regulation
(EU) 2024/2847. Part-IS artifacts in the repository are experimental and are
not part of the supported workflow.

## What runs

Docker Compose starts the complete application:

| Service | URL | Purpose |
|---|---|---|
| Frontend | <http://localhost> | Main RegComply application |
| Backend | <http://localhost:8000/docs> | FastAPI API and interactive documentation |
| ADK web | <http://localhost:8080> | Agent development UI |
| Neo4j | <http://localhost:7474> | Knowledge graph browser |
| Ollama | <http://localhost:11434> | Local language and embedding models |

Application data is persisted in Docker volumes. Generated CRA article JSON
and batch logs are written under `outputs/` on the host.

## Prerequisites

- Docker Desktop with Docker Compose v2
- At least 10 GB of free disk space for images and local models
- A Google AI API key only when using Gemini offload mode

The first startup can take several minutes because Compose downloads the
language model and embedding model.

## Configure the environment

Create `.env` in the repository root. Do not commit this file.

For local inference with Ollama:

```dotenv
NEO4J_USER=neo4j
NEO4J_PASSWORD=replace-with-a-strong-password
MODEL_TYPE=LOCAL
OLLAMA_MODEL=gemma4:e2b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
GOOGLE_API_KEY=
```

For Gemini offload:

```dotenv
NEO4J_USER=neo4j
NEO4J_PASSWORD=replace-with-a-strong-password
MODEL_TYPE=OFFLOAD
GOOGLE_API_KEY=replace-with-your-google-ai-api-key
GEMINI_MODEL=gemini-2.5-flash
BATCH_MODEL=gemini-2.5-flash-lite
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
```

The runtime maintenance flag must be a file named `maintenance.json` in the
repository root:

```json
{
  "enabled": false
}
```

Set `enabled` to `true` to replace the frontend with the maintenance page.

## Start the application

From the repository root, run:

```bash
docker compose up --build -d
docker compose ps
```

Wait until `neo4j` and `ollama` are healthy. The two `ollama-model-pull`
services should finish with exit code `0`; they are one-time setup jobs and
are not expected to remain running.

Check the application:

```bash
curl -fsS http://localhost/maintenance.json
curl -fsS http://localhost:8000/docs >/dev/null
```

Open <http://localhost/login> and sign in with the initial account:

```text
Username: admin
Password: admin
```

The account is created only when the user table is empty. Change its password
from the profile menu immediately. If the Docker data volume already contains
users, use the password previously assigned to `admin`.

## Create a user

User creation is admin-only and is currently exposed through the API. Log in
as an administrator, capture a bearer token, and register the new account:

```bash
TOKEN=$(curl -fsS -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=admin' \
  --data-urlencode 'password=admin' \
  | python3 -c 'import json, sys; print(json.load(sys.stdin)["access_token"])')

curl -fsS -X POST http://localhost:8000/api/auth/register \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "username": "assessor",
    "password": "replace-with-a-strong-password",
    "full_name": "CRA Assessor",
    "is_admin": false
  }'
```

The response contains the new username, full name, and administrator status.
The new user can then sign in at <http://localhost/login>.

To create another administrator, set `is_admin` to `true`. Use administrator
accounts sparingly because they can manage users and access all products.

## Load the CRA knowledge graph

The source document is
`outputs/CRA_requirements_statemachine.md`. Keep that file in place before
starting ingestion.

1. Sign in to the main application.
2. Open **AI Assistant** in the sidebar.
3. Run a small batch first to verify the model and Neo4j connection:

   ```text
   Ingest CRA articles 1-3
   ```

4. Confirm the result:

   ```text
   Show graph stats
   ```

5. Run the full pipeline with one prompt at a time:

   ```text
   Ingest all CRA articles
   Ingest all CRA recitals
   Ingest all CRA annexes
   ```

Each prompt invokes one batch tool. Articles accept ranges such as `3-10` or
`1,3,5-10`; recitals accept `1-130`; annexes accept Roman numerals such as
`I-III` or `I,III,V`.

Existing parsed JSON is reused by default. Ask the assistant to **force
re-parse** a range when the source Markdown or parsing logic has changed, for
example:

```text
Force re-parse and ingest CRA articles 13-15
```

To load existing JSON without calling the parsing model:

```text
Ingest existing JSON for CRA articles 13-15 without parsing
```

Monitor a batch from another terminal:

```bash
docker compose logs -f backend
```

The batch log is also available at `outputs/batch_progress.log`.

## Run a product assessment

After the graph contains CRA data:

1. Open <http://localhost> and sign in.
2. Select **New Product** from the overview.
3. Keep **Cyber Resilience Act (CRA)** selected.
4. Enter a product name and a detailed technical description, or upload a
   PDF, DOCX, TXT, Markdown, or image specification.
5. Select **Generate Assessment**.
6. Review the classification, applicable obligations, verification questions,
   evidence, and generated report in the assessment workspace.

Better descriptions produce better matching. Include the product's purpose,
network interfaces, deployment environment, user roles, update mechanism,
security features, and whether it performs critical or security-related
functions.

## Common operations

View service status and recent logs:

```bash
docker compose ps
docker compose logs --tail=100 backend
docker compose logs --tail=100 adk
```

Rebuild after changing source code:

```bash
docker compose up --build -d
```

Stop the application without deleting persisted data:

```bash
docker compose down
```

## Troubleshooting

### Frontend fails to mount `maintenance.json`

The host path must be a regular file, not a directory:

```bash
test -f maintenance.json
```

Create it with the JSON shown in the configuration section if it is missing.

### Startup waits for model downloads

Follow the one-time pull jobs:

```bash
docker compose logs -f ollama-model-pull ollama-model-pull-embedding
```

Both jobs should eventually exit with code `0`.

### Login fails with `admin` / `admin`

The default credentials are seeded only into an empty database. Existing
Docker volumes retain password changes and created users across rebuilds.

### Ingestion cannot read the CRA source

Verify that `outputs/CRA_requirements_statemachine.md` exists and that the
`outputs/` directory is mounted into the backend and ADK services:

```bash
docker compose exec backend test -f /app/outputs/CRA_requirements_statemachine.md
docker compose exec adk test -f /app/outputs/CRA_requirements_statemachine.md
```

### Ingestion or assessment returns a model error

For `MODEL_TYPE=LOCAL`, verify Ollama and its models:

```bash
curl -fsS http://localhost:11434/api/tags
docker compose logs --tail=100 ollama backend
```

For `MODEL_TYPE=OFFLOAD`, verify that `GOOGLE_API_KEY` is valid and inspect the
backend logs for quota or rate-limit errors.

## Further documentation

- [Architecture and workflow](ARCHITECTURE.md)
- [CRA agent internals](cra_agents/README.md)
- [Ingestion details](INGESTION_v2.md)