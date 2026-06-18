# `scripts/` — automation & verification helpers

Per the repo [`automate-verify`](../.cursor/rules/automate-verify.mdc) rule:
prefer scripted, repeatable checks over manual steps. This directory grows
incrementally as the project matures.

## Contents

- [`check-connectivity.sh`](check-connectivity.sh) — **Phase-0/1 helper**.
  Verifies reachability of both backends (Galileo + Splunk Observability) and
  that local provider prerequisites respond, so a cold setup can be validated
  before building. Secret-safe (never prints tokens).
- [`stage-setup.sh`](stage-setup.sh) — **Phase-1**, idempotent. Vendors the
  upstream demo at the pinned ref (`stage/demo.ref`, the single source of truth)
  into `stage/opentelemetry-demo/` and wires our tracked Splunk overrides into
  the clone. Makes the stage reproducible from a fresh checkout with no manual
  `git clone`. Reads no secrets; needs network only on first clone.
- [`stage-up.sh`](stage-up.sh) — **Phase-1**. Runs `stage-setup.sh` (so it's
  self-bootstrapping), then brings up the vendored Astronomy Shop via
  docker-compose with the Collector exporting to Splunk Observability over
  OTLP/HTTP. Usage: `scripts/stage-up.sh [full|minimal]` (default `full`). Reads
  `SPLUNK_ACCESS_TOKEN` / `SPLUNK_REALM` from `.env`; never echoes them.
- [`stage-down.sh`](stage-down.sh) — **Phase-1**. Stops/removes the stage.
  Usage: `scripts/stage-down.sh [full|minimal] [--volumes]`.
- [`agent-run.sh`](agent-run.sh) — **Phase-2**, self-bootstrapping. Creates/reuses
  the venv, installs deps, and runs the concierge (`python -m agent`).
- [`control-plane.sh`](control-plane.sh) — **Phase-3**, self-bootstrapping. Runs
  the SE control plane / scenario harness (`python -m control_plane`):
  `list / play / reset / verify / playlist`. Adding a scenario is a drop-in folder
  under `scenarios/` — this script never changes. Reads creds from `.env`; never
  echoes them.

## TODO

- [ ] **Phase 1:** stage smoke check — curl the storefront and assert the
      Splunk OTel Collector is healthy (interim manual checks documented in
      [`stage/README.md`](../stage/README.md)).
- [ ] **Phase 2:** drive a scripted prompt and assert spans land in *both*
      backends.
