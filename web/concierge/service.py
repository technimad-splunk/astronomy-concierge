"""Session management + execution primitives for the concierge web service."""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from queue import Empty, Queue
from typing import Any, AsyncGenerator

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.errors import GraphRecursionError
from openinference.instrumentation import using_session
from opentelemetry import trace as trace_api
from opentelemetry.trace import Status, StatusCode

from agent import overlay
from agent import rag
from agent.graph import build_concierge
from agent.store_client import StoreClient
from agent.telemetry import Telemetry

_RECURSION_SENTINEL_REPLY = "Sorry, need more steps to process this request."


class TokenQueueCallback(BaseCallbackHandler):
    """Collect streaming LLM tokens so SSE can emit them incrementally."""

    def __init__(self, token_queue: Queue[str]) -> None:
        self._token_queue = token_queue

    def on_llm_new_token(self, token: str, **_: Any) -> None:
        if token:
            self._token_queue.put(token)


@dataclass
class TurnResult:
    conversation_id: str
    session_id: str
    reply: str
    cart_mutated: bool = False
    history: list[Any] | None = None
    outcome: str = "ok"
    truncated: bool = False


@dataclass
class ConciergeSession:
    conversation_id: str
    session_id: str
    store: StoreClient
    agent: Any
    galileo_logger: Any = None
    callbacks: list[Any] = field(default_factory=list)
    history: list[Any] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def _max_concurrent_turns() -> int:
    raw = os.getenv("CONCIERGE_MAX_CONCURRENT_TURNS", "4").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 4


def _turn_recursion_limit() -> int:
    raw = os.getenv("CONCIERGE_TURN_RECURSION_LIMIT", "18").strip()
    try:
        return max(4, int(raw))
    except ValueError:
        return 18


def _turn_timeout_seconds() -> float:
    raw = os.getenv("CONCIERGE_TURN_TIMEOUT_SECONDS", "120").strip()
    try:
        return max(10.0, float(raw))
    except ValueError:
        return 120.0


def _stream_progress_interval_seconds() -> float:
    raw = os.getenv("CONCIERGE_STREAM_PROGRESS_INTERVAL_SECONDS", "5").strip()
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 5.0


