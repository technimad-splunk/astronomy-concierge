# Web Interface Plan — Control Plane UI + Storefront Concierge

> Status: **Phases 7.0–7.4 implemented (static/integration-verified, 2026-06-19); Phase 7.5 live
> clean-room sign-off PENDING.** This document analyses the implications of, and sequences the work
> for, augmenting the project's two CLIs with web experiences. The web layers have now been built by
> two parallel coding subagents as thin wrappers over the unchanged `agent/` and `control_plane/`
> cores. Source of truth for *what the demo is* remains [`docs/demo-design.md`](demo-design.md); the
> build sequencing is now reflected in [`docs/implementation-plan.md`](implementation-plan.md)
> (Phase 7 added — the user confirmed and directed the Phase 7 build). The open decisions were
> signed off on **2026-06-18** (W1–W8 — see [§14 Resolved decisions](#14-resolved-decisions)); the
> headline outcomes are a **standalone "Astronomy Concierge" chat app first**, a
> **containerized-only** agent service, and **two separately-sequenced web slices** (concierge after
> Phase 2, control-plane UI after Phase 3) rather than one monolithic late phase. The optional Envoy
> `<script>` storefront injection (W1) remains **out of scope** as a later, optional fidelity
> enhancement. **What's verified so far is static/integration only** (deps install; both apps boot;
> loopback guard accepts loopback / rejects `0.0.0.0`; registry discovers all 8 scenarios with no
> core edits; compose override merges; frontend `dist` builds); the **live clean-room proof**
> (Phase 7.5) is not yet done — see [§10](#10-phased-task-breakdown-proposed-phase-7).

## How to read this

- This plan covers **two related but separately-audienced** UI changes:
  1. A **web UI for the SE control plane** (today the `control_plane/` CLI: `list/play/reset/verify/playlist`).
  2. The **concierge embedded as a chat experience in the Astronomy Shop storefront** (today the `agent/` CLI).
- It follows the existing plan's conventions: dependency-ordered phases, **verifiable Exit
  criteria** (per [`automate-verify`](../.cursor/rules/automate-verify.mdc)), and a Decisions
  table. Limitations referenced by ID (**L1**, **L2**) map to `docs/demo-design.md` §9.
- The hardest calls — **reproducible frontend injection**, **agent-as-a-service**, and **trigger
  hot-reload** — each get options + tradeoffs + a recommendation, and the user's signed-off
  outcomes are restated in [§14 Resolved decisions](#14-resolved-decisions).

---

## 1. Goals

1. **SE control-plane web UI.** Give the SE a browser surface for the demo harness — discover
   scenarios, play/reset a vignette, watch live play/verify output stream, and compose playlists —
   without losing the stable seam that makes scenarios drop-in folders.
2. **Storefront concierge chat.** Let a shopper talk to the concierge **inside the Astronomy
   Shop** rather than via a host terminal, turning the agent into a request/response (and
   streaming) service while **preserving the single-instrument → dual-fan-out telemetry** keystone
   (design §3) and the harness trigger seam (design §7).
3. **Lose nothing we just earned.** Reproducibility (clean-room rebuild from scripts + pinned
   refs), the `gen_ai.*` spans + GenAI histograms to Splunk AI Agent Monitoring, the Galileo
   Sessions→Traces→Spans, and the "drop-in scenario, no core edits" guarantee must all survive.

**Non-goals (this plan):** writing the apps, scaffolding frameworks, changing the vignette set,
or re-theming the store (design §9.5 keeps the Astronomy Shop theme).

---

## 2. Current-state recap (what we are replacing)

| Surface | Today | Key mechanics relevant to a web port |
|---|---|---|
| **Concierge** | `agent/` LangGraph ReAct agent, run as a **host CLI** (`python -m agent --prompt …` / interactive). | `build_concierge()` builds the graph **once per process/session**; `setup_telemetry()` runs **once** at startup; each turn wrapped in `using_session(session_id)` + `galileo_logger.start_session(...)`. `StoreClient` calls the storefront at `http://localhost:8080/api/...`. Telemetry fans out to Splunk (OTLP/gRPC → `localhost:4317`) and Galileo (`GalileoCallback`). |
| **Control plane** | `control_plane/` package, **CLI** (`python -m control_plane …`). | `registry.discover()` auto-finds `scenarios/*/scenario.yaml`; `apply_trigger`/`reset_trigger` over the four fixed triggers; `play` shells out to `python -m agent` as a subprocess; `verify` polls Galileo with retry. Stable seam: adding scenarios never edits the package. |
| **Stage** | Vendored upstream OTel demo (the Astronomy Shop), **gitignored clone pinned to `stage/demo.ref` (`2.2.0`)**, materialized by `scripts/stage-setup.sh`. | `frontend` = Next.js/React behind the **Envoy `frontend-proxy` at `:8080`**; `flagd` hot-reloads `src/flagd/demo.flagd.json`. Our only touches are **tracked overrides re-synced into the clone** by setup: `otelcol-config-extras.yml` (Splunk export via the collector's documented extras merge) and `docker-compose.override.yml` (collector ports + `SPLUNK_*`). **We never hand-edit the clone.** |

**Trigger → agent seam (today).** Three of the four triggers write to the gitignored overlay
`agent/_overlay/` and the agent reads them **when it builds the graph/tools** (i.e. at process/
session start, not per request):

| Trigger | Writes | Read by | When it takes effect today |
|---|---|---|---|
| `feature_flag` | edits vendored `demo.flagd.json` | the demo's services | immediately (flagd hot-reloads) |
| `rag_corpus` | `agent/_overlay/knowledge/*.md` | `agent/rag.py` | next corpus load (note: `rag.py` uses `lru_cache`) |
| `prompt_overlay` | `agent/_overlay/prompt_overlay.txt` | `agent/graph.py` | next `build_concierge()` |
| `tool_fault` | `agent/_overlay/tool_faults.json` | `agent/tools.py` | next `make_tools()` |

The CLI sidesteps freshness entirely: every `play` is a **new agent process**, so overlays are
always read fresh. **A long-lived service breaks that assumption** — see [§6](#6-trigger-hot-reload-on-a-long-lived-agent).

---

## 3. Proposed target architecture

Two new browser surfaces, two thin web backends, **the existing `agent/` and `control_plane/`
packages preserved unchanged as the stable cores**. The CLIs remain as thin clients/fallbacks
over the same cores.

```
        ┌──────────────── Shopper (browser) ────────────────┐         ┌──── SE (browser, localhost only) ────┐
        │  Astronomy Shop storefront  (Envoy proxy :8080)   │         │   Control-plane web UI                │
        │     └─ embedded concierge chat widget ─────────┐  │         │   (list / play / reset / verify /     │
        └────────────────────────────────────────────┐  │  │         │    playlist, live SSE output)         │
                                                       │  │  │         └───────────────┬──────────────────────┘
                                          chat (HTTP/SSE) │  │                         │ REST + SSE
                                                       ▼  ▼  │                         ▼
                                   ┌──────────────────────────────┐        ┌──────────────────────────────┐
                                   │  Concierge service (FastAPI)  │        │  Control-plane service (FastAPI)│
                                   │  thin wrapper over agent/     │        │  thin wrapper over control_plane/│
                                   │  • setup_telemetry() ONCE     │        │  • registry / triggers / verify │
                                   │  • per-session graph build    │        │  • streams play/verify output    │
                                   └───────────────┬──────────────┘        └───────────────┬──────────────┘
                                                   │                                         │ writes overlays / flips flags
                  gen_ai.* spans + GenAI metrics   │  GalileoCallback                        │ (agent/_overlay, demo.flagd.json)
                       (OTLP → local collector)    │  (Sessions→Traces→Spans)                ▼
                                                   ▼                              (the stable trigger seam — unchanged)
                          Splunk OTel Collector ──▶ Splunk Observability            ◀────────┘
                          Galileo SaaS  ◀──────────────────────────────────────────
```

**Design intent:**

- The two web apps are **separate frontends for separate audiences** (shopper vs SE). They MAY
  share a Python web stack and even a single repo `web/` tree, but they are deployed/served
  distinctly — critically because the **control plane triggers faults and must stay localhost-bound**
  ([§8.1 Security](#81-security-local-demo)).
- `agent/` and `control_plane/` stay the **cores/seams**. The web layers only *call* them. This
  keeps the CLI working and means scenarios remain drop-in.

---

## 4. Contentious decision A — reproducible frontend injection

**Constraint (critical, [`automate-verify`](../.cursor/rules/automate-verify.mdc)):** the
storefront is a **pinned, gitignored vendored clone run from pre-built pinned images**
(`DEMO_VERSION=${DEMO_REF}`). We must **not** hand-edit it, and anything that requires *rebuilding
the frontend image from source* is a major deviation (the demo ships pre-built images; building
locally is slow and fragile across upgrades). The whole stage must remain clean-room reproducible.

| Option | What it is | Reproducible? | Upgrade-friendly? | Fidelity | Verdict |
|---|---|---|---|---|---|
| **(a) Scripted patch/overlay of `src/frontend`** applied by `stage-setup.sh` against the pinned ref | Commit a patch; setup applies it to the clone | Only if the patch always applies — **and it forces a local frontend image rebuild** (pinned images won't contain the change) | **Poor** — React source drifts every demo bump; patch rot | High (native) | ✗ Rejected — rebuild + patch-rot defeats the pinned-image reproducibility we just hardened |
| **(b) Separate co-located chat web app** (our own tracked container) the store embeds via iframe / web-component, or links to | New service in our compose override; widget served by us | **Excellent** — 100% our tracked code; clone untouched | **Excellent** — independent of frontend internals | Medium (panel/iframe, not in the React tree) | ✔ Safe core of the recommendation |
| **(c) Envoy / `frontend-proxy`-level injection** | Add a tracked Envoy overlay that injects a one-line `<script>` loader into HTML responses; the script mounts our self-hosted widget | Good **if** done via a tracked file materialized by setup (same idea as the collector extras) | Medium — Envoy has **no clean "extras" merge** like the collector; risk from gzip/streamed bodies + CSP | High (appears in-page) | ◐ Stretch enhancement, with risk |
| **(d) Fork the frontend** | Maintain our own Next.js fork | Reproducible but heavy | **Worst** — we own upgrades forever | Highest | ✗ Rejected |

**Recommendation: (b) as the baseline, with (c) as an opt-in fidelity upgrade.**

- Build the concierge chat as a **self-contained widget app we fully own and track**, served by a
  **new container declared in `stage/splunk-otel/docker-compose.override.yml`** (the same tracked
  override seam already used for the collector — zero edits to the clone, no image rebuild).
- Surface it embedded. **Primary path:** expose the widget through the proxy on a dedicated path
  (e.g. `/concierge`) or its own published port (e.g. `:8090`) and present it as a chat panel; for
  an in-page floating button, add a **single tracked Envoy overlay** that injects one `<script>`
  tag — and **only** if the body-rewrite proves robust (watch gzip + the store's CSP).
- **Fallback (always works):** if proxy injection is fiddly, the widget lives on its own
  port/route and the store links to it — still "embedded-feeling," still zero clone edits.

This deliberately trades a little fidelity for **maximum reproducibility and upgrade-safety**,
which the repo rules prioritise.

> **Signed-off outcome (W1, 2026-06-18):** the **standalone co-located chat web app — "Astronomy
> Concierge" — is the primary FIRST deliverable** (its own route/port, fully tracked by us). This
> is a **deviation** from the recommendation's framing: the optional Envoy `<script>` injection /
> proxy embedding into the Astronomy Shop is a **later, optional fidelity enhancement — not merely
> a fallback**. The store linking-to / patching-in the standalone app is explicitly optional. See
> [§14 Resolved decisions](#14-resolved-decisions).

> **Reproducibility requirement for whichever path wins:** any new container, Envoy overlay, or
> script bundle must be **tracked outside the clone** and **materialized/wired by a script**
> (extend `stage-setup.sh` and/or the compose override), then **clean-room verified** (delete the
> clone + `down`, re-run setup/up, confirm the widget loads).

---

## 5. Contentious decision B — concierge as a service vs CLI

Wrap the existing LangGraph agent in a **FastAPI** service: `POST /chat` (turn in → reply out),
`GET /chat/stream` (SSE token streaming), session-scoped carts and Galileo sessions. The graph,
tools, RAG, store client, and `telemetry.py` are **reused unchanged**; the service only adds an
HTTP shell + session management. The CLI stays as a thin client over the same core.

### 5.1 Where it runs (host process vs container)

| | (A) **Host process** (recommended default) | (B) **Containerized** (compose-override service) |
|---|---|---|
| Ollama (macOS) | **Native `localhost:11434` — keeps Metal acceleration** | Must use `host.docker.internal:11434` (Ollama itself stays native on the host — **never** containerize Ollama on mac, design §8.4) |
| OpenAI | Works | Works (no host dependency) |
| Collector endpoint | `localhost:4317` (today's wiring, unchanged) | `otel-collector:4317` on the compose network — set via `OTEL_EXPORTER_OTLP_ENDPOINT` |
| Store API | `localhost:8080` | `frontend-proxy:8080` on the network |
| Browser → service | Browser is on the host → calls `localhost:PORT` directly (CORS to the storefront origin) | Reached via a published port or proxied path |
| Best fit | **Apple-silicon laptop runtime** | **EC2 / OpenAI runtime** (no Metal concern) |

**Recommendation (superseded — see signed-off outcome below):** the recommendation had been to
ship a **FastAPI concierge service that runs as a host process by default**, **plus an optional
containerized profile**. Because every endpoint is already env-driven (`OLLAMA_HOST`,
`OTEL_EXPORTER_OTLP_ENDPOINT`, `STORE_BASE_URL`), switching between runtimes is **config only —
telemetry is preserved either way**, extending the existing two-runtime split (design §8.1).

> **Signed-off outcome (W2, 2026-06-18):** build **only the containerized implementation** — the
> **containerized concierge service is expected to also work on macOS / Apple Silicon** (Ollama
> itself stays native on the host at `host.docker.internal:11434`; we never containerize Ollama,
> design §8.4). This is a deliberate **deviation** from the "host-process default + optional
> container" recommendation, chosen to **avoid double work** (one implementation, not two).
> **Escape hatch:** if the container path proves to have **major drawbacks on macOS**, fall back to
> also providing the host-process profile. See [§14 Resolved decisions](#14-resolved-decisions).

### 5.2 Telemetry preservation & multi-user sessions (do not regress §3)

- **Instrument once, at process start.** `setup_telemetry()` is called **once** when the service
  boots (not per request). The single `TracerProvider` + `MeterProvider` + Traceloop
  `LangchainInstrumentor` and the dual fan-out are unchanged: `gen_ai.*` spans + GenAI histograms
  → Splunk (with the collector's `send_otlp_histograms: true`), Galileo via `GalileoCallback`.
  `service.name=astronomy-concierge` / `deployment.environment=local-agent-galileo` are preserved
  (env-driven) so the agent keeps correlating with the store in Splunk APM.
- **OTLP endpoint** stays `localhost:4317` for the host-process default; only the containerized
  profile points at `otel-collector:4317`. Metrics stay **delta** (set explicitly in code).
- **Web chat session → Galileo session.** Map each chat conversation to a stable `session_id`
  and call `using_session(session_id)` per request (OpenInference context is request-scoped) so
  spans group into the right Galileo Session. Also set **`gen_ai.conversation.id`** per
  conversation — this is a **net improvement**: it gives Splunk **AI Agent Monitoring / AI trace
  data** first-class conversation grouping the one-shot CLI never produced.
- **Concurrency caveat to design for (real implication):** `galileo_logger.start_session(...)`
  and a single shared `GalileoLogger` are **process-global mutable state** today. Concurrent web
  sessions need either (i) a per-session/request `GalileoLogger` + callback, or (ii) serialized
  session handling, to avoid cross-session trace bleed. **Must be verified early** against the
  Galileo SDK's concurrency model (Galileo OTel/agent tracing is **Beta**, L2). The plan treats
  this as a Phase-7 spike, not an assumption.
- **Lifecycle.** No more per-run `shutdown()`/flush; the long-lived service flushes on a timer/
  shutdown hook. Ensure graceful drain so the last spans/metrics aren't lost.

---

## 6. Contentious decision C — trigger hot-reload on a long-lived agent

Today every `play` is a fresh process, so overlays are always read fresh. A long-running service
must decide **how an SE's just-applied trigger takes effect** — **without** breaking the
"drop-in scenario, no core edits" seam (`overlay.py` stays the read seam; the control plane keeps
just writing files).

| Option | How | Pros | Cons |
|---|---|---|---|
| **(a) Per-session overlay read** (recommended) | Build the graph + tools (and read the corpus) **when a new chat session starts**, via the existing `overlay.py` seam | No new control-plane↔agent coupling; seam untouched; matches SE flow (apply → open a fresh chat → behaviour applies; reset → next fresh chat is baseline) | An **in-flight** conversation keeps its overlay until a new session (acceptable, even desirable for demo stability) |
| **(b) File-watcher hot-reload** | Service watches `agent/_overlay/` + `demo.flagd.json`, rebuilds on change | Mid-conversation changes apply | More moving parts; races mid-turn; debounce needed |
| **(c) Signal / admin endpoint** | Control plane signals the service (`SIGHUP` or `POST /admin/reload`) to rebuild | Explicit, immediate | Couples the control plane to the running service (knows its PID/URL) — erodes the clean seam |

**Recommendation: (a) per-session overlay read**, optionally with a **localhost-only
`POST /admin/reload`** convenience so the control-plane UI can force a rebuild without asking the
SE to open a new chat. Rationale: it preserves the stable seam (control plane still only *writes*
overlay files; the agent still only *reads* them), needs no watcher/signal machinery, and fits
the demo cadence. `feature_flag` already hot-reloads via flagd, so only the three agent-side
overlays are in scope.

> **Implementation note to carry forward:** `agent/rag.py` memoizes corpus load with
> `lru_cache`; a per-session/`reload` rebuild **must invalidate that cache** or a `rag_corpus`
> overlay won't apply on a running service. This is the one small, contained change inside the
> agent core the service port implies — flag it explicitly so it isn't missed.

---

## 7. Control-plane web UI

A **thin web layer over the existing `control_plane/` package** (kept as the stable core/seam):

- **REST** for `list`, `play`, `reset`, `playlist`; **streaming (SSE)** for the live, long-running
  output of `play` (which drives the agent) and `verify` (which polls Galileo with retry under L2
  ingestion lag). SSE is simpler than websockets for one-directional server→browser log streaming;
  use websockets only if bidirectional control is later needed.
- **Framework options:** (i) **FastAPI backend + lightweight frontend (htmx or a small static
  React)** — same stack as the concierge service, full control over SSE and subprocess output;
  (ii) **Streamlit / Gradio** — fastest to stand up but weaker control over streamed subprocess
  logs and a less "product" feel. **Recommendation:** FastAPI + a lightweight frontend, to share
  the concierge's stack and stream cleanly.
- **Relationship to the concierge UI:** **separate apps, separate audiences** (SE vs shopper),
  but they can **share the FastAPI/Python stack and repo `web/` tree** and the same
  session/telemetry concepts. A **shared backend process is possible** but **not recommended**:
  keep the control plane on its own localhost-bound process so its fault-triggering surface is
  never co-exposed with the shopper-facing widget.

---

## 8. Cross-cutting implications

### 8.1 Security (local demo)

- The **control-plane web UI triggers faults** (flips flags, faults tools, injects prompts). It
  MUST be **bound to `127.0.0.1`** only and never exposed on `0.0.0.0` / a public port. Note this
  loudly; do not add auth complexity for a local demo, but **do** keep it loopback-only.
- Apply **light** web hygiene appropriate to a local tool (ref. the repo's client-side and API
  security rules): set a restrictive **CORS** policy (concierge service allows only the storefront
  origin; control-plane UI same-origin), include basic **CSRF**/`SameSite` protection on any
  state-changing POST, and standard security headers. **Don't over-engineer** — this is a
  localhost demo, not an internet service.
- Preserve the agent's existing **input validation** (product-id/currency/quantity allow-lists in
  `store_client.py`) and **no-secrets-in-logs** discipline. The web layer must not echo
  `GALILEO_*` / `SPLUNK_*` / `OPENAI_*`.
- If the Envoy injection path (option c) is chosen, mind the storefront **CSP** so the injected
  script/widget origin is allowed.

### 8.2 Reproducibility of the new pieces

Everything new must be **scripted + pinned + clean-room verifiable** (the rule we just hardened in
Phase 1):

- New services declared in the **tracked** `stage/splunk-otel/docker-compose.override.yml` (or new
  tracked compose files), never by editing the clone.
- New launcher scripts in `scripts/` (e.g. `concierge-serve.sh`, `control-plane-web.sh`, and/or a
  `web-up.sh`) — self-bootstrapping like `agent-run.sh` (venv + pinned deps) — and documented in
  `README.md` / `scripts/README.md` as part of the zero-to-running path.
- `.env.example` additions (pin versions / ports / origins): e.g. `CONCIERGE_API_URL`,
  `CONCIERGE_WEB_PORT`, `CONTROL_PLANE_WEB_PORT`, `WEB_ALLOWED_ORIGIN`, and (containerized
  profile) an `OTEL_EXPORTER_OTLP_ENDPOINT` override.
- Frontend assets/deps pinned (lockfile committed) per the supply-chain rule.
- **Clean-room proof** before "done": from a fresh clone + `.env`, the documented script sequence
  must bring up stage + both web apps with the widget visible and telemetry flowing to both
  backends.

---

## 9. Relationship to the implementation plan

This work is a **candidate new Phase 7** in `docs/implementation-plan.md` (it builds on the
Phase-2 agent and Phase-3 harness, both complete). It does **not** require editing that file now;
when adopted, it would amend:

- **Phase 3** — the control-plane web UI is an *additional surface* over the same package; the CLI
  "stable seam" note stays true (web layer also never edits the package on scenario add).
- **Phase 6 (Delivery & polish)** — the SE runbook gains the web flows; the README backfill
  documents the web entry points.
- **Decisions table** — add the framework/runtime/injection decisions below once signed off.
- **Sequencing & effort** — the two workstreams (control-plane UI vs storefront concierge) are
  **independently parallelizable** (different audiences, different cores), sharing only the FastAPI
  stack choice.

> **Signed-off sequencing (W7, 2026-06-18):** the web interfaces are **first-class, not an
> afterthought**. They are sequenced as **two separate slices**: the **concierge web UI lands
> after Phase 2** (it mostly wraps the existing agent), and the **control-plane web UI lands after
> Phase 3** (it builds on the mature harness). They are **not** bundled into one monolithic late
> phase. See [§14 Resolved decisions](#14-resolved-decisions).

---

## 10. Phased task breakdown (proposed Phase 7)

> **Sequencing (signed off, W7):** these tasks are **not** one monolithic late phase. The
> **concierge slice (7.0–7.3) lands after Phase 2**; the **control-plane web UI (7.4) lands after
> Phase 3**. Phase 7.5 (reproducibility/docs/verification) closes out each slice as it ships. The
> "Phase 7" label is retained only as a grouping; the web UIs are **first-class deliverables**.

### Phase 7.0 — Decisions & scaffolding seam (no app code) — ✅ implemented (static-verified)
**Tasks:** lock the open decisions (§11); choose web stack; reserve ports + env keys in
`.env.example`; decide host-vs-container default; pick the injection path + fallback.
**Exit criteria:** decisions recorded in this doc's Decisions table + the journal; `.env.example`
lists the new keys; no behaviour change yet.
**Status (2026-06-19):** ✅ done — decisions W1–W8 recorded; `.env.example` carries
`CONCIERGE_WEB_PORT=8090`, `CONTROL_PLANE_WEB_PORT=8099`, `WEB_ALLOWED_ORIGIN`, `CONCIERGE_API_URL`,
and the commented containerized `OTEL_EXPORTER_OTLP_ENDPOINT`; web deps added to `pyproject.toml`.

### Phase 7.1 — Concierge service (HTTP wrapper over `agent/`) — ✅ implemented (static/integration-verified)
**Tasks:** FastAPI app exposing `POST /chat` + `GET /chat/stream` (SSE); session manager mapping
chat → `session_id`; `setup_telemetry()` once at boot; per-session graph build via `overlay.py`;
set `gen_ai.conversation.id`; graceful flush on shutdown. **Spike first:** Galileo multi-session
concurrency (§5.2).
**Exit criteria:** a scripted multi-turn HTTP conversation produces clean **Sessions→Traces→Spans
in Galileo** AND **`gen_ai.*` spans + GenAI histograms in Splunk** (parity with the CLI baseline,
design Vignette 0); two concurrent sessions do **not** cross-contaminate traces; `MODEL_PROVIDER`
swap still needs no code change.
**Status (2026-06-19):** ✅ built — `web/concierge/app.py` (module-level `app`) + `service.py`
expose `POST /chat`, `GET /chat/stream` (SSE tokens), `/healthz`, optional localhost
`POST /admin/reload`; `setup_telemetry()` once at boot; per-session graph build via `overlay.py`;
sets `gen_ai.conversation.id`; `telemetry.py` reused verbatim. **Concurrency-spike finding +
resolution:** in **callback mode** a shared `GalileoLogger` + `start_session(...)` mutate
process-global state, so concurrent sessions could cross-contaminate Galileo traces — **resolved**
by serializing graph execution behind a global async lock **only** when `galileo_mode ==
"callback"` (the `GALILEO_OTEL_EXPORT=1` path stays fully concurrent). Boot verified
(`/healthz`=200). ⏳ **Pending Phase 7.5:** live multi-turn telemetry parity and concurrent-session
Galileo isolation in a running stage.

### Phase 7.2 — Concierge web widget + embedding — ✅ implemented (static-verified; live pending)
**Tasks:** build the tracked widget app; serve it from a new tracked compose-override container;
embed per the chosen path (proxy route/port; optional Envoy `<script>` injection with fallback);
wire CORS to the storefront origin.
**Exit criteria:** a shopper can chat from the storefront; the widget is delivered with **zero
edits to the vendored clone**; **clean-room rebuild** (delete clone + `down`, re-run setup/up)
reproduces the widget and telemetry.
**Status (2026-06-19):** ✅ built as a **standalone "Astronomy Concierge" React/Vite app**
(`web/concierge/frontend/**`, lockfile committed) served by a new tracked `concierge-web` container
appended to `stage/splunk-otel/docker-compose.override.yml` (existing collector config preserved);
containerized only (W2), Ollama stays native via `host.docker.internal:11434`. The optional Envoy
`<script>` injection into the storefront remains **out of scope** (later, optional enhancement, W1).
Frontend `dist` builds and the compose override merges with `concierge-web`. ⏳ **Pending Phase
7.5:** live in-browser chat against a running stage and the clean-room rebuild proof.

### Phase 7.3 — Trigger hot-reload semantics — ✅ implemented (static-verified; live pending)
**Tasks:** implement per-session overlay read (§6); invalidate `rag.py`'s `lru_cache` on
session/reload; add localhost-only `POST /admin/reload` (optional).
**Exit criteria:** `control_plane play <id>` (or web equivalent) then a **new** chat shows the
trigger's effect; `reset` then a new chat is baseline — verified for all three agent-side triggers;
`feature_flag` still hot-reloads via flagd; the control plane still only **writes** overlays (seam
intact).
**Status (2026-06-19):** ✅ built — per-session graph build via `overlay.py` plus an optional
localhost `POST /admin/reload`; `agent/rag.py` gained `clear_corpus_cache()` to invalidate the
`lru_cache` on per-session/reload (the one contained core touch the service implies). ⏳ **Pending
Phase 7.5:** live proof that an applied trigger takes effect on a fresh session and resets cleanly.

### Phase 7.4 — Control-plane web UI — ✅ implemented (static/integration-verified)
**Tasks:** FastAPI layer over `control_plane/` (REST for list/play/reset/playlist; SSE for live
play/verify output); lightweight frontend; **bind to `127.0.0.1`**; light CORS/CSRF/headers.
**Exit criteria:** the SE can run the full `list→play→verify→reset` loop and a playlist from the
browser with live streamed output; dropping a new stub scenario folder appears in the web UI
**without code edits** (seam proof, design §7.2); service refuses non-loopback binds.
**Status (2026-06-19):** ✅ built — `web/control_plane/app.py` (`create_app()` factory) +
`__main__.py` + templates/static; REST `list/play/reset/playlist` + `verify`, SSE
`GET /api/play/stream` and `GET /api/verify/stream` with a live log pane, thin over
`registry.discover()` / `apply_trigger` / `reset_trigger` / `run_verification` (`control_plane/`
internals unchanged — drop-in seam intact). Security: **loopback-only bind enforced**
(`_require_loopback_bind()` rejects `0.0.0.0`/non-loopback before Uvicorn starts), CSRF
(SameSite=Strict cookie + header token for POST + query token for acting SSE GETs), CSP + security
headers, secret redaction for `GALILEO_*`/`SPLUNK_*`/`OPENAI_*`; launcher
`scripts/control-plane-web.sh`. Verified: `/api/list`=200, loopback guard accepts loopback /
rejects `0.0.0.0`, registry discovers all 8 scenarios with no core edits.

### Phase 7.5 — Reproducibility, docs & verification — ⏳ PENDING (live clean-room sign-off)
**Tasks:** `scripts/` launchers (self-bootstrapping); `README.md` / `scripts/README.md` zero-to-
running updates; `CHANGELOG.md` entry (at implementation time); SE runbook web flows.
**Exit criteria:** clean-room: fresh clone + `.env` → documented scripts → stage + both web apps
up, widget visible, control-plane loop runnable, telemetry in **both** backends; CLIs still work as
fallbacks.
**Status (2026-06-19):** ⏳ **not yet done.** Partial scaffolding exists (`scripts/concierge-serve.sh`
and `scripts/control-plane-web.sh` launchers; `web/README.md`), but the live clean-room proof —
stage up + Ollama + `concierge-web` healthy in a browser, multi-turn chat, concurrent-session
Galileo isolation, trigger hot-reload via a fresh session, and telemetry parity (`gen_ai.*` spans +
GenAI histograms) in Splunk AI Agent Monitoring and Galileo — remains outstanding. The full README
Installation/Example-usage backfill is gated on this proof.

---

## 11. Decisions (signed off 2026-06-18)

| # | Decision | Chosen option | Status |
|---|---|---|---|
| W1 | Frontend injection approach | **Standalone co-located "Astronomy Concierge" chat web app is the primary FIRST deliverable** (own route/port, fully tracked by us). Optional Envoy `<script>`/proxy injection or store-linking into the Astronomy Shop is a **later, optional fidelity enhancement — not merely a fallback**. *(Deviation from the prior "widget-container baseline + injection opt-in + standalone fallback" framing.)* | ✅ signed off 2026-06-18 |
| W2 | Where the concierge service runs | **Containerized implementation ONLY** — the container is expected to also work on macOS / Apple Silicon (Ollama stays native at `host.docker.internal:11434`). Build one implementation, not two. **Escape hatch:** add a host-process profile only if the container has major drawbacks on macOS. *(Deviation from the prior "host-process default + optional container" recommendation.)* | ✅ signed off 2026-06-18 |
| W3 | Trigger hot-reload | **Per-session overlay read** + optional localhost `POST /admin/reload`; invalidate `rag` cache (as recommended) | ✅ signed off 2026-06-18 |
| W4 | Web stack | **FastAPI** backends + lightweight frontend + **SSE** for streaming (as recommended) | ✅ signed off 2026-06-18 |
| W5 | Keep the CLIs? | **Yes — keep both CLIs as supported thin clients/fallbacks over the same cores** | ✅ signed off 2026-06-18 |
| W6 | Shared vs separate web backends | **Separate processes** (control plane stays loopback-only), shared stack/repo OK (as recommended) | ✅ signed off 2026-06-18 |
| W7 | Sequencing | Web UIs are **first-class, not an afterthought**: **concierge web UI after Phase 2**; **control-plane web UI after Phase 3** (two separate slices, not one monolithic late phase) | ✅ signed off 2026-06-18 |
| W8 | Streaming transport | **SSE** for the live play/verify and chat token streams (websockets only if bidirectional control is later needed); covered by the W4 web-stack sign-off | ✅ signed off 2026-06-18 |

---

## 12. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| **Galileo multi-session concurrency** (process-global logger; Beta tracing, L2) | Cross-session trace bleed in Galileo | Phase-7.1 spike; per-session logger/callback or serialized sessions; verify before building UI |
| **Frontend injection brittleness** (gzip body-rewrite, CSP, upgrade drift) | Widget doesn't embed cleanly / breaks on demo bump | Recommend the low-coupling widget-container path; standalone-route fallback; clean-room verify on every demo bump |
| **Reproducibility regression** | A hand-edited clone or unscripted step breaks clean-room rebuild | All new pieces tracked outside the clone + materialized by scripts; clean-room proof is an Exit criterion |
| **Telemetry regression** | Lose `gen_ai.*` histograms / Galileo sessions we just fixed | Reuse `telemetry.py` verbatim; instrument once at boot; parity check vs CLI baseline as an Exit criterion |
| **`rag` cache staleness** on a long-lived service | `rag_corpus` triggers silently no-op | Invalidate `lru_cache` on session/reload (§6 note) |
| **Control-plane exposure** | Fault-triggering surface reachable off-host | Hard loopback bind; Exit criterion rejects non-loopback |
| **L1 nondeterminism / L2 ingestion lag** | Live demo wobble in chat + verify | Keep known-good prompt cards; verify retains poll/retry timeouts |

## 13. Effort signal (relative)

- **Heaviest:** Phase 7.1 (concierge service + the Galileo concurrency spike) and Phase 7.2
  (widget + reproducible embedding) — these carry the genuine unknowns.
- **Moderate:** Phase 7.4 (control-plane web UI) — mostly a thin shell over a mature package +
  SSE plumbing.
- **Light:** Phase 7.3 (hot-reload; the seam already exists) and Phase 7.5 (scripts/docs, by
  analogy to existing self-bootstrapping scripts).
- The two workstreams parallelize cleanly (different audiences, different cores).

---

## 14. Resolved decisions

The user signed these off on **2026-06-18**. They map to the Decisions table in [§11](#11-decisions-signed-off-2026-06-18):

1. **Frontend injection (W1) — RESOLVED.** The **standalone co-located "Astronomy Concierge" chat
   web app is the primary FIRST deliverable** (own route/port, fully tracked by us). Optional Envoy
   `<script>`/proxy injection or store-linking into the Astronomy Shop is a **later, optional
   fidelity enhancement — not merely a fallback**. *(Deviation from the prior framing, which had the
   widget-container as baseline with injection opt-in and the standalone route only as a fallback.)*
2. **Where the agent runs (W2) — RESOLVED.** Build **only the containerized implementation**; it is
   expected to also work on macOS / Apple Silicon (Ollama stays native on the host). Do not do the
   double work of also shipping a host-process default. **Escape hatch:** add a host-process profile
   only if the container proves to have major drawbacks on macOS. *(Deviation from the prior
   "host-process default + optional container" recommendation.)*
3. **Trigger hot-reload (W3) — RESOLVED as recommended.** Per-session overlay read, plus an
   optional localhost-only `POST /admin/reload`; invalidate `rag.py`'s `lru_cache` on reload.
4. **Framework picks (W4) — RESOLVED as recommended.** FastAPI backends + a lightweight frontend +
   SSE for streaming.
5. **Keep the CLIs (W5) — RESOLVED.** Yes — keep **both** CLIs as supported thin clients/fallbacks
   over the same cores.
6. **Backend topology (W6) — RESOLVED as recommended.** Separate control-plane and concierge
   processes (control plane stays loopback-only); sharing the stack/repo is fine.
7. **Sequencing (W7) — RESOLVED.** The web interfaces are **first-class, not an afterthought**:
   the **concierge web UI lands after Phase 2** and the **control-plane web UI lands after
   Phase 3** — two separate slices, not one monolithic late phase.
8. **Streaming transport — RESOLVED as recommended.** SSE for the live play/verify and chat token
   streams (websockets only if bidirectional control is later needed). *(Covered by the W4 web-stack
   sign-off; no separate user decision was requested.)*
