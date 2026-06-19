# astronomy-concierge

An SE-led, guided demo environment that showcases Galileo AI as the AI/agent intelligence layer alongside Splunk Observability as the systems/infrastructure backdrop.

## Goal

`astronomy-concierge` is a best-in-class AI-agent demo environment that replays common agent scenarios to show **Galileo AI** (the hero — reasoning quality, evaluation, and guardrails) working together with **Splunk Observability** (the operational backdrop — services, traces, metrics, logs, and cost). A Python AI shopping concierge is added to a forked OpenTelemetry "Astronomy Shop" microservices app; the agent is instrumented **once** with OpenTelemetry GenAI conventions and the same telemetry is fanned out to **both** backends, so a single induced fault produces correlated, two-lens incidents. It exists to give prospective customers a credible, repeatable demonstration — and a preview of the integrated Cisco (Splunk + Galileo) story — of why probabilistic GenAI needs a dedicated trust layer that traditional APM cannot provide. See [`docs/demo-design.md`](docs/demo-design.md) for the full design.

## Installation

> Phases 0–3 complete: the **stage** (forked Astronomy Shop + Splunk Collector
> wiring) runs locally and exports to Splunk Observability over OTLP; the
> **concierge agent** (`agent/`) is a LangGraph shopping concierge that answers
> via RAG and acts via the store's APIs, instrumented once with OpenTelemetry
> GenAI and fanned out to **both** Galileo and Splunk; and the **scenario harness
> + SE control plane** (`control_plane/`) make vignettes drop-in folders with the
> four fixed triggers and an `expected_signals` auto-verification hook. Authoring
> the reference vignette content is Phase 4 (see
> [`docs/implementation-plan.md`](docs/implementation-plan.md)).

### Prerequisites

- **Docker Desktop** — to run the forked Astronomy Shop microservices stack
  (~6 GB RAM full / ~3 GB minimal, ~14 GB disk).
- **Python 3.12+**.
- A Python package manager: **`uv`** (recommended) or **`pip`**.
- **One model provider:**
  - **Ollama** installed natively (Apple-silicon laptop runtime — do *not* run it
    in Docker on macOS), **or**
  - an **OpenAI API key** (EC2 runtime).
- Accounts/tokens (captured out-of-band): **Galileo** (enterprise) API key and a
  **Splunk Observability Cloud** access token + realm.

### Steps

```sh
git clone https://github.com/your-org/astronomy-concierge
cd astronomy-concierge

cp .env.example .env        # then fill in your tokens (see comments in the file)

# Install dependencies (resolves and locks exact versions on first run):
uv sync                     # or: pip install -e .
```

### Project structure

| Path | Purpose |
|---|---|
| `agent/` | The Python AI shopping concierge (LangGraph). Holds the model-provider abstraction today; RAG + tools + OTel fan-out land in Phase 2. |
| `stage/` | The forked OpenTelemetry "Astronomy Shop" + Splunk OTel Collector wiring (Phase 1). |
| `scenarios/` | The pluggable vignette library — each vignette is a drop-in folder with a `scenario.yaml`. Includes the reference `invisible-failure/` and Phase-3 harness stubs (`stub-*`). |
| `control_plane/` | The SE control-plane + harness package (Phase 3): scenario registry, manifest loader, the four trigger handlers, pluggable `expected_signals` verification, the `list/play/reset/verify/playlist` CLI, and the SE-facing `README.md`. |
| `scripts/` | Automation & verification helpers (e.g. connectivity checks). |
| `docs/` | Design, implementation plan, and the agent journal. |

## Example usage

### Start the environment (web interfaces first)

Use the **web interfaces as the primary demo surfaces**. Use the CLI only as a
**fallback for expert users or automation**.

Start the environment in this order:

```sh
# 1. Configure: copy the template and fill in your tokens (GALILEO_*, SPLUNK_*,
#    and your model-provider keys). See the comments in the file.
cp .env.example .env

# 2. Recommended: verify your backends/tokens are reachable (secret-safe).
scripts/check-connectivity.sh

# 3. If using Ollama (the default), pull your model BEFORE bring-up.
ollama pull llama3.1:8b              # or your OLLAMA_MODEL value

# 4. Bring up the full demo stage (non-blocking).
#    This starts the storefront, concierge web app, and SE console web UI.
scripts/stage-up.sh                 # or: scripts/stage-up.sh minimal  (lighter ~3 GB RAM)
```

Then open the primary web interfaces:

### Primary interface map

| Surface | URL | Purpose |
|---|---|---|
| **Astronomy Concierge (chat)** | http://localhost:8090/ | Shopper-facing AI concierge |
| **SE Control-Plane UI (SE console)** | http://127.0.0.1:8099/ | Scenario control UI: list / play / reset / verify |
| **Astronomy Shop storefront + embedded AI Concierge overlay** | http://localhost:8080/ | Storefront experience with embedded concierge |
| flagd UI (optional) | http://localhost:8080/feature | Feature-flag inspection/toggles |
| Jaeger (optional) | http://localhost:8080/jaeger/ui/ | Local trace viewer |
| Splunk Observability (APM / AI Agent Monitoring) | your Observability Cloud realm | Operational backdrop — env `local-agent-galileo` |
| Galileo console | value of `GALILEO_CONSOLE_URL` (project/log-stream from `.env`) | The hero lens — Sessions → Traces → Spans, evaluators, guardrails |

### Teardown

```sh
scripts/stage-down.sh               # stop the stack AND the backgrounded SE console
scripts/stage-down.sh --volumes     # also drop named data volumes (clean slate)
```

`stage-down.sh` reads the SE console's PID from `.harness/control-plane-web.pid`
and stops it (gracefully handling a missing/stale PID), then tears down the
containers. Pass the same mode (`full` | `minimal`) you brought it up with.

---

### Fallback: run concierge standalone (without full stage)

Use this only when you explicitly want the concierge outside the full stage:

```sh
scripts/concierge-serve.sh          # FastAPI concierge on 127.0.0.1:8090 (venv-bootstrapping)
```

This is a fallback launcher, not the primary path.

### Fallback: drive the demo from the CLI (expert / automation)

For automation or when you prefer the terminal, use:

```sh
scripts/control-plane.sh list                         # discover all scenarios
scripts/control-plane.sh play  invisible-failure --prompt "..."   # apply trigger + drive the agent
scripts/control-plane.sh reset invisible-failure      # restore baseline
scripts/control-plane.sh verify invisible-failure     # auto-verify expected_signals (Galileo real)
scripts/control-plane.sh playlist --message demo --budget 3       # compose a run
```

The **four fixed triggers** (`feature_flag | rag_corpus | tool_fault |
prompt_overlay`) each `apply` a fault and `reset` it deterministically;
`feature_flag` flips a flagd flag in the running stage, while the other three
write to a stable agent overlay seam (`agent/_overlay/`) that `agent/` reads on
its next run — so scenarios never edit core. The concierge is instrumented
**once** with OpenTelemetry GenAI (`gen_ai.*` spans + GenAI histogram metrics)
and fans the same telemetry out to **both** Galileo (Sessions → Traces → Spans)
and Splunk (APM + AI Agent Monitoring under `local-agent-galileo`). The
`expected_signals` hook verifies **Galileo** signals for real and reports the
**Splunk** `apm_all_green` signal as *operator-attested*. To view AI
conversation details in Splunk, an admin must (one-time) enable the **LLM
Providers** integration and grant `read_apm_ai_conversation`. See
[`control_plane/README.md`](control_plane/README.md), [`agent/README.md`](agent/README.md),
and the SE runbook at [`docs/runbook.md`](docs/runbook.md) for the full talk
tracks and per-vignette reference.

