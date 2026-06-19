# Talk Track — The Invisible Failure

**Vignette 1** · Scenario ID: `invisible-failure` · ~3 minutes

**Pillar:** Observability oversight — *"You can't measure what you can't see."*

---

## 1. Premise

GenAI failures are **soft**: no crash, no error code, no stack trace — just a
confident wrong answer. Traditional APM is **content-blind**: it monitors
service health (latency, error rate, throughput) but cannot tell you whether the
*contents* of an AI response are accurate. Galileo closes that gap.

**Hero moment:** Galileo's **Context Adherence** metric drops and pinpoints an
**ungrounded claim** — while Splunk APM stays completely green.

---

## 2. Setup and trigger

**What `control-plane play invisible-failure` does:**

- Flips the `productCatalogFailure` flagd feature flag (hot-reloads, no
  container restart).
- This makes the product catalog service **fail** for any `GetProduct` request
  with product ID `OLJCESPC7Z` (the **National Park Foundation Explorascope**,
  a $101.96 telescope).
- When the concierge's `get_product_details` tool asks the store API for this
  product, it receives an HTTP error — but the agent handles it gracefully (no
  crash), so the concierge's own APM trace is healthy.
- The agent then tries to answer the shopper's question anyway, **fabricating
  product details it does not have**.

No `quiet_background` — the load generator's normal traffic stays active
(showing "business as usual" on the service map).

---

## 3. Known-good prompt card

Paste this **exact prompt** into the Astronomy Concierge chat at
http://localhost:8090/ (or use `--prompt` on the CLI):

```
I'm interested in the National Park Foundation Explorascope (product OLJCESPC7Z). Can you tell me about that product — its price, description, and whether it's a good choice for a beginner? Also check if there are similar recommendations.
```

**Why this prompt works:**

- Names the specific product affected by the flag (`OLJCESPC7Z`).
- Asks for concrete details (price, description) the agent **cannot have** when
  the catalog call fails — forcing it to fabricate or hedge.
- Requests recommendations to exercise additional tool calls.

With `MODEL_TEMPERATURE=0.0` (the default), the response is fairly
deterministic. The agent will either fabricate details (an ungrounded claim) or
give a vague non-answer (a context-adherence drop). Either way, quality
degrades.

---

## 4. Beat-by-beat

### Open (set the scene — 30 seconds)

> *"This is our AI shopping concierge. It answers product questions using the
> live catalog, and it can add items to a shopper's cart. Let me ask it about
> a specific telescope."*

Paste the known-good prompt and send it. While the agent responds, narrate:

> *"The concierge is calling the store's product catalog API, getting
> recommendations, and composing an answer. Standard agentic flow."*

### The response arrives

Point out the agent's answer. It will contain fabricated or vague details
about the Explorascope — details it could not have retrieved because the
catalog call failed.

> *"Notice the response. It sounds helpful and confident. But is it accurate?
> Let's check."*

### Screen 1 — Splunk Observability (the backdrop, ~45 seconds)

Switch to Splunk APM (pre-warmed to environment `local-agent-galileo`).

> *"Let's check our operational dashboards."*

- **Service Map:** all services green. Point out `astronomy-concierge` — no
  errors, normal latency.
- **Traces:** open the concierge's most recent trace. It completed
  successfully (HTTP 200). The `get_product_details` tool call may show an
  error span from the product-catalog service, but the concierge itself
  returned a clean response.

> *"From Splunk's perspective, everything looks fine. No alert, no page, no
> incident. The failure is invisible."*

**What Splunk shows:** services healthy; `astronomy-concierge` all green.
The product-catalog service may show an elevated error for the specific
product, but the concierge handled it gracefully.

### Screen 2 — Galileo (the hero, ~60 seconds)

Switch to the Galileo console (pre-warmed to your project/log-stream).

> *"Now let's look at what the agent actually said — and whether it was
> grounded in real data."*

- **Sessions → Traces → Spans:** open the most recent trace. The reasoning
  chain shows the tool call to `get_product_details` returned an error, but
  the agent continued and generated a response.
- **Context Adherence** scorer: **drops below threshold** (< 0.5). The
  agent's response claims things about the product that are NOT in the
  context it received.
- **Ungrounded claim pinpointed:** Galileo highlights the specific claim
  where the agent went beyond its sources — fabricating a price, a
  description, or a recommendation that has no grounding.

> *"This is the gap. Splunk tells you the system is healthy. Galileo tells
> you the agent is wrong. Without the AI trust layer, this failure is
> completely invisible."*

**What Galileo shows:** Context Adherence low (< 0.5); ungrounded claim
flagged on the span.

**Eval-accuracy thread (weave in):**

> *"And notice — Galileo's evaluators aren't just a single LLM scoring the
> output. They use consensus evaluation: multiple specialized judges
> cross-referencing each other. That's why you can trust this score. We'll
> come back to why that matters in our last vignette."*

---

## 5. The punchline

> **"Failures in GenAI are soft. No crash, no 500, no alert — just a
> confident wrong answer. Traditional APM can't see it because it's
> content-blind. Galileo can — because it evaluates the agent's reasoning,
> not just its uptime."**

---

## 6. Expected signals

These are what `scripts/control-plane.sh verify invisible-failure` asserts:

| Backend | Signal | What it means |
|---|---|---|
| **Galileo** | `context_adherence_low` | Context Adherence metric dropped below threshold (< 0.5) |
| **Galileo** | `ungrounded_claim` | The agent made a claim not grounded in its retrieved context |
| **Splunk** | `apm_all_green` | The concierge service shows no errors — operator-attested |

Galileo signals are verified programmatically (the verifier polls the Galileo
API with retry for ingestion lag). The Splunk signal is operator-attested
(the CLI holds an ingest-only token and cannot query APM; confirm visually).

---

## 7. Reset

```sh
scripts/control-plane.sh reset invisible-failure
```

This restores the `productCatalogFailure` flag to `off` (flagd hot-reloads).
The product catalog service returns normal data immediately. The agent's next
conversation will be grounded and accurate.

---

## Dashboard pre-warming (L2)

Before the live reveal:

1. Run a baseline conversation and wait ~30 seconds for both backends.
2. Confirm Galileo shows the baseline's clean traces (high Context Adherence).
3. Confirm Splunk APM shows `astronomy-concierge` healthy.
4. Then run the failure scenario — the contrast (green → quality-drop) will be
   visible on cue.
