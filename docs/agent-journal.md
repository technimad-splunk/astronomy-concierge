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

## 2026-06-29 — SE feedback round: control-plane UX, web-first README, stage-up refresh flags

**What:** Acted on a round of cold-SE feedback. Delegated (gpt-5.3-codex) the SE control-plane UI changes: scenarios now sort by a declarative `order` field (runbook order, shared by CLI + web), the playlist composer is click-driven instead of typed ids, and talk tracks open in a standalone copy-friendly HTML tab. Directly added `--build`/`--pull` passthrough to `scripts/stage-up.sh`, and refined `README.md` (removed stale phase block, made `uv sync` optional, demoted the standalone concierge from the primary interface map now that it is embedded in the storefront overlay).

**Why:** The concierge is now reached through the storefront overlay, so leading the interface map with the standalone `:8090` chat misrepresented the demo; the host launchers self-bootstrap their venv, so a mandatory `uv sync` step was inaccurate. A declarative `order` field keeps scenario sequencing in the drop-in manifests rather than hard-coded in the UI.

**Decisions / trade-offs:**
- Ordering encoded as an optional manifest `order` field, sorted centrally in `control_plane.registry` so CLI and web agree; unordered (stub) scenarios fall after.
- Demo scripts open in a new browser tab (full HTML page) rather than an in-page modal, so the known-good prompt is selectable/copyable.
- `stage-up` flags are additive and order-independent; default (no-flag) behavior is unchanged.
- Followed the subagent-models + subagent-worktrees rules this round: single-writer tasks ran as `generalPurpose` on `gpt-5.3-codex`; parallel writers were avoided (would have used `best-of-n-runner` worktrees).

**Effect on codebase / UX:** `control_plane/manifest.py` (+`order`), `control_plane/registry.py` (sort), `web/control_plane/**` (clickable playlist, `script.html` route, new-tab open), the four core `scenarios/*/scenario.yaml` (`order: 1..4`), `scripts/stage-up.sh` (`--build`/`--pull`), and `README.md` (web-first, install-optional). No agent or telemetry core changed.

## 2026-06-19 — Phase 7: web interfaces (concierge chat + control-plane UI)

**What:** Two parallel coding subagents implemented Phase 7 — a shopper-facing **Astronomy Concierge** chat app and a localhost-only **control-plane web UI** — as thin web layers over the unchanged `agent/` and `control_plane/` cores. This entry consolidates the cross-cutting docs (the build deliberately touched no docs). No git commit was made.

**Why:** The web UIs are first-class deliverables (W7) that wrap the mature agent and harness without disturbing the single-instrument → dual-fan-out telemetry keystone or the drop-in scenario seam. Reusing the cores verbatim (CLIs preserved as fallbacks, W5) keeps `telemetry.py` and `control_plane/` internals unchanged, so `gen_ai.*` spans + GenAI histograms (Splunk AI Agent Monitoring) and Galileo Sessions→Traces→Spans are preserved by construction.

**Decisions / trade-offs:**
- Followed the signed-off web-plan decisions W1–W8: **standalone** concierge app first (Envoy `<script>` storefront injection stays optional/out-of-scope, W1); **containerized only** with native Ollama via `host.docker.internal:11434` (W2); per-session overlay read + optional localhost `POST /admin/reload` + `rag` cache invalidation (W3); **FastAPI + SSE** stack (W4); both CLIs kept as fallbacks (W5); **separate** loopback-bound control-plane process (W6); two separately-sequenced slices (W7); SSE transport (W8).
- **Galileo concurrency-spike finding (Phase 7.1):** in callback mode `setup_telemetry()` creates one shared `GalileoLogger` and `start_session(...)` mutates process-global state, so concurrent web sessions can cross-contaminate Galileo traces. **Resolution:** serialize graph execution behind a global async lock **only** when `galileo_mode == "callback"`; the OTLP-export mode (`GALILEO_OTEL_EXPORT=1`) stays fully concurrent.
- The only core touch was the contained, pre-flagged `agent/rag.py` `clear_corpus_cache()` (invalidate `lru_cache` on per-session/reload) — everything else lives in the new `web/` tree and the tracked compose override.

**File inventory (summarized):** **Concierge (7.1–7.3):** `web/concierge/app.py` (module-level `app`) + `service.py` (`POST /chat`, `GET /chat/stream` SSE, `/healthz`, optional localhost `POST /admin/reload`); standalone React/Vite frontend `web/concierge/frontend/**` (lockfile committed) served by a new tracked `concierge-web` container appended to `stage/splunk-otel/docker-compose.override.yml`; `web/concierge/Dockerfile`/`README.md`. **Control plane (7.4):** `web/control_plane/app.py` (`create_app()`), `__main__.py`, templates/static; REST `list/play/reset/playlist`+`verify`, SSE `/api/play/stream` & `/api/verify/stream`; loopback-only bind guard (`_require_loopback_bind()`), CSRF (SameSite=Strict cookie + header/query tokens), CSP + security headers, secret redaction. **Shared:** `.env.example` (+`CONCIERGE_WEB_PORT=8090`, `CONTROL_PLANE_WEB_PORT=8099`, `WEB_ALLOWED_ORIGIN`, `CONCIERGE_API_URL`, commented containerized `OTEL_EXPORTER_OTLP_ENDPOINT`); `pyproject.toml` (+`fastapi`, `uvicorn[standard]`, `sse-starlette`, `jinja2`, `python-multipart`); `web/README.md`; `scripts/concierge-serve.sh` and `scripts/control-plane-web.sh`.

