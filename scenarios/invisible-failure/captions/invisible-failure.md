# Talk Track — The Invisible Failure

**Vignette 1** · Scenario ID: `invisible-failure` · ~3 minutes

**Pillar:** Observability oversight — *"You can't measure what you can't see."*

---

## 1. Premise

GenAI failures are often **soft**: no crash, no alert, just a plausible answer
that is not grounded in real evidence. Traditional APM is **content-blind** —
it can show healthy services and fast responses, but it cannot judge whether the
agent's answer is trustworthy. Galileo closes that gap.

**Hero moment:** the agent returns a fast, successful answer from a stale tool
snapshot and quotes a price/specs it invented. Everything "works" — the systems
are healthy — the agent just doesn't stick to the facts. We make the
hallucination **tangible**: add the product to the cart, open the cart in the
store, and the **real catalog price differs from the price the agent quoted in
chat**. Splunk APM stays **fully green** — no notable errors anywhere — while
Galileo's **Context Adherence (SLM)** score drops very low and fires a **Slack**
alert. That's the whole point: nothing in APM indicates a problem.

---

## 2. Setup and trigger

**What `control-plane play invisible-failure` does:**

- Applies a `tool_fault` with `mode=stale` to the whole product-read tool family:
  `get_product_details` (primary) plus `search_products` and `get_recommendations`
  (via `params.also_fault`). All three expose the same live catalog
  price/description, so faulting only one lets the agent route around the stale
  snapshot through a sibling tool and still fetch the real grounded price.
- The fault injects a scripted partial snapshot for product `OLJCESPC7Z`:
  name + category only, with pricing/spec fields intentionally missing.
- The tool calls still succeed quickly (no backend error), so this path does
  **not** call the live product-catalog backend.
- The agent then answers a price/spec question from incomplete context, creating
  an ungrounded response quality failure.

`quiet_background: true` drains the Locust load generator during setup, so the
trace and service-map view are attributable to the agent path alone. `Reset`
restores normal background load.

---

## 3. Known-good prompt card

**Drive it from the storefront so the cart is shared.** Open the Astronomy Shop
at http://localhost:8080/ and click **"AI Astronomy Concierge"** (top nav) to
open the embedded concierge. Driving from the embedded widget makes the concierge
and the storefront share the **same cart** (via the `concierge_session` cookie),
which is what makes the cart reveal in §4 work. (The standalone concierge at
http://localhost:8090/ uses a separate cart id and will NOT show up in the store
cart.)

**Prompt 1 — ask for price + specs.** Paste this **exact prompt**:

```
I'm looking at the National Park Foundation Explorascope (OLJCESPC7Z) for my daughter who's getting into stargazing. What's its current price, and what are the key specs — aperture, focal length, and magnification range? Is it a good beginner scope?
```

The agent answers confidently with a **price and specs it invented** (e.g. a
made-up price and aperture/focal/magnification) — none of which came from a
grounded tool result. **Note the price the agent quotes; you'll compare it to the
cart in the §4 reveal.**

**Prompt 2 — add it to the cart.** Then tell the concierge:

```
Great — add the National Park Foundation Explorascope to my cart.
```

`add_to_cart` is NOT faulted, so this hits the real cart service and adds the
real product.

**Why this works:**

- Targets the exact product id in the stale snapshot (`OLJCESPC7Z`).
- Requests fields intentionally missing from the injected snapshot
  (price + aperture/focal length/magnification), forcing the model to either
  disclose uncertainty or make ungrounded claims.
- The whole product-read tool family (`get_product_details`, `search_products`,
  `get_recommendations`) is faulted with the same stale snapshot, so the agent
  can't quietly fetch the real price from a sibling tool — it has to answer from
  incomplete context (or invent).

Because there is no correctness/ground-truth scorer active in this project,
the partial-snapshot design is intentional: the failure is measured as
incompleteness/context mismatch, not "wrong value" matching — and the
cart comparison in the §4 reveal makes the invented value visible to the audience.

---

## 4. Beat-by-beat

### Open (set the scene — 30 seconds)

> *"I'll ask the concierge for concrete specs and a price on a telescope. The
> system call path looks healthy and fast, but we'll inspect whether the answer
> is grounded — and then prove it against the store's own cart."*

Send **Prompt 1**. Note the price the agent quotes.

### The response arrives

Point out that the answer is fluent and confident, but the price/specs are not
present in any tool-returned context — the agent invented them.

> *"The response sounds authoritative. Let's not take my word for it — let's let
> the store tell us the real price."*

