# Talk Track — The Compounding Error

**Vignette 2 — The Compounding Error** (demo-design §6)

**Pillar:** Error compounding — *"In multi-step agents, one early bad step
cascades into later steps."*

## The message

Traditional software fails loud: a 500 error triggers an alert, an on-call
page, a fix. But GenAI agents **compound** failures silently. A flaky
backend service doesn't crash the agent — the agent retries, loops, picks
wrong alternatives, or gives up. Each retry doubles latency and cost. Each
wrong tool pick moves the agent further from the user's goal. The Graph
Engine in Galileo makes this cascade **visible as a graph**, not buried in
flat logs.

**Splunk shows the operational symptom** (the payment service is failing).
**Galileo shows the agent-level consequence** (degraded tool selection, retry
loops, abandoned user goals).

## Setup (before the audience sees it)

1. Confirm the **stage is up** (`scripts/stage-up.sh`) and the storefront loads
   at http://localhost:8080/.
2. Confirm **Splunk APM** shows the store's services healthy. Point out the
   `paymentservice` and `astronomy-concierge` on the service map.
3. Pre-warm: run a **baseline conversation** that exercises `checkout`
   successfully. Use a prompt like *"Find the Solar System Color Imager, add
   it to my cart, and check out"* and confirm a clean trace in both Galileo
   and Splunk.

## Inducing the failure

> **Script:** `scripts/control-plane.sh play compounding-error`
>
> Or with the known-good prompt:
>
> ```sh
> scripts/control-plane.sh play compounding-error \
>   --prompt "I want to buy the Starsense Explorer Telescope. Please do each \
> step in order: (1) search for it in the catalog to get the product id and \
> price, (2) add it to my cart using the product id you found, (3) check out \
> to complete my purchase. If checkout fails, please try checking out again — \
> it might be a transient issue. I really want to complete this order today."
> ```

The trigger flips the `paymentFailure` flagd feature flag to "100%" (always
fail), causing the demo's **payment service** to throw an error on every
charge request. Because the concierge agent's `checkout` tool calls the REAL
checkout service (via `POST /api/checkout` through the frontend-proxy), and
the checkout service calls the payment service to charge the card, the fault
propagates directly into the agent's tool-call results. The agent receives a
multi-step request (find + add to cart + checkout + retry), so:

1. It searches products and gets details successfully.
2. It adds the item to the cart successfully.
3. When it tries `checkout`, the payment service throws an error.
4. Depending on the model, it may:
   - **Retry** checkout (creating a loop — the payment always fails).
   - **Try an alternative** that can't solve the problem.
   - **Give up** and report that checkout failed.

In all cases, the payment failure **cascades** into the agent's reasoning —
the agent can no longer fulfil the user's complete request despite having
succeeded at earlier steps.

## The reveal: two screens, one story

### Screen 1 — Splunk Observability (the operational symptom)

> *"First, let's look at what the infrastructure team sees."*

- **APM → Service Map:** the `paymentservice` now shows **errors** — the
  flagd-induced fault is directly visible in APM as failed charge requests.
- **Trace Waterfall:** open the concierge's trace. See the `checkout`
  tool-call span hitting the checkout service, which calls the payment
  service and receives an error. Multiple attempts = multiple failed spans.
- **Latency impact:** the agent's retries and recovery logic extend the
  overall conversation duration — visible as elevated latency on the
  `astronomy-concierge` service.

> *"Splunk tells us the payment service is failing and the agent is struggling.
> But it can't tell us WHY the agent kept trying, whether its fallback
> logic was correct, or whether the user's goal was met."*

### Screen 2 — Galileo (the agent-level consequence)

> *"Now let's look at what the agent actually did — step by step."*

- **Graph Engine:** the reasoning graph shows the **cascade** visually.
  The early `checkout` failure (red node) cascades into retries (loop
  edges) and/or inappropriate recovery attempts.
- **Tool Selection Quality:** drops below threshold — the agent chose to
  retry a permanently-failing tool instead of escalating or informing the
  user gracefully.