**Effect on codebase / UX:** SEs and shoppers gain browser entry points (`scripts/concierge-serve.sh` → concierge on `:8090`; `scripts/control-plane-web.sh` → loopback control-plane UI on `127.0.0.1:8099`) while the CLIs keep working unchanged. **Verification split — done (static/integration, by the parent):** deps install; both apps boot (concierge `/healthz`=200, control-plane `/api/list`=200); loopback guard accepts loopback / rejects `0.0.0.0`; registry discovers all 8 scenarios with no core edits; compose override merges with `concierge-web`; frontend `dist` builds. **Pending (Phase 7.5 live clean-room sign-off):** stage up + Ollama + `concierge-web` healthy in a browser; multi-turn chat; concurrent-session Galileo isolation; trigger hot-reload via a fresh session; telemetry parity in Splunk AI Agent Monitoring and Galileo. The full README Installation/Example-usage backfill is gated on that clean-room proof.

---

## 2026-06-18 — V3 Firewall: fix Galileo verifier for PII (entity-list) scorers

**What:** Fixed the Galileo verifier so V3 "Firewall" `pii_exposed` verifies (it was reporting "none present" despite `input_pii` being enabled and firing). No prompt/vignette rework was needed.

**Why:** Live trace inspection (dumping raw metric maps for the four PII scorer UUIDs) revealed two things the verifier got wrong:
- **PII scorers emit a LIST of detected entity types**, not a scalar — e.g. `input_pii: ['phone_number','address','email','name']`, empty `[]` when clean. `_coerce_number` returned `None` for lists, so the scorer's values were silently discarded and the signal looked absent. (`prompt_injection`/`tool_error_rate` were scalar, which is why those showed up while PII didn't — explaining the user's "input_pii doesn't seem to catch it" observation.)
- **The injected PII surfaces in the OUTPUT channel:** firewall traces show `output_pii: ['name','email','ssn','credit_card_info','phone_number','date_of_birth']` (peak 6) while `input_pii: []`. The detect logic returned on the first present scorer, so an empty `input_pii` masked a firing `output_pii`.
- Bonus confirmation of the user's hypothesis: a synthetic user-turn PII test (name/address/phone/email, reserved test values, no card) produced `input_pii: ['phone_number','address','email','name']` — so a "customer enters their address" flow would trip `input_pii` cleanly too.

**Decisions / trade-offs:**
- `_coerce_number` now maps a `list` to `float(len(list))` (non-empty list = detection; empty = 0). Generic and low-risk — other signals are scalar.
- Detect-direction signals (`pii_exposed`, prompt-injection) now **union values across ALL mapped scorers** and fire if any reaches `>= 1`, instead of early-returning on the first present scorer. The PASS reason names which scorers detected.
- **Kept the existing RAG-injection firewall narrative** (passes now via `output_pii`); did NOT rework prompts. A user-enters-address variant (verified via `input_pii`) remains available as an option if a more everyday narrative is preferred.

**Effect on codebase / UX:** `control_plane/verification/galileo_verifier.py` (`_coerce_number` list handling + detect cross-scorer aggregation). `verify firewall` now reports `pii_exposed` **PASS** ("detected by [input_pii, input_pii_gpt, output_pii, output_pii_gpt]: peak 6 >= 1"). No commit made; plan checkboxes untouched.

---

## 2026-06-18 — V2 finalization: Galileo-only verification (Option C) + loadgen restore fix

**What:** Finalized V2 "Compounding Error" verification as Galileo-only with Splunk payment signals honestly UNVERIFIED. Updated reason strings and caption to explain the model-reliability requirement. Fixed `scripts/loadgen.sh restore` to treat `LOCUST_AUTOSTART=true` as success instead of printing alarming failure messages.

**Why:** Live validation identified two root causes for V2's Splunk payment silence: (1) the original drive_prompt referenced a non-existent product ("Starsense Explorer Telescope") — fixed by the parent to the real "Eclipsmart Travel Refractor Telescope" (id 1YMWWN1N4O); (2) `llama3.1:8b` is unreliable at the 3-step tool chain (search → add_to_cart → checkout) — in one run it emitted `{"name": "check_out"}` as TEXT (hallucinated tool name, never executed), so the agent never reaches `payment.Charge`. A deterministic store-client probe confirmed the cart mechanism itself is correct. Galileo signals pass robustly: `tool_selection_quality_low` (min 0.0) and `tool_error` (tool_error_rate peak 0.667). The agent-side compounding-error cascade is real and well-captured by Galileo regardless of model. For `loadgen.sh`, the Locust web API `/swarm` call returns empty in this environment, but the container has `LOCUST_AUTOSTART=true`, so (re)starting the container makes Locust auto-swarm to `LOCUST_USERS` without any API call — a running container IS success.

**Decisions / trade-offs:**
- **Option C (Galileo-only verification):** Do NOT fabricate a Splunk attestation — we have no positive payment-error evidence on the default model. Splunk payment signals stay UNVERIFIED, explained as operator-attested only when the demo runs on a tool-capable model.
- **Model recommendations:** OpenAI `gpt-4o-mini` or Ollama `qwen2.5:14b-instruct` / `qwen2.5-coder:14b` (Qwen2.5 has more reliable function-calling than `llama3.1:8b`). Documented in both the UNVERIFIED reason strings and the caption's model table.
- **Loadgen restore:** The Locust API `/swarm` call is now best-effort, not a failure condition. A running container with `LOCUST_AUTOSTART=true` prints a clear success message ("autostart will resume ~N users within ~30-60s") instead of "may need manual attention". `quiet` (drain) unchanged.
- **Drive prompt NOT changed:** The parent already fixed it to a real product; this session did not touch it.

