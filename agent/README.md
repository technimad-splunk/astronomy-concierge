# `agent/` — Astronomy Shop AI shopping concierge

The one new service we add to the forked OTel demo: a Python AI shopping
concierge built on **LangGraph** (decision D1). It has two responsibilities,
each chosen to expose a specific failure surface (demo-design §4):

- **(a) Answers questions** — RAG over a product catalog + policy docs
  (exposes hallucination / groundedness).
- **(b) Takes actions** — calls the store's existing microservice APIs as its
  tools (exposes tool-selection / cost).

The agent is instrumented **once** with OpenTelemetry GenAI semantic
conventions and the same telemetry is fanned out to **both** Galileo (OTLP /
`GalileoSpanProcessor`) and Splunk (via the Splunk OTel Collector) — the
keystone of the whole design (demo-design §3).

### Why the Traceloop instrumentor (Splunk AI Agent Monitoring)

Splunk **AI Agent Monitoring** (`APM > AI agents` / `AI trace data`) only renders
when telemetry follows the **OTel GenAI semantic conventions** (`gen_ai.*` span
attributes) **and** includes **GenAI histogram metrics**. OpenInference's `llm.*`
attributes are not recognized there, so the OTel/Splunk instrumentor is the
OpenLLMetry / **Traceloop** `opentelemetry-instrumentation-langchain`
(`LangchainInstrumentor`) — which Splunk's setup doc lists as a supported
"third-party instrumentation" source. It hooks the LangChain callback-manager
layer, so it populates `gen_ai.*` for **every** LangChain chat model — including
our default `ChatOllama` — unlike the official OTel-contrib LangChain
instrumentor, which only emits `gen_ai.*` for `ChatOpenAI`/`ChatBedrock` and
silently skips other providers. `telemetry.py` therefore also stands up a
`MeterProvider` with an OTLP metric exporter (delta temporality) to the same
local collector so the GenAI histograms are exported.

Concretely it emits spans carrying e.g. `gen_ai.operation.name`,
`gen_ai.provider.name`, `gen_ai.request.model` / `gen_ai.response.model`,
`gen_ai.input.messages` / `gen_ai.output.messages`,
`gen_ai.usage.input_tokens` / `output_tokens` / `total_tokens`,
`gen_ai.tool.*`, `gen_ai.agent.*`, `gen_ai.workflow.*` — and the histograms
`gen_ai.client.token.usage` and `gen_ai.client.operation.duration`.

OpenInference is retained only for `using_session` (Galileo session context); it
is no longer the active OTel instrumentor. **Galileo is unaffected** — its
`GalileoCallback` is independent of the OTel GenAI conventions.

