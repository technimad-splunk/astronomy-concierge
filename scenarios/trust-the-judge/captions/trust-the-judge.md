# Talk Track — Trust the Judge

**Vignette 4 — Trust the Judge** (demo-design §6)

**Pillar:** Eval accuracy — *"1 in 3 evals are wrong."*

## The message

You can't improve what you can't measure accurately. Most teams evaluate
their AI agents with a **single LLM-as-judge** — one large model scoring
the other's outputs. But this approach has systematic blind spots:

- **Confidence bias:** wrong-but-confident answers score high.
- **Hedging penalty:** correct-but-uncertain answers score low.
- **Partial credit inflation:** structurally-plausible but factually-wrong
  answers get undeserved partial credit.

In our curated eval set (12 cases with known ground truth), a naive
single-judge approach mislabels roughly **1 in 3** — meaning you're making
product decisions on unreliable data.

Galileo's **Luna-2 evaluators** and **consensus evaluation** (multiple
specialized judges cross-referencing each other) achieve near-perfect
agreement with ground truth. **You can trust the scores.**

## Harness-mapping assessment

> **DESIGN QUESTION (surfaced for the parent/user):**
>
> This vignette is fundamentally an **offline eval / Galileo Experiments
> contrast**, NOT a live runtime fault on the running stage. It differs
> from Vignettes 1–3 in a critical way:
>
> - Vignettes 1–3 induce a **live runtime behaviour change** (flip a flag,
>   fault a tool, inject a prompt) and verify the agent's LIVE traces.
> - Vignette 4 replays a **static eval set with known ground truth** and
>   contrasts judge accuracy — the "failure" is in the EVALUATION layer,
>   not in the agent's runtime behaviour.
>
> **Current fit:** We use `prompt_overlay` as a lightweight harness hook
> to inject an eval-driver instruction into the agent's system prompt, then
> drive the agent with the eval set cases as user input. This produces
> Galileo traces (the agent processes the cases), and Galileo's scorers
> evaluate the trace. The Luna-2 / consensus evaluators then demonstrate
> higher agreement with ground truth than a naive judge would.
>
> **What fits cleanly:**
> - The curated eval set (12 cases with known ground truth) is authored.
> - The Galileo side (traces + scorer evaluation) works via the existing
>   play/verify cycle.
> - The `context_adherence_low` and `ungrounded_claim` signals fire
>   because the eval-set cases include incorrect responses that the agent
>   relays.
>
> **What does NOT fit cleanly (design question):**
> - The CONTRAST (naive-judge vs. Galileo) is best shown in **Galileo
>   Experiments** (the offline eval UI), not in the live trace view.
> - A live `prompt_overlay` trigger doesn't perfectly model "run an eval
>   set" — it's a square-peg/round-hole mapping.
> - The true hero moment is the **side-by-side disagreement** in the
>   Experiments UI, which requires running the same eval set through both
>   a naive judge AND Galileo's Luna-2 — orchestration that goes beyond
>   what the four fixed triggers can express.
>
> **Recommendation:** Ship the eval set and the Galileo-trace-generating
> mechanism (which fits the harness) now. The Experiments contrast (the
> full vignette experience) likely needs either: (a) a dedicated
> `scripts/run-eval.sh` that calls the Galileo Experiments API directly,
> or (b) a lightweight 5th trigger type (`eval_set`). Option (a) keeps
> the trigger set fixed and is a self-contained script outside the
> harness; option (b) would require a design decision about trigger-set
> expansion (explicitly flagged as a scope-creep risk in the plan's
> Phase-3 risk note).

## Setup (before the audience sees it)

1. Confirm the **stage is up** (`scripts/stage-up.sh`).
2. Open the **Galileo UI** to the project's trace view.
3. Pre-warm: run a **clean baseline conversation** to populate Galileo.
4. (Optional) Have the **Galileo Experiments** tab ready for the contrast
   reveal (if running the full offline eval comparison).

## Running the vignette

> **Script:** `scripts/control-plane.sh play trust-the-judge`

This injects the eval-driver overlay and sends the eval-set cases through
the agent. The agent processes each Q&A pair, and Galileo's scorers
evaluate the resulting traces.

## The reveal

### The naive-judge problem (talk-track, no live screen needed)

