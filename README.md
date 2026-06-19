# local-agent-galileo

An SE-led, guided demo environment that showcases Galileo AI as the AI/agent intelligence layer alongside Splunk Observability as the systems/infrastructure backdrop.

## Goal

`local-agent-galileo` is a best-in-class AI-agent demo environment that replays common agent scenarios to show **Galileo AI** (the hero — reasoning quality, evaluation, and guardrails) working together with **Splunk Observability** (the operational backdrop — services, traces, metrics, logs, and cost). A Python AI shopping concierge is added to a forked OpenTelemetry "Astronomy Shop" microservices app; the agent is instrumented **once** with OpenTelemetry GenAI conventions and the same telemetry is fanned out to **both** backends, so a single induced fault produces correlated, two-lens incidents. It exists to give prospective customers a credible, repeatable demonstration — and a preview of the integrated Cisco (Splunk + Galileo) story — of why probabilistic GenAI needs a dedicated trust layer that traditional APM cannot provide. See [`docs/demo-design.md`](docs/demo-design.md) for the full design.

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
git clone https://github.com/your-org/local-agent-galileo
cd local-agent-galileo

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

### Run the stage (Phase 1)

Bring up the forked OpenTelemetry "Astronomy Shop" and stream its telemetry to
Splunk Observability over OTLP. The whole stage is reproducible from a fresh
clone of this repo — every step maps to a script, no manual checkout required.

**Prerequisites:** Docker running with **~6 GB RAM** (~14 GB disk), plus `git`.

```sh
cp .env.example .env            # 1. fill in SPLUNK_ACCESS_TOKEN + SPLUNK_REALM (and provider keys)
scripts/check-connectivity.sh   # 2. verify backends/tokens are reachable (secret-safe)
scripts/stage-setup.sh          # 3. vendor the demo @ pinned ref + wire Splunk overrides (idempotent)
scripts/stage-up.sh             # 4. start the stack (also runs setup) — or: scripts/stage-up.sh minimal
open http://localhost:8080/     # 5. verify the storefront (expect HTTP 200)
scripts/stage-down.sh           # 6. stop it (add --volumes to also drop data)
```

`scripts/stage-up.sh` is self-bootstrapping (it runs `stage-setup.sh` for you),
so step 4 alone is enough after step 1. The pinned demo version lives in **one
place**, [`stage/demo.ref`](stage/demo.ref). The store's services appear in
**Splunk APM under environment `local-agent-galileo`**. See
[`stage/README.md`](stage/README.md) for the Splunk wiring and local verification.

### Run the concierge (Phase 2)

The AI shopping concierge runs on the host (alongside the stage) and is
instrumented once with OpenTelemetry GenAI, fanning the same telemetry out to
**both** Galileo and Splunk Observability.

**Prerequisites:** the stage is up (above); a model provider is reachable —
either native **Ollama** serving `llama3.1:8b` (`MODEL_PROVIDER=ollama`, the
default) or an **OpenAI** key (`MODEL_PROVIDER=openai`); and `.env` has your
`GALILEO_*` and `SPLUNK_*` values filled in.

```sh
# One self-bootstrapping script: creates a venv, installs deps, runs the agent.
scripts/agent-run.sh --prompt "Recommend a beginner telescope and add it to my cart"
scripts/agent-run.sh                       # interactive conversation (Ctrl-D to exit)
```

The concierge reports — without printing secrets — which backends it enabled,
the `service.name` (`astronomy-concierge`), and the `deployment.environment`
(`local-agent-galileo`, the same APM environment as the store, so the two
correlate in Splunk). A conversation that calls a tool (e.g. add-to-cart) shows
up as **Sessions → Traces → Spans in Galileo** and as spans on the
**`astronomy-concierge` service in Splunk APM**. See
[`agent/README.md`](agent/README.md) for the module map and telemetry detail.

The concierge emits **OpenTelemetry GenAI conventions** (`gen_ai.*` spans) and
**GenAI histogram metrics**, so it also lights up **Splunk AI Agent Monitoring**
(`APM > AI agents` / `AI trace data`). To view AI conversation details there, a
Splunk admin must (one-time) enable the **LLM Providers** integration under
`Data Management > Available integrations` and grant the `read_apm_ai_conversation`
capability (in the `admin` / `ai_monitoring` roles). See
[`agent/README.md`](agent/README.md) for the instrumentation details.

### Run the scenario harness / control plane (Phase 3)

Vignettes are **drop-in folders** under `scenarios/`: a new folder with a
`scenario.yaml` appears in the control plane with **no core edits**. The SE drives
everything from one self-bootstrapping script.

**Prerequisites:** for `list`/`playlist`, none beyond `.env`. For `play`/`reset`
of a `feature_flag` scenario, the stage must be up; for driving the agent, a model
provider must be reachable; for `verify`, `GALILEO_*` must be set.

