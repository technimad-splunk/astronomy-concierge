"""FastAPI wrapper for the Astronomy Concierge agent core."""

from __future__ import annotations

import json
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sse_starlette.sse import EventSourceResponse

from agent.telemetry import setup_telemetry

from .service import ConciergeSessionManager

_CONVERSATION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
# The shared shopper / cart id. The storefront uses a UUIDv4; the concierge may
# generate its own UUID. Accept the same safe charset as conversation ids.
_CART_USER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"
_EMBED_DIR = Path(__file__).parent / "embed"
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _normalize_message(message: str) -> str:
    text = message.strip()
    if not text:
        raise ValueError("message must not be empty")
    return text


def _validate_conversation_id(conversation_id: str | None) -> str | None:
    if conversation_id is None:
        return None
    if not _CONVERSATION_ID_RE.match(conversation_id):
        raise ValueError(
            "conversation_id must match [A-Za-z0-9_-] and be at most 64 chars"
        )
    return conversation_id


def _validate_cart_user_id(cart_user_id: str | None) -> str | None:
    if cart_user_id is None:
        return None
    value = cart_user_id.strip()
    if not value:
        return None
    if not _CART_USER_ID_RE.match(value):
        raise ValueError(
            "cart_user_id must match [A-Za-z0-9_-] and be at most 64 chars"
        )
    return value


def _loopback_only(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in {"127.0.0.1", "::1", "localhost"}


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, max_length=64)
    cart_user_id: str | None = Field(default=None, max_length=64)

    @field_validator("message")
    @classmethod
    def _validate_message(cls, value: str) -> str:
        return _normalize_message(value)

    @field_validator("conversation_id")
    @classmethod
    def _validate_conversation(cls, value: str | None) -> str | None:
        return _validate_conversation_id(value)

    @field_validator("cart_user_id")
    @classmethod
    def _validate_cart_user(cls, value: str | None) -> str | None:
        return _validate_cart_user_id(value)


class ChatResponse(BaseModel):
    conversation_id: str
    session_id: str
    reply: str


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Load .env for non-container launches (e.g. scripts/concierge-serve.sh runs
    # uvicorn directly without injecting telemetry env). Existing process env —
    # such as the docker compose `environment:` block — always wins, so the
    # containerized collector/Galileo config is unaffected.
    load_dotenv(dotenv_path=_REPO_ROOT / ".env")
    telemetry = setup_telemetry()
    app.state.manager = ConciergeSessionManager(telemetry)
    yield
    await app.state.manager.shutdown()


app = FastAPI(
    title="Astronomy Concierge Web",
    version="0.1.0",
    lifespan=_lifespan,
)

allowed_origin = os.getenv("WEB_ALLOWED_ORIGIN", "http://localhost:8080").rstrip("/")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[allowed_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    # Allow embedding from the storefront origin only (plus self), so the
    # injected bridge on :8080 can present the concierge app in a modal iframe.
    response.headers["Content-Security-Policy"] = (
        f"frame-ancestors 'self' {allowed_origin}"
    )
    response.headers["Cache-Control"] = "no-store"
    return response


if (_FRONTEND_DIST / "assets").is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=str(_FRONTEND_DIST / "assets")),
        name="concierge-assets",
    )

# Vite copies `frontend/public/*` (e.g. the bundled Astronomy Shop logo at
# /images/opentelemetry-demo-logo.png) to the dist root, which is not covered by
# the hashed `/assets` mount. Serve it from the concierge's own origin so the
# header logo does not depend on the storefront being up.
if (_FRONTEND_DIST / "images").is_dir():
    app.mount(
        "/images",
        StaticFiles(directory=str(_FRONTEND_DIST / "images")),
        name="concierge-images",
    )


def _manager(request: Request) -> ConciergeSessionManager:
    return request.app.state.manager


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    manager = _manager(request)
    try:
        turn = await manager.run_turn(
            payload.message, payload.conversation_id, payload.cart_user_id
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ChatResponse(
        conversation_id=turn.conversation_id,
        session_id=turn.session_id,
        reply=turn.reply,
    )


@app.get("/chat/stream")
async def chat_stream(
    request: Request,
    message: Annotated[str, Query(min_length=1, max_length=4000)],
    conversation_id: Annotated[str | None, Query(max_length=64)] = None,
    cart_user_id: Annotated[str | None, Query(max_length=64)] = None,
):
    try:
        normalized_message = _normalize_message(message)
        normalized_conversation_id = _validate_conversation_id(conversation_id)
        normalized_cart_user_id = _validate_cart_user_id(cart_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    manager = _manager(request)

    async def _events():
        try:
            async for event in manager.stream_turn(
                normalized_message,
                normalized_conversation_id,
                normalized_cart_user_id,
            ):
                if await request.is_disconnected():
                    break
                yield event
        except RuntimeError as exc:
            yield {"event": "error", "data": json.dumps({"detail": str(exc)})}
        except Exception:
            yield {
                "event": "error",
                "data": json.dumps({"detail": "streaming failed"}),
            }

    return EventSourceResponse(_events(), ping=15)


@app.post("/admin/reload")
async def admin_reload(request: Request) -> dict[str, int | str]:
    if not _loopback_only(request):
        raise HTTPException(status_code=403, detail="admin reload is loopback-only")
    cleared = await _manager(request).reload()
    return {"status": "reloaded", "cleared_sessions": cleared}


@app.get("/embed/concierge-bridge.js", include_in_schema=False)
async def concierge_bridge_js():
    """Serve the storefront-side bridge script.

    This file is injected into the Astronomy Shop storefront page (via the
    frontend-proxy Envoy override) and therefore executes on the storefront's
    OWN origin, where it can read the real shopper session from localStorage and
    mirror it into the cross-port `concierge_session` cookie. It is also the hook
    point for later mounting the concierge widget (an iframe to this origin) into
    the storefront UI. Served as a classic script (no CORS needed)."""
    bridge_file = _EMBED_DIR / "concierge-bridge.js"
    if not bridge_file.is_file():
        raise HTTPException(status_code=404, detail="bridge script not found")
    return FileResponse(bridge_file, media_type="application/javascript")


@app.get("/", include_in_schema=False)
async def index():
    index_file = _FRONTEND_DIST / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)
    return HTMLResponse(
        """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Astronomy Concierge</title>
    <style>
      body { font-family: sans-serif; margin: 2rem; max-width: 40rem; line-height: 1.5; }
      code { background: #f4f4f4; padding: 0.2rem 0.4rem; border-radius: 0.25rem; }
    </style>
  </head>
  <body>
    <h1>Astronomy Concierge</h1>
    <p>The frontend bundle is not present. Build it from <code>web/concierge/frontend</code>:</p>
    <pre>npm ci && npm run build</pre>
  </body>
</html>
        """.strip()
    )