The Splunk-documented GenAI env knobs (`OTEL_INSTRUMENTATION_GENAI_EMITTERS=span_metric`,
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=SPAN_ONLY`,
`OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=delta`, and
`TRACELOOP_TRACE_CONTENT=true`) are applied as defaults by `telemetry.py` and
documented in `.env.example`.

### Closing the gaps: GenAI translator + collector model fix

The bare Traceloop instrumentor leaves three things AI Agent Monitoring needs
unsatisfied for this stack. Each is closed without leaving the
"instrument-once" design:

1. **Agents/workflows don't render.** Traceloop keeps the agent/workflow
   structure in its own `traceloop.*` shape (`traceloop.span.kind`,
   `traceloop.entity.*`, `traceloop.workflow.*`), which the AI Agent Monitoring
   pages do not understand. Splunk's **Traceloop→GenAI translator**
   (`splunk-otel-util-genai-translator-traceloop`) is a `SpanProcessor` that
   promotes that shape into the OTel GenAI **entity model**
   (`gen_ai.agent.*` / `gen_ai.workflow.*`, `invoke_agent` / `create_agent`
   operations). `telemetry.py` registers it FIRST (before the export
   `BatchSpanProcessor`) so its in-place attribute mutation is exported. Toggle
   with `SPLUNK_GENAI_TRANSLATOR` (default on).
2. **"No parsable message event found".** LLM spans carry no message content
   unless `TRACELOOP_TRACE_CONTENT=true`. With content on, the same translator
   reconstructs `gen_ai.input.messages` / `gen_ai.output.messages` in the schema
   the conversation view parses (roles + `parts`, including `tool_call` parts).
3. **`gen_ai.request.model = "unknown"`.** Traceloop can't read the model off
   `ChatOllama`, so it stamps `"unknown"`; the real name lives in
   `traceloop.association.properties.ls_model_name` (e.g. `llama3.1:8b`). The
   translator does NOT map it, so the LOCAL Splunk collector promotes it via an
   OTTL `transform/genai_model` (see `stage/splunk-otel/otelcol-config-extras.yml`),
   only when the model is missing/blank/`"unknown"` (never clobbering a real
   model from e.g. `ChatOpenAI`).

> **Console-side prerequisites (one-time, done by a Splunk admin):** enable the
> **LLM Providers** data integration (`Data Management > Available integrations`)
> for platform-side evaluations, and ensure your role has the
> `read_apm_ai_conversation` capability (included in the `admin` / `ai_monitoring`
> roles) to view AI conversation details.

## Modules (Phase 2)

| File | Role |
|---|---|
| `config.py` | **Model-provider abstraction** (D6): `MODEL_PROVIDER=ollama` → `ChatOllama`, `openai` → `ChatOpenAI`. All config from env; no embedded credentials. |
| `graph.py` | Builds the LangGraph ReAct concierge (`create_react_agent`) from the model + tools + system prompt. |
| `tools.py` | The agent's tools (per session): `search_knowledge_base` (RAG) plus store actions (`search_products`, `get_product_details`, `get_recommendations`, `add_to_cart`, `view_cart`, `list_currencies`). |
| `rag.py` | Dependency-free, deterministic TF-IDF retriever over `knowledge/*.md` (capability (a)). |
| `store_client.py` | Validated HTTP client for the Astronomy Shop frontend-proxy API at `:8080/api/...` (capability (b)). |
| `telemetry.py` | The keystone: one OTel `TracerProvider` + `MeterProvider` + one Traceloop `LangchainInstrumentor` (emits `gen_ai.*` spans + GenAI histograms) + the Splunk Traceloop→GenAI translator span processor (entity model + conversation reconstruction), fanned out to **Splunk** (OTLP/gRPC spans + metrics → local collector) and **Galileo** (`GalileoCallback`, or opt-in OTLP). |
| `main.py` / `__main__.py` | Runnable entrypoint (`python -m agent`): one-shot `--prompt` or interactive chat; wraps each turn in a Galileo session and flushes both backends on exit. |
| `knowledge/` | The curated RAG corpus: shipping & returns, warranty, buying guide, store FAQ. |

## Tools = the agent's two capabilities

- **(a) Answer** — `search_knowledge_base` does RAG over `knowledge/` for
  policy/shipping/returns/warranty/buying questions (exposes groundedness).
- **(b) Act** — the store tools turn the agent's actions into **real calls into
  Astronomy Shop services** through the frontend-proxy (exposes tool-selection /
  cost). Cart operations are scoped to the conversation's session id.

## Telemetry fan-out (design §3)

A single Traceloop `LangchainInstrumentor` instruments the LangGraph run once,
emitting OTel GenAI conventions (`gen_ai.*` spans) and GenAI histograms.
The same telemetry goes to:

- **Splunk** — `BatchSpanProcessor` (spans) + `PeriodicExportingMetricReader`
  (delta histograms), both OTLP/**gRPC** to the local Splunk OTel Collector
  (`localhost:4317`), which forwards to Splunk Observability. OTLP only — never
  `sapm`. `service.name=astronomy-concierge`,
  `deployment.environment=local-agent-galileo` (joins the store's APM environment).
  In the collector the GenAI histograms leave via the `signalfx` exporter **only**
  (with `send_otlp_histograms: true`, which Splunk's "Set up AI Agent Monitoring"
  doc REQUIRES) so they reach AI Agent Monitoring; the OTLP-metrics path
  (`otlphttp/splunk`) is deliberately **not** in the metrics pipeline, so the same
  histogram isn't delivered twice (see `stage/splunk-otel/`). Metrics use **delta**
  temporality, set explicitly on the OTLP metric exporter in `telemetry.py`
  (`preferred_temporality`), not only via the env var.

> **Verifying GenAI metrics — use the UI, not the metric finder.** Native OTLP
> histograms are a distinct metric type in Splunk o11y and **do not appear in the
> metric-name finder/catalog** (which lists gauges/counters). "`gen_ai.*` not in
> the metric finder" is therefore a **false negative**, not proof of missing data.
> Confirm histogram-backed data in **`APM > AI agents` / `AI trace data`**. Do NOT
> set `send_otlp_histograms: false` to "make names show up" — that drops the native
> histogram AI Agent Monitoring needs.

To PROVE the agent actually produces and flushes the GenAI histograms
(`gen_ai.client.token.usage`, `gen_ai.client.operation.duration`) without the
collector, set `GENAI_METRICS_CONSOLE_DEBUG=1`: `telemetry.py` adds a console
metric exporter that dumps every metric data point to stdout. Off by default; it
does not affect the normal OTLP export.
- **Galileo** — the SDK's first-class `GalileoCallback` (Sessions → Traces →
  Spans + agent metrics), reading `GALILEO_*` from env. Set `GALILEO_OTEL_EXPORT=1`
  to instead use the pure-OTLP `GalileoSpanProcessor` path.

## Run

```sh
# from the repo root, with the stage up and Ollama serving llama3.1:8b
scripts/agent-run.sh --prompt "recommend a beginner telescope and add it to my cart"
scripts/agent-run.sh                       # interactive chat
# equivalently, inside the venv: python -m agent --prompt "..."
```

Switching `MODEL_PROVIDER` between `ollama` and `openai` requires **no code
change** — only env. Note: small local models (e.g. `llama3.1:8b`) are
occasionally inconsistent at multi-step tool calling; `MODEL_TEMPERATURE=0`
(the default) maximizes reliability.