```sh
scripts/control-plane.sh list                         # discover all scenarios (drop-in proof)
scripts/control-plane.sh play  stub-tool-fault --prompt "Recommend a telescope"   # apply trigger + drive agent
scripts/control-plane.sh reset stub-tool-fault        # restore baseline
scripts/control-plane.sh verify stub-feature-flag     # auto-verify expected_signals (Galileo real)
scripts/control-plane.sh playlist --message harness-stub --budget 3   # compose a run
```

The **four fixed triggers** (`feature_flag | rag_corpus | tool_fault |
prompt_overlay`) each `apply` a fault and `reset` it deterministically;
`feature_flag` flips a flagd flag in the running stage, while the other three
write to a stable agent overlay seam (`agent/_overlay/`) that `agent/` reads on its
next run — so scenarios never edit core. The `expected_signals` hook verifies
**Galileo** signals for real (poll/retry for ingestion lag; scorer UUIDs are
resolved to human names live) and reports the **Splunk** `apm_all_green` signal as
*operator-attested* with embedded evidence (our token is ingest-only, so the CLI
can't query APM — the operator confirms it via the Splunk Observability MCP/UI).
See [`control_plane/README.md`](control_plane/README.md).

### Run the reference vignette — "The Invisible Failure" (Phase 4)

The first end-to-end vignette: Galileo catches a quality failure (ungrounded
answer) that Splunk APM, staying green on the concierge service, cannot see.

**Prerequisites:** stage is up, model provider reachable, `.env` has `GALILEO_*`
and `SPLUNK_*` values.

```sh
# Play: flip the feature flag + drive the agent with the known-good prompt
scripts/control-plane.sh play invisible-failure \
  --prompt "I'm interested in the Roof Binoculars (product OLJCESPC7Z). Can you tell me about that product — its price, description, and whether it's a good choice for a beginner? Also check if there are similar recommendations."

# Verify: auto-check expected_signals (Galileo real PASS; Splunk apm_all_green attested)
scripts/control-plane.sh verify invisible-failure

# Reset: restore baseline (flag off, product catalog healthy)
scripts/control-plane.sh reset invisible-failure
```

The concierge handles the product-catalog error gracefully (no crash), so its
own traces in Splunk APM stay green — but Galileo's Context Adherence drops and
pinpoints the ungrounded claim. See the full talk track at
[`scenarios/invisible-failure/captions/invisible-failure.md`](scenarios/invisible-failure/captions/invisible-failure.md).

### Web interfaces (Phase 7)

Two optional browser surfaces wrap the same cores — built as thin web layers over
the unchanged `agent/` and `control_plane/` packages. **The CLIs above remain
supported fallbacks.**

```sh
scripts/concierge-serve.sh        # shopper-facing Astronomy Concierge chat on :8090
scripts/control-plane-web.sh      # SE control-plane UI, loopback-only on 127.0.0.1:8099
```

**All interfaces at a glance** (once `scripts/stage-up.sh` is running and the two web
apps are started):

| Surface | URL |
|---|---|
| Astronomy Shop storefront | http://localhost:8080/ |
| Astronomy Concierge chat | http://localhost:8090/ |
| SE Control-Plane UI (loopback-only) | http://127.0.0.1:8099/ |
| Feature-flag (flagd) UI | http://localhost:8080/feature |
| Jaeger local trace view | http://localhost:8080/jaeger/ui/ |
| Splunk Observability (APM / AI Agent Monitoring) | your Observability Cloud realm |
| Galileo console | value of `GALILEO_CONSOLE_URL` (project/log-stream from `.env`) |

The concierge container talks to a **native** Ollama on the host
(`host.docker.internal:11434`); confirm your `OLLAMA_MODEL` is pulled.

- **Astronomy Concierge** — a standalone chat app (FastAPI + React/Vite frontend,
  containerized) over the Phase-2 agent; preserves the `gen_ai.*` spans + GenAI
  histograms (Splunk) and Galileo Sessions→Traces→Spans.
- **Control-plane web UI** — a FastAPI layer over the Phase-3 harness
  (`list/play/reset/verify/playlist` with live SSE output); **bound to
  `127.0.0.1` only** because it triggers faults.

> **Status:** Phases 7.0–7.4 are implemented and verified at the static/integration
> level (both apps boot, the loopback guard rejects non-loopback binds, all
> scenarios still discover with no core edits, the frontend builds). The **live
> clean-room sign-off and full Installation/Example-usage steps are finalized in
> Phase 7.5** (not yet complete). See
> [`docs/web-interface-plan.md`](docs/web-interface-plan.md) and
> [`web/README.md`](web/README.md).

