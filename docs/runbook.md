# SE Runbook — Galileo × Splunk Observability Demo

> **Audience:** a cold SE who has never seen this demo. Follow this guide to run
> all four Core vignettes end-to-end.

---

## The story in 60 seconds

This demo shows why probabilistic GenAI needs a **dedicated trust layer** that
traditional APM cannot provide. It uses two products side-by-side:

| Lens | Product | What it shows |
|---|---|---|
| **The agent's mind** | **Galileo AI** (hero) | Reasoning quality, evaluation accuracy, guardrails |
| **The agent's world** | **Splunk Observability** (backdrop) | Services, latency, errors, cost |

A Python AI shopping concierge lives inside a real OpenTelemetry "Astronomy
Shop" microservices app. The agent is instrumented **once** with OTel GenAI
conventions — the same telemetry fans out to **both** backends. Each vignette
induces a fault and reveals the contrast:

| # | Vignette | Punchline | Galileo hero moment |
|---|---|---|---|
| 1 | **The Invisible Failure** | Infra stays fully green (no notable errors); the agent invents a price — proven by the cart showing the real `$101.96` | **Context Adherence (SLM)** drops very low → Slack alert |
| 2 | **The Compounding Error** | One flaky payment cascades into retries and wasted tokens | Graph Engine cascade; Tool Selection Quality drop |
| 3 | **The Firewall** | PII smuggled via a poisoned review; infra sees nothing | PII guardrail fires on the poisoned content |
| 4 | **Trust the Judge** | 1 in 3 evals from a naive LLM-judge are wrong | Luna-2 / consensus evaluators agree with ground truth |

The **eval-accuracy thread** ("why should you trust a metric?") is woven
through every vignette: whenever you show a Galileo scorer, explain that
Galileo's evaluators use **consensus evaluation** — multiple specialized judges
cross-referencing each other — to avoid the systematic blind spots a single
LLM-as-judge has (confidence bias, hedging penalty, partial-credit inflation).
Vignette 4 makes this the explicit hero moment.

---

## Prerequisites

| Requirement | Detail |
|---|---|
| **Docker Desktop** | ~6 GB RAM (full stack), ~14 GB disk |
| **Python 3.12+** | With `uv` (recommended) or `pip` |
| **Model provider** | **Ollama** native on Apple Silicon — do NOT run it in Docker on macOS (loses Metal acceleration). Default model: `llama3.1:8b`. **Or** an OpenAI API key (EC2 runtime, model: `gpt-4o-mini`). |
| **Galileo enterprise** | API key; project name and log-stream (see `.env.example`) |
| **Splunk Observability Cloud** | Access token + realm (e.g. `us1`) |
| **Internet** | Required for Galileo + Splunk SaaS telemetry (even with local Ollama) |

### Model provider note

Set `MODEL_PROVIDER` in `.env`:

| Provider | Value | Config vars |
|---|---|---|
| Ollama (laptop) | `MODEL_PROVIDER=ollama` | `OLLAMA_HOST=http://localhost:11434`, `OLLAMA_MODEL=llama3.1:8b` |
| OpenAI (EC2) | `MODEL_PROVIDER=openai` | `OPENAI_API_KEY=<key>`, `OPENAI_MODEL=gpt-4o-mini` |

---

## One-time setup and bring-up

```sh
# 1. Clone and configure
git clone <repo-url> && cd astronomy-concierge
cp .env.example .env          # Fill in all tokens (GALILEO_*, SPLUNK_*, model provider)
# CONCIERGE_ADMIN_TOKEN is auto-generated and saved to .env on first
# `scripts/stage-up.sh` (trust-on-first-use) — no manual step needed.

# 2. Verify connectivity (optional but recommended)
scripts/check-connectivity.sh

# 3. If using Ollama, pull the model
ollama pull llama3.1:8b        # (or your OLLAMA_MODEL value)

# 4. Bring everything up with ONE command
scripts/stage-up.sh            # Vendors the demo, wires Splunk, starts containers
                               # (self-bootstrapping; runs stage-setup.sh for you),
                               # starts the Astronomy Concierge container (:8090),
                               # AND launches the SE Control-Plane web UI as a
                               # backgrounded host process (127.0.0.1:8099).
                               # Returns immediately. Add "minimal" for ~3 GB RAM.
```