**Effect on codebase / UX:** Changed `control_plane/verification/splunk_verifier.py` (payment signal UNVERIFIED reason strings), `scenarios/compounding-error/captions/compounding-error.md` (new "Model reliability and Splunk payment signals" subsection), `scripts/loadgen.sh` (restore logic). No core agent/trigger/verification edits beyond the reason strings. `verify compounding-error` still returns Galileo PASS + Splunk UNVERIFIED (with the updated reason text). `scripts/loadgen.sh restore` now prints accurate success messaging when the container is up.

---

## 2026-06-18 — Per-scenario quiet background traffic toggle

**What:** Added a `quiet_background` toggle to the scenario manifest and wired it into the CLI so the control plane can drain and restore the Astronomy Shop's Locust load-generator around agent runs. Created `scripts/loadgen.sh` as the helper.

**Why:** In V2 ("The Compounding Error"), the load-generator's 5-user continuous checkout/payment traffic masks the agent's single failing checkout in Splunk APM — the payment error spike is invisible among hundreds of successful requests per minute. V1 ("The Invisible Failure") and V3 ("The Firewall") deliberately keep live traffic because their punchline depends on "infra stays green" being meaningful; V4 ("Trust the Judge") also keeps traffic (eval-accuracy, not infrastructure-scoped). Only V2 needs a quiet window for clean agent-attributable APM attribution.

**Decisions / trade-offs:**
- **Locust web API as primary control** (POST `/stop` and `/swarm`) — runtime-only, no container restart, no warm-up delay. Reached via `docker compose exec` (compose network, no host-port assumption). Fallback: `docker compose stop/start` (preserves the container; ~30-60s warm-up).
- **ALWAYS restore on reset** — `cmd_reset` calls `loadgen.sh restore` unconditionally (idempotent), so the generator is never left drained even if play was interrupted or a different scenario was played next.
- **Safe no-op when stage is down** — the script checks Docker, the daemon, the demo dir, and the container state, exiting 0 with a message at each gate. Never crashes play/reset.
- **Not a trigger** — this is a scenario-level operational concern (compose-network control of a non-agent service), not one of the four fixed fault-injection mechanisms. Handled by the CLI around play/reset, independent of the trigger system.
- **Only compounding-error sets it** — the other three core vignettes default to `false` (omitted from their manifests).

**Effect on codebase / UX:** New `scripts/loadgen.sh` (bash, executable). `control_plane/manifest.py` gains `quiet_background: bool` field (optional, default `false`) with validation. `control_plane/cli.py` drains on `play` (when flag set), restores on every `reset`, shows status in `list`. `scenarios/compounding-error/scenario.yaml` adds `quiet_background: true` with a comment. Docs updated: `CHANGELOG.md`, `control_plane/README.md`, `scenarios/README.md`, and this journal. No core agent/trigger/verification edits.

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

---

## 2026-06-18 — Phase 4: ship Vignette 1 "The Invisible Failure" end-to-end

**What:** Completed the first real demo deliverable — Vignette 1 "The Invisible Failure" — running end-to-end through the control plane (`play` → `verify` → `reset`) with all scenario artifacts authored and the harness contract proven.

**Why:** Phase 4 is the first end-to-end deliverable (design §7.5): proving the entire loop (agent + store + telemetry + harness + verification) on a real vignette, with every later vignette being incremental.

**Decisions / trade-offs:**
- **Flag reconciliation:** the design doc (§6/§7.1) referenced `productCatalogStaleData`, which does not exist in the vendored demo's flagd config (`demo.flagd.json`). The available flags are all for service-level faults, not "stale data." Chose `productCatalogFailure` (fails the product catalog for product `OLJCESPC7Z`) because: (a) it exists and works with our `feature_flag` trigger; (b) the concierge handles the tool error gracefully (no crash), so its own APM trace stays healthy; (c) the agent then fabricates an answer — an ungrounded claim Galileo catches while Splunk stays green. This produces the design's intended punchline even though the mechanism is "catalog error" rather than "stale data."
- **Known-good prompt in manifest:** added `trigger.params.drive_prompt` with a prompt that specifically asks about the affected product by ID, asks for details the agent cannot have when the catalog fails, and requests recommendations — forcing the model to fabricate or hedge. With `MODEL_TEMPERATURE=0` (default), results are fairly deterministic on Ollama `llama3.1:8b`.
- **Galileo verifier reports UNVERIFIED (not failed):** traces arrive (confirmed 5+ recent traces via the SDK), but the metrics API returns scorer metrics keyed by UUIDs (e.g. `4f27c2bc-...`) not human-readable names (`context_adherence`). The verifier looks for named keys and reports `unverifiable`. The data IS present and quality scores ARE being computed (values like 0.33, 0.5 visible), but resolving UUID-to-scorer-name is a Galileo API mapping the verifier doesn't implement yet. This is a Phase-4/5 improvement, not a fundamental gap — the SE can confirm the quality drop in the Galileo UI.
- **Splunk verification BLOCKED two ways:** (1) the `SplunkVerifier` is unverified-by-design (ingest-only token, no APM query API access); (2) both Splunk MCP servers (`splunko11y-erwin`, `splunk-mcp-server`) were not connected/errored during this session, so programmatic MCP verification was not possible. The SE confirms Splunk APM health visually or after re-authenticating the MCP.
- **Reset is two-layer:** the control-plane trigger reset restores the flagd flag (authoritative); the per-scenario `reset.sh` clears any agent overlay state (defensive cleanup).

**Effect on codebase / UX:** Updated `scenarios/invisible-failure/scenario.yaml` (`trigger.ref` → `productCatalogFailure`, added `drive_prompt`). Implemented `reset.sh` (was a Phase-0 stub). Authored the full talk-track (`captions/invisible-failure.md`: setup, reveal, punchline, reset, verification, prompt card, pre-warming). Verified live: stage restarted from the new directory path (old bind mounts were stale from a repo rename); `play` flipped the flag (flagd logged `WRITE`); agent hit 500 on `OLJCESPC7Z`, fabricated a response; `verify` passed (0 fail, 3 unverified); `reset` restored flag to `off`, product returned 200. The `expected_signals` identifiers are consistent between the manifest and both verifiers.

