# Demo Environment Design — Galileo × Splunk Observability

> Status: **Agreed design / pre-implementation.** This document is the starting point for an
> implementation plan. It describes *what* we are building and *why*; it does not yet prescribe
> the full implementation detail. No application code exists yet.

---

## 1. Goal & concept

Build a best-in-class AI-agent demo environment that **(re)plays common agent scenarios** to
demonstrate two products working together:

- **Galileo AI — the hero.** The AI/agent intelligence layer: reasoning quality, evaluation,
  guardrails.
- **Splunk Observability — the operational backdrop.** The systems/infrastructure layer:
  services, traces, metrics, logs, and cost.

**Context.** Cisco owns Splunk and has acquired Galileo. Splunk Observability's *AI Agent
Monitoring* is being superseded by Galileo's functionality. This gives us clean, non-overlapping
roles for the two products and lets the demo double as a **preview of the integrated Cisco
story**.

| | Galileo (hero) | Splunk Observability (backdrop) |
|---|---|---|
| **Layer** | AI / agent intelligence | Systems / infrastructure |
| **Answers** | *Is the agent reasoning well?* | *Is the system healthy?* |
| **Surfaces** | Reasoning quality, evaluation, guardrails | Services, traces, metrics, logs, cost |
| **Models** | Sessions → Traces → Spans (+ AI metrics) | Service map, traces, metrics, logs |

- **Audience:** prospective customers; SE-led guided demos.
- **Backends:** **real SaaS** — Galileo SaaS + Splunk Observability Cloud. **Live LLM calls.**

---

## 2. Framing & roles (the wedge)

Galileo is positioned as **the trust layer for probabilistic GenAI**. The reason a separate trust
layer is needed — i.e. why traditional APM is not enough — is the wedge of the whole demo:

- **Failures are soft.** No crash, no error, no stack trace — just *degraded quality* (a wrong or
  ungrounded answer). APM stays green.
- **Errors compound.** In multi-step agents, one early bad step cascades into later steps.
- **APM is content-blind.** It tells you nothing about the *contents* of a response.

AI observability closes that gap by **capturing every reasoning step** (tool calls, retrieval),
modelling **Sessions → Traces → Spans**, and **enriching with AI metrics** (safety scores,
LLM-as-judge evaluations).

### Galileo's three reliability pillars

| Pillar | One-liner | How the demo proves it |
|---|---|---|
| **1. Eval accuracy** | "1 in 3 evals are wrong" | Vignette 4 — Trust the Judge (live contrast: naive LLM-judge vs. Galileo Luna-2 / consensus evaluators) — plus talk-track woven through every vignette |
| **2. Observability oversight** | "Can't measure what you can't see" | Vignette 1 — The Invisible Failure |
| **3. Guardrail control** | "Can't govern without accurate coverage" | Vignette 3 — The Firewall |

---

## 3. The technical keystone

Both Splunk and Galileo consume **OpenTelemetry GenAI semantic conventions**. The keystone of the
whole architecture follows directly:

> **Instrument the agent ONCE with OTel GenAI, then fan the same telemetry out to BOTH backends.**

```
                                  ┌──────────────────────────────┐
                                  │  Galileo SaaS (AI layer)     │
                          OTLP ──▶│  GalileoSpanProcessor / OTLP │
                          │       └──────────────────────────────┘
  ┌───────────────────┐   │
  │  Python AI agent  │───┤
  │  (OTel GenAI      │   │
  │   instrumented    │   │       ┌──────────────────────────────┐
  │   ONCE)           │   └─OTLP─▶│  Splunk Distribution of the  │
  └───────────────────┘           │  OTel Collector ──▶ Splunk   │
                                  │  Observability Cloud (infra) │
                                  └──────────────────────────────┘
```

**Build constraints (firm):**

- **Transport: OTLP only.** Do **not** use the deprecated `sapm` exporter for Splunk.
- Splunk path goes through the **Splunk Distribution of the OpenTelemetry Collector** (OTLP in,
  Splunk Observability out).
- Galileo path uses Galileo's **`GalileoSpanProcessor` / OTLP** export.
- **Agent language: Python.** GenAI instrumentation maturity in other languages is unverified;
  do not assume parity.
- ⚠️ **Galileo's distributed / OTel tracing is Beta.** Expect rough edges and plan narrative
  pacing around ingestion behaviour (see §8, L2).

---

## 4. The stage (the app the agent lives in)

