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
scripts/control-plane.sh play  <id> [--prompt "…"]  # apply trigger; for agent-side triggers, drive via web chat
scripts/control-plane.sh play  <id> --no-drive      # apply the trigger only
scripts/control-plane.sh reset <id>                 # trigger-level reset + the scenario's reset.sh
scripts/control-plane.sh verify <id> [--timeout 30] [--interval 3]   # auto-verify expected_signals
```

`CONCIERGE_ADMIN_TOKEN` (which bearer-authenticates control-plane -> concierge
trigger mutations) is auto-generated and saved to `.env` on first
`scripts/stage-up.sh` (trust-on-first-use), so the host control-plane and the
containerized concierge automatically share it — no manual step needed.

- **list** — shows every drop-in folder discovered under `scenarios/` via the
  registry (and reports any folder whose manifest fails to validate, without
  breaking the rest of the listing).
- **play** — applies the scenario's `trigger` (the fault is induced). For
  `tool_fault`, `prompt_overlay`, and `rag_corpus`, the CLI applies the trigger
  through the concierge admin API and prints the scenario drive prompt so you can
  drive the run in the concierge web chat. `feature_flag` may still use CLI
  driving when a prompt is provided. If the scenario declares
  `quiet_background: true`, the Astronomy Shop's Locust load-generator is
  **drained first** (via `scripts/loadgen.sh quiet`) so the agent's traffic is
  the only store activity — useful when a single failing checkout would be
  masked by continuous healthy background load.
- **reset** — runs the **trigger-level reset** (authoritative, deterministic) and
  then the scenario's `reset.sh` if present. Restores baseline. **Always**
  restores the load-generator (via `scripts/loadgen.sh restore`, idempotent) so
  it is never left drained.
- **verify** — runs the `expected_signals` auto-verification hook and prints a
  report.   Galileo signals are checked for **real** (poll/retry to tolerate
  ingestion lag, L2); named signals include quality metrics (e.g.
  `context_adherence_low`), error metrics (`tool_error`), and detection signals
  (`prompt_injection_detected`, `pii_exposed`). The Splunk `apm_all_green`
  signal is reported **attested** (operator-verified out-of-band, with embedded
  evidence — the CLI's ingest-only token can't query APM; see below).
## `quiet_background` and `scripts/loadgen.sh`

Some scenarios need the demo's background load silenced so the agent's traffic
is cleanly attributable in APM. The optional boolean field `quiet_background`
(default `false`) in `scenario.yaml` controls this:

- **`play`** — if `quiet_background: true`, runs `scripts/loadgen.sh quiet`
  before applying the trigger. This POSTs to the Locust web API (`/stop`) via
  `docker compose exec` (no host-port assumption), draining active users to 0.
  Falls back to `docker compose stop load-generator` if the API is unreachable.
- **`reset`** — **always** runs `scripts/loadgen.sh restore` (idempotent),
  POSTing `/swarm` with `user_count` from the demo's `.env` (`LOCUST_USERS`,
  default 5). If the container was stopped (fallback), it starts it first.

The script is a safe no-op (exit 0, clear message) when Docker, the daemon, or
the load-generator container are unavailable — it never breaks play/reset when
the stage is down.

## The four fixed trigger mechanisms (demo-design §7.3)

The trigger set is **fixed** — scope creep erodes the "drop-in folder" guarantee.
Each handler has `apply()` + `reset()`:

| `trigger.type` | `apply` does… | `reset` does… | Reads it |
|---|---|---|---|
| `feature_flag` | sets the named flagd flag's `defaultVariant` to "on" in the running stage (flagd hot-reloads) | restores the original variant (saved under `.harness/state/`) | the demo's services |
| `rag_corpus` | POSTs scenario `*.md` docs to concierge `/admin/scenario/apply` as in-memory knowledge overlay | POSTs `/admin/scenario/reset` to clear rag overlay | `agent/rag.py` |
| `tool_fault` | POSTs a named tool fault spec (`mode=error`/`remove`/`stale`) to concierge `/admin/scenario/apply` | POSTs `/admin/scenario/reset` to clear that tool fault | `agent/tools.py` |
| `prompt_overlay` | POSTs the scenario payload to concierge `/admin/scenario/apply` (system prompt + dual-channel knowledge doc) | POSTs `/admin/scenario/reset` to clear prompt overlay state | `agent/graph.py` |

The agent-side triggers now deliver to the running concierge process over an
authenticated admin API. The concierge stores overlay state in-memory, runs
`/admin/reload` behavior to drain and rebuild sessions, and the next chat turn
uses the updated trigger state without filesystem overlays.

## `expected_signals` auto-verification (demo-design §7.4)

Verifiers are **pluggable per backend** (the `SignalVerifier` interface):

- **Galileo (real):** reads `GALILEO_*` from the environment, resolves the project
  + log stream, and polls recent traces with retry/timeout. Galileo returns each
  trace's scorer metrics keyed by the scorer's **UUID**, so the verifier fetches
  the project's scorer definitions (`Scorers().list()`), builds a live name→UUID
  map, and looks each signal's scorer up by **both** name and UUID across its
  value sub-keys (`@average`/`@min`/`@max`/`_multijudge_average`). Named signals
  map to concrete checks (e.g. `context_adherence_low` → `context_adherence`'s
  worst value `< GALILEO_METRIC_LOW_THRESHOLD`; `ungrounded_claim` →
  `completeness`/`chunk_attribution_*`). Where a scorer isn't present (not enabled
  / no data), the signal is reported `unverifiable` — **never faked as a pass**.
- **Splunk (`apm_all_green` is operator-attested):** our `SPLUNK_ACCESS_TOKEN` is
  **ingest-only** (the management/APM API returns 401), so the CLI **cannot** query
  Splunk APM live. Rather than leave the signal an indefinite "unverifiable", the
  Splunk verifier reports `apm_all_green` as **`attested`**: a distinct result
  state meaning the operator confirmed it out-of-band via the Splunk Observability
  APM MCP / UI, with the **evidence embedded** in the result. It is **concierge-
  scoped** — *the concierge path stayed green / the failure was operationally
  invisible to APM*, NOT a claim that every service is green (the Astronomy Shop
  ships built-in background chaos). Any other Splunk signal stays `unverifiable`.

A run is `PASS` when nothing **failed/errored**; `attested` (operator-verified)
and `unverifiable` (a transparent gap) signals do not by themselves fail the run.