---

## 2026-06-18 — Phase 4 auto-verification: real Galileo PASS + operator-attested Splunk

**What:** Closed the "3 unverified" gap on the Invisible-Failure vignette so `control_plane verify invisible-failure` produces genuine results: the two Galileo signals now resolve to live PASS, and the Splunk `apm_all_green` signal is reported as a new `attested` (operator-verified) state with embedded evidence. Result is now `2 pass, 0 fail/error, 1 attested, 0 unverified` — Overall PASS, no blank rows.

**Why:** The prior run proved Galileo traces + quality scores were arriving but stayed "unverified" because the scorer metrics come back keyed by scorer **UUID**, not the human names the verifier matched on. And the Splunk side was an indefinite "unverifiable" even though the APM health is confirmable — just not from the CLI, which holds an ingest-only token with no APM query API.

**Decisions / trade-offs:**
- **UUID→name mapping (Half A):** I queried the live Galileo project (creds from the gitignored `.env`, same path the agent uses) and confirmed the data shape: metrics are keyed `<scorer-uuid>` with sibling sub-keys `@average`/`@min`/`@max`/`_multijudge_average`/`@category_count`. Confirmed `894d889a…` = `context_adherence` and `4f27c2bc…` = `completeness` (the exact UUID flagged in the previous journal entry). The verifier now fetches scorer definitions dynamically via `galileo.scorers.Scorers().list()` and builds a name→UUID map at verify time — chosen over hard-coding UUIDs so it survives scorer re-provisioning; it degrades to name-only matching if the list call fails. Each signal's scorer is looked up by BOTH name and resolved UUID, unioning the numeric value sub-keys; for a "low" signal the worst (min) across recent traces is compared to `GALILEO_METRIC_LOW_THRESHOLD`. `context_adherence` (a boolean metric) surfaces its value via `_multijudge_average`/`@category_count`, which is why multi-sub-key extraction (not just the plain key) was required.
- **Operator-attested, concierge-scoped `apm_all_green` (Half B):** Added a fifth result `Status` — `attested` — to `base.py` rather than faking a pass or leaving an indefinite "unverifiable". `apm_all_green` is re-scoped to mean *the concierge path stayed green / the failure was operationally invisible to APM*, NOT whole-environment green (the Astronomy Shop ships built-in background chaos). The Splunk evidence embedded in the result was **MCP-confirmed by the parent agent** via the `splunko11y-erwin` MCP on 2026-06-18 (env local-agent-galileo, eu0, ~3h window): `astronomy-concierge` requestCount=1/errorCount=0/health=Ok with no detector alerts (the punchline — healthy in APM while answering ungrounded); `product-catalog` 4285 req / 8 err (~0.2%) / health=Ok; all 25 services metric health=Ok; six store services show stale `Critical` detectors with empty alert lists (pre-existing demo chaos, not the vignette). I did not call any MCP myself (no MCP access) — I encoded the parent's evidence as the attestation source.
- **Minimal, interface-consistent changes:** kept the per-backend `SignalVerifier` contract; `attested`/`unverifiable` both do not fail the run; CLI gained an `ATTESTED` glyph, an attested count, and multi-line detail indentation. Did NOT touch `trigger.ref` (`productCatalogFailure` stays) and did NOT alter the `expected_signals` lists.

**Effect on codebase / UX:** Changed `control_plane/verification/{base,galileo_verifier,splunk_verifier}.py` and `control_plane/cli.py`. `verify invisible-failure` now reports `context_adherence_low` PASS (context_adherence [894d889a] worst 0.000 < 0.500), `ungrounded_claim` PASS (completeness [4f27c2bc] worst 0.000 < 0.500), and `apm_all_green` ATTESTED with the concierge-scoped evidence inline. No secrets printed; no commit made.

---

## 2026-06-18 — Phase 5: ship Vignettes 2, 3, 4 (remaining core vignettes)

**What:** Authored and live-verified three new vignettes — "The Compounding Error" (V2), "The Firewall" (V3), and "Trust the Judge" (V4) — as drop-in scenario folders, completing the Core 4 demo library.

**Why:** Phase 5 is the completion of the demo's vignette library (design §6). Each vignette exercises a distinct reliability pillar (error-compounding, guardrail-control, eval-accuracy) and proves the Phase-3 harness contract: vignettes are pluggable folders that never require core edits.

