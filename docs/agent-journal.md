# Agent Journal

A running record of meaningful actions taken by agents in this project: what was done, why, and what decisions or trade-offs were made.

**Format for new entries:**

```
## YYYY-MM-DD — <Short title>

**What:** <1-2 sentences describing what was done>

**Why:** <rationale — why this approach over alternatives>

**Decisions / trade-offs:**
- <decision 1>
- <decision 2>

**Effect on codebase / UX:** <what changed and for whom>
```

Entries are append-only. Never delete or rewrite past entries.

---

## 2026-06-18 — Web-interface decisions W1–W7 signed off

**What:** Reconciled [`docs/web-interface-plan.md`](web-interface-plan.md) to record the user's
sign-off of the open web-interface decisions (dated 2026-06-18). Updated the §11 Decisions table
(every row now ✅ signed off with the chosen option, heading renamed from "proposed — pending
sign-off" to "signed off 2026-06-18"), converted the former §14 "Open decisions for the user"
question list into "§14 Resolved decisions", and aligned the header/status, §4, §5.1, §9, and the
§10 phase breakdown so the document is internally consistent. **No application code or config
changed** — this is decision-capture only.

**Why:** A prior pass had already flipped the document header to "signed off" but left the §11
table and §14 still phrased as open questions with only the original recommendations, leaving the
doc internally contradictory. The user supplied explicit choices for W1–W7, so the table, the
resolved-decisions section, and the header needed to agree.

**Decisions / trade-offs (now signed off):**
- **W1 (deviation):** the **standalone co-located "Astronomy Concierge" chat web app is the primary
  FIRST deliverable** (own route/port, fully tracked). Optional Envoy/proxy injection or
  store-linking into the Astronomy Shop is a **later, optional fidelity enhancement — not merely a
  fallback** (the prior framing had the widget-container as baseline and the standalone route only
  as a fallback).
- **W2 (deviation):** build **only the containerized concierge implementation**; it is expected to
  also work on macOS/Apple Silicon (Ollama stays native via `host.docker.internal`). Avoids the
  double work of also shipping a host-process default. **Escape hatch:** add a host-process profile
  only if the container has major drawbacks on macOS (deviates from the prior "host-process default
  + optional container" recommendation).
- **W3/W4/W6 (as recommended):** per-session overlay read (+ optional localhost `POST /admin/reload`,
  invalidate `rag` cache); FastAPI backends + lightweight frontend + SSE; separate processes
  (control plane loopback-only), shared stack/repo OK.
- **W5:** keep **both** CLIs as supported thin clients/fallbacks over the same cores.
- **W7 (sequencing):** web UIs are **first-class, not an afterthought** — **concierge web UI after
  Phase 2**, **control-plane web UI after Phase 3** (two separate slices, not one monolithic late
  phase). There is no W8 row in the table, so the header was made consistent as "W1–W7".

**Effect on codebase / UX:** Only `docs/web-interface-plan.md` and this journal were edited. No
CHANGELOG entry (planning/decision recording, pre-implementation; per the changelog rule, plan
decisions live in the journal). `docs/implementation-plan.md` was intentionally left unedited (the
web-interface sequencing lives in the plan doc only, per the user's prior instruction).

---

## 2026-06-16 — Plan produced: web interfaces for the control plane + storefront concierge

**What:** Investigated the current CLIs and stage, then wrote a new planning doc
[`docs/web-interface-plan.md`](web-interface-plan.md) proposing how to replace the two CLIs with
web experiences: a localhost SE **control-plane web UI** over the existing `control_plane/`
package, and the **concierge embedded as a chat experience** in the Astronomy Shop storefront via
a FastAPI service wrapping the LangGraph agent. **No code or config was changed** — this is a
decision-capture and a proposed amendment (candidate Phase 7) to `docs/implementation-plan.md`.

**Why:** The user wants the implications + a plan before any implementation. The three genuinely
contentious calls (reproducible frontend injection, agent-as-a-service, trigger hot-reload) each
needed options/tradeoffs/recommendations and explicit user sign-off before building.

**Decisions / trade-offs (recommended, pending sign-off):**
- **Frontend injection:** self-hosted, fully-tracked **chat widget container** declared in our
  existing compose-override seam (zero edits to the gitignored pinned clone, no frontend image
  rebuild), embedded via a proxy route/port with an optional Envoy `<script>` injection for
  in-page fidelity and a standalone-route fallback. Rejected patching `src/frontend` (forces image
  rebuild + patch-rot) and forking (worst upgrade story) — reproducibility/upgrade-safety over
  literal in-React fidelity.
- **Agent-as-a-service:** FastAPI over the unchanged `agent/` core, **host-process default**
  (preserves macOS-native Ollama + today's `localhost:4317`/`:8080` wiring) with an **optional
  containerized profile** for EC2/OpenAI (Ollama stays native; container reaches it via
  `host.docker.internal`, collector via the in-network service name). Telemetry preserved by
  reusing `telemetry.py` verbatim and instrumenting once at boot; web chat sessions map to Galileo
  sessions + `gen_ai.conversation.id` (a net improvement for Splunk AI trace data). Flagged the
  **Galileo multi-session concurrency** risk (process-global logger; Beta tracing, L2) as a
  Phase-7 spike.
- **Trigger hot-reload:** **per-session overlay read** through the existing `overlay.py` seam
  (control plane keeps only *writing* files), optional localhost `POST /admin/reload`; noted the
  required `agent/rag.py` `lru_cache` invalidation so `rag_corpus` overlays apply on a running
  service.
- **Cross-cutting:** control-plane UI must stay **loopback-bound** (it triggers faults); light
  CORS/CSRF/headers only (local demo); all new pieces tracked outside the clone, scripted, pinned,
  and clean-room verifiable.

**Effect on codebase / UX:** Added `docs/web-interface-plan.md` (goals, current-state recap,
target architecture diagram, the three contentious decisions with recommendations, telemetry/
reproducibility/security implications, a phased Phase-7 breakdown with verifiable exit criteria,
risks, effort, and an "Open decisions for the user" list) and this journal entry. No CHANGELOG
entry — there is no user-facing change yet. No application code or config touched.

---

## 2026-06-16 — FINAL: `send_otlp_histograms: true` is correct (the metric-name finder can't see native histograms)

**What:** Reverted the `send_otlp_histograms: false` experiment back to **`true`** — the Splunk-documented, required value. The "zero `gen_ai.*` in the o11y metric catalog" signal that drove the whole detour was a **FALSE NEGATIVE**: Splunk o11y's metric-NAME finder does not surface native OTLP **histogram** metrics (a distinct metric type), so absence there is NOT evidence the data is missing. Splunk "Set up AI Agent Monitoring" states verbatim: *"Histogram metrics are required to display data on AI Agent Monitoring pages. To send histogram data to Splunk Observability Cloud with the SignalFx exporter, set `send_otlp_histograms: true`."* Also made **delta temporality explicit in code** (`OTLPMetricExporter(preferred_temporality={Histogram: DELTA, Counter: DELTA, ...})`) rather than relying solely on the env var, and proved it (`Histogram temporality = DELTA`) independently of the ConsoleMetricExporter (which always prints cumulative).

**Why:** The correct authority is the Splunk doc + the AI Agent Monitoring UI, not the metric-name finder. Native histograms are exactly what AI Agent Monitoring consumes; translating them away (`false`) would have removed the very representation the product needs. The earlier clean-egress runs with `true` were very likely correct all along.

**Decisions / trade-offs:**
- `send_otlp_histograms: true`; metrics via `signalfx` ONLY (no double-send); traces unchanged; `realm:` form kept (both ingest hosts equivalent).
- Delta set explicitly per instrument kind for determinism (env var retained as belt-and-suspenders).
- VERIFICATION RULE going forward: confirm histogram-backed AI data via **`APM > AI agents` / `AI trace data`** in the UI. The MCP metric-name finder cannot see histograms — do not use it as the success criterion.

**Effect on codebase / UX:** `stage/splunk-otel/otelcol-config-extras.yml` (`send_otlp_histograms: true` + corrected comments), `agent/telemetry.py` (explicit delta `preferred_temporality`). Live re-run: histograms non-zero + delta, clean `signalfx`/trace egress, collector healthy, Galileo logs, `gen_ai.*` spans intact. Operator to confirm in the AI Agent Monitoring UI.

---

## 2026-06-16 — [SUPERSEDED by the FINAL entry above] Switch to SignalFx-TRANSLATED histograms (candidate)

> **SUPERSEDED / REVERTED:** This experiment (`send_otlp_histograms: false`) was wrong. It was driven by the false-negative metric-finder signal and contradicts the Splunk doc, which REQUIRES `send_otlp_histograms: true` for AI Agent Monitoring. Reverted to `true`. Kept below for audit only.

**What:** The parent's o11y MCP check confirmed that even after the `signalfx`-only + `realm:` change, and >20 min / multiple runs later, the metric catalog still has **ZERO** `gen_ai.*` MTS (substring search for `gen_ai`, `gen_ai.client`, `token.usage`, `operation.duration` all empty). So neither the host nor the dual-path were the cause, and exporter `sent>0/failed=0` was again not sufficient evidence. New, better-supported hypothesis: the `signalfx` exporter's **native OTLP histogram** emission (`send_otlp_histograms: true`) is accepted-then-dropped server-side for this tenant — native OTLP histograms don't register as queryable MTS here. Candidate change now live: **`send_otlp_histograms: false`**, so the exporter emits the classic SignalFx-**translated** histogram representation (`<name>_count` / `_sum` / `_min` / `_max` / `_bucket`), which reliably registers as standard MTS.

**Why:** The translated counter/gauge representation is the long-standing, robust SignalFx path and is discoverable in the metric finder; native OTLP histogram ingestion is newer and may be disabled/unsupported on this tenant. Verified agent-side (console dump) that the histograms carry **non-zero** counts (e.g. `gen_ai.client.token.usage` sum≈2382 input tokens / 78 output; `gen_ai.client.operation.duration` sum≈19.6s) and that the OTLP→collector path is delta (`OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=delta`; the console reader's `temporality:2`/cumulative is just the ConsoleMetricExporter's own default and does not reflect the OTLP exporter).

**Decisions / trade-offs:**
- Kept metrics on `signalfx` ONLY (user directive); traces unchanged; only flipped `send_otlp_histograms` to `false`.
- This is a CANDIDATE pending the parent's catalog check — not yet declared the final cause. Expected MTS names after this run: `gen_ai.client.token.usage_count` / `_sum` / `_bucket` (and possibly `_min` / `_max`) and `gen_ai.client.operation.duration_count` / `_sum` / `_bucket`.
- Open caveat: Splunk **AI Agent Monitoring** dashboards may specifically expect the native histogram metric; if so, surfacing the translated MTS solves catalog discoverability but native-histogram ingestion may still need a Splunk-side enablement. To be reconciled after the catalog check.

**Effect on codebase / UX:** Only `stage/splunk-otel/otelcol-config-extras.yml` (`send_otlp_histograms: false` + comment). Collector restarted clean; agent run drove non-zero `gen_ai.client.*` histograms into the pipeline; no signalfx/trace egress errors; Galileo callback still logs; `gen_ai.*` spans unchanged. **Awaiting parent MCP confirmation that the translated MTS now appear.**

---

## 2026-06-16 — CORRECTION to the "signalfx wrong ingest host" root cause (below)

**What:** The immediately-following entry ("GenAI histogram metrics silently dropped at collector egress (signalfx wrong ingest host)") states an **incorrect** root cause. It is preserved (append-only) but is **superseded** by this note. The host was NOT the problem.

**Evidence the host theory is wrong:**
- An unauthenticated `POST` to both `/v2/datapoint` and `/v2/datapoint/otlp` returns **`401` on BOTH** `ingest.eu0.signalfx.com` and `ingest.eu0.observability.splunkcloud.com` — i.e. both routes exist and require the token. `*.signalfx.com` and `*.observability.splunkcloud.com` are **equivalent valid Splunk Observability ingests for the same realm/tenant**, differing only in routing infrastructure (the DNS difference I cited — istio ingress vs. direct — does **not** mean a different service). My "Splunk Cloud Platform / silent 404 drop" claim was a misread of DNS.
- My own run-1 counters were captured under the **original** config (`observability.splunkcloud.com` host + both exporters): the gen_ai histograms reached the metrics pipeline and **both** exporters reported `sent>0, send_failed=0` to that host. So the data was already leaving the collector cleanly to a valid ingest under the original config — this was never a collector-egress failure, and the endpoint change was effectively a **no-op**.

**Best-supported root cause now:** The only substantive, evidence-backed change is collapsing the metrics pipeline to a **single** exporter (`signalfx` with `send_otlp_histograms: true`) and dropping `otlphttp/splunk` from it (operator's directive). The original dual-path sent the SAME delta histogram twice to the same realm `/v2/datapoint/otlp` — once SignalFx-translated (`signalfx`) and once raw OTLP (`otlphttp/splunk`) — a duplicate/conflicting-MTS hazard. **However**, whether the parent's earlier catalog absence was caused by that duplication or simply by **first-MTS ingestion/catalog lag** cannot be determined from collector telemetry alone (both configs egress cleanly with zero errors). The decisive test is an operator-side A/B via the Splunk o11y MCP: revert to dual-path → confirm absent → re-apply single-path → confirm present. If metrics appear now, that alone does not prove the single-path change caused it (could be lag).

**Decisions / trade-offs:**
- Kept the operator directive (metrics via `signalfx` ONLY) and kept the `realm:`-derived endpoint (canonical, least-error-prone) — but explicitly **not** as a "host fix"; either endpoint form is acceptable. Did not churn the endpoint further.
- Corrected `CHANGELOG.md` [Unreleased] Fixed entry, `agent/README.md`, and `stage/README.md` in place to state the accurate cause and that both endpoint forms are equivalent. Left the erroneous journal entry below intact and appended this correction instead of rewriting it.

**Effect on codebase / UX:** No code/config behavior change vs. my prior fix (metrics still `signalfx`-only, `realm:`). Only docs were corrected. Spans + Galileo verified unaffected. Final root-cause determination (dual-path vs. lag) is deferred to the parent's MCP catalog check.

---

## 2026-06-16 — Fix: GenAI histogram metrics silently dropped at collector egress (signalfx wrong ingest host)

> **SUPERSEDED — see the correction entry above (2026-06-16).** The "wrong ingest host / different service / silent drop" root cause stated here is INCORRECT: both `*.signalfx.com` and `*.observability.splunkcloud.com` are equivalent valid Observability ingests, and the original host was already egressing cleanly. The real, evidence-backed change was making the metrics pipeline use a single exporter (`signalfx`). Entry retained verbatim below for the append-only audit trail.

**What:** The prior change got `gen_ai.*` **spans** into Splunk, but the two GenAI **histograms** (`gen_ai.client.token.usage`, `gen_ai.client.operation.duration`) never appeared in Splunk's metric catalog. Instrumented every hop to get proof: (1) **agent** — added an off-by-default `GENAI_METRICS_CONSOLE_DEBUG` console metric dump and saw both histograms produced and force-flushed on shutdown; (2) **collector ingress** — a detailed `debug` exporter on the metrics pipeline printed both histogram metric points arriving (proving the deep-merge keeps the upstream `otlp` receiver, since our override omits `receivers`); (3) **collector egress** — the collector's internal counters (`otelcol_exporter_sent/send_failed_metric_points`, via a temporary Prometheus pull endpoint) showed `signalfx sent>0, send_failed=0` — **no error** — yet nothing landed. Root cause: the `signalfx` exporter's `api_url`/`ingest_url` were `*.eu0.observability.splunkcloud.com`, which DNS-resolves to a Splunk **Cloud Platform** istio ingress (not Splunk **Observability**); it returned HTTP 2xx and silently discarded the datapoints, while traces on `ingest.eu0.signalfx.com` worked. Fixed by switching `signalfx` to `realm: ${SPLUNK_REALM}` (derives the validated `ingest.eu0.signalfx.com` / `api.eu0.signalfx.com`). Per the operator's directive, the metrics pipeline now uses `signalfx` ONLY (removed `otlphttp/splunk` from metrics to avoid double-counting; traces unchanged).

**Why:** "Export returned no error" was actively misleading here — the wrong-but-real host ACKed the POSTs. The decisive evidence was DNS (splunkcloud.com = Cloud Platform ingress, a different service) plus the fact that the working traces and the Phase-0 connectivity check both use `ingest.eu0.signalfx.com`. Using `realm:` (the canonical signalfx exporter config) keeps metrics on that same validated ingest. Using a single metrics exporter (`signalfx`, with `send_otlp_histograms: true`) is both what AI Agent Monitoring needs and what avoids duplicate datapoints from two parallel paths.

**Decisions / trade-offs:**
- **`realm:` over explicit `api_url`/`ingest_url`** — least-error-prone; the exporter derives the correct realm hosts and there is one fewer place to mistype a domain.
- **Metrics via `signalfx` only** — followed the operator directive; `otlphttp/splunk` is now traces-only (kept its `traces_endpoint`, dropped the unused `metrics_endpoint`).
- **Proof tooling was temporary** — the detailed `debug/genai` exporter and the Prometheus pull telemetry reader were applied only to the gitignored clone during investigation and removed afterward (tracked source stayed clean). The durable, off-by-default diagnostic is the agent-side `GENAI_METRICS_CONSOLE_DEBUG` toggle.
- **Did not touch the agent's export path, Galileo, or span behavior** — the bug was 100% collector config; the agent already produced and flushed the histograms correctly.

**Effect on codebase / UX:** Changed `stage/splunk-otel/otelcol-config-extras.yml` (signalfx `realm:`; metrics exporters `[signalfx]`; otlphttp/splunk traces-only), `agent/telemetry.py` (off-by-default console metric debug toggle), `.env.example`/`.env` (document the toggle), and docs (`agent/README.md`, `stage/README.md`). Verified live on Ollama `llama3.1:8b`: histograms reach the collector and egress via `signalfx` to `ingest.eu0.signalfx.com` with `send_failed=0` and zero trace/exporter errors; Galileo still logs; `gen_ai.*` spans still export. **The parent confirms the metric names `gen_ai.client.token.usage` + `gen_ai.client.operation.duration` in the Splunk metric catalog + AI Agent Monitoring (realm `eu0`) via the o11y MCP** — the repo cannot, by design.

---

## 2026-06-16 — Fix: light up Splunk AI Agent Monitoring (gen_ai.* spans + GenAI metrics)

**What:** The concierge's traces appeared in plain Splunk APM but the **AI Agent Monitoring** pages (`APM > AI agents` / `AI trace data`) stayed empty. Root cause (diagnosed by the parent, confirmed here): the agent used the **OpenInference** `LangChainInstrumentor`, whose spans carry only `llm.*` attributes (zero `gen_ai.*`), and it exported **no metrics**. Splunk AI Agent Monitoring requires the OTel **GenAI semantic conventions** (`gen_ai.*`) plus **GenAI histogram metrics**. Replaced the active OTel/Splunk instrumentor with the OpenLLMetry / **Traceloop** `opentelemetry-instrumentation-langchain` (`LangchainInstrumentor`) and added a delta-temporality `MeterProvider` + OTLP metric exporter to the same local Splunk collector. Set the Splunk-documented GenAI env defaults. Galileo's `GalileoCallback` path was left untouched.

**Why:** Two PyPI-installable LangChain instrumentors emit `gen_ai.*`: the official OTel-contrib one and Traceloop's. The official one only instruments `ChatOpenAI`/`ChatBedrock` and **silently skips** other providers — including our default `ChatOllama` — so it would leave the laptop runtime uninstrumented. Traceloop hooks the LangChain callback-manager layer, so it populates `gen_ai.*` (and the GenAI client histograms) for **every** chat model, and Splunk's setup doc explicitly lists third-party (Traceloop-style) instrumentation as a supported translation source. An empirical probe against `ChatOllama` + `create_react_agent` confirmed Traceloop emits the conventions + both histograms; the official path does not for Ollama.

**Decisions / trade-offs:**
- Instrument at the framework/callback layer via Traceloop rather than the LLM-client layer — it covers Ollama and OpenAI uniformly with no per-provider code.
- Keep `openinference-instrumentation-langchain` installed only for `using_session` (Galileo session context); it is no longer the active OTel instrumentor (no double-instrumentation, since OpenInference only instruments when `.instrument()` is called, which we no longer do).
- Collector override needed no functional change: the `signalfx` exporter already had `send_otlp_histograms: true` (top-level per the exporter schema; Splunk's doc renders it beside an empty `correlation:` block) and the metrics pipeline already inherits the upstream `otlp` receiver via the list-replace merge. Added clarifying comments only.
- Set the three Splunk GenAI env knobs as process defaults (real `.env` wins) so intent is explicit and the config also fits the Splunk SDOT GenAI-utility path if one switches to it; only the metrics temporality (`delta`) is functionally consumed by the Traceloop/OTLP path today.

**Effect on codebase / UX:** Changed `agent/telemetry.py` (instrumentor swap + meter provider + env defaults + status), `agent/main.py` (status print), `pyproject.toml` (new pinned deps), `.env.example`/`.env` (three GenAI vars), `stage/splunk-otel/otelcol-config-extras.yml` (comments), and docs (`agent/README.md`, `README.md`). Verified live on Ollama `llama3.1:8b`: 27 distinct `gen_ai.*` span keys + the histograms `gen_ai.client.token.usage` and `gen_ai.client.operation.duration` were produced and exported to the collector with zero OTLP errors; the collector accepted them with no new errors; Galileo still logged the session→trace. Remaining work is operator-side in the Splunk console: enable the **LLM Providers** integration (Data Management → Available integrations) for platform-side evaluations and grant the `read_apm_ai_conversation` capability. Confined changes to `agent/`, `stage/splunk-otel/`, `pyproject.toml`, `.env*`, and docs (stayed out of `control-plane/` and `scenarios/`).

---

## 2026-06-16 — Phase 3: scenario harness + SE control plane

**What:** Built the extensibility core in a new `control_plane/` package: a registry that auto-discovers `scenarios/*/scenario.yaml`, a strict manifest loader/validator matching design §7.1 exactly, the four FIXED trigger handlers (`feature_flag | rag_corpus | tool_fault | prompt_overlay`) with `apply()`/`reset()`, a pluggable per-backend `expected_signals` verification hook (Galileo real with poll/retry; Splunk unverified-by-design), and a `list/play/reset/verify/playlist` CLI (`scripts/control-plane.sh`). Added a stable agent overlay seam (`agent/overlay.py` + tiny hooks in `rag.py`/`graph.py`/`tools.py`) and four clearly-marked stub scenarios. Proved drop-in discovery, per-trigger apply/reset against the live stage/agent, a full driven play, and the verify hook against real Galileo.

**Why:** Design §7 mandates that vignettes are drop-in folders that never require core edits. Putting all machinery behind stable seams (the package + the `agent/_overlay/` overlay) means the agent, telemetry fan-out, and CLI are untouched when scenarios are added. The trigger set is kept closed (validator rejects unknown types) to protect that guarantee.

**Decisions / trade-offs:**
- **Agent-side triggers use a gitignored overlay dir (`agent/_overlay/`) the agent reads on startup**, rather than env-var coordination across processes — non-destructive (baseline corpus/prompt/tools untouched) and reset = drop the overlay. Chosen over mutating `agent/knowledge` or the system prompt in place.
- **`feature_flag` edits the vendored demo's `demo.flagd.json`** (flagd hot-reloads on file write) instead of an OFREP/UI API call — file-based is offline-capable, deterministic, and saves the original variant for reset. Note the design's `productCatalogStaleData` flag isn't in the vendored demo's flag set (it ships `productCatalogFailure`, `recommendationCacheFailure`, etc.); the stub uses `recommendationCacheFailure`, and Phase 4 will pick the right flag for the Invisible-Failure vignette.
- **`tool_fault` faults the agent's own tools** (overlay) rather than depending on stage failure flags, so it proves apply/reset deterministically without the stage; demo backend-failure flags remain reachable via `feature_flag` when a Splunk-layer fault is wanted.
- **Galileo verifier is real but honest:** it connects and queries live traces, but maps only signals with a queryable metric; the rest (and all of Splunk) are reported `unverifiable` with a clear reason — never faked. Phase-3 `overall_pass` = "nothing failed/errored", so unverifiable signals (pending Phase-4 scorer config) don't block.
- **Splunk is unverified-by-design:** the ingest-only token can't query the APM/management API (401); encoded a clear message and left live Splunk confirmation to the SE via the o11y MCP.
- Kept the Python package name `control_plane` (underscore) distinct from the docs dir `control-plane/` (hyphen, not importable); docs point at the package.

**Effect on codebase / UX:** SEs run everything from `scripts/control-plane.sh` (`list/play/reset/verify/playlist`). Adding a vignette is now a pure drop-in folder. Verified live: all 5 scenarios discovered with no core edits, a malformed manifest reported without breaking the list, all four triggers apply+reset against the running stage/agent (incl. a full driven concierge run that hit a faulted tool and recovered), and the verify hook produced a pass/fail report querying real Galileo traces. Reference vignette authoring (incl. `invisible-failure` reset.sh/captions/live signals) remains Phase 4. **Parent should confirm the Splunk side via the Splunk Observability o11y MCP** (the repo cannot, by design).

---

## 2026-06-16 — Phase 2: concierge MVP + dual telemetry fan-out

**What:** Built the AI shopping concierge in `agent/` — a LangGraph ReAct agent that answers via RAG over a curated corpus (`agent/knowledge/`) and acts by calling the Astronomy Shop's frontend-proxy APIs as tools — and instrumented it once with OpenInference, fanning telemetry to both Galileo (`GalileoCallback`) and Splunk (OTLP/gRPC → local collector). Verified a real tool-calling conversation lands in both backends.

**Why:** Implements design §3 (instrument once → two backends) and §4 (the two failure-surface capabilities). Reused the existing `get_chat_model()` provider abstraction so `MODEL_PROVIDER` swaps Ollama↔OpenAI with no code change. Chose the frontend-proxy HTTP surface (not gRPC microservices) because the agent runs on the host, matching how a browser talks to the store.

**Decisions / trade-offs:**
- **Galileo via callback, not OTLP, by default.** The pure-OTLP `GalileoSpanProcessor` path derived endpoint `https://api.multitenant.galileocloud.io/splunkse/otel/traces`, which returned 404 on this enterprise/multitenant tenant. Rather than guess endpoints (and to avoid sending credential-bearing raw probes), I used Galileo's first-class `GalileoCallback` — the documented LangGraph integration that yields Sessions→Traces→Spans + agent metrics. The OTLP path is preserved behind `GALILEO_OTEL_EXPORT=1` for tenants where it works. Splunk remains pure single-instrument OTLP via OpenInference. Net: one agent run, observed by two collectors; rich data in both.
- **RAG is a dependency-free TF-IDF retriever over markdown**, surfaced as a tool — keeps the agent offline-capable and deterministic for the MVP; can be swapped for embeddings later without changing the tool surface.
- **Published stable collector ports (4317/4318).** The upstream compose only mapped the collector's OTLP ports to random host ports, so the host-run agent couldn't use the documented `localhost:4317`. Added fixed port publishing to our tracked `docker-compose.override.yml` (reproducible) and recreated the collector — a minimal, justified stage change to support Phase 2.
- **`MODEL_TEMPERATURE=0` default.** `llama3.1:8b` is inconsistent at multi-step tool calling (occasionally prints a tool call as text); temperature 0 materially improved reliability. Documented as a known local-model limitation.

**Effect on codebase / UX:** Added `agent/{graph,tools,rag,store_client,telemetry,main,__main__}.py` + `agent/knowledge/*.md`; extended `agent/config.py`; pinned tested deps in `pyproject.toml`; new env vars in `.env.example`/`.env`; added `scripts/agent-run.sh`; updated `README.md`, `agent/README.md`, and the stage override. Verified: cart actually populated by a tool call, Galileo session+trace logged, Splunk OTLP export with zero errors, service `astronomy-concierge` in environment `local-agent-galileo`.

---

## 2026-06-16 — Project governance bootstrap

**What:** Initialized the project with a full governance layer: five `alwaysApply` Cursor rules, `AGENTS.md`, `README.md` skeleton, `CHANGELOG.md`, this journal, `.gitignore`, and a git repository with an initial commit.

**Why:** Starting with explicit, machine-enforced conventions prevents drift across agent sessions. Encoding rules in `.cursor/rules/` makes them automatically active without requiring agents to be reminded each session. Scaffolding the artifacts (README, changelog, journal) upfront ensures they exist and have a defined structure before any real code is written.

**Decisions / trade-offs:**
- Chose `alwaysApply: true` for all five rules so they fire regardless of which files are open. A file-glob approach would be less intrusive but risks the rules being silently skipped.
- Split hygiene concerns into five separate rule files (one concern per file) rather than one monolithic rule, keeping each under ~50 lines and easy to update independently.
- Kept `automate-verify.mdc` as a principle only (no scripts or CI yet) since the project's language and toolchain are not yet defined. The rule explicitly asks agents to grow automation incrementally.
- Added an agent journal (this file) in addition to the changelog. The changelog is user-facing and captures intent/impact; the journal is agent/developer-facing and captures decisions and trade-offs.

**Effect on codebase / UX:** No production code yet. All files are governance scaffolding. Future agents will automatically maintain the README, changelog, and this journal.

---

## 2026-06-16 — Demo-environment design defined

**What:** Authored `docs/demo-design.md`, the agreed pre-implementation design for the Galileo × Splunk demo: a Python AI shopping concierge added to a forked OpenTelemetry "Astronomy Shop", instrumented once with OTel GenAI and fanned out to both Galileo (OTLP) and Splunk (Splunk OTel Collector, OTLP). Also filled the `README.md` Goal section and recorded the work in `CHANGELOG.md`. Documentation only — no application code.

**Why:** The design has meaningful trade-offs (provider/backend roles, build constraints, extensibility model) that needed to be captured precisely before any implementation, so stakeholders and future agents share one source of truth and the build avoids architectural drift.

**Decisions / trade-offs:**
- **Roles fixed**: Galileo = AI/agent intelligence (hero); Splunk = systems/infrastructure backdrop. Clean, non-overlapping framing that also previews the integrated Cisco story.
- **Single instrumentation, dual fan-out** via OpenTelemetry GenAI conventions, **OTLP only** (not the deprecated `sapm` exporter); **Python** agent because GenAI instrumentation maturity elsewhere is unverified. Flagged Galileo distributed tracing as Beta.
- **Extensibility-first**: vignettes are pluggable folders (declarative `scenario.yaml`, auto-discovered registry, fixed trigger set `feature_flag | rag_corpus | tool_fault | prompt_overlay`, declarative `expected_signals` tied to the `automate-verify` rule). Core seams (agent, fan-out, control plane) stay stable.
- **First deliverable** scoped to the scenario harness + one reference vignette end-to-end, rather than all vignettes at once.
- **Pluggable model provider** for two runtimes (Apple-silicon/Ollama, EC2/OpenAI); explicitly called out that observability is still cloud SaaS (internet required), so the demo is not truly air-gapped.
- Verified runtime facts via light web search: OTel demo needs ~6 GB RAM full / ~3 GB minimal and ~14 GB disk; Ollama runs natively on Apple Silicon (don't containerize it on macOS). EC2 instance size left as "to validate".
- **Secrets**: Splunk token, Galileo key, OpenAI key all via env/`.env` (gitignored); no hardcoded credentials.
- Left the **space/astronomy theme acceptability** as an open question for stakeholders.

**Effect on codebase / UX:** Added `docs/demo-design.md` and populated the README Goal; no production code. Provides a skimmable, agreed starting point for the implementation plan and a defined first build target.

---

## 2026-06-16 — Phased implementation plan authored

**What:** Authored `docs/implementation-plan.md`, a phased (Phase 0–6), dependency-ordered build plan for the Galileo × Splunk demo, derived entirely from `docs/demo-design.md`. Each phase carries goal/tasks/deliverables/exit-criteria/dependencies/risks; added decisions-needed, sequencing/effort, git-hygiene, and a "demo-ready" milestone. Updated `CHANGELOG.md`. Documentation/planning only — no application code, scaffolding, or installs.

**Why:** The design captured *what/why* but not *how/in what order*. A plan with verifiable per-phase exit criteria (tied to the `automate-verify` rule) gives the build an acceptance-gated sequence, exposes the critical path vs. parallelizable work, and consolidates the gating decisions so Phase 0 can start with eyes open.

**Decisions / trade-offs:**
- **Phase ordering** mirrors design §7.5 / §10: the scenario harness + one reference vignette (Phase 4) is the first true end-to-end deliverable; remaining vignettes are incremental drop-ins.
- **Recommended LangGraph** as the agent framework (Galileo `sdk-examples` + `langgraph-open-telemetry` precedent, Graph Engine cascade fit) but explicitly marked it a decision to confirm (D1) rather than locking it in a planning doc.
- **Exit criteria written as automatable checks** (smoke scripts, `expected_signals` auto-verification) to honour `automate-verify`, while acknowledging L2 ingestion latency forces poll/retry rather than instant assertion.
- **Carried all design limitations/gates forward by ID** (L1 nondeterminism → induced faults + known-good prompt cards; L2 latency/Beta → pre-warmed dashboards; Galileo Pro gate for Vignette 3; 5k-trace cap; theme open question).
- **Surfaced six decisions (D1–D6)** with the phase each blocks; only D2 (theme) and D6 (provider shape) are non-architectural, and none hard-block Phase 0.

**Effect on codebase / UX:** Added `docs/implementation-plan.md`; updated `CHANGELOG.md`. No production code. Gives stakeholders/agents an actionable roadmap with explicit acceptance gates and a first "demo-ready" definition (Core 3 vignettes runnable + auto-verified from the control plane in both runtimes).

---

## 2026-06-16 — Enterprise Galileo access secured; design decisions resolved

**What:** Updated `docs/demo-design.md` and `docs/implementation-plan.md` to reflect a major constraint change (enterprise Galileo access) and to record now-resolved decisions, keeping the two docs mutually consistent. Updated `CHANGELOG.md`. Documentation only — no application code.

**Why:** Enterprise access removes the prior tier/feature gates (5k-trace cap, Galileo Pro for real-time guardrails, enterprise-only Luna-2 / Agent Control / self-hosting), which had been shaping the design as risks. With the constraint lifted, the gating decisions could be settled and the eval-accuracy pillar — previously a "known weak spot" with no clean live trigger — becomes a live, demoable vignette via Luna-2.

**Decisions / trade-offs:**
- **Constraint change:** Luna-2, real-time guardrails, Agent Control, and unlimited traces are now treated as available capabilities. Reframed design §9.2 from gates to capabilities; kept the "Protect" → "guardrails / Agent Control" terminology note.
- **D1 = LangGraph** (was recommended/to-confirm): matches Galileo `sdk-examples` incl. `langgraph-open-telemetry`, fits the Graph Engine cascade, clean provider swap via LangChain chat models. Phase 0 framework item changed from "to confirm" to "decided".
- **D6 = LangChain chat-model interface** behind `MODEL_PROVIDER=ollama|openai` (`ChatOllama`/`ChatOpenAI`); follows from D1.
- **D2 = keep the Astronomy Shop theme as-is** — resolved the open reskin question (no reskin).
- **D4 = promote eval-accuracy to a live vignette** ("Trust the Judge", Vignette 4): naive LLM-judge wrong ~1 in 3 vs. Luna-2 / consensus evaluators on a curated known-ground-truth eval set. Core set is now four; Pre-Production Gate renumbered to 5 (still optional); Baseline remains warm-up.
- **D5 Galileo Pro purchase = moot** (covered by enterprise); removed as an active decision. The Firewall vignette drops the Pro-tier/LLM-as-judge-latency caveat.
- **D3 EC2 instance size = deferred to a Phase-1 empirical spike** (not by fiat). Starting assumption `t3.xlarge`-class (16 GB / 4 vCPU); no local GPU since EC2 uses OpenAI — only the docker-compose stack (~6 GB) + the agent.
- **Keystone risk retired/softened:** enterprise provides OTLP ingest, so the earlier "does the free Developer tier expose OTLP?" risk no longer blocks the dual-fan-out design. Kept the note that Galileo distributed/OTel tracing is Beta.
- **Self-hosting/VPC** added as a forward-looking offline option, but Splunk Observability remains SaaS, so "internet required for the observability layer" still holds for now.
- **Kept limitations L1** (live nondeterminism) and **L2** (ingestion latency / Beta tracing).

**Effect on codebase / UX:** Updated both planning docs (pillars, vignette library, runtime/self-hosting, capabilities, decisions, phases, sequencing, and the demo-ready milestone — now Core 4) plus `CHANGELOG.md`. No production code. The two design docs remain mutually consistent; Phase 0 entry is clearer (only provider accounts/tokens gate the start).

---

## 2026-06-16 — Phase-0 repository skeleton scaffolded

**What:** Created the lightweight Phase-0 repo skeleton: top-level dirs (`agent/`, `stage/`, `scenarios/`, `control-plane/`, `scripts/`), `pyproject.toml`, the committed `.env.example`, the reference `scenarios/invisible-failure/` folder (manifest + reset stub + placeholder talk-track), and per-directory READMEs. Filled the `README.md` Installation + Project-structure sections; updated `CHANGELOG.md`. No agent/vignette/control-plane logic implemented; no installs, branches, or commits.

**Why:** Phase 0 of the implementation plan calls for an agreed repo skeleton + secrets scaffolding + toolchain decisions before app code. Stubs and READMEs per directory pin the stable seams now so later phases drop in code without restructuring.

**Decisions / trade-offs:**
- **Only one piece of real code:** `agent/config.py` implements the `MODEL_PROVIDER=ollama|openai` chat-model selector (D6) because the provider abstraction is central. It uses lazy imports of the LangChain integrations and a guarded `dotenv` import so the module stays importable before the Phase-0 dependency install. Non-secret defaults only (hosts/model names); credentials are never defaulted.
- **Dependencies as minimum specifiers, not pins:** `uv` was unavailable and only system Python 3.9 was on PATH, so rather than invent precise pins, `pyproject.toml` lists `>=` minimums with a comment that exact versions lock during the Phase-0 install. The `galileo` SDK is listed unpinned with its minimum version flagged UNVERIFIED.
- **`.env.example` placeholders only** (no hardcoded credentials, per `codeguard-1`), grouped into model-provider / Galileo / Splunk sections with inline guidance and a `cp .env.example .env` header. `.gitignore` already ignored `.env` / `.env.*` while keeping `!.env.example`; verified with `git check-ignore`.
- **Reference manifest copied verbatim** from demo-design §7.1; the `talk_track` path already lined up with the `captions/` file, so no manifest edits were needed. `reset.sh` and `check-connectivity.sh` are executable echo-TODO stubs.

**Effect on codebase / UX:** Added the agent/stage/scenarios/control-plane/scripts skeleton, tooling, and secrets template; populated README Installation + structure. Still no runnable application logic. A contributor can now copy the env template, see every required token, and read a per-directory map of the planned system.

---

## 2026-06-16 — Phase-0 connectivity check implemented and run

**What:** Replaced the `scripts/check-connectivity.sh` stub with a real, secret-safe verifier and ran it against the user's gitignored `.env`. It reports PASS/FAIL/WARN with HTTP status codes and remediation hints for the selected model provider, Splunk Observability, and the Galileo enterprise deployment. Result: model provider (ollama) PASS, Galileo PASS (deployment + key), Splunk FAIL (HTTP 401 — invalid/expired token across all realms). Updated `CHANGELOG.md`.

**Why:** Phase-0 exit criteria require a trivial connectivity check confirming each account/token before building, so a cold setup fails fast instead of deep inside a vignette. Automating it (per `automate-verify`) makes the check repeatable.

**Decisions / trade-offs:**
- **Read-only probes only:** Ollama `GET /api/tags` (model-presence is a non-fatal WARN — it can be pulled); OpenAI `GET /v1/models` (bearer) when selected; Splunk `GET /v2/metric?limit=1` with `X-SF-Token`; Galileo unauthenticated `GET /v2/healthcheck` then read-only authenticated `GET /v2/datasets` with `Galileo-API-Key`. No POSTs, no telemetry, no mutation.
- **Secret hygiene:** secrets are passed to curl via expanded env vars inside `-H` headers (never in echoed strings) and `curl -s -o /dev/null -w '%{http_code}'` discards bodies. Only pass/fail, status codes, and non-secret config (provider/realm/host/console/project) are printed.
- **Galileo API base derivation:** confirmed via Galileo docs — take the console URL host, replace the leading `console` label with `api`, and drop the org-slug path (`https://console.multitenant.galileocloud.io/splunkse` → `https://api.multitenant.galileocloud.io`). Healthcheck is `/v2/healthcheck`; auth header is `Galileo-API-Key`. The endpoints are **confirmed** (both returned HTTP 200), not guessed.
- **Sandboxing reality:** the gitignored `.env` is served as redacted placeholder content to sandboxed shells; the real tokens are only readable with sandboxing disabled, so the live run required explicit approval. The run made authenticated read-only calls only.
- **Splunk diagnosis:** the token is rejected with 401 on every valid realm (eu0 included, which resolves — so not a DNS/realm-typo issue), indicating an invalid/expired access token rather than a realm mismatch. Remediation: regenerate the Splunk Observability access token (realm `eu0` is fine).

**Effect on codebase / UX:** `scripts/check-connectivity.sh` is now a runnable Phase-0 gate (`set -euo pipefail`, exit 1 on failure). A contributor gets an at-a-glance, secret-safe report of which backends are wired correctly. No application/telemetry code added (Phase 1+).

---

## 2026-06-16 — Phase-0 connectivity check: Splunk validated as an ingest token

**What:** Corrected the Splunk check in `scripts/check-connectivity.sh`. The earlier version probed the management API (`api.${SPLUNK_REALM}.signalfx.com/v2/metric`), which returned 401 — expected, because `SPLUNK_ACCESS_TOKEN` is an **ingest** (access) token, not an org/management token. The check now validates the token the way the Phase-1 Splunk OTel Collector actually uses it. After the fix, all three backends PASS.

**Why:** Validate credentials against the endpoint they are actually scoped for. An ingest token only authenticates against the ingest API, so testing it against the management API produced a misleading FAIL. (Supersedes the Splunk "invalid/expired token" assessment in the previous 2026-06-16 connectivity entry — that 401 was an endpoint mismatch, not a bad token.)

**Decisions / trade-offs:**
- **Endpoint:** `POST https://ingest.${SPLUNK_REALM}.signalfx.com/v2/datapoint` with header `X-SF-Token` (token via env, never echoed).
- **No real telemetry:** body is an empty payload `{"gauge":[],"counter":[],"cumulative_counter":[]}`, so the request authenticates without ingesting any datapoints.
- **Auth-not-payload heuristic (documented in-script):** 2xx => token accepted (PASS); 400 => payload-level rejection that still proves the token authenticated (PASS); 401/403 => auth rejected (FAIL); other => inconclusive (FAIL). Uses `curl -s -o /dev/null -w '%{http_code}'`.
- Left Ollama and Galileo checks unchanged.

**Effect on codebase / UX:** Splunk now reports PASS (HTTP 200, realm `eu0`) consistent with how telemetry will flow in Phase 1. Full re-run result: model provider (ollama) PASS, Splunk ingest PASS, Galileo (health + key) PASS — all secrets masked.

---

## 2026-06-16 — Phase 1: stage stood up; collector exporting to Splunk over OTLP

**What:** Vendored the OpenTelemetry "Astronomy Shop" into `stage/opentelemetry-demo`, ran it locally via docker-compose, and wired its OpenTelemetry Collector to export traces + metrics to Splunk Observability Cloud over OTLP/HTTP. All 28 containers run, the storefront returns HTTP 200, and the collector starts clean with zero `otlphttp/splunk` export errors. Added `scripts/stage-up.sh` / `scripts/stage-down.sh`, tracked overrides under `stage/splunk-otel/`, gitignored the clone, and updated the READMEs + CHANGELOG.

**Why:** Phase 1 needs the store running with infrastructure telemetry flowing to Splunk over OTLP (not the deprecated `sapm` exporter) before the concierge agent (Phase 2) can fan out to both backends.

**Decisions / trade-offs:**
- **Upstream over the Splunk fork.** Verified `splunk/opentelemetry-demo` is current (v2.0.5) but its docker-compose path is broken (compose references collector config files absent from the tree) and its Splunk O11y integration is Kubernetes-only (`SPLUNK-BUILD.md`). Since the plan calls for docker-compose, used the task's documented fallback: **upstream `open-telemetry/opentelemetry-demo` pinned to `2.2.0`** + our own Splunk exporter. Recorded the rationale in `stage/README.md`.
- **OTLP/HTTP, not gRPC, not `sapm`.** Splunk Observability rejects OTLP over gRPC, so used the `otlphttp` exporter to `ingest.${SPLUNK_REALM}.signalfx.com/v2/trace/otlp` (traces) and `/v2/datapoint/otlp` (metrics) with `X-SF-Token`. Verified endpoints against current Splunk docs.
- **Overrides outside the gitignored clone.** Source-of-truth config lives in tracked `stage/splunk-otel/` (`otelcol-config-extras.yml`, `docker-compose.override.yml`); `stage-up.sh` repoints the demo's existing extras mount (`OTEL_COLLECTOR_CONFIG_EXTRAS`) and adds `SPLUNK_*` env to the collector — upstream files stay pristine. The large clone (`/stage/opentelemetry-demo/`) is gitignored and re-creatable via a documented `git clone`.
- **Pin images to the source.** The demo ships `DEMO_VERSION=latest`; that pulled images newer than the `2.2.0` source and crash-looped the frontend-proxy (its envoy template gained `telemetry-docs`/`profiles` clusters whose env vars don't exist in 2.2.0's `.env`). `stage-up.sh` exports `DEMO_VERSION=IMAGE_VERSION` so images and source always match — diagnosed by reading the rendered envoy config (empty cluster addresses at index 9/10).
- **APM environment name = `local-agent-galileo`**, set via a collector `resource` processor (`deployment.environment` upsert) so it applies to every service in one place; namespace stays `opentelemetry-demo`.
- **Full stack** (Docker had 8.2 GB / 12 CPU, ≥ the ~6 GB requirement); `minimal` mode is supported via a script arg.
- **Secret hygiene:** `SPLUNK_ACCESS_TOKEN` read from the gitignored `.env`, passed to the collector via env only, never echoed/committed; collector logs contain no token (0 mentions of splunk/signalfx).

**Effect on codebase / UX:** `scripts/stage-up.sh` / `stage-down.sh`, `stage/splunk-otel/` overrides, gitignore rule, and refreshed READMEs/CHANGELOG. A contributor can clone the demo, run one script, and get the store at <http://localhost:8080/> exporting to Splunk APM (environment `local-agent-galileo`). Splunk-side verification (services/service map/traces visible) is left to the parent agent per the verification boundary.

---

## 2026-06-16 — Phase-1 reproducibility hardening (clean-room verified)

**What:** Closed the reproducibility gap from the initial Phase-1 stand-up: the demo was vendored by a hand-run `git clone` into the gitignored `stage/opentelemetry-demo/`, so a fresh checkout of our repo couldn't recreate the stage. Added a single-source pinned ref (`stage/demo.ref`) and an idempotent `scripts/stage-setup.sh` that clones the demo at that tag and wires our tracked Splunk overrides into the clone; made `stage-up.sh` self-bootstrapping; documented the full zero-to-running path; and proved it with a clean-room rebuild. Splunk-side APM verification had already PASSED (all Astronomy Shop services visible in the `local-agent-galileo` environment).

**Why:** The newly-added `automate-verify` "Reproducibility" rule requires the whole environment to come up from committed scripts + READMEs alone — no manual or machine-specific steps — with a clean-room proof.

**Decisions / trade-offs:**
- **Single source of truth = `stage/demo.ref`** (`DEMO_REPO`, `DEMO_REF=2.2.0`), sourced by both `stage-setup.sh` (clone tag) and `stage-up.sh` (image pin `DEMO_VERSION=${DEMO_REF}`). Replaced the earlier "read IMAGE_VERSION from the demo `.env`" pin so the version lives in exactly one place.
- **Materialize overrides into the clone** (vs. the earlier runtime `-f`/env approach): `stage-setup.sh` copies `splunk-otel/otelcol-config-extras.yml` to the clone's default collector-extras path and `splunk-otel/docker-compose.override.yml` to the clone root, re-syncing on every run. The tracked files remain the single source; setup (always re-run by stage-up) prevents drift, and the clone becomes self-wired so it exports to Splunk with no manual edits.
- **Idempotency rules:** clone is a no-op when present at the correct version; a *different* version present is a hard error with remediation (never silently mix); post-clone the script verifies the tag resolved to the expected release via the clone's `IMAGE_VERSION`.
- **Secret-safe throughout:** setup reads no secrets; up still reads `SPLUNK_*` from `.env` and passes them via env only; down exports empty `SPLUNK_*` defaults purely to silence compose's unset-variable warnings on teardown. Token never printed.
- **Gitignore confirmed:** only `/stage/opentelemetry-demo/` is ignored; `stage/demo.ref`, both `stage/splunk-otel/` overrides, and all `scripts/` are tracked (checked with `git check-ignore`).

**Effect on codebase / UX:** Added `stage/demo.ref` + `scripts/stage-setup.sh`; rewired `stage-up.sh`/`stage-down.sh`; documented the prerequisites→env→setup→run→verify→teardown sequence (each step a script) in `README.md`, `stage/README.md`, `scripts/README.md`; CHANGELOG updated. **Clean-room result:** after `down` + `rm -rf stage/opentelemetry-demo`, running `stage-setup.sh && stage-up.sh` from scratch reproduced a working stack — clone back at `2.2.0`, 28/28 containers up, storefront HTTP 200, collector 0 restarts, zero `otlphttp/splunk` export errors. Stack left running.

---

## 2026-06-18 — Consolidate `control-plane/` into `control_plane/`

**What:** Merged the two sibling directories — `control-plane/` (hyphen, which held only the SE-facing `README.md`) and `control_plane/` (underscore, the Python package) — into the single canonical package directory `control_plane/`. Moved the README in, deleted the empty hyphenated directory, and fixed live path references across the repo.

**Why:** Hyphenated names are not importable in Python, so the package must keep the underscore name; the hyphenated folder was redundant (docs-only) and a source of confusion. Co-locating the SE-facing README with the package it documents removes a directory that could only ever hold docs.

**Decisions / trade-offs:**
- **Canonical dir = `control_plane/` (underscore).** The hard Python-import constraint settles the name; the README moves into the package.
- **Plain filesystem move** (both directories were untracked `??`), then `rmdir control-plane`.
- **Only true directory/path references were rewritten.** Kept the shell launcher filename `scripts/control-plane.sh` (hyphenated filenames are conventional and fine), the CLI/command names, and the English phrase "control plane".
- **Historical records left intact (append-only).** Past `CHANGELOG.md` narrative entries and prior agent-journal entries that mention creating `control-plane/` at the time were not rewritten — they are an accurate audit trail; a new `[Unreleased]` CHANGELOG entry documents the consolidation instead.
- **Untouched by design:** did not search for or modify any `local-agent-galileo` string.

**Effect on codebase / UX:** `control_plane/README.md` now exists (heading + self-link fixed); `control-plane/` is gone. Updated live references in `README.md` (merged the duplicated project-structure rows into one `control_plane/` row; repointed the README link) and `docs/implementation-plan.md` (proposed repo-structure line). Verified the package still imports and the CLI is intact (`python -m control_plane --help`). No behavioural change for SEs.
