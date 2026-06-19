# Implementation Plan — Galileo × Splunk Observability Demo

> Status: **Phases 0–4 built; Phase 5 (Core-4 vignettes) committed; Phase 7 web UIs
> implemented (static/integration-verified, live clean-room sign-off pending).** Source of
> truth for *what to build* is [`docs/demo-design.md`](demo-design.md); this document sequences
> *how and in what order* we build it. Phase 6 (delivery & polish) and the Phase 7.5 live
> clean-room verification remain outstanding.

## How to read this

- Phases are **dependency-ordered**; later phases assume earlier ones are complete (see
  [Dependencies](#sequencing--effort) for what can run in parallel).
- Every phase has **Exit criteria** that are *verifiable*, per the repo
  [`automate-verify`](../.cursor/rules/automate-verify.mdc) rule: work is not "done" until it has
  been run and checked.
- Limitations referenced by ID (**L1**, **L2**) and gates map to `docs/demo-design.md` §9.
- The **first end-to-end deliverable** is the scenario harness + one reference vignette
  (design §7.5), reached at the end of **Phase 4**.

---

## Phase 0 — Foundations & prerequisites

**Goal:** Everything needed to start building exists and is decided: accounts, secrets scaffolding,
repo structure, and the core tech-stack decisions — *without* writing app code.

**Tasks**
- [ ] Confirm **enterprise Galileo access** and capture the API key out-of-band. Enterprise unlocks
      Luna-2, real-time guardrails, Agent Control, self-hosting, and **unlimited traces** (no 5k cap)
      (design §9.2).
- [ ] Create a **Splunk Observability Cloud trial**; capture the **access token** and **realm**.
- [ ] Sign up / confirm an **OpenAI API key** (for the EC2 runtime) and confirm **Ollama** install
      path for the Apple-silicon runtime.
- [ ] Add secrets scaffolding: a gitignored `.env` and a committed **`.env.example`** with
      placeholder keys only (`GALILEO_API_KEY`, `SPLUNK_ACCESS_TOKEN`, `SPLUNK_REALM`,
      `OPENAI_API_KEY`, `OLLAMA_HOST`, `MODEL_PROVIDER`). **No hardcoded credentials**
      (rule `codeguard-1-hardcoded-credentials`; design §8.5). Confirm `.env` is in `.gitignore`.
- [ ] Define the **repo structure** (proposed): `agent/` (concierge), `stage/` (forked OTel demo /
      compose overrides), `scenarios/` (drop-in vignettes), `control_plane/` (SE CLI/panel),
      `scripts/` (automation/verification), `docs/`.
- [ ] Decide Python toolchain (Python 3.12+, dependency manager e.g. `uv`/`poetry`) and pin it.

**Decided tech stack (D1, D6 — see Decisions table)**

The agent framework and provider abstraction are **decided**, not open:

| Decision | Outcome | Tie-in |
|---|---|---|
| **Agent framework = LangGraph** | Matches Galileo's first-party examples | Galileo `sdk-examples` + the `langgraph-open-telemetry` example |
| | Graph model fits the multi-step cascade story | Powers the "Compounding Error" vignette (Graph Engine, design §6 V2) |
| | Native OTel GenAI instrumentation path | The single-instrument / dual-fanout keystone (design §3) |
| | Clean provider swap via LangChain chat models | Enables D6 below |
| **Provider abstraction = LangChain chat-model interface** | `MODEL_PROVIDER=ollama\|openai` switch (`ChatOllama` vs `ChatOpenAI`) | Mirrors Galileo's `sdk-examples` `openai-ollama` variant (design §8.2); follows from D1 |

**Deliverables:** provider accounts + captured secrets (out of band), `.env.example`, `.gitignore`
confirmed, agreed repo skeleton (directories only). Framework (LangGraph) and provider abstraction
decisions are settled (recorded here and in the journal).

**Exit criteria / acceptance**
- `cp .env.example .env` works and lists every required key; `git status` shows `.env` ignored.
- A trivial connectivity check (manual is acceptable this phase) confirms each account/token is
  valid: Galileo project reachable, Splunk realm/token accepted, OpenAI key authorizes, `ollama`
  responds locally.

**Dependencies:** none (entry point).

**Blockers (the only real Phase-0 blockers):**
- Obtaining provider accounts/tokens: **Galileo enterprise** access, **Splunk** trial, and an
  **OpenAI key** / **Ollama** install. (Framework and Galileo-Pro questions are no longer blockers —
  D1 is decided and enterprise access removes the Pro purchase.)

**Risks/limitations**
- **L2 / Beta:** Galileo distributed tracing is Beta — expect rough edges. (Enterprise provides OTLP
  ingest, so the earlier "does the free Developer tier expose OTLP?" risk no longer blocks the
  dual-fan-out design.)
- Theme is **decided** (design §9.5: keep Astronomy Shop, no reskin) — not a blocker.

---

## Phase 1 — Stand up the stage

**Goal:** The forked Astronomy Shop runs locally and its **infrastructure** telemetry flows to
Splunk Observability Cloud over OTLP.

**Tasks**
- [ ] Fork / vendor **`splunk/opentelemetry-demo`** (Astronomy Shop) into `stage/` (design §4).
- [ ] Run it locally via **docker-compose**; confirm the storefront + load generator + feature-flag
      service are up.
- [ ] Configure the **Splunk Distribution of the OpenTelemetry Collector**: OTLP in →
      Splunk Observability out. **OTLP only — do NOT use the deprecated `sapm` exporter**
      (design §3, §9.3).
- [ ] Inject `SPLUNK_ACCESS_TOKEN` / `SPLUNK_REALM` via env only.
- [ ] Decide minimal vs full stack to control RAM (design §8.4: ~6 GB full / ~3 GB minimal,
      ~14 GB disk).

**Deliverables:** runnable `stage/` compose, collector config (OTLP→Splunk), a documented
`make stage-up` / script entry.

**Exit criteria / acceptance**
- Store loads locally and load generator produces traffic.
- **Splunk APM shows the store's services, service map, and traces** within expected ingestion lag.
- Collector logs show OTLP export success and **zero `sapm` usage**.
- A `scripts/` smoke check (curl storefront + assert collector healthy) passes.

**Dependencies:** Phase 0 (Splunk token/realm, repo structure).

**Risks/limitations**
- Resourcing (design §8.4): on 16 GB Macs prefer minimal mode; **don't run Ollama in Docker on
  macOS** (loses Metal — but that's a Phase 2 concern).
- **L2:** ingestion latency — don't treat "not visible yet" as failure; allow warm-up.

---

## Phase 2 — The concierge agent (MVP, no scenarios yet)

**Goal:** A working Python AI shopping concierge that answers (RAG) and acts (tools = store APIs),
instrumented **once** with OTel GenAI and fanned out to **both** Galileo and Splunk.

**Tasks**
- [ ] Scaffold the **Python concierge** service in `agent/` (framework per Phase 0 decision).
- [ ] Implement the **model-provider abstraction**: `MODEL_PROVIDER=ollama` (Apple-silicon, native
      Ollama) | `MODEL_PROVIDER=openai` (EC2), with provider config (`OLLAMA_HOST`/model name or
      `OPENAI_API_KEY`) (design §8.1–8.2).
- [ ] Implement **RAG** over a product catalog + policy docs (capability (a), design §4).
- [ ] Implement **tools** that call the store's existing microservice APIs (capability (b)).
- [ ] **Instrument once** with OTel GenAI semantic conventions; configure **dual export**:
      Galileo (`GalileoSpanProcessor`/OTLP) **and** Splunk (via the Phase-1 collector) (design §3).
- [ ] Wire Sessions→Traces→Spans naming so a conversation is legible in Galileo.

**Deliverables:** runnable concierge, provider abstraction, RAG corpus loader, tool adapters,
single-instrument/dual-fanout telemetry config.

**Exit criteria / acceptance**
- A **normal conversation** produces clean **Sessions → Traces → Spans in Galileo** AND
  corresponding **traces in Splunk** (this is design Vignette 0 / baseline).
- Switching `MODEL_PROVIDER` between `ollama` and `openai` works with no code change.
- A `scripts/` check drives a scripted prompt and asserts spans land in both backends.

**Dependencies:** Phase 0 (keys, framework), Phase 1 (store APIs + collector to fan out to).

**Risks/limitations**
- **L2 / Beta:** Galileo OTel tracing Beta — expect rough edges in span linkage; verify early.
- Theme is **decided** (design §9.5: keep Astronomy Shop, no reskin) — concierge copy can target it
  directly; enterprise access means **no trace-cap** concern on baseline runs.

---

## Phase 3 — The scenario harness (the extensibility core)

**Goal:** The stable extensibility machinery so vignettes are **drop-in folders, never core edits**
(design §7).

**Tasks**
- [ ] Build the **scenario registry** that auto-discovers `scenarios/*/scenario.yaml` (design §7.2).
- [ ] Implement the **declarative manifest** contract exactly as design §7.1 (`id`, `title`,
      `message`, `duration_min`, `trigger`, `expected_signals`, `talk_track`, `reset`).
- [ ] Implement the **pluggable trigger layer** — the four **fixed** mechanisms (design §7.3):
      `feature_flag | rag_corpus | tool_fault | prompt_overlay`.
- [ ] Implement a **reset mechanism** (per-scenario `reset.sh` contract).
- [ ] Build a **minimal SE control plane** (CLI first; simple panel optional): list / play / reset /
      compose **playlists** keyed by `message`/`duration` (design §7.2).
- [ ] Implement the **`expected_signals` auto-verification hook**: assert promised Galileo + Splunk
      signals actually fire (design §7.4; ties to `automate-verify`).

**Deliverables:** registry, manifest schema + loader, four trigger implementations, reset contract,
SE CLI/control plane, verification harness.

**Exit criteria / acceptance**
- Dropping an empty/stub scenario folder makes it appear in the control plane **without core edits**
  (proves the stable seam, design §7.2).
- Each trigger type can be invoked and reset from the control plane.
- The verification hook can read a manifest's `expected_signals` and produce a pass/fail report
  (validated against a stub in Phase 4).

**Dependencies:** Phase 2 (agent + fan-out are the things scenarios manipulate and verify).

**Risks/limitations**
- Verification depends on **queryable** Galileo/Splunk signals; **L2** ingestion latency means the
  hook needs polling/retry with timeouts, not instant assertion.
- Keep trigger set **fixed** — scope creep here erodes the "drop-in folder" guarantee.

---

## Phase 4 — Reference vignette end-to-end

**Goal:** Prove the whole loop and the harness contract by shipping **Vignette 1 — "The Invisible
Failure"** (design §6, cleanest punchline).

**Tasks**
- [ ] Author `scenarios/invisible-failure/` with `scenario.yaml` per design §7.1.
- [ ] Trigger: `feature_flag` → **stale product-catalog data** (`productCatalogStaleData`).
- [ ] Confirm Galileo signals: **Context Adherence drops** + **ungrounded claim pinpointed**.
- [ ] Confirm Splunk backdrop: **APM dashboards stay GREEN** (the punchline assertion).
- [ ] Wire `expected_signals`: `galileo: [context_adherence_low, ungrounded_claim]`,
      `splunk: [apm_all_green]` and make the Phase-3 hook assert them.
- [ ] Author the talk-track caption file and a **`reset.sh`**.

**Deliverables:** complete first vignette folder, passing auto-verification, talk-track + reset.

**Exit criteria / acceptance** *(this is the design §7.5 "first implementation deliverable")*
- From the control plane: **play** the vignette → Galileo shows the groundedness drop + ungrounded
  claim; **Splunk APM stays green**; **reset** restores baseline.
- `expected_signals` **auto-verification passes** (no manual signal-spotting required).
- Runs in **both** runtimes (Ollama laptop, OpenAI — EC2 validated in Phase 5 if not already).

**Dependencies:** Phases 1–3.

**Risks/limitations**
- **L1 (nondeterminism):** rely on the **induced** feature-flag fault + seeded corpus, plus an SE
  **"known-good prompt" card**, not luck.
- **L2:** pre-warm dashboards before the reveal so the green/anomaly contrast is visible on cue.

---

## Phase 5 — Remaining core vignettes

**Goal:** Complete the **Core 4** and (optionally) the warm-up and pre-prod gate.

**Tasks**
- [ ] **Vignette 2 — "The Compounding Error"** (design §6): trigger via constrained tools /
      **flaky checkout service** (`tool_fault`). Galileo: **Graph Engine** cascade, **Tool Selection
      Quality**, **Insights Engine** loop-clustering. Splunk: latency/cost spike, service map, trace
      waterfall.
- [ ] **Vignette 3 — "The Firewall"** (design §6): trigger via **poisoned product review (prompt
      injection)** / **PII in a reply** (`prompt_overlay`). **Real-time Luna-2 guardrails block
      before the agent acts** — low-latency, available with enterprise access (design §9.2); no
      Pro-tier purchase or LLM-as-judge-latency caveat.
- [ ] **Vignette 4 — "Trust the Judge"** (eval-accuracy contrast, design §6): trigger via a
      **curated eval set with known ground truth**. A naive single **LLM-as-judge mislabels ~1 in 3**
      cases, while Galileo's **Luna-2 / consensus evaluators agree with ground truth**. Galileo hero
      moment is the side-by-side disagreement. (Unlocked by enterprise Luna-2 access.)
- [ ] *(Optional)* **Vignette 0 — Baseline** warm-up folder for a clean opener.
- [ ] *(Optional)* **Vignette 5 — Pre-Production Gate**: Galileo **Experiments** catch an offline
      regression.
- [ ] Each vignette: `scenario.yaml` + `expected_signals` + talk-track + `reset.sh`; all
      auto-verified.

**Deliverables:** Vignettes 2, 3 & 4 (core) complete and verified; optional vignettes as time allows.

**Exit criteria / acceptance**
- Each new vignette is **drop-in** (no core edits) and its `expected_signals` **auto-verify**.
- Core 4 all playable + resettable from the control plane in both runtimes.

**Dependencies:** Phase 4 (proves the contract). No external tier dependency — enterprise access
covers Luna-2 (V4) and real-time guardrails (V3).

**Risks/limitations**
- **L1/L2** apply per vignette (known-good prompts, pre-warmed dashboards).

---

## Phase 6 — Demo delivery & polish

**Goal:** Make the demo **SE-runnable and resilient** to the validated limitations.

**Tasks**
- [ ] Author **talk-track captions** per vignette (including the **eval-accuracy** thread woven
      through every vignette, and the dedicated **Trust the Judge** vignette caption, design §6).
- [ ] Build **pre-built dashboards** (Galileo + Splunk) and a **dashboard pre-warming** step
      (mitigates **L2** ingestion latency).
- [ ] Write the **SE runbook** (setup, play order, reset, recovery).
- [ ] Ship **"known-good prompt" cards** per vignette (mitigates **L1** nondeterminism, design §9.1).
- [ ] **Backfill `README.md`** Installation + Example usage once the harness runs (design §10.9;
      required by the `readme` rule).

**Deliverables:** captions, dashboards + pre-warm script, runbook, prompt cards, README backfill.

**Exit criteria / acceptance**
- A cold SE can run the **Core 4** end-to-end from the runbook + control plane in **both** runtimes.
- Pre-warm script leaves dashboards populated before the reveal.
- `README.md` Installation + Example usage are accurate and tested from zero.

**Dependencies:** Phase 5 (content to caption/dashboard).

**Risks/limitations**
- **Eval-accuracy is now a live vignette** (design §9.4, V4 — Trust the Judge via Luna-2); it is no
  longer a known weak spot to dramatize via talk-track only.
- **L2/Beta** can still surprise live; rehearse with pre-warming.

---

## Phase 7 — Web interfaces

> Added after the user confirmed and directed the Phase-7 build. The **detailed spec, options,
> tradeoffs, and signed-off decisions (W1–W8)** live in
> [`docs/web-interface-plan.md`](web-interface-plan.md); this section is the implementation-plan
> summary and exit gate.

**Goal:** Augment the project's two CLIs with browser surfaces — a shopper-facing **Astronomy
Concierge** chat app and a localhost-only **control-plane web UI** — built as **thin web layers over
the unchanged `agent/` and `control_plane/` cores**, preserving the single-instrument →
dual-fan-out telemetry keystone (design §3), the drop-in scenario seam (design §7), and the CLIs as
supported fallbacks (W5).

**Two slices (independently parallelizable):**

- **Concierge slice (7.1–7.3):** a FastAPI service (`web/concierge/`) exposing `POST /chat`,
  `GET /chat/stream` (SSE), `/healthz`, and an optional localhost `POST /admin/reload`;
  `setup_telemetry()` once at boot; per-session graph build via `overlay.py`; `gen_ai.conversation.id`
  set per conversation; a **standalone React/Vite frontend** served by a tracked `concierge-web`
  container in the compose override (containerized only, Ollama native via `host.docker.internal`,
  W2); per-session trigger hot-reload with `agent/rag.py` `clear_corpus_cache()` (W3). The optional
  Envoy `<script>` storefront injection (W1) is **out of scope** as a later optional enhancement.
  A Phase-7.1 spike found and resolved a **Galileo callback-mode concurrency hazard** (shared
  `GalileoLogger` + process-global `start_session`) by serializing graph execution behind a global
  async lock only in callback mode.
- **Control-plane slice (7.4):** a FastAPI layer (`web/control_plane/`) — REST `list/play/reset/
  playlist` + `verify`, SSE `play`/`verify` streams with a live log pane — thin over
  `registry.discover()` / `apply_trigger` / `reset_trigger` / `run_verification` (internals
  unchanged). **Loopback-only bind enforced**; CSRF + CSP + security headers + secret redaction.

**Phase 7.5 — live clean-room sign-off (the exit gate):** stage up + Ollama + `concierge-web`
healthy in a browser; multi-turn chat; concurrent-session Galileo isolation; trigger hot-reload via
a fresh session; telemetry parity (`gen_ai.*` spans + GenAI histograms) in Splunk AI Agent
Monitoring and Galileo; CLIs still work as fallbacks. The full README Installation/Example-usage
backfill is gated on this proof.

**Status (2026-06-19):** Phases **7.0–7.4 implemented and static/integration-verified** by two
parallel coding subagents (deps install; both apps boot — concierge `/healthz`=200, control-plane
`/api/list`=200; loopback guard accepts loopback / rejects `0.0.0.0`; registry discovers all 8
scenarios with no core edits; compose override merges with `concierge-web`; frontend `dist`
builds). **Phase 7.5 (live clean-room sign-off) is PENDING.**

**Exit criteria / acceptance:** the Phase-7.5 clean-room proof above passes from a fresh clone +
`.env` via the documented scripts (`scripts/concierge-serve.sh`, `scripts/control-plane-web.sh`),
with both CLIs still functional.

**Dependencies:** Phase 2 (concierge slice) and Phase 3 (control-plane slice).

**Risks/limitations:** Galileo multi-session concurrency (mitigated, see above); reproducibility /
telemetry regression (reuse `telemetry.py` verbatim; all new pieces tracked outside the clone);
control-plane exposure (hard loopback bind). See [`docs/web-interface-plan.md`](web-interface-plan.md) §12.

---

## Decisions (status)

| # | Decision | Status | Outcome |
|---|---|---|---|
| D1 | **Agent framework** | ✅ **DECIDED** | **LangGraph** — matches Galileo `sdk-examples` (incl. `langgraph-open-telemetry`); best fit for the Graph Engine cascade ("Compounding Error"); clean provider-swap via LangChain chat models |
| D2 | **Theme**: keep space/astronomy vs neutral reskin (§9.5) | ✅ **DECIDED** | **Keep the Astronomy Shop theme as-is — no reskin** |
| D3 | **EC2 instance size** (§8.4) | ⏳ **DEFERRED to a Phase-1 empirical spike** | Starting assumption: `t3.xlarge`-class (16 GB / 4 vCPU). EC2 uses OpenAI (API), so **no local GPU needed** — only the docker-compose stack (~6 GB) + the agent. Validate by measurement, not fiat |
| D4 | **Eval-accuracy pillar** (§6, §9.4) | ✅ **DECIDED** | **Promoted to a real, live vignette** — "Trust the Judge" contrast (naive LLM-judge wrong ~1 in 3 vs. Luna-2 / consensus evaluators), unlocked by enterprise Luna-2. No longer talk-track-only |
| D5 | **Galileo Pro** purchase | ⛔ **MOOT — removed** | Covered by enterprise access; no Pro purchase needed |
| D6 | **Provider abstraction** (§8.2) | ✅ **DECIDED** | **LangChain chat-model interface** behind `MODEL_PROVIDER=ollama\|openai` (`ChatOllama` vs `ChatOpenAI`); follows from D1 |
| W1–W8 | **Web interface decisions** (Phase 7) | ✅ **DECIDED** (signed off 2026-06-18) | Standalone "Astronomy Concierge" app first / Envoy injection optional-out-of-scope (W1); containerized-only, Ollama native (W2); per-session overlay read + `rag` cache invalidation (W3); FastAPI + lightweight frontend (W4); keep both CLIs as fallbacks (W5); separate loopback-bound control-plane process (W6); two separately-sequenced slices (W7); SSE streaming (W8). Full detail in [`docs/web-interface-plan.md`](web-interface-plan.md) §11/§14 |

---

## Sequencing & effort

**Critical path (must be serial):**

```
Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4 (first end-to-end deliverable) → Phase 5 → Phase 6
                         └─────────────────────┴──▶ Phase 7 (web interfaces: concierge slice after Phase 2, control-plane slice after Phase 3)
```

Phase 7 is **not** on the Core-4 critical path: its concierge slice depends only on Phase 2 and its
control-plane slice only on Phase 3, so it can proceed in parallel with Phases 4–6 (see
[`docs/web-interface-plan.md`](web-interface-plan.md) §9).

**Can proceed in parallel (off the critical path):**

| Parallel track | Can start after | Runs alongside |
|---|---|---|
| RAG content authoring (catalog + policy docs) | Phase 0 | Phase 1 collector wiring |
| Splunk collector wiring + dashboard scaffolding | Phase 0 | Phase 2 agent build |
| Talk-track / caption drafting | Phase 0 (design is fixed) | Phases 2–5 |
| Provider-account validation | Phase 0 | Phases 1–4 |
| **EC2 sizing empirical spike (D3)** | Phase 1 | Phases 1–4 (measure stack RAM; OpenAI offloads the LLM, so no GPU) |
| `scripts/` verification utilities | Phase 2 | Phase 3 harness |

**Effort signal (relative):** Phases 2 and 3 are the heaviest (agent + dual-fanout; harness +
verification). Phase 4 is integration-heavy but small in new code. Phases 5–6 are largely
incremental (drop-in folders + content) by design.

---

## Git hygiene

Per [`.cursor/rules/git-hygiene.mdc`](../.cursor/rules/git-hygiene.mdc):

- **One feature branch per phase**, named `feat/<slug>` — e.g. `feat/stage-otel-demo`,
  `feat/concierge-mvp`, `feat/scenario-harness`, `feat/vignette-invisible-failure`.
- `main` stays releasable; merge each phase back once stable; avoid long-lived branches.
- **Commits only when the user explicitly asks**; pushes only when the user explicitly asks.
- Conventional commit types (`feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `ci`).

---

## Milestone — first definition of "demo-ready"

> **Demo-ready (v1):** the **Core 4 vignettes** — *The Invisible Failure*, *The Compounding Error*,
> *The Firewall*, and *Trust the Judge* (eval-accuracy contrast) — are **runnable and resettable
> from the SE control plane**, each with **auto-verified `expected_signals`**, in **both runtime
> environments** (Apple-silicon/Ollama and EC2/OpenAI), with **pre-warmed dashboards** and a
> **known-good prompt card** per vignette.

This milestone is reached when **Phase 5 (Core 4)** is complete and the **Phase 6** delivery aids
needed to run them reliably (runbook, pre-warm, prompt cards) are in place.