That single command brings up all three primary web surfaces: the Astronomy
Concierge chat (`:8090`, container), the SE Control-Plane web UI
(`127.0.0.1:8099`, host process), and the storefront (`:8080`, with the
embedded concierge overlay). `stage-up.sh` prints the URLs and the SE-console log path
(`.harness/control-plane-web.log`) on exit; the console bootstraps its venv on
first launch, so `:8099` may take a few seconds to start listening.

**Fallback — concierge on the host instead of the container:** if you want the
concierge as a host process (rapid iteration without rebuilding the image), run
`scripts/concierge-serve.sh` (FastAPI on `127.0.0.1:8090`). Don't run it
alongside the containerized concierge — they share port `:8090`.

### Health checks

After bring-up, confirm each surface:

| Check | Command / URL | Expected |
|---|---|---|
| Storefront | `curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/` | `200` |
| Concierge web | `curl -s -o /dev/null -w '%{http_code}' http://localhost:8090/healthz` | `200` |
| Control-plane API | `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8099/api/list` | `200` |
| Collector healthy | `docker logs otel-collector 2>&1 \| grep -i 'Exporting failed'` | No `otlphttp/splunk` errors |
| Ollama (if used) | `ollama list` | Shows your `OLLAMA_MODEL` |

### Interface map (web primary)

| Surface | URL | Purpose |
|---|---|---|
| Astronomy Concierge chat | http://localhost:8090/ | Shopper-facing AI concierge (web) |
| SE Control-Plane UI | http://127.0.0.1:8099/ | Scenario list/play/reset/verify (loopback-only) |
| Astronomy Shop storefront | http://localhost:8080/ | The e-commerce app the agent lives in (embedded concierge overlay) |
| Feature-flag (flagd) UI | http://localhost:8080/feature | See/toggle the flagd flags |
| Jaeger local traces | http://localhost:8080/jaeger/ui/ | Local trace viewer |
| Splunk Observability | Your realm (`https://<realm>.signalfx.com`) | APM: env `local-agent-galileo` |
| Galileo console | `GALILEO_CONSOLE_URL` value (or default SaaS) | Project: per `.env` `GALILEO_PROJECT` / `GALILEO_LOG_STREAM` |

---

## Using the control plane

The control-plane UI at http://127.0.0.1:8099/ is the primary operator surface.
The CLI is a supported fallback for automation or terminal-first workflows:

```sh
scripts/control-plane.sh list                           # discover all scenarios
scripts/control-plane.sh play  <scenario-id>            # apply trigger (agent-side triggers: drive via concierge web chat)
scripts/control-plane.sh play  <scenario-id> --prompt "..."  # apply trigger; prints drive prompt guidance
scripts/control-plane.sh reset <scenario-id>            # restore baseline
scripts/control-plane.sh verify <scenario-id>           # auto-verify expected_signals
```

### Workflow per vignette

1. **Pre-warm** dashboards (see below).
2. **Play** the scenario (via UI button or CLI).
3. **Drive** the concierge with the known-good prompt in the concierge web chat
   at http://localhost:8090/ (for agent-side triggers, this is the only driving
   path; the control-plane applies setup only).
4. Wait 15–30 seconds for telemetry ingestion.
5. **Reveal**: show Splunk first (the backdrop), then Galileo (the hero).
6. Deliver the **punchline**.
7. **Verify** (optional): confirm the expected signals fired.
8. **Reset** before the next vignette.

---

## Recommended play order

| Order | Vignette | Why this position |
|---|---|---|
| 1st | **The Invisible Failure** | The cleanest punchline; establishes the "APM is content-blind" wedge |
| 2nd | **The Compounding Error** | Builds on the wedge: now Splunk ALSO lights up, but can't explain the agent's reasoning cascade |
| 3rd | **The Firewall** | Shifts from observation to prevention: Galileo as the guardrail layer |
| 4th | **Trust the Judge** | The meta-question: why should you trust the metrics from the first three? Capstone |

