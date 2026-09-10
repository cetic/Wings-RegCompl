"""Reflection memory for product-scoped assessor feedback.

Pattern:
    Step 1 — Agent produces a result (assessment / obligation list).
    Step 2 — Assessor evaluates by posting a comment ("too many obligations",
             "this is EEA-only", "include only essential requirements", …).
    Step 3 — `reflect_on_comment(...)` (or `reflect_on_assessment(...)`)
             asks the LLM to distill the new feedback + current rules into a
             clean, deduplicated set of imperative directives.
    Step 4 — Future runs load the distilled rules via `format_rules_block(...)`,
             which is injected into the classification + obligation-selection
             prompts.

Why distilled rules rather than raw comments?
    * Stable, structured constraints survive across assessments.
    * One prompt-injection point that the model is trained (by instructions)
      to honour, instead of conversational free text the model may discount.
    * Reflection can merge / deduplicate / sharpen overlapping feedback.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

log = logging.getLogger(__name__)


# Ordered, restricted vocabulary. Anything else falls back to "scope".
ALLOWED_CATEGORIES = ("scope", "classification", "obligations", "evidence", "other")


_REFLECT_SYSTEM = """\
You are a compliance memory curator. Your job is to maintain a small,
high-quality set of **scoping rules** that constrain how a downstream AI
agent classifies a product against the EU Cyber Resilience Act (CRA) and
selects applicable obligations.

You will be given:
  1. The product (name + short description).
  2. The CURRENT set of active rules (may be empty).
  3. The NEW feedback (one or more assessor comments and/or an assessment
     outcome that prompted reflection).

Produce a JSON object with one key, "add", listing the NEW rules to add to
memory. Each rule must:
  - be a single, imperative directive (start with EXCLUDE / INCLUDE /
    PREFER / LIMIT / TREAT-AS / REQUIRE / ASSUME),
  - be specific to THIS product (cite the constraint that justifies it),
  - never duplicate or weaken an existing rule,
  - be at most one sentence (≤ 200 characters),
  - pick a category from: scope, classification, obligations, evidence, other.

If the feedback adds no new constraint (e.g. it only restates an existing
rule or is purely conversational), return {"add": []}.

Output format — STRICT JSON, no markdown fences, no commentary:
{
  "add": [
    {"text": "EXCLUDE obligations about extra-EU market surveillance — product is EEA-only.", "category": "scope"},
    {"text": "PREFER only Annex I essential requirements; drop generic transitional provisions.", "category": "obligations"}
  ]
}
"""


def _coerce_category(value: Any) -> str:
    if isinstance(value, str) and value.strip().lower() in ALLOWED_CATEGORIES:
        return value.strip().lower()
    return "scope"


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _parse_add_payload(raw: str) -> list[dict]:
    """Parse the reflector LLM output, tolerating partial JSON or arrays."""
    text = _strip_fences(raw)
    try:
        obj = json.loads(text)
    except Exception:  # noqa: BLE001
        # Try to recover a bare list
        try:
            obj = json.loads(re.search(r"\[.*\]", text, re.S).group(0))  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            log.warning("Reflection JSON parse failed; ignoring output: %s", text[:300])
            return []
    if isinstance(obj, dict):
        items = obj.get("add", [])
    elif isinstance(obj, list):
        items = obj
    else:
        return []
    out: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        rule_text = str(it.get("text") or "").strip()
        if not rule_text:
            continue
        if len(rule_text) > 400:
            rule_text = rule_text[:397].rstrip() + "…"
        out.append(
            {"text": rule_text, "category": _coerce_category(it.get("category"))}
        )
    return out


def _is_duplicate(new_text: str, existing_texts: list[str]) -> bool:
    """Very lightweight duplicate guard: case-insensitive substring match
    in either direction. Prevents the LLM from adding obvious near-duplicates
    of rules that already exist."""
    nt = new_text.strip().lower()
    if not nt:
        return True
    for ex in existing_texts:
        et = ex.strip().lower()
        if not et:
            continue
        if nt == et:
            return True
        if len(nt) > 20 and (nt in et or et in nt):
            return True
    return False


def _build_prompt(
    product_name: str,
    product_description: str,
    existing_rules: list[str],
    new_feedback: str,
) -> str:
    desc = (product_description or "").strip()
    if len(desc) > 1200:
        desc = desc[:1200].rstrip() + "…"
    rules_block = (
        "\n".join(f"- {r}" for r in existing_rules) if existing_rules else "(none)"
    )
    return f"""{_REFLECT_SYSTEM}

PRODUCT:
  name: {product_name}
  description: {desc}

CURRENT RULES:
{rules_block}

NEW FEEDBACK:
{new_feedback.strip()}
"""


def reflect(
    product_name: str,
    product_description: str,
    existing_rules: list[str],
    new_feedback: str,
) -> list[dict]:
    """Run one reflection step. Returns a list of {text, category} dicts.

    Never raises — on any failure returns []. The fallback ensures the calling
    endpoint always succeeds even if the LLM is unavailable.
    """
    if not (new_feedback or "").strip():
        return []
    try:
        from cra_agents.tools._llm import generate as _generate
    except Exception as e:  # noqa: BLE001
        log.warning("Reflection unavailable (LLM import failed): %s", e)
        return []

    prompt = _build_prompt(
        product_name, product_description, existing_rules, new_feedback
    )
    try:
        raw = _generate(prompt)
    except Exception as e:  # noqa: BLE001
        log.warning("Reflection LLM call failed: %s", e)
        return []

    proposed = _parse_add_payload(raw)
    # De-duplicate against existing rules.
    deduped: list[dict] = []
    seen_local: list[str] = list(existing_rules)
    for p in proposed:
        if _is_duplicate(p["text"], seen_local):
            continue
        deduped.append(p)
        seen_local.append(p["text"])
    return deduped


# ── Prompt-injection helpers ─────────────────────────────────────────


def format_rules_block(rules: list[str]) -> str:
    """Return the canonical prompt-injection block for active rules."""
    if not rules:
        return ""
    lines = [
        "",
        "=== ASSESSOR DIRECTIVES (authoritative scoping constraints — apply as filters; do NOT treat as additional product features) ===",
    ]
    for r in rules:
        text = (r or "").strip()
        if not text:
            continue
        if not text.startswith("- "):
            text = f"- {text}"
        lines.append(text)
    lines.append(
        "=== END ASSESSOR DIRECTIVES — When classifying or selecting obligations, EXCLUDE any obligation that contradicts or is rendered irrelevant by the directives above. ==="
    )
    return "\n".join(lines)


def make_rule_id() -> str:
    return str(uuid.uuid4())
