# Web Stack Overview

`web/` holds the shared web scaffolding for the Phase 7 browser surfaces.

## Tree

- `web/concierge/` — shopper-facing standalone **Astronomy Concierge** web app and API (this slice).
- `web/control_plane/` — SE-facing control-plane web surface (separate slice, separate owner).

## Shared stack

- Backend: **FastAPI**.
- Streaming transport: **SSE** (`/chat/stream` and control-plane streaming endpoints).
- Frontend: lightweight app per surface (concierge currently ships a small static React app).
- Telemetry: wraps existing package cores (`agent/`, `control_plane/`) rather than re-implementing logic.

## Port map (env-driven)

- `CONCIERGE_WEB_PORT` (default `8090`) — shopper-facing concierge app + API.
- `CONTROL_PLANE_WEB_PORT` (default `8099`) — reserved for the SE control-plane UI.
- `CONCIERGE_API_URL` (default `http://localhost:8090`) — browser/API base for concierge clients.
- `WEB_ALLOWED_ORIGIN` (default `http://localhost:8080`) — storefront origin allowed by concierge CORS.

## Topology (signed off W6)

- Concierge and control-plane web services are **separate processes**.
- They may share implementation patterns and dependencies, but do not share a runtime process.
- The control plane is fault-triggering infrastructure and must remain **loopback-only** (`127.0.0.1`/`::1`), never exposed as a public bind.
