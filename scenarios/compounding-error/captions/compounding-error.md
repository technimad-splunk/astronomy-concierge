# Talk Track — The Compounding Error

**Vignette 2** · Scenario ID: `compounding-error` · ~4 minutes

**Pillar:** Error compounding — *"In multi-step agents, one early bad step
cascades into later steps."*

---

## 1. Premise

Traditional software fails loud: a 500 error triggers an alert. But GenAI
agents **compound** failures silently. A flaky backend doesn't crash the
agent — it retries, loops, picks wrong alternatives, or gives up. Each retry
doubles latency and cost. Each wrong tool pick moves the agent further from
the user's goal. Unlike Vignette 1, **Splunk lights up here too** — but it
can only show the operational symptom (payment service down), not the
agent-level reasoning cascade.

**Hero moment:** Galileo's **Graph Engine** visualizes the cascade;
**Tool Selection Quality** drops; the **Insights Engine** clusters the
failure pattern.

---

## 2. Setup and trigger

**What `control-plane play compounding-error` does:**

- Flips the `paymentFailure` flagd feature flag to `100%` (every payment
  charge fails; hot-reloads, no container restart).
- The concierge's `checkout` tool calls `POST /api/checkout` through the
  frontend-proxy, which calls the payment service to charge the card — the
  flagd fault makes every charge fail.
- The agent receives a multi-step request (search → add-to-cart → checkout),
  succeeds at the first two steps, then hits the payment failure on checkout.

**`quiet_background: true`** — the harness drains the Locust load generator
before driving the agent, so the payment-error spike in Splunk APM is
attributable to the agent's checkout attempt, not masked by normal traffic.

---

## 3. Known-good prompt card

Paste this **exact prompt** into the Astronomy Concierge chat at
http://localhost:8090/:

```
I want to buy the Eclipsmart Travel Refractor Telescope today. Please do each step in order: (1) search the catalog for that telescope and note its exact product id and price from the search results, (2) add that product to my cart using the product id you found, (3) check out to complete my purchase. If checkout fails, please try checking out again — it might be a transient issue. I really want to complete this order today.
```

**Why this prompt works:**

- Explicitly numbers the steps (1→2→3), ensuring the agent populates the cart
  with a real product before attempting checkout (required so the payment
  service charge is exercised).
- Names a real catalog product (**Eclipsmart Travel Refractor Telescope**,
  id `1YMWWN1N4O`) — an invented name would make search return nothing.
- Includes a **retry instruction** ("try checking out again") — testing whether
  the agent's recovery logic is sound against a persistent failure.
- Expresses urgency ("I really want to complete this order today") — encouraging
  the agent to persist rather than giving up immediately.

**Follow-up turn (if the agent asks for confirmation):** The agent may ask
"Should I proceed with checkout?" or similar. Reply:

```
Yes, please go ahead and check out.
```

**Model reliability note:** On **OpenAI `gpt-4o-mini`** or **Ollama
`qwen2.5:14b-instruct`**, the full search→add→checkout chain completes and the
payment failure fires. On the default **`llama3.1:8b`**, the agent may emit
malformed tool calls and never reach checkout — Galileo signals still fire
(degraded tool selection), but the Splunk payment-error spike may not appear.

---

## 4. Beat-by-beat

### Open (set the scene — 30 seconds)

> *"Now let's see what happens when the agent hits a multi-step problem.
> I'm going to ask it to find a telescope, add it to my cart, and check out
> — a realistic e-commerce workflow."*

Paste the known-good prompt. While the agent works:

> *"Watch the steps: it searches the catalog, finds the product, adds it to
> the cart... now it's trying to check out."*

### The response arrives

The agent will report checkout failure. Depending on the model, it may:
- **Retry** checkout (creating a loop — the payment always fails).
- **Try an alternative** that can't solve the problem.
- **Give up** and report that checkout failed.

> *"The agent found the product and added it to the cart — those steps
> worked. But checkout failed because of a payment error. Now watch what
> happens: does it retry? Does it spiral? Does it give up gracefully?"*