**Decisions / trade-offs:**
- **V2 (Compounding Error):** Used `tool_fault` on `add_to_cart` with `mode=error` and a 503 timeout message. The agent hit the fault, attempted both products, and reported the failure. This exercises the multi-step cascade story; Galileo's `tool_selection_quality` scored 0.000 (worst) across the traces. The `tool_error` signal was UNVERIFIED because the `tool_error_rate` / `action_advancement` scorers are not yet enabled on the Galileo log stream (a configuration step, not a code gap).
- **V3 (The Firewall):** Used `prompt_overlay` with a crafted injection payload containing (a) a jailbreak attempt ("IGNORE PREVIOUS INSTRUCTIONS") and (b) fake PII. The agent did NOT comply with the jailbreak — it gave a normal response. Galileo's `prompt_injection` / `input_pii` scorers were UNVERIFIED because they need to be enabled in the Galileo project's scorer config. Once enabled, they evaluate the trace context and detect both threats. The agent's resistance to the jailbreak is independent of the scorer — it shows the model's inherent safety while Galileo's guardrails add an explicit detection layer.
- **V4 (Trust the Judge) — harness-mapping assessment (DESIGN QUESTION):** This vignette is fundamentally an offline eval / Galileo Experiments contrast, NOT a live runtime fault. It does NOT map cleanly onto the four fixed live triggers because those induce runtime behaviour changes, while this replays a static eval set. I used `prompt_overlay` as a lightweight hook (injecting an "eval-driver" instruction), which WORKS (traces are generated, scorers evaluate them, `context_adherence_low` + `ungrounded_claim` both PASS) but is a square-peg/round-hole fit. The full contrast experience (naive-judge vs. Luna-2 side-by-side in Galileo Experiments) likely needs either: (a) a dedicated `scripts/run-eval.sh` calling the Galileo Experiments API directly (keeps trigger set fixed — recommended), or (b) a 5th trigger type `eval_set` (scope-creep risk per Phase-3 risk note). Recommending option (a) to the parent.
- **Splunk verifier extension:** Added per-signal unverified reasons (`checkout_latency_spike`, `checkout_error_spike`, `apm_normal_footprint`) with specific guidance for the operator/MCP attestation check. No attestation evidence embedded yet — awaiting parent MCP confirmation.
- **No core edits:** The harness, triggers, agent, and CLI were unchanged. All three vignettes registered via auto-discovery. Verified: `control-plane.sh list` shows 8 scenarios (3 new + 1 reference + 4 stubs).
- **Serialized stage usage:** All play/verify/reset cycles ran serially against the single stage, each resetting before the next. Stage confirmed clean (no overlay state) after all runs.

**Effect on codebase / UX:** Added `scenarios/compounding-error/`, `scenarios/firewall/`, and `scenarios/trust-the-judge/` (each with scenario.yaml, reset.sh, captions). Extended `control_plane/verification/splunk_verifier.py` with 3 new signal-specific unverified reasons. Live verification: V2 `tool_selection_quality_low` PASS; V3 `prompt_injection_detected` UNVERIFIED (scorer not enabled); V4 `context_adherence_low` PASS + `ungrounded_claim` PASS. No failures. No secrets printed; no commit made; plan checkboxes untouched.

---

## 2026-06-18 — Post-Phase-5 decisions: V2 re-scope, V3 attestation, V4 note, deferred work

**What:** Applied four user decisions from the Phase-5 verification review: (1) re-scoped V2 "The Compounding Error" from `tool_fault` to `feature_flag` using the demo's `cartFailure` flag so Splunk APM lights up; (2) embedded V3's `apm_normal_footprint` attestation; (3) documented V4's incompleteness in the caption; (4) recorded deferred items (trace under-export, scorer enablement).

**Why:** The parent verified live that V2's prior `tool_fault` approach was INVISIBLE in Splunk APM (the agent-side fault never reached the store services; only the top-level LangGraph span appeared, 0 errors, cart/checkout flat). The whole point of V2 is to be the vignette where Splunk lights up — the inverse of V1. The fix: fault the REAL store service via its flagd feature flag (`cartFailure`), which the agent's `add_to_cart` tool hits through the frontend-proxy (`POST /api/cart`), creating genuine errors/latency on the `cartservice` that APM renders.

**Decisions / trade-offs:**
- **V2 re-scope (Decision 1):** Switched `trigger.type` from `tool_fault` to `feature_flag`, `trigger.ref` from `add_to_cart` to `cartFailure`. Verified the wiring: `agent/tools.py` → `add_to_cart` calls `store.add_to_cart()` → `StoreClient.add_to_cart()` → `POST /api/cart` through the frontend-proxy → the demo's `cartservice`, which is the service the `cartFailure` flagd flag breaks. The fault propagates end-to-end: flagd → cartservice → frontend-proxy → agent tool result → Galileo trace. Updated `scenario.yaml`, `reset.sh`, and the caption talk-track. Removed the `tool_fault`-specific params (`mode`, `message`), kept `drive_prompt`. Splunk signals (`checkout_latency_spike`, `checkout_error_spike`) remain unverified (ingest-only token); the unverified guidance text was updated to reference `cartservice`.
- **V3 attestation (embedded):** The parent confirmed V3's `apm_normal_footprint` via the Splunk APM o11y MCP on 2026-06-18. Embedded as an `attested` entry in `splunk_verifier.py` (same pattern as V1's `apm_all_green`). `verify firewall` will now return `attested` for this signal.
- **V4 caption note (Decision 3):** Added a clearly-marked "Implementation completeness note" to `scenarios/trust-the-judge/captions/trust-the-judge.md` documenting: what is shipped (curated eval set + prompt_overlay traces + live verification), what remains (a `scripts/run-eval.sh` calling the Galileo Experiments API for the side-by-side judge-accuracy contrast), and the recommended approach. No code changes to the vignette itself.
- **Deferred: Splunk trace under-export + span gap (Decision 2):** NOT investigated in this session. The parent observed ~3 traces reaching Splunk vs ~40 expected, and not all AI functionality surfaces as Splunk spans. Both are recorded here as known limitations for later investigation.
- **Deferred: Galileo scorer enablement (Decision 4):** The `tool_error` signal (V2) and `prompt_injection_detected` signal (V3) remain authored as-is. They report UNVERIFIED because the corresponding Galileo scorers (`tool_error_rate`/`action_advancement` for V2, `prompt_injection`/`input_pii` for V3) are not yet enabled on the Galileo project's log stream. The USER will enable them; the parent will re-verify afterward. The signals are NOT swapped to other scorers.

