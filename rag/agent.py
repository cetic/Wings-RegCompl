"""
CRA Agent — main retrieval pipeline.

Architecture:
  Question
    → Intent classification + entity extraction  (small LLM call)
    → Vector search                               (find seed nodes)
    → Fixed graph traversal                       (expand context)
    → Answer synthesis                            (main LLM call)

Swap in your LLM and embedding model via the adapter functions below.
"""

from __future__ import annotations
from dataclasses import dataclass, field

from tools.neo4j_client import Neo4jClient
from tools.intent_classifier import classify_intent
from prompts.answer_synthesis import build_answer_prompt


# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------

@dataclass
class AgentConfig:
    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    embedding_property: str = "embedding"   # property name on your nodes

    # Retrieval
    vector_top_k: int = 5                   # seed nodes from vector search
    expand_per_node: bool = True            # run graph traversal per seed node

    # LLM (filled in by you — see adapters below)
    llm_fn: callable = None                 # llm_fn(system, user) -> str
    embed_fn: callable = None               # embed_fn(text) -> list[float]

    # Feedback memory (grows over time)
    feedback_rules: list[str] = field(default_factory=list)


# ------------------------------------------------------------------
# LLM / Embedding adapters — swap these for your stack
# ------------------------------------------------------------------

def make_ollama_llm(model: str = "mistral", base_url: str = "http://localhost:11434"):
    """Adapter for any Ollama-served model (Mistral, LLaMA, Gemma...)."""
    import requests

    def llm_fn(system: str, user: str) -> str:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            "stream": False,
        }
        resp = requests.post(f"{base_url}/api/chat", json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    return llm_fn


def make_openai_compatible_llm(model: str, base_url: str, api_key: str = ""):
    """
    Adapter for any OpenAI-compatible endpoint
    (LM Studio, vLLM, Together AI, Groq...).
    """
    from openai import OpenAI
    client = OpenAI(base_url=base_url, api_key=api_key or "none")

    def llm_fn(system: str, user: str) -> str:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        )
        return resp.choices[0].message.content

    return llm_fn


def make_sentence_transformer_embedder(model_name: str = "all-MiniLM-L6-v2"):
    """Local embedder using sentence-transformers."""
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_name)

    def embed_fn(text: str) -> list[float]:
        return model.encode(text).tolist()

    return embed_fn


def make_huggingface_embedder(model_name: str):
    """Generic HuggingFace embedder (e.g. multilingual models)."""
    from transformers import AutoTokenizer, AutoModel
    import torch

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)

    def embed_fn(text: str) -> list[float]:
        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        with torch.no_grad():
            outputs = model(**inputs)
        # Mean pooling
        embeddings = outputs.last_hidden_state.mean(dim=1).squeeze()
        return embeddings.tolist()

    return embed_fn


# ------------------------------------------------------------------
# Assessor feedback integration
# ------------------------------------------------------------------

def apply_feedback_to_prompt(system_prompt: str, feedback_rules: list[str]) -> str:
    """
    Inject accumulated assessor feedback rules into the system prompt.
    This implements the 'persistent lessons' pattern discussed earlier.
    """
    if not feedback_rules:
        return system_prompt

    rules_text = "\n".join(f"- {r}" for r in feedback_rules)
    feedback_block = f"""
## Assessor Feedback Rules (always apply):
{rules_text}
"""
    return system_prompt + feedback_block


# ------------------------------------------------------------------
# Main agent
# ------------------------------------------------------------------

class CRAAgent:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.neo4j = Neo4jClient(
            uri=config.neo4j_uri,
            user=config.neo4j_user,
            password=config.neo4j_password,
            embedding_property=config.embedding_property,
        )

    def answer(self, question: str) -> dict:
        """
        Full pipeline: question → answer.

        Returns:
            {
              "answer": str,
              "intent": str,
              "entities": dict,
              "seed_nodes": list,
              "context_size": int,
            }
        """
        cfg = self.config

        # ── Step 1: Classify intent + extract entities ──────────────
        entities = classify_intent(question, cfg.llm_fn)
        intent = entities.get("intent", "obligation_lookup")

        # ── Step 2: Embed the question + vector search ───────────────
        query_embedding = cfg.embed_fn(question)
        seed_nodes = self.neo4j.vector_search(query_embedding, k=cfg.vector_top_k)

        # ── Step 3: Expand each seed node via fixed traversal ────────
        graph_context = []
        if cfg.expand_per_node:
            for node in seed_nodes:
                expanded = self.neo4j.expand_node(intent, node.get("props", {}), entities)
                graph_context.extend(expanded)
        else:
            # Just use seed node properties as context
            graph_context = [n.get("props", {}) for n in seed_nodes]

        # ── Step 4: Synthesize answer ────────────────────────────────
        system_prompt, user_prompt = build_answer_prompt(question, graph_context)

        # Apply any accumulated assessor feedback
        system_prompt = apply_feedback_to_prompt(system_prompt, cfg.feedback_rules)

        answer = cfg.llm_fn(system=system_prompt, user=user_prompt)

        return {
            "answer": answer,
            "intent": intent,
            "entities": entities,
            "seed_nodes": seed_nodes,
            "context_size": len(graph_context),
        }

    def add_feedback(self, assessor_comment: str):
        """
        Add an assessor rule that will be injected into every future answer prompt.
        """
        self.config.feedback_rules.append(assessor_comment)

    def close(self):
        self.neo4j.close()