### Screen 1 — Splunk Observability (the operational symptom, ~45 seconds)

Switch to Splunk APM (environment `local-agent-galileo`).

> *"First, let's look at what the infrastructure team sees."*

- **Service Map:** the `paymentservice` now shows **errors** (red) — the
  flagd-induced fault is directly visible as failed charge requests.
- **Trace Waterfall:** open the concierge's trace. See the `checkout`
  tool-call span hitting the checkout service, which calls the payment
  service and receives an error. Multiple attempts = multiple failed spans.
- **Latency:** the agent's retries and recovery logic extend the conversation
  duration — visible as elevated latency on `astronomy-concierge`.

> *"Splunk tells us the payment service is failing and the agent is
> struggling. But it can't tell us WHY the agent kept trying, whether its
> fallback logic was correct, or whether the user's goal was met."*

**What Splunk shows:** payment service errors + latency spike; concierge
elevated latency from retries.

### Screen 2 — Galileo (the agent-level consequence, ~60 seconds)

Switch to the Galileo console.

> *"Now let's look at what the agent actually did — step by step."*

- **Graph Engine:** the reasoning graph shows the **cascade** visually.
  The early `checkout` failure (red node) cascades into retries (loop edges)
  and/or inappropriate recovery attempts.
- **Tool Selection Quality:** drops below threshold — the agent chose to
  retry a permanently-failing tool instead of escalating or informing the
  user gracefully.
- **Insights Engine:** clusters the retry loop and flags it as an anomalous
  pattern (loop clustering).

> *"Galileo doesn't just show you the error — it shows you the REASONING
> cascade. Why did the agent retry three times? Was it the right choice?
> Should it have escalated? This is the 'compounding' that's invisible to
> flat APM traces."*

**What Galileo shows:** Tool Selection Quality low (< 0.5); tool error
flagged; reasoning graph showing the cascade path.

**Eval-accuracy thread (weave in):**

> *"Again, these aren't single-LLM scores. Galileo's Tool Selection Quality
> metric uses consensus evaluation to determine whether the agent's tool
> choices were appropriate — not just whether a tool call succeeded."*

---

## 5. The punchline

> **"In multi-step agents, errors don't just fail — they compound. One flaky
> payment call turns into a retry loop, wasted tokens, and an abandoned user
> goal. Splunk sees the payment service down. Galileo sees the reasoning
> cascade that caused the agent to spiral — and that's where you fix it."**

---

## 6. Expected signals

These are what `scripts/control-plane.sh verify compounding-error` asserts:

| Backend | Signal | What it means |
|---|---|---|
| **Galileo** | `tool_selection_quality_low` | Tool Selection Quality metric dropped below threshold |
| **Galileo** | `tool_error` | Tool error rate elevated (action advancement stalled) |
| **Splunk** | `payment_latency_spike` | Payment service latency elevated — operator-attested |
| **Splunk** | `payment_error_spike` | Payment service error rate elevated — operator-attested |

Galileo signals are verified programmatically. Splunk signals are
operator-attested (ingest-only token; confirm visually in Splunk APM).

The Galileo signals fire reliably regardless of model (the agent's degraded
tool selection is visible even if checkout is never fully reached). The Splunk
payment signals require the agent to complete the full search→add→checkout
chain (see model reliability note above).

---

## 7. Reset

```sh
scripts/control-plane.sh reset compounding-error
```

This restores the `paymentFailure` flagd flag to `off` (hot-reloads). The
payment service resumes normal operation immediately — no container restart
needed. The agent's next checkout will succeed.

---

## Dashboard pre-warming (L2)

Before the live reveal:

1. Run a baseline conversation that exercises `checkout` successfully (e.g.
   "Find the Solar System Color Imager, add it to my cart, and check out").
2. Wait ~30 seconds for both backends to ingest.
3. Confirm Galileo shows the baseline's clean graph (no loops).
4. Confirm Splunk shows the concierge + payment service healthy.
5. Then run the failure scenario — the contrast (clean → cascade) will be
   visible on cue.