**Fork `splunk/opentelemetry-demo`** (Splunk's distribution of the upstream
[OpenTelemetry Demo](https://github.com/open-telemetry/opentelemetry-demo)) — the
**"Astronomy Shop"**, a fake telescope / astronomy e-commerce store:

- ~15–20 polyglot microservices, **fully pre-instrumented with OpenTelemetry**.
- Ships with a **load generator** and a **feature-flag service** for fault injection.

> **Important:** the Astronomy Shop is **not an AI app today and has no agent.** We add one. Its
> built-in fault injection breaks **services** (the Splunk layer). **Agent-level failures we induce
> ourselves** (the Galileo layer).

### What we add: ONE new Python service — the **AI shopping concierge**

The concierge has exactly two responsibilities, each chosen to expose a specific failure surface:

| Capability | What it does | Failure surface it exposes |
|---|---|---|
| **(a) Answers questions** | RAG over a product catalog + policy docs | **Hallucination / groundedness** |
| **(b) Takes actions** | Calls the store's existing microservice APIs as its **tools** | **Tool-selection / cost** |

**The bridge (why this design is powerful):** the agent's tool calls become **real calls into
Astronomy Shop services**. Injecting a backend fault via the demo's **feature flags** makes the
agent **receive bad data** — producing **correlated, two-lens incidents**: one lens in Splunk
(the service fault) and one lens in Galileo (the degraded reasoning that resulted).

---

## 5. Messaging spine

The narrative spine the vignettes dramatize (from stakeholder notes):

- **Galileo = the trust layer for probabilistic GenAI.**
- The three reliability pillars (§2): **eval accuracy**, **observability oversight**, **guardrail
  control**.
- The wedge vs. traditional APM: failures are **soft**, errors **compound**, APM is
  **content-blind**.
- AI observability **captures every reasoning step**, models **Sessions → Traces → Spans**, and
  **enriches with AI metrics** (safety, LLM-as-judge).

---

## 6. Vignette library

Each vignette dramatizes **one** message and is **reliably induced** (no reliance on luck — see
§8, L1).

| # | Vignette | Message it proves | Trigger (how we INDUCE it) | Galileo hero moment | Splunk backdrop |
|---|---|---|---|---|---|
| **0** | **Baseline — "it just works"** | Trust / what good looks like | Normal flow | Clean Sessions → Traces → Spans | All green |
| **1** | **The Invisible Failure** | Observability oversight / soft failure | Feature-flag **stale product-catalog data** | Context Adherence drops; ungrounded claim pinpointed | **APM dashboards GREEN** (the punchline) |
| **2** | **The Compounding Error** | Errors compound in multi-step agents | Constrain tools / **flaky checkout service** | Graph Engine shows early bad step cascading; Tool Selection Quality + Insights Engine loop-clustering | Latency/cost spike; service map; trace waterfall |
| **3** | **The Firewall** | Guardrail control | **Poisoned product review (prompt injection)** / **PII in a reply** | Real-time **Luna-2 guardrails block before the agent acts** (low-latency) | The blocked attempt's operational footprint |
| **4** | **Trust the Judge** | Eval accuracy ("1 in 3 evals are wrong") | Run a **curated eval set with known ground truth**; a naive single LLM-as-judge mislabels ~1 in 3 | **Luna-2 / consensus evaluators agree with ground truth** where the naive judge is wrong | n/a (eval layer) |
| **5** | **The Pre-Production Gate** *(optional)* | Dev-time challenges (manual evals & test-set pain) | Run an eval set before "deploy" | Galileo **Experiments** catch a regression offline | n/a (pre-prod) |

**Run structure:**

- **Core 4** = Invisible Failure, Compounding Error, Firewall, Trust the Judge.
- **Baseline** is the warm-up.
- **Pre-Production Gate** is optional.

### Special handling: the eval-accuracy pillar

**Eval accuracy ("1 in 3 evals are wrong") is now a live, demoable vignette** (Vignette 4 — Trust
the Judge), unlocked by enterprise access to **Luna-2 evaluators**. The vignette is a **contrast
scene**: against a **curated eval set with known ground truth**, a naive single LLM-as-judge
mislabels roughly **1 in 3** cases, while Galileo's **Luna-2 / consensus evaluators** agree with
ground truth. The eval-accuracy message also remains a **talk-track woven through every vignette**:
expand Galileo's metric explanations / consensus reasoning so the audience trusts **why** a metric
fired.

---

## 7. Extensibility architecture

**Principle:** the **agent + store + telemetry pipeline are STABLE infrastructure**; **vignettes
are pluggable data + small hooks**. Adding a vignette = **dropping in a folder, never editing
core.**

### 7.1 Scenario contract (declarative per-vignette manifest)

Each vignette ships a manifest that a registry auto-discovers. Illustrative example:

```yaml
# scenarios/invisible-failure/scenario.yaml
id: invisible-failure
title: "The Invisible Failure"
message: observability-oversight        # which pillar it proves (for SE playlists)
duration_min: 3
trigger:                                 # how we INDUCE it (no reliance on luck)
  type: feature_flag                     # feature_flag | rag_corpus | tool_fault | prompt_overlay
  ref: productCatalogStaleData
expected_signals:
  galileo: [context_adherence_low, ungrounded_claim]
  splunk:  [apm_all_green]               # the punchline assertion
talk_track: captions/invisible-failure.md
reset: scenarios/invisible-failure/reset.sh
```

### 7.2 Components

| Component | Responsibility |
|---|---|
| **Scenario registry** | Auto-lists drop-in folders under `scenarios/` in an SE control panel |
| **Pluggable trigger layer** | A small **fixed** set of mechanisms (below) |
| **Declarative `expected_signals`** | Auto-verification: each vignette asserts the Galileo/Splunk signals it promises actually fire |
| **Composable playlists** | Keyed by `message` / `duration` so the SE assembles a run per audience |
| **Stable seams** | Agent core, OTel fan-out, and control plane do not change when scenarios are added |

### 7.3 Fixed trigger mechanisms

| Trigger type | Induces a failure by… | Primary layer |
|---|---|---|
| `feature_flag` | Flipping a demo feature flag to break a backend service | Splunk (→ feeds bad data to agent) |
| `rag_corpus` | Swapping/seeding the RAG corpus (e.g. stale or poisoned docs) | Galileo (groundedness) |
| `tool_fault` | Constraining/faulting the agent's available tools | Galileo (tool selection) + Splunk |
| `prompt_overlay` | Injecting an SE-controlled prompt overlay (e.g. injection payload) | Galileo (guardrails) |

### 7.4 Verification (ties to the `automate-verify` rule)

`expected_signals` is **declarative on purpose**: it lets us **auto-verify** every vignette — i.e.
confirm the promised Galileo and Splunk signals actually fire — rather than discovering a dead
demo live. This is the concrete expression of the repo's **`automate-verify`** rule for this
project: a vignette is not "done" until its `expected_signals` are asserted by automation.

### 7.5 First implementation deliverable

> **The FIRST implementation deliverable is the scenario harness:**
> **agent + store + OTel fan-out + registry + ONE reference vignette end-to-end.**
> Every later vignette is incremental (drop-in folder, no core changes).

---

## 8. Runtime & environment

The demo must run in **two target environments** behind a **pluggable model provider**.

### 8.1 Environment matrix

| | (A) Apple-silicon laptop | (B) Amazon EC2 |
|---|---|---|
| **LLM** | **Ollama**, local models (offline-capable for the LLM) | **OpenAI** via API key |
| **Selector** | `MODEL_PROVIDER=ollama` | `MODEL_PROVIDER=openai` |
| **Provider config** | `OLLAMA_HOST`, model name | `OPENAI_API_KEY` |
| **Observability** | Galileo + Splunk SaaS (**internet required**) | Galileo + Splunk SaaS (**internet required**) |
| **Use case** | Local dev, booth-on-laptop | Shared/hosted demo |

### 8.2 Model-provider abstraction

A provider abstraction is selected by env var (`MODEL_PROVIDER=ollama|openai`), plus
provider-specific config (`OLLAMA_HOST` / model name, or `OPENAI_API_KEY`).

> Precedent: **Galileo's `sdk-examples` chatbot already ships an `openai-ollama` variant**, so this
> pattern is established rather than novel.

### 8.3 "Local models, cloud observability" — important constraint

> Even with **local Ollama models**, **Splunk Observability is cloud SaaS**, so **internet is still
> required for the observability layer.** This **limits true air-gapped / offline booth use** — only
> the LLM is offline-capable, not the demo as a whole.

> **Forward-looking:** with enterprise access, **Galileo self-hosting / VPC deployment** is now an
> option. It could enable more offline / air-gapped operation later (the Galileo side of the
> observability layer). **However**, Splunk Observability remains SaaS, so "internet required for the
> observability layer" still holds for now.

### 8.4 Resourcing

- The forked OTel demo is a **sizable docker-compose stack**. Official guidance: **~6 GB RAM for
  the full deployment** (≈3 GB in minimal mode, which drops Kafka and its dependents) and **~14 GB
  disk**.
  ([OpenTelemetry Docker deployment docs](https://opentelemetry.io/docs/demo/docker-deployment/))
- Runs fine on a **16 GB+ Apple-silicon Mac**. Ollama runs **natively on Apple Silicon** with
  automatic Metal/MLX GPU acceleration; 16 GB comfortably serves a 7–8B model (≈6–8 GB), leaving
  room for Docker. ⚠️ **Do not run Ollama inside Docker on macOS** — it loses Metal acceleration
  (5–6× slower); run it natively on the host.
  ([Ollama system requirements 2026](https://convly.ai/ollama-system-requirements-2026/))
- **EC2 sizing (to validate):** the demo stack alone wants ~6 GB RAM + headroom for the concierge
  and OS; a starting point is a general-purpose instance with **≥16 GB RAM and 4+ vCPUs** (e.g.
  `t3.xlarge` / `m6i.xlarge` class) plus ~30 GB disk. ⚠️ **Flagged: validate empirically** — exact
  size depends on how many of the ~15–20 services we keep and OpenAI offloading the LLM (so no GPU
  needed on EC2).

### 8.5 Secrets

- **Splunk access token**, **Galileo API key**, and **OpenAI key** all via **env / `.env`**
  (`.env` is gitignored).
- **NO hardcoded credentials anywhere** (per repo rule `codeguard-1-hardcoded-credentials`). Ship a
  `.env.example` with placeholder keys only.

---

## 9. Validated limitations & open questions

Carry all of these into the implementation plan.

### 9.1 Limitations & mitigations

| ID | Limitation | Mitigation |
|---|---|---|
| **L1** | Live LLM **nondeterminism** | **Induce** failures (seeded data, constrained tools, feature flags) + an SE **"known-good prompt" card** per vignette |
| **L2** | **Ingestion latency** + Galileo distributed tracing is **Beta** | Narrative pacing; **pre-warmed dashboards** |

### 9.2 Galileo capabilities (enterprise access secured — no tier limits)

We have **enterprise Galileo access**, so the former tier/feature gates **no longer apply** — these
are all **available capabilities** we can build on:

| Capability | Status |
|---|---|
| **Luna-2 evaluators** | **Available** — powers the live eval-accuracy vignette (§6, V4) |
| Real-time **guardrails** | **Available** — low-latency; no Pro purchase needed (§6, V3) |
| **Agent Control** | **Available** |
| **Self-hosting / VPC** | **Available** — forward-looking offline option (§8.3) |
| **Traces** | **Unlimited** — no 5,000-traces/month cap |

> Terminology: **"Protect" is deprecated** — say **"guardrails / Agent Control."**

### 9.3 Build constraints

- **OTLP**, not `sapm`.
- **Python** agent.
- Non-Python GenAI instrumentation maturity **unverified**.

### 9.4 Eval-accuracy pillar — now demoable

- **Eval accuracy** is now a **live vignette** (§6, V4 — Trust the Judge): enterprise **Luna-2**
  access lets us stage a contrast (naive LLM-judge wrong ~1 in 3 vs. Luna-2 / consensus evaluators
  agreeing with ground truth). It is **no longer a known weak spot** / talk-track-only pillar.

### 9.5 Resolved decision — theme

> **DECIDED: keep the Astronomy Shop theme as-is — no reskin.** The earlier open question (whether
> the playful space / astronomy theme should be reskinned to a neutral domain) is resolved in favour
> of keeping the fork's existing theming. This affects only theming, not the architecture.

---

## 10. Suggested next steps toward an implementation plan

1. **Theme is decided (§9.5): keep the Astronomy Shop as-is** — no reskin needed before concierge UX/copy.
2. **Stand up the scenario harness** (§7.5): fork the Astronomy Shop, add the Python concierge,
   wire the **single OTel GenAI instrumentation** and the **OTLP fan-out** to both backends.
3. **Implement the registry + trigger layer** with the four fixed mechanisms (§7.3).
4. **Build ONE reference vignette end-to-end** — recommended: **Vignette 1 (Invisible Failure)**,
   the cleanest punchline — including its `expected_signals` auto-verification (§7.4).
5. **Add the model-provider abstraction** (§8.2) and validate **both** environments (Ollama laptop,
   OpenAI EC2), including **EC2 sizing** (§8.4).
6. **Author the SE control panel + playlists** (§7.2).
7. **Layer in remaining Core-4 vignettes** (Compounding Error, Firewall, Trust the Judge), then optional ones.
8. **Build the eval-accuracy contrast vignette** (Trust the Judge, §6, V4) using Luna-2 / consensus
   evaluators against a curated known-ground-truth eval set, and write the supporting talk-track.
9. **Backfill `README.md`** Installation + Example-usage once the harness runs.

---

## Appendix A — Glossary of named Galileo capabilities referenced

| Term | Where used |
|---|---|
| Context Adherence | Vignette 1 — groundedness metric |
| Graph Engine | Vignette 2 — visualises step cascade |
| Tool Selection Quality | Vignette 2 — tool-choice metric |
| Insights Engine | Vignette 2 — loop-clustering |
| Guardrails / Agent Control | Vignette 3 — real-time blocking ("Protect" deprecated) |
| Luna-2 / consensus evaluators | Vignette 4 — eval-accuracy contrast vs. naive LLM-judge |
| Experiments | Vignette 5 — offline eval / regression catch |
| LLM-as-judge | Cross-cutting — metric enrichment; naive baseline in Vignette 4 |