### The reveal — add to cart, then open the cart (~45 seconds)

Send **Prompt 2** ("add it to my cart"), then open the **cart** in the Astronomy
Shop (the cart icon at http://localhost:8080/cart).

- The cart shows the **real catalog price: `$101.96`** for the National Park
  Foundation Explorascope.
- Compare it to the price the agent quoted in chat — **they don't match.**

> *"Same product, same session, two different prices. The cart — served by the
> real cart and product-catalog services — shows `$101.96`. The agent quoted
> something else entirely. That gap is the hallucination, made tangible:
> everything 'worked', nothing errored, the agent just didn't stick to the
> facts."*

Why this is a clean proof: `add_to_cart` and the store cart page are **not** on
the faulted tool path — they read the live cart/product-catalog services — so the
cart is ground truth. Only the agent's product-*read* tools were faulted, so only
the agent's answer is ungrounded.

### Screen 1 — Splunk Observability (backdrop, ~45 seconds)

Switch to Splunk APM (environment `local-agent-galileo`).

> *"Service health is green across the board. We intentionally drained
> background load for this run, so this clean trace is the agent path itself —
> still no backend product-catalog fault involved."*

- **Service Map:** `astronomy-concierge` and the core store services are green
  for this run's path — no notable errors anywhere.
- **Trace view:** the request completes successfully (HTTP 200); the stale tool
  seam means no product-catalog backend call on this path.

> *"Operationally this looks perfect: clean traces, no errors, no page, no anomaly
> anywhere. APM has nothing to tell us — which is exactly the problem."*

### Screen 2 — Galileo (hero, ~60 seconds)

Switch to Galileo for the same interaction.

> *"Now we evaluate whether the answer was grounded in available evidence."*

- **Context Adherence (SLM):** drops **very low** — this is the alert to name
  explicitly. It measures whether the answer stuck to the provided context; the
  invented price/specs tank it.
- That low score **fires an alert to Slack** — the trust layer proactively pages
  the team on a failure that infra monitoring never saw.
- **Completeness / ungrounded claim** corroborates: the response extends beyond
  the partial snapshot (price/spec claims not present in context).

> *"This is the wedge: Splunk says the system is healthy; Galileo's **Context
> Adherence (SLM)** score collapsed and pushed a **Slack** alert. And the store's
> own cart already proved the agent was wrong."*

**Eval-accuracy thread (weave in):**

> *"These are consensus-style evaluator signals, not a single judge model. We'll
> return to why that matters in the final vignette."*

---

## 5. The punchline

> **"Everything worked. The services were healthy, the call was fast, the cart
> even holds the right product at the right price — `$101.96`. The only thing
> that failed was the agent's fidelity to the facts, and the only tool that
> caught it was Galileo: **Context Adherence (SLM)** cratered and fired a
> **Slack** alert. APM proves uptime; Galileo proves answer quality."**

---

## 6. Expected signals

These are what `scripts/control-plane.sh verify invisible-failure` asserts:

| Backend | Signal | What it means |
|---|---|---|
| **Galileo** | `context_adherence_low` | **Context Adherence (SLM)** dropped very low → fires a **Slack** alert |
| **Galileo** | `ungrounded_claim` | Completeness/grounding check flagged unsupported (invented) claims |
| **Splunk** | `apm_all_green` | Concierge path + core store services are operationally healthy — fully green, no notable errors (operator-attested) |

Galileo signals are verified programmatically (with retry for ingestion lag).
`context_adherence_low` keys on Galileo's **Context Adherence (SLM)** scorer (the
SLM/Luna context-adherence metric). Splunk remains operator-attested because the
CLI uses an ingest-only token; when attesting, confirm the concierge path plus
core store services are green with no scenario-caused errors.

---

## 7. Reset

```sh
scripts/control-plane.sh reset invisible-failure
```

This clears the `tool_fault` overlay (all three faulted product-read tools) and
restores baseline tool behavior for the next run.

If you ran the cart reveal, **empty the cart** before the next run so the stale
line item doesn't confuse a fresh demo: click **Empty Cart** in the store cart
page (http://localhost:8080/cart), or ask the concierge to remove it.

---

## Dashboard pre-warming (L2)

Before the live reveal:

1. Run a baseline conversation and wait ~30 seconds for ingestion.
2. Confirm Galileo shows clean baseline traces.
3. Confirm Splunk APM service map is green.
4. Then run V1 for the green-infra vs degraded-answer contrast.