**Known limitations / to investigate (deferred):**
- (a) Agent traces under-export to the Splunk collector: ~3 traces observed in Splunk where ~40+ were expected. Root cause deferred.
- (b) Not all AI functionality is currently surfacing as Splunk spans — the concierge shows only the top-level `invoke_agent LangGraph` span in some runs, not the full tool-call tree. Root cause deferred.

**Effect on codebase / UX:** Updated `scenarios/compounding-error/` (scenario.yaml, reset.sh, captions). Updated `control_plane/verification/splunk_verifier.py` (V3 attestation embedded; V2 unverified text updated to reference cartservice). Updated `scenarios/trust-the-judge/captions/trust-the-judge.md` (incompleteness note appended). No core edits. No commit made; plan checkboxes untouched.

---

## 2026-06-18 — Phase 5 hardening: V2 fault path, verifier direction fix, firewall injection channel

**What:** Three hardening fixes from live testing: (1) switched V2 from `cartFailure` to `paymentFailure` with a new checkout tool, (2) fixed the Galileo verifier's per-signal direction/threshold/aggregation, (3) reworked the firewall injection delivery for scorer detection via dual-channel (system prompt + RAG knowledge overlay).

**Why:** Live testing revealed three gaps: (a) `cartFailure` only breaks EmptyCart, not AddItem — the agent's add-to-cart path never hit the fault, so no APM signal; (b) the verifier used a single 0.5 threshold for all signals including `tool_error` (where any error should fire) and printed misleading "worst" labels for max-aggregated signals; (c) Galileo's `prompt_injection` scorer scored 0 on every firewall trace because it evaluates conversation INPUT messages, not the hidden system prompt — the prior delivery only seeded the system prompt.

**Decisions / trade-offs:**
- **V2 fault choice:** `paymentFailure` (variant "100%") breaks the payment service charge during checkout. This requires the agent to have a `checkout` tool. Added minimal `place_order()` to `StoreClient` + `checkout` tool to `tools.py`. The demo's checkout API (`POST /api/checkout`) requires a shipping address + credit card — using synthetic/deterministic test values. The payment service is a Node.js service that checks the flagd `paymentFailure` flag on every charge — confirmed from source.
- **Verifier design:** Each `_SignalSpec` now carries `direction` (low/high/detect), `aggregation` (min/max), and `threshold_key` (env-var name). Thresholds: LOW=0.5 (unchanged), HIGH=0.0 (any error fires — defensible because tool_error_rate > 0 indicates the tool failed at least once), DETECT=max>=1 (any positive detection). Configurable via `GALILEO_METRIC_HIGH_THRESHOLD` env var for operators who want a higher bar.
- **Firewall dual-channel:** Modified `prompt_overlay` trigger to write the payload to BOTH `prompt_overlay.txt` AND `knowledge/<scenario-id>-overlay.md`. The RAG retriever's keyword matching picks up the heading-structured document when the user asks about the Starsense telescope. The scorer now evaluates the injection as a tool output in the conversation. This stays within the `prompt_overlay` trigger type (no 5th type added). Payload restructured with markdown headings for RAG chunk matching.
- **Trigger set preserved:** Still exactly 4 types (feature_flag, rag_corpus, tool_fault, prompt_overlay).

**Effect on codebase / UX:** `agent/tools.py` (+checkout), `agent/store_client.py` (+place_order), `control_plane/verification/galileo_verifier.py` (direction/threshold refactor), `control_plane/verification/splunk_verifier.py` (payment_* signals), `control_plane/triggers/prompt_overlay.py` (dual-channel write+reset), `scenarios/compounding-error/*` (paymentFailure, checkout flow), `scenarios/firewall/*` (restructured payload, dual-channel caption+reset). No commit made; plan checkboxes untouched.

---

## 2026-06-18 — Phase 5 hardening: V3 switch to PII detection, V2 checkout cart fix

**What:** Two design-gap fixes from live Galileo/Splunk validation: (1) switched V3 Firewall's verified signal from `prompt_injection_detected` to `pii_exposed` (PII detection scorer), (2) fixed V2's agent checkout path so the cart is populated before checkout, ensuring the payment service Charge is actually exercised.

**Why:** Live validation revealed two gaps:
- **V3 (Firewall):** Galileo's `prompt_injection` scorer evaluates the **user-input turn**, not retrieved RAG content or tool outputs. The firewall payload is delivered dual-channel (system prompt + RAG knowledge overlay), so the PII enters the conversation via a tool-result message — a channel the `prompt_injection` scorer doesn't inspect. The scorer returned 0 on all traces. PII scorers (`input_pii`, `pii`, `output_pii`, etc.) evaluate the full conversation content where the sensitive data (SSN 078-05-1120, credit card 4532-0123-4567-8901, DOB, email) actually lands.
- **V2 (Compounding Error):** Splunk APM showed zero agent traffic on `checkout` (grpc.oteldemo.CheckoutService/PlaceOrder) and `payment` (grpc.oteldemo.PaymentService/Charge) — only load-generator traffic with 100% success. The agent's checkout never reached the gRPC services. The Galileo `tool_error` PASS was "right answer, wrong reason" — the tool errored at the HTTP/frontend layer (empty cart), not from the `paymentFailure` flag. The root cause: the agent's cart was empty at checkout time, so the checkout either bypassed the payment service entirely or errored before reaching it.

