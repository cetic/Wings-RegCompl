"""Model error handling helpers for Gemini and tool-calling failures."""

from __future__ import annotations

import asyncio
import logging
import time

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

log = logging.getLogger(__name__)

# ── Shared state ───────────────────────────────────────────────────────
_last_call_ts: float = 0.0
MIN_INTERVAL_SEC = 4.5  # keep under 15 RPM (gemini-2.5-flash-lite free tier)


async def throttle_before_model(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> LlmResponse | None:
    """Insert a minimum delay between successive Gemini calls."""
    global _last_call_ts
    now = time.monotonic()
    wait = MIN_INTERVAL_SEC - (now - _last_call_ts)
    if wait > 0:
        log.info("Rate-limit throttle: waiting %.1f s", wait)
        await asyncio.sleep(wait)
    _last_call_ts = time.monotonic()
    return None  # continue with normal model call


MAX_RETRIES = 3
BACKOFF_BASE = 10  # seconds
MAX_MALFORMED_RETRIES = 2
MALFORMED_BACKOFF_BASE = 1.5  # seconds


async def retry_on_429(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
    error: Exception,
) -> LlmResponse | None:
    """Retry transient model failures, including malformed function calls.

    Handles two broad classes of recoverable failures:
    1. API pressure / transient upstream failures (429/503/high demand)
    2. Function-calling serialization/formatting failures reported by provider
       (e.g. MALFORMED_FUNCTION_CALL).
    """
    err_str = str(error).lower()
    is_malformed_tool_call = (
        "malformed_function_call" in err_str
        or "malformed function call" in err_str
        or "invalid function call" in err_str
        or "invalid tool call" in err_str
    )

    if is_malformed_tool_call:
        state = callback_context.state
        malformed_key = "_malformed_tool_call_retries"
        retries = state.get(malformed_key, 0)

        if retries >= MAX_MALFORMED_RETRIES:
            state[malformed_key] = 0
            log.error(
                "Malformed function call persisted after %d retries: %s",
                MAX_MALFORMED_RETRIES,
                error,
            )
            return LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            text=(
                                "⚠️ The model produced an invalid tool call format multiple times. "
                                "Please retry the same request once, or switch MODEL_TYPE=LOCAL "
                                "for more stable tool execution."
                            )
                        )
                    ],
                )
            )

        retries += 1
        state[malformed_key] = retries
        wait = MALFORMED_BACKOFF_BASE * retries
        log.warning(
            "Malformed function call — retry %d/%d in %.1fs",
            retries,
            MAX_MALFORMED_RETRIES,
            wait,
        )
        await asyncio.sleep(wait)
        return None

    is_retryable = (
        "429" in err_str
        or "resource exhausted" in err_str
        or "rate" in err_str
        or "503" in err_str
        or "unavailable" in err_str
        or "high demand" in err_str
    )

    if not is_retryable:
        log.error("Non-retryable model error: %s", error)
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        text=f"⚠️ We encountered an error from the AI model (API key issue or invalid model name):\n\n`{error}`\n\nPlease check your `.env` configuration."
                    )
                ],
            )
        )

    # Use callback_context state to track retries
    state = callback_context.state
    retry_key = "_rate_limit_retries"
    retries = state.get(retry_key, 0)

    if retries >= MAX_RETRIES:
        log.error("Max retries (%d) exceeded for 429. Giving up.", MAX_RETRIES)
        state[retry_key] = 0
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        text=(
                            "⚠️ Gemini API rate limit reached after multiple retries. "
                            "Please wait a minute and try again, or upgrade to a paid API plan."
                        )
                    )
                ],
            )
        )

    retries += 1
    state[retry_key] = retries
    wait = BACKOFF_BASE * (2 ** (retries - 1))  # 10s, 20s, 40s
    log.warning("429 rate limit — retry %d/%d in %ds", retries, MAX_RETRIES, wait)
    await asyncio.sleep(wait)

    # Return None to signal ADK to retry the model call
    return None
