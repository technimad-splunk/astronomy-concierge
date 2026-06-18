# `control_plane/` — the SE control plane

The SE-facing surface for running guided demos. **CLI first** (a panel is
optional). It is a **stable seam**: adding scenarios must never require changing
the control plane (demo-design §7.2).

> **Implementation (Phase 3):** the control plane is this Python package
> [`control_plane/`](.) (run via
> [`scripts/control-plane.sh`](../scripts/control-plane.sh) or
> `python -m control_plane`). This README is the SE-facing doc; the package
> holds the machinery (registry, manifest loader, the four trigger handlers, the
> pluggable verification hook, and the CLI).

## Commands

```sh
scripts/control-plane.sh list                       # discover every scenarios/*/scenario.yaml
scripts/control-plane.sh play  <id> [--prompt "…"]  # apply the trigger (+ optionally drive the agent)
scripts/control-plane.sh play  <id> --no-drive      # apply the trigger only
scripts/control-plane.sh reset <id>                 # trigger-level reset + the scenario's reset.sh
scripts/control-plane.sh verify <id> [--timeout 30] [--interval 3]   # auto-verify expected_signals
scripts/control-plane.sh playlist [--message <pillar>]... [--budget <min>]   # compose a run
```

- **list** — shows every drop-in folder discovered under `scenarios/` via the
  registry (and reports any folder whose manifest fails to validate, without
  breaking the rest of the listing).
- **play** — applies the scenario's `trigger` (the fault is induced), then, if a
  `--prompt` (or `trigger.params.drive_prompt`) is given, drives the concierge so
  the run produces telemetry. `--no-drive` applies the trigger only.
- **reset** — runs the **trigger-level reset** (authoritative, deterministic) and
  then the scenario's `reset.sh` if present. Restores baseline.
- **verify** — runs the `expected_signals` auto-verification hook and prints a
  pass/fail report. Galileo signals are checked for **real** (poll/retry to
  tolerate ingestion lag, L2); Splunk signals are reported **unverified-by-design**
  (see below).
- **playlist** — composes a run by selecting/ordering scenarios keyed by `message`
  (pillar) and fitting a `--budget` time budget (minutes).

## The four fixed trigger mechanisms (demo-design §7.3)

The trigger set is **fixed** — scope creep erodes the "drop-in folder" guarantee.
Each handler has `apply()` + `reset()`:

| `trigger.type` | `apply` does… | `reset` does… | Reads it |
|---|---|---|---|
| `feature_flag` | sets the named flagd flag's `defaultVariant` to "on" in the running stage (flagd hot-reloads) | restores the original variant (saved under `.harness/state/`) | the demo's services |
| `rag_corpus` | overlays the scenario's `*.md` onto `agent/knowledge` via `agent/_overlay/knowledge/` (non-destructive) | removes the overlay dir | `agent/rag.py` |
| `tool_fault` | records a fault for a named tool in `agent/_overlay/tool_faults.json` (`mode=error`/`remove`) | clears that tool's fault | `agent/tools.py` |
| `prompt_overlay` | writes the scenario payload to `agent/_overlay/prompt_overlay.txt` (appended to the system prompt) | clears the overlay file | `agent/graph.py` |

The agent-side triggers write to a stable **overlay seam** (`agent/_overlay/`,
gitignored) that `agent/` reads on startup — so scenarios bend the agent **without
core edits**. The agent picks up agent-side overlays on its **next run**.

## `expected_signals` auto-verification (demo-design §7.4)

Verifiers are **pluggable per backend** (the `SignalVerifier` interface):

- **Galileo (real):** reads `GALILEO_*` from the environment, resolves the project
  + log stream, and polls recent traces with retry/timeout. Named signals map to
  concrete metric checks (e.g. `context_adherence_low` →
  `context_adherence`/`groundedness < GALILEO_METRIC_LOW_THRESHOLD`;
  `tool_selection_quality_low` → `tool_selection_quality`). Where a metric isn't
  queryable yet (scorer not enabled / no data), the signal is reported
  `unverifiable` ("needs Phase-4 data") — **never faked as a pass**.
- **Splunk (unverified-by-design):** our `SPLUNK_ACCESS_TOKEN` is **ingest-only**
  (the management/APM API returns 401), so this repo does **not** query Splunk APM
  live. The Splunk verifier reports every signal (e.g. `apm_all_green`)
  `unverified (ingest-only token; needs an org/API token or SE-driven MCP/UI
  check)`. **The SE confirms Splunk via the Splunk Observability MCP / UI.**

Phase-3 semantics: a run is `PASS` when nothing **failed/errored**; `unverifiable`
signals are reported transparently and complete in Phase 4 (scorer config + the
reference vignette).