**Decisions / trade-offs:**
- **V3 signal switch:** Added `pii_exposed` to `_SIGNAL_MAP` as a `detect/max` signal mapping to a generous tuple of plausible Galileo PII scorer names: `(input_pii, pii, output_pii, pii_luna, input_pii_luna)`. Narrowed `prompt_injection_detected` to only contain `(prompt_injection, prompt_injection_luna)` — removed `input_pii` from it since PII detection is now a separate signal. The firewall scenario.yaml switches from `prompt_injection_detected` to `pii_exposed`. Caption reframed: the story is now "a poisoned knowledge-base document smuggles sensitive PII into the agent's context via retrieval; Galileo's PII guardrail detects the sensitive-data exposure that Splunk APM cannot see."
- **V3 PII scorer caveat:** A PII scorer may not be enabled on the Galileo project/log stream. The verifier resolves scorer names→UUIDs via `Scorers().list()` and reports `unverifiable` if no matching scorer produced values. If validation comes back `unverifiable`, the user must enable a PII scorer in Galileo — the same enablement step required for other scorers. Documented in the caption and this entry.
- **V2 cart pre-check:** `store_client.py` `place_order()` now calls `get_cart()` before `POST /api/checkout` and raises `StoreError` if the cart is empty. This catches the empty-cart condition early with a clear error message rather than silently posting an empty checkout. The `add_to_cart` tool now warns if the cart appears empty after the add call. The checkout tool docstring clarifies the cart-non-empty prerequisite.
- **V2 drive_prompt:** Strengthened to explicitly number the steps: "(1) search for it in the catalog to get the product id and price, (2) add it to my cart using the product id you found, (3) check out to complete my purchase." This increases reliability of the search→add→checkout sequence across different model sizes/providers.
- **Trigger set preserved:** Still exactly 4 types (feature_flag, rag_corpus, tool_fault, prompt_overlay). No 5th type added.

**Effect on codebase / UX:** `control_plane/verification/galileo_verifier.py` (added `pii_exposed` signal, narrowed `prompt_injection_detected`, updated docstring table+note). `scenarios/firewall/scenario.yaml` (signal→`pii_exposed`, header comment reframed). `scenarios/firewall/captions/firewall.md` (full rewrite for PII-detection narrative). `agent/store_client.py` (`place_order` cart pre-check). `agent/tools.py` (`add_to_cart` empty-cart warning, `checkout` docstring). `scenarios/compounding-error/scenario.yaml` (drive_prompt numbered steps). `scenarios/compounding-error/captions/compounding-error.md` (updated prompt+card). No commit made; plan checkboxes untouched.

---

## 2026-06-19 — Subagent model selection rule

