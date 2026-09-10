"""Generates Verification compliance actions for CRA obligations."""

import json
import logging
import re
import time

from pathlib import Path
from dotenv import load_dotenv

from ._llm import generate as _llm_generate

log = logging.getLogger(__name__)

_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(_ENV_PATH)

MIN_INTERVAL = 4.5
_last_call: float = 0.0


def _throttle():
    global _last_call
    now = time.time()
    wait = MIN_INTERVAL - (now - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()


VERIFICATION_PROMPT = """You are a Legal Compliance Expert for the EU Cyber Resilience Act (CRA).

Given a legal obligation text, generate 1 to 3 "VerificationActions" that an organization must perform to prove they are compliant with this specific requirement.

A VerificationAction is a concrete action taken to verify compliance.
It MUST be one of these 4 types: "inspection", "review", "testcase", or "waiver".
It MUST output concrete "evidence" (an artifact, document, or log).

Return ONLY valid JSON (no markdown fences) in this exact format:
{{
  "verifications": [
    {{
      "type": "inspection" | "review" | "testcase" | "waiver",
      "description": "<What specifically is being verified/tested/reviewed, max 20 words>",
      "evidence": "<The artifact produced, e.g. 'Signed security architecture review document'>"
    }}
  ]
}}

OBLIGATION:
{obligation_text}
"""


def generate_verifications_for_obligation(action_text: str) -> list[dict[str, str]]:
    """Use the configured LLM to generate verifications for an obligation."""
    _throttle()
    text = ""
    try:
        prompt = VERIFICATION_PROMPT.format(obligation_text=action_text)
        text = _llm_generate(prompt).strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        data = json.loads(text)
        return data.get("verifications", [])
    except Exception as e:
        import traceback

        print(f"ERROR: {e}")
        if text:
            print(f"Raw text returned by LLM: {text}")
        traceback.print_exc()
        log.warning(
            "Verification generation failed for action: %s...", action_text[:50]
        )
        return []