Run a **baseline conversation** before the first vignette (e.g. "Recommend a
beginner telescope and add it to my cart") to populate both dashboards with
clean data. This establishes the "what good looks like" contrast.

---

## Dashboard pre-warming

Galileo and Splunk have ingestion latency (typically 15–60 seconds). Pre-warm
**before the audience joins** so the green/anomaly contrast is visible on cue.

### Galileo pre-warm

1. Open the Galileo console to your project and log stream:
   - **Project:** the value of `GALILEO_PROJECT` in `.env` (default: `local-agent-galileo`)
   - **Log stream:** the value of `GALILEO_LOG_STREAM` in `.env` (default: `dev`)
2. Run a baseline conversation and confirm a clean
   **Sessions → Traces → Spans** view appears.
3. Leave the trace-list or session view open and ready to refresh.

### Splunk APM pre-warm

1. Open **Splunk Observability → APM**.
2. Set the environment filter to **`local-agent-galileo`**.
3. Confirm the **service map** shows the store's services (including
   `astronomy-concierge`) with green status.
4. Leave the service map or trace view open.

### Splunk AI Agent Monitoring (known limitation)

The concierge emits `gen_ai.*` spans and GenAI histogram metrics, which are the
data source for **APM → AI agents / AI trace data**. However:

- Not all AI panels light up consistently in all Splunk environments. The
  concierge's spans appear reliably under `astronomy-concierge` in APM traces,
  but the dedicated "AI Agent Monitoring" pages may show partial data.
- **Rely on standard APM traces and the `gen_ai.*` span attributes** as the
  primary Splunk evidence. The AI Agent Monitoring page is a "nice to have"
  supplement, not the primary Splunk reveal surface.
- A Splunk admin must (one-time) enable the **LLM Providers** integration under
  `Data Management → Available integrations` and grant the
  `read_apm_ai_conversation` capability.

---

## Reset and recovery

### Per-scenario reset

Each vignette has its own reset:

```sh
scripts/control-plane.sh reset <scenario-id>
```

This restores the trigger state through the authoritative trigger reset path
(`feature_flag` via flagd; `tool_fault`/`prompt_overlay`/`rag_corpus` via
authenticated concierge admin API reset + session reload). The agent's next
conversation runs at baseline.

### Full teardown

```sh
scripts/stage-down.sh              # Stop all containers AND the backgrounded SE console
scripts/stage-down.sh --volumes    # Stop + remove data volumes (clean slate)
```

`stage-down.sh` also stops the backgrounded SE Control-Plane web UI started by
`stage-up.sh` (reads `.harness/control-plane-web.pid`; handles a missing/stale
PID gracefully).

### Quick fixes for common failures

| Symptom | Fix |
|---|---|
| **Ollama not running / model not found** | `ollama serve` (if not running); `ollama pull llama3.1:8b` (if model missing) |
| **Concierge container not starting** | Check `docker logs concierge-web`; confirm `OLLAMA_HOST`, `GALILEO_API_KEY` are exported |
| **Stale containers after code change** | `scripts/stage-down.sh && scripts/stage-up.sh` (rebuilds) |
| **Galileo shows no traces** | Verify `GALILEO_API_KEY` is set and non-empty; the concierge logs "Galileo export: enabled" at startup |
| **Splunk shows no data** | Verify `SPLUNK_ACCESS_TOKEN` + `SPLUNK_REALM`; check collector logs for export errors |
| **Load-generator noise** masks the vignette signal | V1 (`invisible-failure`) and V2 (`compounding-error`) use `quiet_background: true` (the harness drains the Locust load generator); V3 and V4 intentionally keep background load present |
| **Scenario play has no effect** | Run `scripts/control-plane.sh reset <id>` first, then re-play; confirm the stage is up |
| **Flagd flag not applying** | Check `http://localhost:8080/feature` to see current flag states; flagd hot-reloads from its config, no restart needed |
| **Agent gives unexpected response** | Set `MODEL_TEMPERATURE=0.0` in `.env` (the default); use the exact known-good prompt from the talk track |