**What:** Added `.cursor/rules/subagent-models.mdc`, an `alwaysApply` governance rule that maps each subagent type to an explicit model slug. Updated `AGENTS.md` (principle #6) and `CHANGELOG.md`.

**Why:** In Cursor's multitask mode, subagents inherit the parent model by default. This means `composer-2.5-fast` is never chosen for cheap read-only work, and `gpt-5.3-codex` (the dedicated coding model) is never chosen for code generation unless explicitly set. Without a standing rule, each session falls back to the expensive parent model for all subtasks.

**Decisions / trade-offs:**
- Mapped `explore` and `shell` subagents to `composer-2.5-fast` — these tasks are read-only or command-running and do not need reasoning depth.
- Mapped code-writing `generalPurpose` subagents to `gpt-5.3-codex` — purpose-built, fast, and cheaper than large reasoning models for code.
- Mapped planning/analysis `generalPurpose` to `composer-2.5` (balanced) rather than a thinking model; complex architectural decisions can escalate to `claude-4.6-sonnet-medium-thinking` if needed.
- Kept `bugbot`/`security-review` on `claude-4.6-opus-max` — correctness and depth matter more than cost for security-sensitive work.
- Added an explicit escalation note: if a subagent returns incomplete output, re-run one tier higher and document it here.

**Effect on codebase / UX:** Governance-only change. No production code altered. Future agents will set `model` on every `Task` call, reducing cost and latency for the majority of subtasks.

---

## 2026-06-19 — Subagent worktree isolation rule + model-roster maintenance

**What:** Added `.cursor/rules/subagent-worktrees.mdc` to enforce worktree isolation for parallel writing subagents. Updated `subagent-models.mdc` with a _Last verified_ date and a self-check maintenance instruction. Updated `AGENTS.md` (principle #7) and `CHANGELOG.md`.

**Why:** Two related problems: (1) parallel `generalPurpose` subagents share the working tree — concurrent writes to overlapping files corrupt state and force the coordinator to manually track which files each subagent may touch. (2) The model roster in `subagent-models.mdc` is sourced from Cursor's system prompt, not the repo, so it silently drifts as Cursor releases new models. Neither problem was addressed by the existing rules.

**Decisions / trade-offs:**
- Chose `best-of-n-runner` as the worktree primitive rather than asking agents to manually run `git worktree add`. `best-of-n-runner` is the only subagent type Cursor provides that automatically provisions an isolated branch + working directory. Using it means zero setup overhead and a clean branch per task that the coordinator can review and merge.
- The decision rule is kept simple and binary: single writer → `generalPurpose` is fine; multiple concurrent writers → `best-of-n-runner` for each. A more granular rule (e.g. based on file-overlap analysis) would be harder to follow and rarely worth it.
- The model-roster maintenance instruction is placed inside `subagent-models.mdc` itself rather than a separate rule, so it fires in the same context where the roster is used. The instruction directs agents to cross-check against their own system prompt and update the file if it drifts — making the rule self-healing rather than requiring a human to notice staleness.

**Effect on codebase / UX:** Governance-only. No production code altered. Parallel agent work will now run in isolated branches, eliminating write collisions. The model roster will be kept fresh by agents that read the rule.


## 2026-06-19 — Galileo telemetry fix, concierge UI polish, and storefront cart sharing

**What:** Three post-Phase-7 hardening threads on the concierge web app: (1) fixed containerized Galileo telemetry so interactions upload per turn; (2) restyled the chat frontend to match the Astronomy Shop and tightened input UX; (3) bridged the storefront's shopper id into the concierge so the cart is shared across the `:8080` storefront and `:8090` concierge tabs. No core agent logic changed beyond the additive `StoreClient.user_id` seam.

**Why:** Live testing of the Phase-7 concierge surfaced gaps the static/integration checks could not: Galileo showed no traces from the container, the chat looked disjoint from the shop, and a cart built in the concierge was invisible in the storefront (and vice-versa) — undermining the co-shopping story.

**Decisions / trade-offs:**
- **Galileo root cause = env propagation, not flushing alone.** docker compose resolves `${GALILEO_*}` from the shell, not the demo's auto-loaded `.env`, so `concierge-web` booted unconfigured. Fixed in `scripts/stage-up.sh` by exporting the concierge/Galileo/model vars before `docker compose up`. Galileo is OPTIONAL, so an empty `GALILEO_API_KEY` warns rather than fails; only `SPLUNK_*` stays required. Added per-turn `flush_galileo()` in the long-lived web service (callback-mode buffers otherwise wait for process exit) plus a `load_dotenv()` host-path safety net. The Splunk OTLP path was never broken and was left untouched.
- **Cart identity decoupled from telemetry identity.** Rather than reuse `session_id` for the cart, `StoreClient` gained a separate `user_id` (defaulting to `session_id` so CLI callers are unchanged). This lets the cart follow the shopper across origins while Galileo/OTel session grouping stays keyed on the conversation.
- **Reversed the "Envoy injection out of scope" stance.** Cart sharing genuinely requires reading the storefront's per-origin `localStorage` shopper id, which only a script on the storefront's own origin can do. The id is mirrored into a port-agnostic `concierge_session` cookie on `localhost`. The injection is a tracked Envoy template override bind-mounted at runtime — the gitignored vendored clone is never edited in place. No secrets cross the bridge (the shopper id is a non-sensitive demo UUID the storefront already exposes client-side).

**Effect on codebase / UX:** `scripts/stage-up.sh` (env export), `agent/telemetry.py` (`flush_galileo`), `agent/store_client.py` (`user_id`), `web/concierge/**` (per-turn flush, `cart_user_id` threading, `/images` mount, restyle, Enter-to-send), new tracked `stage/splunk-otel/frontend-proxy/envoy.tmpl.yaml` + `web/concierge/embed/concierge-bridge.js`, and the `frontend-proxy` block in `stage/splunk-otel/docker-compose.override.yml`. Verified live: Galileo uploads per interaction (Splunk unchanged) and the cart is shared across the storefront and concierge tabs.

---

## 2026-06-19 — Web-first docs refresh + model roster update

**What:** Updated the operator-facing docs to make web interfaces the explicit primary path, with CLI usage clearly framed as fallback-only, and reconciled bring-up/teardown language to the current orchestration contract. Also updated `.cursor/rules/subagent-models.mdc` to include newly available model slugs.

**Why:** The owner requested a clearer, authoritative startup walkthrough centered on the three browser surfaces, plus strict consistency between `README.md`, `docs/runbook.md`, and the stage orchestration contract (`stage-up` starts storefront + concierge + SE console; `stage-down` stops the full stack including the SE console). The model roster update is mandated by the rule's maintenance clause when new valid slugs appear.

**Decisions / trade-offs:**
- Kept README's required section structure while replacing casual usage framing with an imperative startup sequence and a prominent primary interface map.
- Limited runbook edits to bring-up/interface reconciliation only (no broad rewrite), preserving the existing vignette guidance.
- Added the four new model slugs to the roster table with concise strength/cost descriptors; retained all existing rows and the same verification date.

**Effect on codebase / UX:** Updated only `README.md`, `docs/runbook.md`, `CHANGELOG.md`, `docs/agent-journal.md`, and `.cursor/rules/subagent-models.mdc`. Operators now get an unambiguous web-first startup flow and consistent URLs across docs; model-selection governance now reflects current available subagent models.

---

## 2026-06-19 — Control-plane UX: ordered scenarios, clickable playlist, script new-tab view

**What:** Implemented three SE-requested control-plane UX updates: declarative run-order support in scenario manifests, clickable scenario selection in the playlist composer, and standalone talk-track pages opened in a new tab. Verified imports, CLI listing, and ephemeral HTTP endpoints.

**Why:** The SE runbook expects a specific play sequence and a low-friction operator flow. Alphabetical listing, typed playlist filters, and modal script rendering added avoidable operator friction during live demos.

**Decisions / trade-offs:**
- Added optional `order` to `scenario.yaml` manifests and sorted centrally in `control_plane.registry` by `(order is None, order, title)` so all consumers (`/api/list`, CLI `list`, and playlist defaults) agree without duplicating sort logic.
- Added `order: 1..4` only to the four core vignettes; stub fixtures remain unordered and therefore naturally sort after ordered scenarios.
- Changed playlist composition to accept explicit `ids` (plus optional `budget`) and updated the web UI to render toggleable scenario chips from `/api/list` non-fixture scenarios; this avoids free-text parsing and preserves operator-selected scope.
- Added `GET /scenarios/{scenario_id}/script.html` to serve a standalone, copy-friendly HTML document derived from existing markdown rendering; switched the scenario "View Demo Script" action to `window.open(..., "_blank", "noopener")`. Kept the existing "Copy prompt" behavior unchanged.

**Effect on codebase / UX:** Updated `control_plane/manifest.py`, `control_plane/registry.py`, `web/control_plane/app.py`, `web/control_plane/static/app.js`, `web/control_plane/templates/index.html`, `web/control_plane/static/styles.css`, and the four core scenario manifests. Both CLI and web now present the preferred scenario order; playlist selection is fully clickable; demo scripts open in a separate tab for easy selection/copy.