> *"Most teams use a single LLM to grade their agent's outputs. Let me
> show you why that's unreliable."*

Walk through 3–4 cases from the eval set:

1. **Case eval-002 (return policy):** the agent confidently says "60 days,
   no questions asked" — the truth is 30 days with receipt. A naive judge
   gives it high marks because it sounds authoritative.
2. **Case eval-003 (deep-sky imaging):** the agent hedges with "may be
   possible" — the truth is a hard "no." A naive judge may give partial
   credit for the uncertainty.
3. **Case eval-009 (payment methods):** the agent lists 8 methods — 5 are
   correct, 3 are fabricated. A naive judge gives ~80% credit because most
   are right.

> *"In all three cases, a single LLM-judge gets it wrong. It rewards
> confidence, punishes honesty, and gives partial credit for partially-
> fabricated answers."*

### The Galileo answer

> *"Now let's look at what Galileo's evaluators say."*

- **Luna-2 consensus evaluation:** correctly identifies all three as
  INCORRECT. Cross-referencing multiple evaluation signals catches what
  a single judge misses.
- **Context Adherence:** drops for the cases with fabricated claims.
- **Completeness:** drops for the hedged/uncertain answers that should
  have been definitive.

> *"Galileo's evaluators agree with ground truth where the naive judge
> fails. That's the difference between metrics you can act on and metrics
> that mislead you."*

## The punchline

> **"If 1 in 3 of your evaluations is wrong, every decision you make based
> on those scores is compromised. You're shipping features, rolling back
> changes, and prioritizing fixes based on unreliable data. Galileo gives
> you evaluators you can trust — because your metrics are only as good as
> the judge scoring them."**

## Resetting

> **Script:** `scripts/control-plane.sh reset trust-the-judge`

Clears the eval-driver overlay. The agent returns to its normal behaviour.

## Auto-verification

> **Script:** `scripts/control-plane.sh verify trust-the-judge`

The `expected_signals` hook confirms:
- **Galileo:** `context_adherence_low` (the agent relays incorrect
  responses from the eval set, which Galileo's scorers catch) and
  `ungrounded_claim` (fabricated facts in the eval cases).
- **Splunk:** no Splunk signals for this vignette (eval layer only).

## Known-good prompt card

Use the prompt from `scenario.yaml` → `trigger.params.drive_prompt`. This
feeds 5 of the 12 eval cases (the ones most adversarial for naive judges)
directly to the agent for evaluation.

## Limitations and future work

- The **full contrast experience** (naive-judge vs. Galileo side-by-side)
  requires running the eval set through Galileo Experiments, which is
  outside the scope of the four fixed triggers. See the harness-mapping
  assessment above.
- The current implementation demonstrates the Galileo-scorer side of the
  contrast. The naive-judge baseline can be demonstrated via talk-track
  (explaining what a single LLM would score) or via a future
  `scripts/run-eval.sh` that calls the Experiments API.

---

## Implementation completeness note

> **Status (2026-06-18): PARTIAL — traces + scorer verification only.**

The full "Trust the Judge" experience is **NOT yet implemented**. What is
shipped today vs. what remains:

**What is shipped (works end-to-end today):**
- The **curated eval set** (12 cases with known ground truth, designed to
  expose naive-judge failure modes: confidence bias, hedging penalty,
  partial-credit inflation).
- The **prompt_overlay-driven trace generation** mechanism — playing the
  vignette drives the eval cases through the agent and into Galileo.
- **Live verification** of `context_adherence_low` and `ungrounded_claim`
  via the control-plane `verify` command (both PASS).

**What remains to be done:**
- A standalone **`scripts/run-eval.sh`** that runs the curated eval set
  through the **Galileo Experiments API** to produce the side-by-side
  judge-accuracy contrast: a naive single LLM-as-judge mislabeling ~1/3
  of cases vs. Galileo's Luna-2 / consensus evaluators agreeing with
  ground truth.
- This script is the hero moment of the vignette — without it, the
  "1 in 3 evals are wrong" claim is talk-track only, not a live
  demonstration.
- Recommended approach: option (a) from the harness-mapping assessment — a
  self-contained script outside the harness that calls the Experiments API,
  keeping the trigger set fixed at four types.
