# CRA Agent

Graph-RAG pipeline for answering EU Cyber Resilience Act questions using a Neo4j knowledge graph.

## Architecture

```
User Question
    │
    ▼
[Intent Classifier]  ← small LLM call
    │  intent + entities
    ▼
[Vector Search]      ← embed question → cosine search over node embeddings
    │  seed nodes (top-k)
    ▼
[Graph Traversal]    ← fixed Cypher patterns per intent (no dynamic query generation)
    │  enriched context
    ▼
[Answer Synthesis]   ← main LLM call with context + assessor feedback rules
    │
    ▼
  Answer
```

## File structure

```
cra_agent/
├── agent.py                  ← main pipeline + LLM/embedding adapters
├── adk_tool.py               ← Google ADK FunctionTool wrappers
├── tools/
│   ├── neo4j_client.py       ← vector search + 8 fixed traversal patterns
│   └── intent_classifier.py  ← intent + entity extraction
└── prompts/
    └── answer_synthesis.py   ← answer prompt builder
```

## Installation

```bash
pip install neo4j sentence-transformers
# If using Ollama (recommended for local LLMs):
# Install Ollama from https://ollama.com and pull your model:
# ollama pull mistral
```

## Quick start

```python
from agent import CRAAgent, AgentConfig
from agent import make_ollama_llm, make_sentence_transformer_embedder

config = AgentConfig(
    neo4j_uri="bolt://localhost:7687",
    neo4j_user="neo4j",
    neo4j_password="your_password",
    embedding_property="embedding",          # property name on your nodes
    llm_fn=make_ollama_llm("mistral"),       # swap for your LLM
    embed_fn=make_sentence_transformer_embedder("all-MiniLM-L6-v2"),  # swap for your embedder
)

agent = CRAAgent(config)
result = agent.answer("What are the obligations of a manufacturer under the CRA?")
print(result["answer"])
```

## ADK integration

```python
from adk_tool import build_cra_agent, cra_tool, feedback_tool
from google.adk.agents import LlmAgent

# Initialize once at startup
build_cra_agent(
    neo4j_uri="bolt://localhost:7687",
    neo4j_user="neo4j",
    neo4j_password="your_password",
    llm_model="mistral",
    embed_model="all-MiniLM-L6-v2",
)

# Plug into your ADK agent
root_agent = LlmAgent(
    name="cra_assistant",
    model="your-adk-model",
    tools=[cra_tool, feedback_tool],
    instruction="You are a CRA compliance assistant. Use the cra_tool to answer questions.",
)
```

## Swapping your LLM

### Ollama (Mistral, LLaMA, Gemma...)
```python
from agent import make_ollama_llm
llm_fn = make_ollama_llm(model="mistral", base_url="http://localhost:11434")
```

### OpenAI-compatible (LM Studio, vLLM, Groq, Together AI...)
```python
from agent import make_openai_compatible_llm
llm_fn = make_openai_compatible_llm(
    model="your-model",
    base_url="http://localhost:1234/v1",
    api_key="your-key",
)
```

## Swapping your embedding model

### sentence-transformers (local)
```python
from agent import make_sentence_transformer_embedder
embed_fn = make_sentence_transformer_embedder("all-MiniLM-L6-v2")
# or multilingual: "paraphrase-multilingual-MiniLM-L12-v2"
```

### HuggingFace model
```python
from agent import make_huggingface_embedder
embed_fn = make_huggingface_embedder("intfloat/multilingual-e5-base")
```

## Assessor feedback

```python
# After an assessor reviews an answer:
agent.add_feedback("Always cite the article number when mentioning an obligation.")
agent.add_feedback("When answering scope questions, always check exclusions (MDR, aviation, vehicles).")
# These rules are injected into every future answer prompt automatically.
```

## Covered intents

| Intent | Example questions |
|---|---|
| `obligation_lookup` | "What must a manufacturer do?" |
| `product_classification` | "Is a VPN a Class I or II product?" |
| `conformity_assessment_path` | "Does a Class II product need a notified body?" |
| `vulnerability_handling` | "How do I handle a discovered vulnerability?" |
| `penalty_lookup` | "What are the fines for non-compliance?" |
| `scope_check` | "Does the CRA apply to open source software?" |
| `cross_regulation` | "How does the CRA relate to NIS2?" |
| `timeline_lookup` | "When does Article 14 apply?" |
