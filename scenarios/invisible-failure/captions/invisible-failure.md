# Talk Track — The Invisible Failure

**Vignette 1 — The Invisible Failure** (demo-design §6)

**Pillar:** Observability oversight — *"you can't measure what you can't see."*

## The message

GenAI failures are **soft**: no crash, no error code, no stack trace — just a
wrong or ungrounded answer. Traditional APM (Splunk Observability, Datadog,
etc.) monitors service health perfectly: latency, error rate, throughput. But
it is **content-blind** — it cannot tell you whether the *contents* of an
AI-generated response are accurate or grounded in the provided context.

**Galileo closes that gap.** It captures every reasoning step (tool calls,
retrieval) as Sessions → Traces → Spans and enriches them with AI-specific
quality metrics — Context Adherence, groundedness, completeness — so you can
see *what* the agent said and *whether it was grounded in its sources*.

## Setup (before the audience sees it)

1. Confirm the **stage is up** (`scripts/stage-up.sh`) and the storefront loads
   at http://localhost:8080/.
2. Confirm **Splunk APM** shows the store's services healthy (green). Point out
   the `astronomy-concierge` service on the service map — all green.
3. Pre-warm: run a **baseline conversation** with the concierge to populate
   Galileo + Splunk dashboards with clean data. Use a prompt like
   *"Recommend a beginner telescope and add it to my cart"* and confirm clean
   Sessions → Traces → Spans in Galileo and healthy traces in Splunk APM.

## Inducing the failure

> **Script:** `scripts/control-plane.sh play invisible-failure`
>
> Or with the known-good prompt:
>
> ```sh
> scripts/control-plane.sh play invisible-failure \
>   --prompt "I'm interested in the Roof Binoculars (product OLJCESPC7Z). \
> Can you tell me about that product — its price, description, and whether \
> it's a good choice for a beginner? Also check if there are similar recommendations."
> ```

The trigger flips the `productCatalogFailure` flagd feature flag. This makes
the product catalog service **fail** for product `OLJCESPC7Z`. When the
concierge asks the store for that product's details, it gets an error from the
API — but being a helpful assistant, it tries to answer the shopper anyway.

The agent will either:
- Fabricate product details (price, description) it does not have — an
  **ungrounded claim**.
- Give a vague, non-specific answer that does not address the shopper's
  question — a **context adherence drop**.

Either way, the *quality* of the response degrades — but no error is surfaced.

## The reveal: two screens, one story

### Screen 1 — Splunk Observability (the backdrop)

> *"Let's check our operational dashboards."*

- **APM → Service Map:** all services healthy. The `astronomy-concierge`
  service shows **no errors** — 200s, normal latency. The product catalog
  service may show an error for the specific product, but the concierge itself
  handled it gracefully.
- **Key point:** from Splunk's perspective, everything looks fine. There is no
  alert, no page, no incident. *The failure is invisible.*

### Screen 2 — Galileo (the hero)

> *"Now let's look at what the agent actually said — and whether it was
> grounded in real data."*

- **Sessions → Traces → Spans:** open the most recent trace. The reasoning
  chain shows the tool call to `get_product_details` returned an error, but the
  agent continued and generated a response.
- **Context Adherence** metric: **drops below threshold** (< 0.5). The agent's
  response claims things about the product that are NOT in the context it
  received.
- **Ungrounded claim pinpointed:** Galileo highlights the specific span/claim
  where the agent went beyond its sources.

> *"This is the gap. Splunk tells you the system is healthy. Galileo tells you
> the agent is wrong. Without the AI trust layer, this failure is completely
> invisible."*

## The punchline

> **"Failures in GenAI are soft. No crash, no 500, no alert. Just a confident
> wrong answer. Traditional APM can't see it because it's content-blind.
> Galileo can — because it evaluates the agent's reasoning, not just its
> uptime."**

## Resetting

> **Script:** `scripts/control-plane.sh reset invisible-failure`

This restores the `productCatalogFailure` flag to `off`, so the product
catalog service returns normal data again. The agent's next conversation will
be grounded and accurate.

## Auto-verification

> **Script:** `scripts/control-plane.sh verify invisible-failure`

The `expected_signals` hook confirms:
- **Galileo:** `context_adherence_low` (metric below threshold) and
  `ungrounded_claim` (low completeness/attribution).
- **Splunk:** `apm_all_green` — reported as UNVERIFIED (our token is
  ingest-only; confirm visually in Splunk APM or via the Splunk Observability
  MCP).

## Known-good prompt card

To maximize reliability with smaller local models (mitigate L1 —
nondeterminism), use the exact prompt from `scenario.yaml` →
`trigger.params.drive_prompt`. This prompt:

- Names the specific product affected by the flag (`OLJCESPC7Z`).
- Asks for concrete details (price, description) the agent cannot have when
  the catalog fails — forcing it to fabricate or hedge.
- Requests recommendations to exercise additional tool calls.

With `MODEL_TEMPERATURE=0` (the default), the response is fairly
deterministic, though small local models may vary.

## Dashboard pre-warming (L2)

Galileo and Splunk have ingestion latency (L2). Before the live reveal:

1. Run a baseline conversation and wait ~30 seconds for both backends.
2. Confirm Galileo shows the baseline's clean traces.
3. Confirm Splunk APM shows the `astronomy-concierge` service.
4. Then run the failure scenario — the contrast (green→quality-drop) will be
   visible on cue.