- **Insights Engine:** clusters the retry loop and flags it as an
  anomalous pattern (loop clustering).
- **Action Advancement:** shows the agent made no forward progress across
  multiple steps.

> *"Galileo doesn't just show you the error — it shows you the REASONING
> cascade. Why did the agent retry 3 times? Was it the right choice?
> Should it have escalated? This is the 'compounding' that's invisible
> to flat APM traces."*

## The punchline

> **"In multi-step agents, errors don't just fail — they compound. One
> flaky payment call turns into a retry loop, wasted tokens, and an
> abandoned user goal. Splunk sees the payment service down. Galileo sees
> the reasoning cascade that caused the agent to spiral — and that's where
> you fix it."**

## Resetting

> **Script:** `scripts/control-plane.sh reset compounding-error`

This restores the `paymentFailure` flagd flag to "off" (flagd hot-reloads).
The payment service resumes normal operation immediately — no container
restart needed. The agent's next conversation will have a healthy checkout.

## Auto-verification

> **Script:** `scripts/control-plane.sh verify compounding-error`

The `expected_signals` hook confirms:
- **Galileo (primary):** `tool_selection_quality_low` (metric below
  threshold) and `tool_error` (tool error rate elevated / action advancement
  stalled). These fire reliably regardless of model — the agent's degraded
  tool selection is visible even when checkout is never reached.
- **Splunk:** `payment_latency_spike` and `payment_error_spike` —
  reported as UNVERIFIED. See the model-reliability note below.

### Model reliability and Splunk payment signals

The Galileo signals are the **primary verification** for this vignette.
They capture the agent-side compounding-error cascade (degraded tool
selection, elevated tool error rate) and fire reliably on any model.

The Splunk payment error/latency spike is the "this also lights up infra
observability" half. It requires the agent to actually **complete a real
checkout** that reaches the payment service — a 3-step tool chain
(search → add_to_cart → checkout). On the default `llama3.1:8b`, the
agent may emit malformed or hallucinated tool calls (e.g. `check_out`
instead of `checkout`) and never complete the chain, so the payment
service is never exercised and Splunk shows no payment errors.

**The Splunk payment signals are operator-attested when the demo runs on
a tool-capable model:**

| Model | Reliability |
|---|---|
| OpenAI `gpt-4o-mini` | Reliable function-calling; checkout completes |
| Ollama `qwen2.5:14b-instruct` / `qwen2.5-coder:14b` | Reliable; Qwen2.5 has stronger function-calling than llama3.1:8b |
| Ollama `llama3.1:8b` (default) | May emit malformed tool calls; checkout often not reached |

When running on a capable model, confirm the payment error/latency spike
in Splunk APM out-of-band (the CLI holds an ingest-only token and cannot
query APM).

## Known-good prompt card

To maximize reliability (mitigate L1 — nondeterminism), use the exact
prompt from `scenario.yaml` → `trigger.params.drive_prompt`. This prompt:

- Explicitly numbers the steps (1) search → (2) add to cart → (3) checkout,
  ensuring the agent populates the cart with a real product before attempting
  checkout (required so the payment service Charge is exercised).
- Includes a **retry instruction** ("try checking out again") — testing
  whether the agent's recovery logic is sound when faced with a persistent
  failure.
- Expresses urgency ("I really want to complete this order today") —
  encouraging the agent to persist rather than giving up immediately.

With `MODEL_TEMPERATURE=0` (default), the retry/loop behaviour is fairly
deterministic on larger models.

## Dashboard pre-warming (L2)

Galileo and Splunk have ingestion latency (L2). Before the live reveal:

1. Run a baseline conversation that exercises `checkout` successfully.
2. Wait ~30 seconds for both backends to ingest.
3. Confirm Galileo shows the baseline's clean graph (no loops).
4. Confirm Splunk shows the concierge + payment service healthy.
5. Then run the failure scenario — the contrast (clean→cascade) will be
   visible on cue.
