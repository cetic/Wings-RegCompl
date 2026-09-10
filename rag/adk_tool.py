"""
Google Agent Development Kit (ADK) integration.

Wraps the CRAAgent as an ADK FunctionTool so it can be plugged
into any ADK agent as a callable tool.

Usage:
    from adk_tool import cra_tool, build_cra_agent
    from google.adk.agents import LlmAgent

    cra_agent = build_cra_agent()   # configure once

    root_agent = LlmAgent(
        name="cra_assistant",
        model="your-model",
        tools=[cra_tool],
        instruction="You are a CRA compliance assistant.",
    )
"""

from __future__ import annotations
from google.adk.tools import FunctionTool
from agent import CRAAgent, AgentConfig


# ------------------------------------------------------------------
# Singleton agent (initialised once at startup)
# ------------------------------------------------------------------
_agent: CRAAgent | None = None


def build_cra_agent(
    neo4j_uri: str = "bolt://localhost:7687",
    neo4j_user: str = "neo4j",
    neo4j_password: str = "password",
    embedding_property: str = "embedding",
    llm_model: str = "mistral",                    # Ollama model name
    embed_model: str = "all-MiniLM-L6-v2",        # sentence-transformers model
    ollama_base_url: str = "http://localhost:11434",
) -> CRAAgent:
    """
    Build and return the CRA agent singleton.
    Call this once at application startup.
    """
    global _agent

    from agent import make_ollama_llm, make_sentence_transformer_embedder

    config = AgentConfig(
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_password,
        embedding_property=embedding_property,
        llm_fn=make_ollama_llm(model=llm_model, base_url=ollama_base_url),
        embed_fn=make_sentence_transformer_embedder(model_name=embed_model),
    )
    _agent = CRAAgent(config)
    return _agent


# ------------------------------------------------------------------
# ADK Tool definitions
# ------------------------------------------------------------------

def answer_cra_question(question: str) -> str:
    """
    Answer any question about the EU Cyber Resilience Act (CRA).

    Searches a structured CRA knowledge graph and synthesizes a precise,
    article-referenced answer.

    Args:
        question: A natural language question about the CRA — obligations,
                  product classifications, conformity assessments, penalties,
                  scope, timelines, or cross-regulation mappings.

    Returns:
        A detailed answer with relevant article references.
    """
    if _agent is None:
        return "CRA agent not initialized. Call build_cra_agent() at startup."

    result = _agent.answer(question)
    return result["answer"]


def add_assessor_feedback(feedback: str) -> str:
    """
    Add an assessor feedback rule to improve future CRA answers.

    Use this when the assessor identifies a recurring issue with the
    agent's answers (e.g. missing citations, wrong scope assumptions).

    Args:
        feedback: A concise rule or correction for the agent to apply
                  in future answers (e.g. "Always cite the article number
                  when mentioning an obligation").

    Returns:
        Confirmation that the feedback was recorded.
    """
    if _agent is None:
        return "CRA agent not initialized."

    _agent.add_feedback(feedback)
    return f"Feedback recorded: '{feedback}'. Will apply to all future answers."


# Register as ADK FunctionTools
cra_tool = FunctionTool(answer_cra_question)
feedback_tool = FunctionTool(add_assessor_feedback)
