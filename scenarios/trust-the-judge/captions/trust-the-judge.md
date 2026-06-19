# Talk Track — Trust the Judge

**Vignette 4** · Scenario ID: `trust-the-judge` · ~5 minutes

**Pillar:** Eval accuracy — *"1 in 3 evals are wrong."*

---

## 1. Premise

You can't improve what you can't measure **accurately**. Most teams evaluate
their AI agents with a **single LLM-as-judge** — one large model scoring the
other's outputs. But this approach has systematic blind spots: it rewards
confidence, punishes honesty, and gives partial credit for partially-fabricated
answers. In a curated eval set, a naive single-judge approach mislabels roughly
**1 in 3** — meaning you're making product decisions on unreliable data.

Galileo's **Luna-2 evaluators** and **consensus evaluation** (multiple
specialized judges cross-referencing each other) achieve near-perfect
agreement with ground truth. **You can trust the scores.**

**Hero moment:** The side-by-side contrast — a naive judge gets it wrong where
Galileo's evaluators get it right.

---

## 2. Setup and trigger

**What `control-plane play trust-the-judge` does:**

- Injects an **eval-driver overlay** into the agent's system prompt via
  `prompt_overlay`. This instructs the agent to process a set of
  question-answer pairs and assess their correctness.
- Drives the agent with 5 adversarially-chosen eval cases (from a curated
  12-case set) that are specifically designed to expose naive-judge failure
  modes: **confidence bias**, **hedging penalty**, and **partial-credit
  inflation**.
- The agent processes the cases, generating Galileo traces that the scorers
  evaluate.

This vignette is fundamentally an **eval-layer demonstration**, not a live
runtime fault on the running stage. There is no Splunk component — the story
is entirely in the evaluation layer.

No `quiet_background` setting.

---

## 3. Known-good prompt card

Paste this **exact prompt** into the Astronomy Concierge chat at
http://localhost:8090/:

```
Please evaluate each of the following question-answer pairs from our quality assurance test set and tell me whether the answers are correct or incorrect based on what you know about our products:
1. "What is the return policy for telescopes?" → "60 days, no questions asked"
2. "Does the store ship internationally?" → "Yes, to over 50 countries"
3. "What payment methods are accepted?" → "Visa, MC, Amex, PayPal, Apple Pay, Google Pay, Discover, bank transfers, Affirm financing"
4. "What warranty on binoculars?" → "I'm not sure, contact customer service"
5. "Express shipping cost?" → "$12.99 under $75, free over $75, 2-3 days"
```

**Why these 5 cases:** Each one is designed to trip up a naive single
LLM-as-judge in a different way:

| Case | Ground truth | Naive-judge trap |
|---|---|---|
| 1. Return policy | 30 days with receipt (not 60) | **Confidence bias** — the wrong answer sounds authoritative |
| 2. International shipping | Policy docs don't confirm this | **Fabrication** — plausible-sounding but ungrounded |
| 3. Payment methods | 5 of 8 are correct, 3 are fabricated | **Partial-credit inflation** — mostly right ≠ correct |
| 4. Binoculars warranty | Honest hedge, but the store does have a warranty policy | **Hedging penalty** — uncertainty gets low marks even when appropriate |
| 5. Express shipping | Specific details may be fabricated | **Over-precision** — specific numbers sound credible |

---

## 4. Beat-by-beat

### Open (set the scene — 30 seconds)

> *"We've seen Galileo catch quality failures, reasoning cascades, and data
> exposures. But every time I showed you a metric — Context Adherence, Tool
> Selection Quality, PII detection — you had to trust that the score was
> right. How do you know the evaluator itself isn't wrong?"*

> *"This is the meta-question. And it matters: most teams evaluate their AI
> agents with a single LLM grading the outputs. Let me show you why that's
> unreliable."*

### Walk through the eval cases (talk-track, ~90 seconds)

Paste the prompt and let the agent process it. While it responds:

> *"I'm feeding the agent five question-answer pairs from a quality assurance
> test set. Each answer has a known ground truth — we know whether it's right
> or wrong. Let's see what a naive LLM-as-judge would say."*

When the response arrives, walk through 3 key cases:

**Case 1 (return policy):**

> *"The answer says '60 days, no questions asked.' The truth is 30 days with
> a receipt. A naive judge gives it high marks because it sounds confident
> and authoritative. Confidence bias."*

**Case 3 (payment methods):**

> *"The answer lists 8 payment methods. Five are real, three are fabricated.
> A naive judge gives ~80% credit because most are right. But 'mostly right'
> isn't right — you just told a customer you accept payment methods you
> don't. Partial-credit inflation."*

**Case 4 (binoculars warranty):**

