"""Unified LLM gateway honoring MODEL_TYPE (LOCAL=Ollama, OFFLOAD=Gemini).

This is the *single* place tools should call to ask "an LLM" for plain text.
It removes the previous fragmentation where some tools hard-coded
``gemini-2.5-flash-lite`` (broken in LOCAL) and others hard-coded
``gemma4:e2b`` via Ollama (broken in OFFLOAD when Ollama is offline).

Usage:

    from cra_agents.tools._llm import generate
    text = generate("Summarise: ...")

Environment:
    MODEL_TYPE       LOCAL | OFFLOAD          (from model_config)
    OLLAMA_BASE_URL  http://ollama:11434      (LOCAL)
    OLLAMA_MODEL     gemma4:e2b               (LOCAL)
    GOOGLE_API_KEY   <required>               (OFFLOAD)
    GEMINI_MODEL     gemini-2.5-flash         (OFFLOAD agent)
    BATCH_MODEL      gemini-2.5-flash-lite    (OFFLOAD batch / utility)
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from ..model_config import IS_LOCAL, IS_OFFLOAD, BATCH_PARSE_MODEL

log = logging.getLogger(__name__)

_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e2b")

_genai_client = None


def _get_genai_client():
    global _genai_client
    if _genai_client is None:
        from google import genai

        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("OFFLOAD mode requires GOOGLE_API_KEY to be set.")
        _genai_client = genai.Client(api_key=api_key)
    return _genai_client


def _ollama_generate(prompt: str, model: str, timeout: float) -> str:
    import httpx

    resp = httpx.post(
        f"{_OLLAMA_BASE_URL}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=timeout,
    )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"Ollama {resp.status_code} for model '{model}': {resp.text[:300]}"
        )
    return resp.json().get("response", "").strip()


def generate(
    prompt: str,
    *,
    model: Optional[str] = None,
    timeout: float = 300.0,
    temperature: Optional[float] = None,
) -> str:
    """Generate text from the currently configured LLM backend.

    Args:
        prompt: The user prompt text.
        model: Optional explicit model override. In OFFLOAD this is a Gemini
            model id; in LOCAL it's an Ollama model tag. Default picks
            ``BATCH_PARSE_MODEL`` (Gemini) or ``OLLAMA_MODEL`` (Ollama).
        timeout: HTTP timeout in seconds (LOCAL only).
        temperature: Sampling temperature. Defaults to the
            ``LLM_TEMPERATURE`` env var (0.2) — low values reduce
            run-to-run drift for selection / classification tasks.
    """
    if temperature is None:
        try:
            temperature = float(os.getenv("LLM_TEMPERATURE", "0.2"))
        except ValueError:
            temperature = 0.2

    if IS_OFFLOAD:
        import time as _time
        from google.genai import types as _genai_types

        client = _get_genai_client()
        target_model = model or BATCH_PARSE_MODEL
        # Disable Gemini's hidden "thinking" budget for selector calls so the
        # model returns immediately with real content (was producing empty
        # responses on 2.5 Flash).
        gen_config = _genai_types.GenerateContentConfig(
            temperature=temperature,
            thinking_config=_genai_types.ThinkingConfig(thinking_budget=0),
        )
        max_attempts = int(os.getenv("GEMINI_MAX_RETRIES", "6"))
        base_delay = float(os.getenv("GEMINI_RETRY_BASE", "4.0"))
        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                resp = client.models.generate_content(
                    model=target_model,
                    contents=prompt,
                    config=gen_config,
                )
                return (resp.text or "").strip()
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                # Retry only on transient errors
                transient = (
                    "503" in msg
                    or "UNAVAILABLE" in msg
                    or "429" in msg
                    or "RESOURCE_EXHAUSTED" in msg
                    or "deadline" in msg.lower()
                )
                last_exc = e
                if not transient or attempt == max_attempts:
                    raise
                delay = base_delay * (2 ** (attempt - 1))
                log.warning(
                    "Gemini %s transient error (attempt %d/%d): %s — retrying in %.1fs",
                    target_model,
                    attempt,
                    max_attempts,
                    msg[:200],
                    delay,
                )
                _time.sleep(delay)
        # Should not reach here
        if last_exc:
            raise last_exc
        return ""

    if IS_LOCAL:
        # Ollama exposes temperature via the "options" field — wire it in
        # without changing the function signature for callers.
        return _ollama_generate_with_options(
            prompt, model or _OLLAMA_MODEL, timeout, temperature
        )

    raise RuntimeError("Unknown MODEL_TYPE; cannot dispatch LLM call.")


def _ollama_generate_with_options(
    prompt: str, model: str, timeout: float, temperature: float
) -> str:
    import httpx

    resp = httpx.post(
        f"{_OLLAMA_BASE_URL}/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        },
        timeout=timeout,
    )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"Ollama {resp.status_code} for model '{model}': {resp.text[:300]}"
        )
    return resp.json().get("response", "").strip()


def is_offload() -> bool:
    return IS_OFFLOAD


def is_local() -> bool:
    return IS_LOCAL
