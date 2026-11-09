import asyncio
import copy
import json
import os
from pathlib import Path
from typing import Any, cast
from urllib.error import URLError
from urllib.request import urlopen
from uuid import uuid4

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from ..config import settings
from .models import ProvisionPackage

EXTRACTION_DIR = Path(__file__).parent
PROMPT_VERSION = "extract_v9"


def gemini_response_schema() -> dict[str, Any]:
    schema = ProvisionPackage.model_json_schema()

    def remove_unsupported_keywords(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: remove_unsupported_keywords(item)
                for key, item in value.items()
                if key != "additionalProperties"
            }
        if isinstance(value, list):
            return [remove_unsupported_keywords(item) for item in value]
        return value

    return cast(dict[str, Any], remove_unsupported_keywords(copy.deepcopy(schema)))


def _generation_config(*, local_only: bool) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        temperature=0.1,
        # Gemini thinking tokens count toward this limit and can truncate the JSON.
        max_output_tokens=8192 if local_only else 32768,
        response_mime_type=None if local_only else "application/json",
    )


def _structured_output(output: Any, final_text: str | None) -> dict[str, Any]:
    if isinstance(output, dict):
        return cast(dict[str, Any], output)
    errors: list[json.JSONDecodeError] = []

    def _extract_valid_object(candidate: str) -> dict[str, Any] | None:
        decoder = json.JSONDecoder()
        for start in [idx for idx, char in enumerate(candidate) if char == "{"]:
            in_string = False
            escape = False
            depth = 0
            for idx in range(start, len(candidate)):
                char = candidate[idx]
                if in_string:
                    if escape:
                        escape = False
                    elif char == "\\":
                        escape = True
                    elif char == '"':
                        in_string = False
                    continue
                if char == '"':
                    in_string = True
                    continue
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        chunk = candidate[start : idx + 1]
                        try:
                            parsed, end = decoder.raw_decode(chunk)
                        except json.JSONDecodeError as parse_error:
                            errors.append(parse_error)
                            continue
                        if isinstance(parsed, dict):
                            tail = candidate[start + end :].lstrip()
                            if tail and tail[0] in ",]}:":
                                continue
                            return cast(dict[str, Any], parsed)
                        break
        return None

    for candidate in (output, final_text):
        if not isinstance(candidate, str):
            continue
        parsed = _extract_valid_object(candidate)
        if parsed is not None:
            return parsed
        try:
            parsed_obj = json.loads(candidate)
        except json.JSONDecodeError as parse_error:
            errors.append(parse_error)
            continue
        if isinstance(parsed_obj, dict):
            return cast(dict[str, Any], parsed_obj)

    if errors:
        last_error = errors[-1]
        raise ValueError(
            f"ADK returned invalid structured JSON at line {last_error.lineno} "
            f"column {last_error.colno}"
        ) from last_error
    raise ValueError("ADK returned no structured ProvisionPackage")


def _agent_instruction(
    prompt: str,
    context_json: str,
    validation_feedback: list[str],
) -> str:
    retry_guidance = ""
    if validation_feedback:
        retry_guidance = (
            "\nCORRECTIONS REQUIRED FROM YOUR PREVIOUS RESPONSE\n"
            + "\n".join(f"- {item}" for item in validation_feedback)
            + "\nReturn one complete, compact corrected package."
        )
    return f"{prompt}\n\nEXTRACTION CONTEXT (JSON)\n{context_json}{retry_guidance}"


class ADKPackageGenerator:
    def preflight(self, model_name: str, *, local_only: bool) -> None:
        if not local_only:
            if not os.environ.get("GOOGLE_API_KEY"):
                raise RuntimeError("Cloud extraction unavailable: GOOGLE_API_KEY is not configured")
            return
        base_url = os.environ.get("OLLAMA_API_BASE", settings.ollama_base_url).rstrip("/")
        try:
            with urlopen(f"{base_url}/api/tags", timeout=4) as response:
                available = {
                    str(item.get("name", "")) for item in json.load(response).get("models", [])
                }
        except (OSError, URLError, ValueError) as error:
            raise RuntimeError("Local extraction unavailable: Ollama is not reachable") from error
        if model_name not in available:
            raise RuntimeError(
                f"Local extraction unavailable: configured model {model_name} is not installed"
            )

    def generate(
        self,
        context_json: str,
        *,
        model_name: str,
        local_only: bool,
        validation_feedback: list[str] | None = None,
    ) -> dict[str, Any]:
        return asyncio.run(
            self._generate_async(
                context_json,
                model_name=model_name,
                local_only=local_only,
                validation_feedback=validation_feedback or [],
            )
        )

    async def _generate_async(
        self,
        context_json: str,
        *,
        model_name: str,
        local_only: bool,
        validation_feedback: list[str],
    ) -> dict[str, Any]:
        prompt = (EXTRACTION_DIR / "prompts" / f"{PROMPT_VERSION}.md").read_text(encoding="utf-8")
        instruction = _agent_instruction(prompt, context_json, validation_feedback)
        model: str | LiteLlm
        output_schema: type[ProvisionPackage] | dict[str, Any]
        if local_only:
            model = LiteLlm(model=f"ollama_chat/{model_name}")
            output_schema = ProvisionPackage
        else:
            model = model_name
            output_schema = gemini_response_schema()
        agent = LlmAgent(
            name="regulatory_unit_extractor",
            model=model,
            description="Extracts a validated, structured package from one regulatory unit.",
            instruction=instruction,
            output_schema=output_schema,
            output_key="provision_package",
            include_contents="none",
            generate_content_config=_generation_config(local_only=local_only),
        )
        app_name = "regcomply_extraction"
        user_id = "build-worker"
        session_id = str(uuid4())
        session_service = InMemorySessionService()  # type: ignore[no-untyped-call]
        await session_service.create_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )
        runner = Runner(
            agent=agent,
            app_name=app_name,
            session_service=session_service,
        )
        message = types.Content(role="user", parts=[types.Part(text="Extract this unit now.")])
        final_text: str | None = None
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=message,
        ):
            if event.is_final_response() and event.content and event.content.parts:
                final_text = "".join(part.text or "" for part in event.content.parts).strip()
        session = await session_service.get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )
        output = session.state.get("provision_package") if session else None
        return _structured_output(output, final_text)
