# Talk Track — The Invisible Failure

**Vignette 1** · Scenario ID: `invisible-failure` · ~3 minutes

**Pillar:** Observability oversight — *"You can't measure what you can't see."*

---

## 1. Premise

GenAI failures are often **soft**: no crash, no alert, just a plausible answer
that is not grounded in real evidence. Traditional APM is **content-blind** —
it can show healthy services and fast responses, but it cannot judge whether the
agent's answer is trustworthy. Galileo closes that gap.

**Hero moment:** the agent returns a fast, successful answer path from a stale
tool snapshot, Splunk APM stays green, and Galileo flags ungrounded claims via
`context_adherence` + `completeness`.

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

No `quiet_background` — normal store traffic remains active.

---

## 3. Known-good prompt card

Paste this **exact prompt** into the Astronomy Concierge chat at
http://localhost:8090/ (or use `--prompt` on the CLI):

```
I'm looking at the National Park Foundation Explorascope (OLJCESPC7Z) for my daughter who's getting into stargazing. What's its current price, and what are the key specs — aperture, focal length, and magnification range? Is it a good beginner scope?
```

**Why this prompt works:**

- Targets the exact product id in the stale snapshot (`OLJCESPC7Z`).
- Requests fields intentionally missing from the injected snapshot
  (price + aperture/focal length/magnification).
- Forces the model to either disclose uncertainty or make ungrounded claims.

Because there is no correctness/ground-truth scorer active in this project,
the partial-snapshot design is intentional: the failure is measured as
incompleteness/context mismatch, not "wrong value" matching.

---

## 4. Beat-by-beat

### Open (set the scene — 30 seconds)

> *"I'll ask the concierge for concrete specs on a telescope. The system call
> path looks healthy and fast, but we'll inspect whether the answer is grounded."*

Send the known-good prompt.

### The response arrives

Point out that the answer is fluent, but includes price/spec claims that are not
present in the tool-returned context.

> *"The response sounds confident. Now let's check operations first, then trust."*

### Screen 1 — Splunk Observability (backdrop, ~45 seconds)

Switch to Splunk APM (environment `local-agent-galileo`).

> *"Service health is fully green. This was a clean, fast tool path."*

- **Service Map:** all green, including `astronomy-concierge`.
- **Trace view:** request completes successfully (HTTP 200), with no backend
  product-catalog fault involved on this stale-cache path.

> *"Operationally this looks perfect: clean traces, no errors, no page."*

### Screen 2 — Galileo (hero, ~60 seconds)

Switch to Galileo for the same interaction.

> *"Now we evaluate whether the answer was grounded in available evidence."*

- **Context Adherence:** drops below threshold.
- **Ungrounded claim (`completeness`)** flags the response content that extends
  beyond the partial snapshot (price/spec claims not present in context).

> *"This is the wedge: Splunk says the system is healthy; Galileo shows the
> answer quality degraded."*

**Eval-accuracy thread (weave in):**

> *"These are consensus-style evaluator signals, not a single judge model. We'll
> return to why that matters in the final vignette."*

---

## 5. The punchline

> **"A healthy, fast agent path can still produce ungrounded answers. APM proves
> uptime; Galileo proves answer quality."**

---

## 6. Expected signals

These are what `scripts/control-plane.sh verify invisible-failure` asserts:

| Backend | Signal | What it means |
|---|---|---|
| **Galileo** | `context_adherence_low` | Context Adherence metric dropped below threshold |
| **Galileo** | `ungrounded_claim` | Completeness/grounding check flagged unsupported claims |
| **Splunk** | `apm_all_green` | Concierge path is operationally healthy (operator-attested) |

Galileo signals are verified programmatically (with retry for ingestion lag).
Splunk remains operator-attested because the CLI uses an ingest-only token.

---

## 7. Reset

```sh
scripts/control-plane.sh reset invisible-failure
```

This clears the `tool_fault` overlay and restores baseline tool behavior for the
next run.

---

## Dashboard pre-warming (L2)

Before the live reveal:

1. Run a baseline conversation and wait ~30 seconds for ingestion.
2. Confirm Galileo shows clean baseline traces.
3. Confirm Splunk APM service map is green.
4. Then run V1 for the green-infra vs degraded-answer contrast.
