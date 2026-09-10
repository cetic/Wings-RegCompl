"""ADK agent chat bridge for the FastAPI backend.

Exposes a single async function `run_agent_message` that the `/api/agent/chat`
endpoint calls. Sessions are kept in-memory keyed by a client-provided
`session_id`; if not provided, a new one is created.

The full ADK orchestrator (`cra_agents.root_agent`) is reused as-is so the
chat assistant can perform every action available via `adk web`:
ingest articles, analyze the graph, query Cypher, list/read regulation
content, manage products, etc.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger(__name__)

_runner = None
_session_service = None
_APP_NAME = "cra_agent_chat"


@dataclass
class ChatEvent:
    """Lightweight wire-format event for the frontend."""

    kind: str  # "tool_call" | "tool_result" | "transfer" | "text" | "error"
    author: Optional[str] = None
    name: Optional[str] = None
    args: Any = None
    result: Any = None
    text: Optional[str] = None
    extra: dict = field(default_factory=dict)


@dataclass
class ChatResult:
    session_id: str
    reply: str
    events: list[ChatEvent]


def _get_runner():
    """Lazily build the ADK Runner so import errors surface only on first use."""
    global _runner, _session_service
    if _runner is not None:
        return _runner

    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    # Defer importing the agent until needed — pulls in google-adk + neo4j.
    from cra_agents.agent import root_agent

    _session_service = InMemorySessionService()
    _runner = Runner(
        agent=root_agent,
        app_name=_APP_NAME,
        session_service=_session_service,
    )
    log.info("ADK chat runner initialised (app=%s)", _APP_NAME)
    return _runner


async def _ensure_session(session_id: str, user_id: str) -> str:
    """Create the session if it doesn't exist yet."""
    assert _session_service is not None
    existing = await _session_service.get_session(
        app_name=_APP_NAME, user_id=user_id, session_id=session_id
    )
    if existing is None:
        await _session_service.create_session(
            app_name=_APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )
    return session_id


def _serialise(value: Any, max_chars: int = 4000) -> Any:
    """Best-effort JSON-safe serialisation, truncating huge blobs."""
    try:
        import json

        json.dumps(value, default=str)
        # Truncate giant strings/blobs
        if isinstance(value, str) and len(value) > max_chars:
            return value[:max_chars] + "… [truncated]"
        return value
    except Exception:
        s = str(value)
        return s[:max_chars] + ("… [truncated]" if len(s) > max_chars else "")


def _extract_events(adk_event) -> list[ChatEvent]:
    """Translate an ADK event into zero or more ChatEvents."""
    out: list[ChatEvent] = []
    author = getattr(adk_event, "author", None)
    content = getattr(adk_event, "content", None)
    if not content or not getattr(content, "parts", None):
        return out

    for part in content.parts:
        # Function (tool) call
        fc = getattr(part, "function_call", None)
        if fc is not None:
            name = getattr(fc, "name", None)
            args = getattr(fc, "args", None)
            if name == "transfer_to_agent":
                target = None
                if isinstance(args, dict):
                    target = args.get("agent_name") or args.get("agent")
                out.append(
                    ChatEvent(
                        kind="transfer",
                        author=author,
                        name=target,
                        args=_serialise(args),
                    )
                )
            else:
                out.append(
                    ChatEvent(
                        kind="tool_call",
                        author=author,
                        name=name,
                        args=_serialise(args),
                    )
                )
            continue

        # Function (tool) response
        fr = getattr(part, "function_response", None)
        if fr is not None:
            out.append(
                ChatEvent(
                    kind="tool_result",
                    author=author,
                    name=getattr(fr, "name", None),
                    result=_serialise(getattr(fr, "response", None)),
                )
            )
            continue

        # Text part
        text = getattr(part, "text", None)
        if text:
            out.append(ChatEvent(kind="text", author=author, text=text))

    return out


async def run_agent_message(
    message: str,
    session_id: Optional[str],
    user_id: str = "user",
) -> ChatResult:
    """Send `message` through the ADK orchestrator and collect the response."""
    runner = _get_runner()
    session_id = session_id or uuid.uuid4().hex
    await _ensure_session(session_id, user_id)

    from google.genai import types as genai_types

    user_msg = genai_types.Content(role="user", parts=[genai_types.Part(text=message)])

    events: list[ChatEvent] = []
    final_text_parts: list[str] = []

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=user_msg,
    ):
        events.extend(_extract_events(event))
        if event.is_final_response() and event.content and event.content.parts:
            for part in event.content.parts:
                t = getattr(part, "text", None)
                if t:
                    final_text_parts.append(t)

    reply = "\n".join(s for s in final_text_parts if s).strip()
    if not reply:
        # Fall back to the last text event if the runner didn't emit a final one
        for ev in reversed(events):
            if ev.kind == "text" and ev.text:
                reply = ev.text
                break
    return ChatResult(session_id=session_id, reply=reply, events=events)


