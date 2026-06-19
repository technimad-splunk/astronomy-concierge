"""Session management + execution primitives for the concierge web service."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from queue import Empty, Queue
from typing import Any, AsyncGenerator

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage
from openinference.instrumentation import using_session
from opentelemetry import trace as trace_api

from agent import rag
from agent.graph import build_concierge
from agent.store_client import StoreClient
from agent.telemetry import Telemetry


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


@dataclass
class ConciergeSession:
    conversation_id: str
    session_id: str
    store: StoreClient
    agent: Any
    history: list[Any] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ConciergeSessionManager:
    """Owns conversation sessions and runs LangGraph turns safely."""

    def __init__(self, telemetry: Telemetry) -> None:
        self._telemetry = telemetry
        self._sessions: dict[str, ConciergeSession] = {}
        self._sessions_lock = asyncio.Lock()
        self._galileo_lock = asyncio.Lock()
        self._activity_lock = asyncio.Lock()
        self._idle = asyncio.Event()
        self._idle.set()
        self._active_turns = 0
        self._shutting_down = False
        self._tracer = trace_api.get_tracer("web.concierge")

    @property
    def galileo_is_serialized(self) -> bool:
        """True when shared Galileo callback mode requires request serialization."""
        return (
            self._telemetry.status.galileo_mode == "callback"
            and bool(self._telemetry.callbacks)
        )

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
        return ConciergeSession(
            conversation_id=conversation_id,
            session_id=session_id,
            store=store,
            agent=agent,
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

    def _invoke_graph(
        self,
        session: ConciergeSession,
        user_text: str,
        extra_callbacks: list[Any] | None = None,
    ) -> TurnResult:
        history = [*session.history, HumanMessage(content=user_text)]
        callbacks = [*self._telemetry.callbacks]
        if extra_callbacks:
            callbacks.extend(extra_callbacks)
        config = {"callbacks": callbacks} if callbacks else {}

        # In callback mode the Galileo logger stores mutable process-global session
        # state. The caller serializes invocations while this mode is active.
        if self._telemetry.status.galileo_mode == "callback":
            self._telemetry.start_session(session.session_id)

        try:
            with using_session(session.session_id):
                with self._tracer.start_as_current_span(
                    "concierge.chat.turn",
                    attributes={
                        "gen_ai.conversation.id": session.conversation_id,
                        "concierge.session.id": session.session_id,
                    },
                ):
                    result = session.agent.invoke({"messages": history}, config=config)

            session.history[:] = result.get("messages", history)
            return TurnResult(
                conversation_id=session.conversation_id,
                session_id=session.session_id,
                reply=self._extract_reply(result),
            )
        finally:
            # In callback mode Galileo buffers traces in-process; flush each turn so
            # long-lived web workers upload interactions immediately.
            if self._telemetry.status.galileo_mode == "callback":
                self._telemetry.flush_galileo()

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
                if self.galileo_is_serialized:
                    async with self._galileo_lock:
                        return await asyncio.to_thread(
                            self._invoke_graph, session, message
                        )
                return await asyncio.to_thread(self._invoke_graph, session, message)
        finally:
            await self._end_turn()

    async def _stream_locked_turn(
        self, session: ConciergeSession, message: str
    ) -> AsyncGenerator[dict[str, str], None]:
        token_queue: Queue[str] = Queue()
        token_callback = TokenQueueCallback(token_queue)
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(
            None,
            self._invoke_graph,
            session,
            message,
            [token_callback],
        )

        streamed_tokens: list[str] = []
        while True:
            if future.done() and token_queue.empty():
                break
            try:
                token = token_queue.get_nowait()
            except Empty:
                await asyncio.sleep(0.02)
                continue
            streamed_tokens.append(token)
            yield {"event": "token", "data": json.dumps({"token": token})}

        turn = await future
        if turn.reply and not streamed_tokens:
            yield {"event": "token", "data": json.dumps({"token": turn.reply})}
        yield {
            "event": "done",
            "data": json.dumps(
                {
                    "conversation_id": turn.conversation_id,
                    "session_id": turn.session_id,
                    "reply": turn.reply,
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
                if self.galileo_is_serialized:
                    async with self._galileo_lock:
                        async for event in self._stream_locked_turn(session, message):
                            yield event
                else:
                    async for event in self._stream_locked_turn(session, message):
                        yield event
        finally:
            await self._end_turn()

    async def reload(self, wait_for_idle: bool = True) -> int:
        """Drop all in-memory sessions and force next turn to rebuild from overlay."""
        if wait_for_idle:
            await self._idle.wait()
        if self._telemetry.status.galileo_mode == "callback" and wait_for_idle:
            if self.galileo_is_serialized:
                async with self._galileo_lock:
                    await asyncio.to_thread(self._telemetry.flush_galileo, True)
            else:
                await asyncio.to_thread(self._telemetry.flush_galileo, True)
        rag.clear_corpus_cache()
        async with self._sessions_lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            session.store.close()
        return len(sessions)

    async def shutdown(self, drain_timeout_s: float = 15.0) -> None:
        async with self._activity_lock:
            self._shutting_down = True
            if self._active_turns == 0:
                self._idle.set()

        try:
            await asyncio.wait_for(self._idle.wait(), timeout=drain_timeout_s)
        except asyncio.TimeoutError:
            pass

        if self._telemetry.status.galileo_mode == "callback":
            if self._idle.is_set() and self.galileo_is_serialized:
                async with self._galileo_lock:
                    await asyncio.to_thread(self._telemetry.flush_galileo, True)
            else:
                await asyncio.to_thread(self._telemetry.flush_galileo, True)
        await self.reload(wait_for_idle=False)
        self._telemetry.shutdown()
