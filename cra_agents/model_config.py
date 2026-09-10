"""Centralized model configuration for the CRA Agent system.

Toggle between LOCAL (Ollama/gemma4) and OFFLOAD (Gemini 2.5 Flash) via:

    MODEL_TYPE=LOCAL    # default — uses Ollama (gemma4:e2b)
    MODEL_TYPE=OFFLOAD  # uses Gemini 2.5 Flash via Google GenAI

Additional tuning:
    OLLAMA_MODEL      e.g. "gemma4:e2b"  (LOCAL only)
    OLLAMA_BASE_URL   e.g. "http://localhost:11434"  (LOCAL only)
    GOOGLE_API_KEY    required for OFFLOAD
    GEMINI_MODEL      e.g. "gemini-2.5-flash"  (OFFLOAD only, has default)
    BATCH_MODEL       which Gemini model to use for batch parsing (OFFLOAD only)
"""

from __future__ import annotations

import logging
import os
from typing import Union

from google.adk.models.lite_llm import LiteLlm

log = logging.getLogger(__name__)

# ── Resolve MODEL_TYPE ────────────────────────────────────────────────────────
MODEL_TYPE: str = os.getenv("MODEL_TYPE", "LOCAL").strip().upper()
if MODEL_TYPE not in ("LOCAL", "OFFLOAD"):
    log.warning("Unknown MODEL_TYPE=%r, defaulting to LOCAL", MODEL_TYPE)
    MODEL_TYPE = "LOCAL"

IS_LOCAL = MODEL_TYPE == "LOCAL"
IS_OFFLOAD = MODEL_TYPE == "OFFLOAD"

# ── LOCAL branch (Ollama) ─────────────────────────────────────────────────────
_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
_RAW_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e2b")

if IS_LOCAL:
    # Ensure ADK/LiteLLM can find the Ollama server
    os.environ.setdefault("OLLAMA_API_BASE", _OLLAMA_BASE_URL)

    # Normalize to the ollama_chat/... prefix expected by LiteLLM
    if _RAW_OLLAMA_MODEL.startswith("ollama_chat/"):
        _LOCAL_MODEL_NAME = _RAW_OLLAMA_MODEL
    elif _RAW_OLLAMA_MODEL.startswith("ollama/"):
        _LOCAL_MODEL_NAME = f"ollama_chat/{_RAW_OLLAMA_MODEL.split('/', 1)[1]}"
    else:
        _LOCAL_MODEL_NAME = f"ollama_chat/{_RAW_OLLAMA_MODEL}"

# ── OFFLOAD branch (Gemini) ───────────────────────────────────────────────────
_GEMINI_AGENT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
# Batch parsing model (used by batch_tool.py for article/recital/annex parsing)
BATCH_PARSE_MODEL = os.getenv("BATCH_MODEL", "gemini-2.5-flash-lite")

# ── Shared exports ────────────────────────────────────────────────────────────

# ADK Agent model — LiteLlm object for Ollama (LOCAL), plain string for Gemini (OFFLOAD).
# Sub-agents use this directly: Agent(model=AGENT_MODEL, ...)
# The root agent must use AGENT_MODEL_STR (plain string) to avoid Pydantic serialization errors.
AGENT_MODEL: Union[LiteLlm, str] = LiteLlm(model=_LOCAL_MODEL_NAME) if IS_LOCAL else _GEMINI_AGENT_MODEL
AGENT_MODEL_STR: str = _LOCAL_MODEL_NAME if IS_LOCAL else _GEMINI_AGENT_MODEL

# Whether the agent model needs Gemini rate-limit callbacks
USE_RATE_LIMIT_CALLBACKS: bool = IS_OFFLOAD

log.info(
    "model_config: MODEL_TYPE=%s  AGENT_MODEL=%s  USE_RATE_LIMIT=%s  BATCH_MODEL=%s",
    MODEL_TYPE,
    AGENT_MODEL,
    USE_RATE_LIMIT_CALLBACKS,
    BATCH_PARSE_MODEL,
)