---

## Two-runtime notes (Ollama vs OpenAI)

| Aspect | Ollama (laptop) | OpenAI (EC2) |
|---|---|---|
| **Latency** | Higher (~5–15 s per turn with 8B model) | Lower (~1–3 s per turn) |
| **Tool-calling reliability** | `llama3.1:8b` may emit malformed tool calls; `qwen2.5:14b-instruct` is more reliable | `gpt-4o-mini` has reliable function-calling |
| **V2 (Compounding Error)** | The 3-step search→add→checkout chain may not complete on `llama3.1:8b` (tool calls break); Galileo signals still fire | Checkout reliably reaches the payment service; both Galileo and Splunk signals fire |
| **V4 (Trust the Judge)** | Works; eval-set processing is model-independent (Galileo scorers evaluate the trace) | Works; same |
| **Demo pacing** | Ollama latency gives you natural "let's see what happens" pauses | OpenAI is fast; you may need to slow your narration |
| **GPU** | Apple Silicon Metal acceleration (native only, not Docker) | No GPU needed (OpenAI API) |

**Recommendation:** For the best demo reliability, use **OpenAI** (`gpt-4o-mini`)
or a larger local model (`qwen2.5:14b-instruct`). The default `llama3.1:8b` is
fine for V1, V3, V4 but may struggle with V2's multi-step tool chain.

---

## Per-vignette quick reference

| Vignette | Scenario ID | Trigger | Splunk shows | Galileo hero |
|---|---|---|---|---|
| V1: The Invisible Failure | `invisible-failure` | `tool_fault` → `get_product_details` + `search_products` + `get_recommendations` (`stale` snapshot) | Fully green (no backend calls, no notable errors) | **Context Adherence (SLM)** low → Slack alert; ungrounded claim |
| V2: The Compounding Error | `compounding-error` | `feature_flag` → `paymentFailure` | Payment service errors/latency spike | Tool Selection Quality low; cascade in Graph Engine |
| V3: The Firewall | `firewall` | `prompt_overlay` → poisoned review | APM normal (HTTP 200) | PII detected in conversation |
| V4: Trust the Judge | `trust-the-judge` | `prompt_overlay` → eval-driver | N/A (eval layer) | Context Adherence low on incorrect eval cases |

Each vignette's full talk track, known-good prompt, and beat-by-beat reveal
are in `scenarios/<id>/captions/<id>.md`.

### V1 reveal (the cart-mismatch payoff)

Drive V1 from the **storefront-embedded** concierge so the cart is shared: open
http://localhost:8080/, click **"AI Astronomy Concierge"** in the top nav, then:

1. Ask for the Explorascope's price + specs (the known-good prompt). The agent
   answers with an **invented** price/specs — note the price it quotes.
2. Tell the concierge to **add the Explorascope to the cart** (`add_to_cart` is
   not faulted, so it adds the real product).
3. Open the store **cart** (http://localhost:8080/cart). It shows the **real
   catalog price `$101.96`**, which **differs from the price the agent quoted**.
   That mismatch is the payoff — a tangible hallucination while everything
   "works." The cart is ground truth because it's served by the real cart /
   product-catalog services, not the faulted agent tool path.

**Signal footprint:**

- **Galileo (hero):** **Context Adherence (SLM)** drops very low and **fires a
  Slack alert** — this is the **only** signal of the failure. `ungrounded_claim`
  (completeness) corroborates.
- **Splunk APM:** **fully green** — the concierge path and core store services
  are healthy with no notable errors. That's the point: nothing in APM indicates
  a problem (V1 flips no feature flag and induces no backend error; it faults the
  agent's tools directly, which APM cannot see).

> Note: driving V1 from the standalone concierge at http://localhost:8090/ uses a
> separate cart id, so the added item won't appear in the store cart — use the
> embedded widget for the cart reveal.