# Regex: matches the [i/N] prefix our batch tools log, e.g.
#   "[3/8] Annex III — parsing via Gemini…"
#   "[12/45] Recital 12 — ingested: ..."
_PROGRESS_RE = re.compile(r"\[(\d+)\s*/\s*(\d+)\]")
# Loggers we forward to the client as progress events. They emit one INFO
# record per item, so they make a perfect progress feed. Names must match
# what the tools actually call `logging.getLogger(...)` with.
_PROGRESS_LOGGER_NAMES = (
    "batch_tool",
    "cra_agents.tools.batch_tool",
    "cra_agents.tools.link_obligations",
    "cra_agents.tools.vector_tools",
)


class _ProgressBridgeHandler(logging.Handler):
    """logging.Handler that pushes records onto an asyncio.Queue.

    Tools log from worker threads, so we hop back onto the event loop with
    ``call_soon_threadsafe`` to keep the queue thread-safe.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue) -> None:
        super().__init__(level=logging.INFO)
        self._loop = loop
        self._queue = queue

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001
            return
        item: dict[str, Any] = {
            "kind": "progress",
            "author": record.name,
            "text": msg,
        }
        m = _PROGRESS_RE.search(msg)
        if m:
            try:
                item["current"] = int(m.group(1))
                item["total"] = int(m.group(2))
            except ValueError:
                pass
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, item)
        except RuntimeError:
            # Loop already closed; drop the record silently.
            pass


async def stream_agent_message(
    message: str,
    session_id: Optional[str],
    user_id: str = "user",
):
    """Async generator yielding ChatEvents progressively + a final result event.

    Each yielded item is a dict ready to be JSON-serialised. The very last
    item has ``kind == "final"`` and carries the consolidated reply +
    ``session_id`` so the client can finalise the turn.

    Tool progress is captured from the ``BATCH``/``INGEST``/``PARSE`` loggers
    and streamed as ``{"kind": "progress", "text", "current", "total"}`` so
    the UI can render a live progress bar even while a single tool call is
    still running.
    """
    runner = _get_runner()
    session_id = session_id or uuid.uuid4().hex
    await _ensure_session(session_id, user_id)

    # Tell the client its session_id immediately (useful on first message).
    yield {"kind": "session", "session_id": session_id}

    from google.genai import types as genai_types

    user_msg = genai_types.Content(role="user", parts=[genai_types.Part(text=message)])

    final_text_parts: list[str] = []
    streamed_text_max: dict[str, str] = {}
    streamed_text_concat: list[str] = []
    # Remember the most useful tool_result string so we can fall back to it
    # if neither the orchestrator nor the sub-agent produces a final text
    # (common when a sub-agent answers with the raw tool output and the root
    # agent doesn't bother summarising).
    last_tool_result_text: Optional[str] = None
    last_tool_name: Optional[str] = None

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    # Hook progress loggers.
    handler = _ProgressBridgeHandler(loop, queue)
    hooked: list[logging.Logger] = []
    for name in _PROGRESS_LOGGER_NAMES:
        lg = logging.getLogger(name)
        lg.addHandler(handler)
        if lg.level == logging.NOTSET or lg.level > logging.INFO:
            lg.setLevel(logging.INFO)
        hooked.append(lg)

    DONE = object()
    ERROR = object()

    async def _produce_adk():
        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=user_msg,
            ):
                await queue.put(("event", event))
        except Exception as e:  # noqa: BLE001
            await queue.put((ERROR, e))
        finally:
            await queue.put((DONE, None))

    producer = asyncio.create_task(_produce_adk())

    try:
        while True:
            item = await queue.get()
            # Progress dicts pushed by the logging handler.
            if isinstance(item, dict):
                yield item
                continue
            tag, payload = item
            if tag is DONE:
                break
            if tag is ERROR:
                log.exception("stream_agent_message failed", exc_info=payload)
                yield {"kind": "error", "text": f"Agent error: {payload}"}
                # Still wait for DONE sentinel which producer enqueues in finally.
                continue
            # tag == "event"
            event = payload
            # Diagnostic: dump every raw event so we can see what the runner emits.
            try:
                _author = getattr(event, "author", None)
                _content = getattr(event, "content", None)
                _parts = getattr(_content, "parts", None) if _content else None
                _kinds = []
                if _parts:
                    for _p in _parts:
                        if getattr(_p, "function_call", None) is not None:
                            _kinds.append(
                                f"fc:{getattr(_p.function_call, 'name', '?')}"
                            )
                        elif getattr(_p, "function_response", None) is not None:
                            _kinds.append(
                                f"fr:{getattr(_p.function_response, 'name', '?')}"
                            )
                        elif getattr(_p, "text", None):
                            _kinds.append(f"text:{len(_p.text)}")
                        else:
                            _kinds.append("other")
                _actions = getattr(event, "actions", None)
                _transfer = (
                    getattr(_actions, "transfer_to_agent", None) if _actions else None
                )
                _escalate = getattr(_actions, "escalate", None) if _actions else None
                _err_code = getattr(event, "error_code", None)
                _err_msg = getattr(event, "error_message", None)
                _finish = getattr(event, "finish_reason", None) or getattr(
                    event, "turn_complete", None
                )
                log.warning(
                    "ADK event author=%s final=%s parts=%s transfer=%s escalate=%s err=%s/%s finish=%s",
                    _author,
                    (
                        event.is_final_response()
                        if hasattr(event, "is_final_response")
                        else "?"
                    ),
                    _kinds,
                    _transfer,
                    _escalate,
                    _err_code,
                    _err_msg,
                    _finish,
                )
            except Exception as _diag_e:  # noqa: BLE001
                log.warning("ADK event diag failed: %s", _diag_e)
            for ev in _extract_events(event):
                if ev.kind == "text" and ev.text:
                    key = ev.author or ""
                    prev = streamed_text_max.get(key, "")
                    if len(ev.text) >= len(prev):
                        streamed_text_max[key] = ev.text
                    streamed_text_concat.append(ev.text)
                elif ev.kind == "tool_result":
                    # Remember the last sizeable string result so we can
                    # surface it if no summary text is produced.
                    result_str = ev.result if isinstance(ev.result, str) else None
                    if result_str and len(result_str.strip()) > 0:
                        last_tool_result_text = result_str
                        last_tool_name = ev.name
                yield {
                    "kind": ev.kind,
                    "author": ev.author,
                    "name": ev.name,
                    "args": ev.args,
                    "result": ev.result,
                    "text": ev.text,
                }
            if event.is_final_response() and event.content and event.content.parts:
                for part in event.content.parts:
                    t = getattr(part, "text", None)
                    if t:
                        final_text_parts.append(t)
    finally:
        for lg in hooked:
            lg.removeHandler(handler)
        if not producer.done():
            producer.cancel()
            try:
                await producer
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    reply = "\n".join(s for s in final_text_parts if s).strip()
    if not reply and streamed_text_max:
        reply = max(streamed_text_max.values(), key=len).strip()
    if not reply and streamed_text_concat:
        reply = "".join(streamed_text_concat).strip()
    if not reply and last_tool_result_text:
        # Last-resort: surface the raw tool output so the user always sees
        # *something* useful rather than "(no reply)".
        snippet = last_tool_result_text.strip()
        if len(snippet) > 6000:
            snippet = snippet[:6000] + "\n… [truncated]"
        reply = (
            f"_(no summary produced — showing raw result from `{last_tool_name or 'tool'}`)_\n\n"
            f"```\n{snippet}\n```"
        )
    if not reply:
        reply = (
            "_The model returned an empty response. This usually means it "
            "didn't pick a tool for the request — try rephrasing, for example_ "
            "`list articles` _or_ `read recital 12`."
        )
    log.warning(
        "stream_agent_message done session=%s reply_len=%d events_text=%d final_parts=%d tool_result=%s",
        session_id,
        len(reply),
        len(streamed_text_concat),
        len(final_text_parts),
        bool(last_tool_result_text),
    )
    yield {"kind": "final", "session_id": session_id, "reply": reply}


async def reset_session(session_id: str, user_id: str = "user") -> None:
    """Delete a chat session so the next message starts fresh."""
    if _session_service is None:
        return
    try:
        await _session_service.delete_session(
            app_name=_APP_NAME, user_id=user_id, session_id=session_id
        )
    except Exception as e:  # noqa: BLE001
        log.warning("reset_session(%s) failed: %s", session_id, e)