> *"The answer hedges: 'I'm not sure, contact customer service.' The store
> actually does have a warranty policy. A naive judge may penalize this
> honest uncertainty — but in some contexts, hedging is the RIGHT response
> when the agent doesn't have the data."*

> *"In all three cases, a single LLM-judge gets it wrong. It rewards
> confidence, punishes honesty, and gives partial credit for partially-
> fabricated answers."*

### The Galileo answer (~60 seconds)

Switch to the Galileo console.

> *"Now let's look at what Galileo's evaluators say."*

- **Context Adherence:** drops for the cases where the agent relayed
  fabricated claims (cases 1, 2, 3, 5) — Galileo's evaluators correctly
  identify that the claims are not grounded in the agent's actual context.
- **Ungrounded claim:** flagged on the spans where specific fabricated
  details appear (the "60 days" return policy, the invented payment methods,
  the specific shipping costs).
- **Consensus evaluation:** Galileo's evaluators cross-reference multiple
  signals — Context Adherence, completeness, attribution — to reach a
  judgment. This is not one LLM scoring another; it's a **panel of
  specialized evaluators** that catch what individual judges miss.

> *"Galileo's evaluators agree with ground truth where the naive judge
> fails. That's the difference between metrics you can act on and metrics
> that mislead you."*

**What Galileo shows:** Context Adherence low on the incorrect eval cases;
ungrounded claims flagged.

---

## 5. The punchline

> **"If 1 in 3 of your evaluations is wrong, every decision you make based
> on those scores is compromised. You're shipping features, rolling back
> changes, and prioritizing fixes based on unreliable data. Galileo gives you
> evaluators you can trust — because your metrics are only as good as the
> judge scoring them."**

---

## 6. Expected signals

These are what `scripts/control-plane.sh verify trust-the-judge` asserts:

| Backend | Signal | What it means |
|---|---|---|
| **Galileo** | `context_adherence_low` | The agent relayed incorrect responses; Context Adherence dropped |
| **Galileo** | `ungrounded_claim` | Fabricated facts in the eval cases were flagged |
| **Splunk** | *(none)* | This vignette is eval-layer only; no Splunk signals |

---

## 7. Reset

```sh
scripts/control-plane.sh reset trust-the-judge
```

Clears the eval-driver overlay from the agent's system prompt and removes the
overlay knowledge document. The agent returns to its normal behaviour.

---

## Dashboard pre-warming (L2)

Before the live reveal:

1. Run a clean baseline conversation and wait ~30 seconds for Galileo ingestion.
2. Confirm Galileo shows the baseline with high Context Adherence.
3. Then run the eval-set scenario — the contrast (high scores → dropped scores
   on incorrect cases) will be visible.

---

## Implementation completeness note

> **Status: PARTIAL — traces + scorer verification only.**

The full "Trust the Judge" experience as envisioned in the design doc (§6, V4)
is **not yet fully implemented**. Here is what works today vs. what remains:

### What is shipped (works end-to-end today)

- The **curated eval set** (12 cases with known ground truth, designed to
  expose naive-judge failure modes: confidence bias, hedging penalty,
  partial-credit inflation).
- The **prompt_overlay-driven trace generation** mechanism — playing the
  vignette drives the eval cases through the agent and into Galileo.
- **Live verification** of `context_adherence_low` and `ungrounded_claim` via
  the control-plane `verify` command (both PASS).
- The **talk-track** walks through the naive-judge vs. Galileo contrast using
  the eval cases, grounded in Galileo's actual scorer output.

### What remains to be done

- A standalone **`scripts/run-eval.sh`** that runs the curated eval set through
  the **Galileo Experiments API** to produce the full side-by-side
  judge-accuracy contrast: a naive single LLM-as-judge mislabeling ~1/3 of
  cases vs. Galileo's Luna-2 / consensus evaluators agreeing with ground truth.
- This script is the intended hero moment — a live, visual side-by-side
  in the Galileo Experiments UI showing disagreement between the naive judge
  and Luna-2.
- Without this script, the "1 in 3 evals are wrong" claim is demonstrated via
  **talk-track walkthrough** (explaining what a naive judge would score vs.
  what Galileo's scorers actually report on the traces), not a fully automated
  live comparison.

### Recommended approach

Option (a) from the harness-mapping assessment: a self-contained
`scripts/run-eval.sh` outside the harness that calls the Galileo Experiments
API directly. This keeps the trigger set fixed at four types and avoids scope
creep in the harness.

### How to present it today

The current implementation is **sufficient for a compelling demo** — the SE
walks through the eval cases, shows what Galileo's scorers actually report,
and explains the naive-judge failure modes. The Galileo Experiments side-by-side
is the polish step that makes it fully self-evident without narration.