class ConciergeSessionManager:
    """Owns conversation sessions and runs LangGraph turns safely."""

    def __init__(self, telemetry: Telemetry) -> None:
        self._telemetry = telemetry
        self._sessions: dict[str, ConciergeSession] = {}
        self._sessions_lock = asyncio.Lock()
        self._turn_semaphore = asyncio.BoundedSemaphore(_max_concurrent_turns())
        self._turn_recursion_limit = _turn_recursion_limit()
        self._turn_timeout_s = _turn_timeout_seconds()
        self._stream_progress_interval_s = _stream_progress_interval_seconds()
        self._activity_lock = asyncio.Lock()
        self._idle = asyncio.Event()
        self._idle.set()
        self._active_turns = 0
        self._shutting_down = False
        self._tracer = trace_api.get_tracer("web.concierge")
        self._prompt_overlay_docs: dict[str, str] = {}
        self._rag_overlay_docs: dict[str, str] = {}

    async def _begin_turn(self) -> None:
        async with self._activity_lock:
            if self._shutting_down:
                raise RuntimeError("Concierge service is shutting down.")
            self._active_turns += 1
            self._idle.clear()

    async def _end_turn(self) -> None:
        async with self._activity_lock:
            self._active_turns = max(self._active_turns - 1, 0)
            if self._active_turns == 0:
                self._idle.set()

    def _create_session(
        self, conversation_id: str, cart_user_id: str | None = None
    ) -> ConciergeSession:
        # Each new conversation should see current overlay state; clear the corpus
        # memoization so rag_corpus overlay changes are picked up.
        rag.clear_corpus_cache()
        session_id = f"concierge-{conversation_id}"
        # Cart identity is the SHARED shopper id (from the storefront session,
        # carried via the `concierge_session` cookie) when provided; otherwise
        # fall back to the conversation-scoped id. Telemetry stays keyed on
        # `session_id` regardless, so Galileo/OTel grouping is unaffected.
        store = StoreClient(session_id=session_id, user_id=cart_user_id or session_id)
        try:
            agent = build_concierge(session_id, store=store)
        except Exception:
            store.close()
            raise
        galileo_logger, callbacks = self._telemetry.new_galileo_session(session_id)
        return ConciergeSession(
            conversation_id=conversation_id,
            session_id=session_id,
            store=store,
            agent=agent,
            galileo_logger=galileo_logger,
            callbacks=callbacks,
        )

    async def get_or_create_session(
        self, conversation_id: str | None = None, cart_user_id: str | None = None
    ) -> ConciergeSession:
        conv_id = conversation_id or uuid.uuid4().hex
        async with self._sessions_lock:
            session = self._sessions.get(conv_id)
            if session is None:
                session = self._create_session(conv_id, cart_user_id=cart_user_id)
                self._sessions[conv_id] = session
            elif cart_user_id and session.store.user_id != cart_user_id:
                # The shopper id can arrive/refresh after the conversation was
                # created (e.g. the storefront tab opened later, or its session
                # id changed). Re-point the existing store so subsequent cart
                # calls hit the shared cart. Tools read `store.user_id` at call
                # time, so no graph rebuild is needed.
                session.store.user_id = cart_user_id
            return session

    @staticmethod
    def _extract_reply(result: dict[str, Any]) -> str:
        messages = result.get("messages", [])
        for msg in reversed(messages):
            if (
                isinstance(msg, AIMessage)
                and isinstance(msg.content, str)
                and msg.content.strip()
            ):
                return msg.content.strip()
        return "(no text reply)"

    @staticmethod
    def _is_recursion_sentinel_reply(reply: str) -> bool:
        return reply.strip() == _RECURSION_SENTINEL_REPLY

    def _recursion_limit_turn(
        self,
        session: ConciergeSession,
        history: list[Any],
        span: Any,
        exc: Exception | None = None,
    ) -> TurnResult:
        reply = (
            "I could not safely complete that request because I hit my "
            "reasoning-step limit. Please rephrase or narrow the ask and try again."
        )
        fallback_history = [*history, AIMessage(content=reply)]
        span.set_status(Status(StatusCode.ERROR, "recursion limit exhausted"))
        span.set_attribute("concierge.turn.outcome", "recursion_limit_exhausted")
        if exc is not None:
            span.record_exception(exc)
        return TurnResult(
            conversation_id=session.conversation_id,
            session_id=session.session_id,
            reply=reply,
            history=fallback_history,
            outcome="recursion_limit_exhausted",
            truncated=True,
        )

    def _invoke_graph(
        self,
        session: ConciergeSession,
        user_text: str,
        extra_callbacks: list[Any] | None = None,
    ) -> TurnResult:
        history = [*session.history, HumanMessage(content=user_text)]
        callbacks = [*session.callbacks]
        if extra_callbacks:
            callbacks.extend(extra_callbacks)
        config: dict[str, Any] = {"recursion_limit": self._turn_recursion_limit}
        if callbacks:
            config["callbacks"] = callbacks

        cart_mutation_before = session.store.cart_mutation_version
        try:
            with using_session(session.session_id):
                with self._tracer.start_as_current_span(
                    "concierge.chat.turn",
                    attributes={
                        "gen_ai.conversation.id": session.conversation_id,
                        "concierge.session.id": session.session_id,
                        "concierge.turn.recursion_limit": self._turn_recursion_limit,
                    },
                ) as span:
                    try:
                        result = session.agent.invoke({"messages": history}, config=config)
                    except GraphRecursionError as exc:
                        return self._recursion_limit_turn(session, history, span, exc)
                    reply = self._extract_reply(result)
                    if self._is_recursion_sentinel_reply(reply):
                        return self._recursion_limit_turn(session, history, span)
                    span.set_attribute("concierge.turn.outcome", "ok")

            cart_mutated = session.store.cart_mutation_version > cart_mutation_before
            return TurnResult(
                conversation_id=session.conversation_id,
                session_id=session.session_id,
                reply=reply,
                cart_mutated=cart_mutated,
                history=result.get("messages", history),
            )
        finally:
            # Each session uses its own callback logger; flush after every turn for
            # immediate upload in long-lived web workers.
            logger = session.galileo_logger
            if logger is not None:
                try:
                    logger.flush()
                except Exception:
                    pass

    async def _invoke_graph_threaded(
        self,
        session: ConciergeSession,
        message: str,
        extra_callbacks: list[Any] | None = None,
    ) -> TurnResult:
        async with self._turn_semaphore:
            return await asyncio.to_thread(
                self._invoke_graph, session, message, extra_callbacks
            )

    @staticmethod
    def _commit_turn_history(session: ConciergeSession, turn: TurnResult) -> None:
        if turn.history is not None:
            session.history[:] = turn.history

    def _timeout_turn(self, session: ConciergeSession, user_text: str) -> TurnResult:
        timeout_s = int(self._turn_timeout_s)
        reply = (
            f"I'm still working, but this turn timed out after about {timeout_s} seconds. "
            "Please try a narrower request."
        )
        history = [*session.history, HumanMessage(content=user_text), AIMessage(content=reply)]
        with using_session(session.session_id):
            with self._tracer.start_as_current_span(
                "concierge.chat.turn",
                attributes={
                    "gen_ai.conversation.id": session.conversation_id,
                    "concierge.session.id": session.session_id,
                    "concierge.turn.recursion_limit": self._turn_recursion_limit,
                    "concierge.turn.timeout_seconds": self._turn_timeout_s,
                    "concierge.turn.outcome": "timeout",
                },
            ) as span:
                span.set_status(Status(StatusCode.ERROR, "turn timeout"))
        return TurnResult(
            conversation_id=session.conversation_id,
            session_id=session.session_id,
            reply=reply,
            history=history,
            outcome="timeout",
            truncated=True,
        )

    @staticmethod
    def _close_session_telemetry(session: ConciergeSession) -> None:
        logger = session.galileo_logger
        if logger is None:
            return
        try:
            logger.flush()
        except Exception:
            pass
        conclude_fn = getattr(logger, "conclude", None)
        if callable(conclude_fn):
            try:
                conclude_fn()
            except Exception:
                pass
        terminate_fn = getattr(logger, "terminate", None)
        if callable(terminate_fn):
            try:
                terminate_fn()
            except Exception:
                pass

    async def run_turn(
        self,
        message: str,
        conversation_id: str | None = None,
        cart_user_id: str | None = None,
    ) -> TurnResult:
        session = await self.get_or_create_session(conversation_id, cart_user_id)
        await self._begin_turn()
        try:
            async with session.lock:
                try:
                    turn = await asyncio.wait_for(
                        self._invoke_graph_threaded(session, message),
                        timeout=self._turn_timeout_s,
                    )
                except asyncio.TimeoutError:
                    turn = self._timeout_turn(session, message)
                self._commit_turn_history(session, turn)
                return turn
        finally:
            await self._end_turn()

    async def _stream_locked_turn(
        self, session: ConciergeSession, message: str
    ) -> AsyncGenerator[dict[str, str], None]:
        token_queue: Queue[str] = Queue()
        token_callback = TokenQueueCallback(token_queue)
        future = asyncio.create_task(
            self._invoke_graph_threaded(session, message, [token_callback])
        )

        streamed_tokens: list[str] = []
        started = time.monotonic()
        next_progress = started + self._stream_progress_interval_s
        while True:
            if future.done() and token_queue.empty():
                break
            try:
                token = token_queue.get_nowait()
            except Empty:
                now = time.monotonic()
                if now >= next_progress:
                    elapsed_s = int(now - started)
                    yield {
                        "event": "progress",
                        "data": json.dumps(
                            {
                                "status": "working",
                                "elapsed_seconds": elapsed_s,
                                "message": f"Still working... ({elapsed_s}s)",
                            }
                        ),
                    }
                    next_progress = now + self._stream_progress_interval_s
                if (now - started) >= self._turn_timeout_s:
                    future.cancel()
                    turn = self._timeout_turn(session, message)
                    self._commit_turn_history(session, turn)
                    yield {
                        "event": "done",
                        "data": json.dumps(
                            {
                                "conversation_id": turn.conversation_id,
                                "session_id": turn.session_id,
                                "reply": turn.reply,
                                "cart_mutated": False,
                                "outcome": turn.outcome,
                                "truncated": turn.truncated,
                            }
                        ),
                    }
                    return
                await asyncio.sleep(0.02)
                continue
            streamed_tokens.append(token)
            yield {"event": "token", "data": json.dumps({"token": token})}

        turn = await future
        self._commit_turn_history(session, turn)
        if turn.reply and not streamed_tokens:
            yield {"event": "token", "data": json.dumps({"token": turn.reply})}
        yield {
            "event": "done",
            "data": json.dumps(
                {
                    "conversation_id": turn.conversation_id,
                    "session_id": turn.session_id,
                    "reply": turn.reply,
                    "cart_mutated": turn.cart_mutated,
                    "outcome": turn.outcome,
                    "truncated": turn.truncated,
                }
            ),
        }

    async def stream_turn(
        self,
        message: str,
        conversation_id: str | None = None,
        cart_user_id: str | None = None,
    ) -> AsyncGenerator[dict[str, str], None]:
        session = await self.get_or_create_session(conversation_id, cart_user_id)
        await self._begin_turn()
        try:
            yield {
                "event": "conversation",
                "data": json.dumps(
                    {
                        "conversation_id": session.conversation_id,
                        "session_id": session.session_id,
                    }
                ),
            }
            async with session.lock:
                async for event in self._stream_locked_turn(session, message):
                    yield event
        finally:
            await self._end_turn()

    async def reload(self, wait_for_idle: bool = True) -> int:
        """Drop all in-memory sessions and force next turn to rebuild from overlay."""
        if wait_for_idle:
            await self._idle.wait()
        rag.clear_corpus_cache()
        async with self._sessions_lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            self._close_session_telemetry(session)
            session.store.close()
        return len(sessions)

    def _merged_overlay_docs(self) -> dict[str, str]:
        merged = dict(self._rag_overlay_docs)
        merged.update(self._prompt_overlay_docs)
        return merged

    async def apply_overlay(self, req: dict[str, Any]) -> int:
        trigger_type = str(req["trigger_type"])
        scenario_id = str(req["scenario_id"])

        if trigger_type == "tool_fault":
            tool_fault = req["tool_fault"]
            overlay.set_tool_fault(
                str(tool_fault["tool"]),
                {
                    "mode": str(tool_fault["mode"]),
                    "message": str(tool_fault.get("message", "")),
                    "data": str(tool_fault.get("data", "")),
                },
            )
        elif trigger_type == "prompt_overlay":
            text = str(req.get("prompt_overlay_text", ""))
            overlay.set_prompt_overlay(text)
            self._prompt_overlay_docs = {f"{scenario_id}-overlay.md": text}
            overlay.set_knowledge_docs(self._merged_overlay_docs())
        elif trigger_type == "rag_corpus":
            docs = {
                str(name): str(content)
                for name, content in dict(req.get("rag_corpus_docs", {})).items()
            }
            self._rag_overlay_docs = docs
            overlay.set_knowledge_docs(self._merged_overlay_docs())
        else:
            raise ValueError(f"unsupported trigger_type: {trigger_type}")

        return await self.reload()

    async def reset_overlay(self, req: dict[str, Any]) -> int:
        trigger_type = str(req["trigger_type"])

        if trigger_type == "tool_fault":
            tool = str(req.get("ref", ""))
            if not tool:
                raise ValueError("tool_fault reset requires ref (tool name)")
            overlay.clear_tool_fault(tool)
        elif trigger_type == "prompt_overlay":
            overlay.clear_prompt_overlay()
            self._prompt_overlay_docs = {}
            overlay.set_knowledge_docs(self._merged_overlay_docs())
        elif trigger_type == "rag_corpus":
            self._rag_overlay_docs = {}
            overlay.set_knowledge_docs(self._merged_overlay_docs())
        else:
            raise ValueError(f"unsupported trigger_type: {trigger_type}")

        return await self.reload()

    async def shutdown(self, drain_timeout_s: float = 15.0) -> None:
        async with self._activity_lock:
            self._shutting_down = True
            if self._active_turns == 0:
                self._idle.set()

        try:
            await asyncio.wait_for(self._idle.wait(), timeout=drain_timeout_s)
        except asyncio.TimeoutError:
            pass

        await self.reload(wait_for_idle=False)
        self._telemetry.shutdown()
