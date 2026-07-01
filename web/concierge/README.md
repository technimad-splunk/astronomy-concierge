# Astronomy Concierge Web Slice (Phase 7.1–7.3)

This directory contains the standalone, co-located **Astronomy Concierge** web app and
the FastAPI service that wraps the existing `agent/` core.

## Galileo multi-session concurrency spike (Phase 7.1 risk)

### Finding

- `agent.telemetry.setup_telemetry()` (callback mode) builds a single shared `GalileoLogger`
  and callback list per process.
- `Telemetry.start_session(session_id)` mutates that shared logger's active session context.
- In a long-lived web process, two simultaneous requests calling `start_session(...)` against
  one shared logger can race and cross-label Galileo session traces.

### Chosen safe approach

- **Serialized request execution only when Galileo callback mode is active**:
  - `ConciergeSessionManager` uses a global async lock around graph execution if
    `telemetry.status.galileo_mode == "callback"`.
  - In OTLP mode (`GALILEO_OTEL_EXPORT=1`) the lock is not applied, so requests can run concurrently.
- This avoids cross-session trace contamination without changing `agent/telemetry.py`.

## Service behavior

- `setup_telemetry()` runs **once at process boot** (FastAPI lifespan).
- Session manager maps each conversation to a stable session:
  - `conversation_id` (web identity) -> `session_id` (`concierge-<conversation_id>`).
  - One `StoreClient` and one `build_concierge(...)` graph per conversation.
- Every turn executes inside `using_session(session_id)`.
- Each turn creates a wrapper span with `gen_ai.conversation.id=<conversation_id>`.
- Endpoints:
  - `POST /chat` — one turn in, one reply out.
  - `GET /chat/stream` — SSE token stream (`conversation`, `token`, `done`, `error` events).
  - `POST /admin/reload` — admin reset; auth-required when `CONCIERGE_ADMIN_TOKEN` is set.
  - `POST /admin/scenario/apply` — apply `tool_fault`, `prompt_overlay`, or `rag_corpus`
    state to in-memory overlay storage and reload sessions.
  - `POST /admin/scenario/reset` — clear one trigger type's overlay state and reload sessions.
  - `GET /healthz` — liveness check.
- Shutdown drains in-flight turns before telemetry shutdown/flush.

## Hot-reload semantics (Phase 7.3)

- Overlay changes are applied through admin API calls and picked up on **new
  conversation sessions** after a manager reload.
- On each new session and on `/admin/reload`, `agent.rag.clear_corpus_cache()` is called to
  invalidate the `lru_cache` corpus memoization.
- `/admin/reload` and `/admin/scenario/*` both drop all in-memory conversation
  sessions, forcing fresh graph/session builds on the next request.

## Security and runtime notes

- CORS is restricted to `WEB_ALLOWED_ORIGIN` (default `http://localhost:8080`).
- Admin auth is a fail-closed dual gate:
  - if `CONCIERGE_ADMIN_TOKEN` is set, `/admin/reload` and `/admin/scenario/*`
    require `Authorization: Bearer <token>`;
  - if `CONCIERGE_ADMIN_TOKEN` is unset, these endpoints stay loopback-only.
- `scripts/stage-up.sh` auto-generates and persists `CONCIERGE_ADMIN_TOKEN` to
  `.env` on first bring-up (trust-on-first-use) so the containerized concierge
  and the host control-plane share it automatically. Standalone host-only runs
  (`scripts/concierge-serve.sh`) work via the loopback fallback when no token is set.
- `conversation_id` and request payloads are validated; tool-level input validation remains in
  `agent/store_client.py`.
- No `GALILEO_*`, `SPLUNK_*`, or `OPENAI_*` values are returned in API payloads or logs.
- Containerized runtime assumptions:
  - Ollama remains native on host: `OLLAMA_HOST=http://host.docker.internal:11434`.
  - Store API on compose network: `STORE_BASE_URL=http://frontend-proxy:8080`.
  - Collector on compose network: `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317`.

## Parent verification checklist (ordered)

1. `cp .env.example .env` (if needed) and set required non-placeholder telemetry/model values.
2. Confirm `CONCIERGE_WEB_PORT`, `WEB_ALLOWED_ORIGIN`, and `CONCIERGE_API_URL` are set as intended.
3. `CONCIERGE_ADMIN_TOKEN` is auto-generated and saved to `.env` on first
   `scripts/stage-up.sh` (trust-on-first-use); no manual token step is needed.
4. Run `scripts/stage-up.sh` (or your existing stage flow) to bring up storefront + collector.
5. Validate compose merge: `docker compose -f stage/opentelemetry-demo/docker-compose.yml -f stage/opentelemetry-demo/docker-compose.override.yml config`.
6. Start concierge web container via stage compose and verify `concierge-web` is healthy/logging.
7. Open `http://localhost:${CONCIERGE_WEB_PORT}` and run a multi-turn chat.
8. Verify `POST /chat` works with `curl` and returns stable `conversation_id`/`session_id`.
9. Verify `GET /chat/stream` emits `token` events and final `done` payload.
10. Run two concurrent chats and confirm Galileo traces remain session-isolated.
11. Apply a `rag_corpus` / `prompt_overlay` / `tool_fault` trigger via `/admin/scenario/apply`,
    start a **new** conversation, and verify behavior changes.
12. Call `POST /admin/reload` (token-auth or loopback, depending on config), then verify new conversations rebuild with fresh overlay state.
13. Call `POST /admin/scenario/reset` and verify only the targeted trigger state is cleared.
14. Confirm telemetry parity:
    - Galileo: Sessions -> Traces -> Spans grouped per conversation/session.
    - Splunk: `gen_ai.*` spans + GenAI histogram metrics present for concierge service.
