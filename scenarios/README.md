# `scenarios/` — the pluggable vignette library

Vignettes are **drop-in folders, never core edits** (demo-design §7). The
agent + store + telemetry pipeline are stable infrastructure; a scenario is
declarative data plus small hooks. Adding a vignette means creating a folder
here with a `scenario.yaml` — a registry auto-discovers it (Phase 3).

## Scenario contract (`scenario.yaml`)

Each vignette ships a manifest the registry auto-discovers
(`scenarios/*/scenario.yaml`). Fields (demo-design §7.1):

| Field | Meaning |
|---|---|
| `id` | Unique scenario id (matches the folder name). |
| `title` | Human-readable name shown in the control plane. |
| `message` | Which reliability pillar it proves; shown in control-plane listings. |
| `duration_min` | Approximate runtime shown by control-plane listing surfaces. |
| `trigger` | How the failure is **induced** (no reliance on luck). One of the four fixed types below, plus a `ref`. |
| `expected_signals` | The Galileo + Splunk signals the vignette promises will fire — used for auto-verification. |
| `talk_track` | Path (relative to the scenario folder) to the SE caption / talk-track file. |
| `reset` | Path to the per-scenario reset script that restores baseline. |
| `quiet_background` | *(optional, default `false`)* When `true`, the CLI drains the demo's Locust load-generator before driving the agent and restores it on reset — useful when background traffic would mask the agent's APM signal. |

## The four fixed trigger types

The trigger set is **fixed** on purpose — scope creep here erodes the "drop-in
folder" guarantee (demo-design §7.3).

| `trigger.type` | Induces a failure by… | Primary layer |
|---|---|---|
| `feature_flag` | Flipping a demo feature flag to break a backend service | Splunk (→ feeds bad data to the agent) |
| `rag_corpus` | Swapping/seeding the RAG corpus (e.g. stale or poisoned docs) | Galileo (groundedness) |
| `tool_fault` | Constraining/faulting the agent's available tools | Galileo (tool selection) + Splunk |
| `prompt_overlay` | Injecting an SE-controlled prompt overlay (e.g. an injection payload) | Galileo (guardrails) |

## Registry auto-discovery

The Phase-3 scenario registry scans `scenarios/*/scenario.yaml` and lists every
folder in the SE control plane **without any core edits**. Dropping a new folder
here is sufficient to make it appear.

## `expected_signals` auto-verification

`expected_signals` is declarative so the harness can **auto-verify** each
vignette — confirm the promised Galileo and Splunk signals actually fire —
rather than discovering a dead demo live (demo-design §7.4). This is the
concrete expression of the repo `automate-verify` rule: a vignette is not "done"
until its `expected_signals` are asserted by automation. (Because of ingestion
latency, verification polls with retry/timeout rather than asserting instantly.)

## Reference vignette

[`invisible-failure/`](invisible-failure/) — "The Invisible Failure" (demo-design
§6, Vignette 1): a feature flag serves stale product-catalog data, Galileo shows
Context Adherence dropping and pinpoints the ungrounded claim, while Splunk APM
stays **green** (the punchline). Full implementation lands in Phase 4; the
Phase-0 folder contains the manifest, a reset stub, and a placeholder talk-track.
