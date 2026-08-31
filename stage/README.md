# `stage/` — the stage the agent lives in

This directory will hold (or point to) the **forked Astronomy Shop** and its
Splunk telemetry wiring. It is the *operational backdrop* the concierge runs
inside (demo-design §4).

## Layout

| Path | Tracked? | What it is |
|---|---|---|
| `demo.ref` | **Yes** | **Single source of truth** for the vendored demo repo + pinned tag (`DEMO_REPO`, `DEMO_REF`). Bump the version here only. |
| `opentelemetry-demo/` | **No** (gitignored) | The vendored upstream demo clone (the "Astronomy Shop"). Large + has its own git history, so we don't track it — `scripts/stage-setup.sh` recreates it. |
| `splunk-otel/otelcol-config-extras.yml` | **Yes** | Our Splunk Observability OTLP/HTTP exporter (the collector merge). |
| `splunk-otel/docker-compose.override.yml` | **Yes** | Injects `SPLUNK_ACCESS_TOKEN` / `SPLUNK_REALM` into the collector container and disables Locust browser traffic (`LOCUST_BROWSER_TRAFFIC_ENABLED=false`) for stable reset/restore behavior. |

Helpers in [`scripts/`](../scripts/): `stage-setup.sh` (vendor + wire), `stage-up.sh` (start, self-bootstrapping), `stage-down.sh` (stop). Everything here is reproducible from a fresh clone of this repo — no manual checkout.

## Which demo we vendored, and why

We use **upstream [`open-telemetry/opentelemetry-demo`](https://github.com/open-telemetry/opentelemetry-demo)**, pinned to the tag in [`demo.ref`](demo.ref) (currently **`2.2.0`**) — *not* the Splunk fork.

The Splunk fork (`splunk/opentelemetry-demo`) exists and is current, but at `v2.0.5` its **docker-compose path is broken** (its `docker-compose.yml` references collector config files that aren't in the tree) and its Splunk Observability integration is **Kubernetes-only** (`SPLUNK-BUILD.md`). Our Phase-1 plan calls for docker-compose, so we use upstream's complete, maintained compose stack and add the Splunk OTLP exporter ourselves via upstream's documented `otelcol-config-extras.yml` merge seam.

## How setup makes it reproducible

`scripts/stage-setup.sh` is idempotent and does the whole vendor-and-wire step:

1. Reads the pinned ref from `demo.ref` (the only place the version lives).
2. Shallow-clones the demo at that exact tag into `opentelemetry-demo/` (no-op if already present at the right version; errors if a different version is present rather than silently mixing). It verifies the tag resolved to the expected release.
3. **Wires our tracked overrides into the clone** (re-synced on every run):
   - `splunk-otel/otelcol-config-extras.yml` → `opentelemetry-demo/src/otel-collector/otelcol-config-extras.yml` (the demo's default collector "extras" config it already loads)
   - `splunk-otel/docker-compose.override.yml` → `opentelemetry-demo/docker-compose.override.yml`

The load-generator browser user is disabled in the tracked override because the
Playwright Locust plugin cannot be re-swarmed safely in-process after `/stop`
and was already erroring every task; keeping only HTTP Locust users preserves
repeatable `scripts/loadgen.sh quiet`/`restore` cycles.

Because `demo.ref` and both overrides are committed and the setup script recreates the rest, a fresh checkout needs no manual `git clone` and no hand-edits.

## How the Splunk wiring works

The upstream collector loads two configs: `--config=/etc/otelcol-config.yml --config=/etc/otelcol-config-extras.yml`. Setup makes the second one OUR file, so the collector exports to Splunk by default. The collector config resolver **replaces** list values on merge, so our extras file re-lists the upstream processors/exporters and appends ours.

Our extras file wires the two Splunk pipelines distinctly:

- **traces** → `otlphttp/splunk` exporter → `https://ingest.${SPLUNK_REALM}.signalfx.com/v2/trace/otlp` (auth header `X-SF-Token: ${SPLUNK_ACCESS_TOKEN}`).
- **metrics** → the `signalfx` exporter **only** (with `send_otlp_histograms: true`), using `realm: ${SPLUNK_REALM}` so it derives `ingest.<realm>.signalfx.com` / `api.<realm>.signalfx.com`. Metrics intentionally do **not** go through `otlphttp/splunk`, so the same histogram isn't delivered twice.

> **Endpoint forms are equivalent (no gotcha):** `*.<realm>.signalfx.com` and `*.<realm>.observability.splunkcloud.com` are **both valid Splunk Observability ingests for the same realm/tenant** — same API paths, same auth (verified: an unauthenticated POST to `/v2/datapoint` and `/v2/datapoint/otlp` returns `401` on **both** hosts, i.e. both routes exist and require the token). They differ only in routing infrastructure, not in the backing service. We use the `realm:`-derived `signalfx.com` form because it's the canonical, least-error-prone `signalfx` exporter config — **not** because the `splunkcloud.com` form was wrong.

> **`send_otlp_histograms: true` is REQUIRED, and verify in the UI (not the metric finder):** Splunk's "Set up AI Agent Monitoring" doc states: *"Histogram metrics are required to display data on AI Agent Monitoring pages. To send histogram data to Splunk Observability Cloud with the SignalFx exporter, set `send_otlp_histograms: true`."* Native OTLP histograms are a distinct metric type in o11y and **do not appear in the metric-name finder/catalog** — so `gen_ai.*` being "absent" from the finder is a **false negative**, not missing data. Confirm GenAI metrics in **`APM > AI agents` / `AI trace data`**. A prior detour set `send_otlp_histograms: false` (SignalFx-translated `_count`/`_sum`/`_bucket`) to chase metric-finder visibility — that was **wrong and reverted**, because it drops the native histogram AI Agent Monitoring needs. Metrics must also be **delta** temporality (set explicitly on the agent's OTLP metric exporter).

`stage-up.sh` pins `DEMO_VERSION` to `DEMO_REF` from `demo.ref`; the demo ships `DEMO_VERSION=latest`, which would pull images newer than our pinned source and break the frontend-proxy.

### Build constraint: OTLP, not `sapm`

> The Splunk path uses **OTLP/HTTP only** (Splunk Observability does not accept OTLP over gRPC). We do **not** use the deprecated `sapm` exporter (demo-design §3, §9.3).

`SPLUNK_ACCESS_TOKEN` / `SPLUNK_REALM` come from the gitignored repo [`.env`](../.env.example) and are passed to the collector via the environment only — never committed, never logged.

## APM environment & services

Our extras file tags all exported telemetry with `deployment.environment=local-agent-galileo`, so in Splunk APM the store appears under **Environment = `local-agent-galileo`** (service namespace `opentelemetry-demo`). Expected APM services: `frontend`, `frontend-proxy`, `cart`, `checkout`, `currency`, `payment`, `shipping`, `product-catalog`, `product-reviews`, `recommendation`, `ad`, `quote`, `email`, `accounting`, `fraud-detection`, `image-provider`, `load-generator`.

## Usage (zero to running)

```sh
cp ../.env.example ../.env      # fill in SPLUNK_ACCESS_TOKEN + SPLUNK_REALM
../scripts/check-connectivity.sh   # optional: verify tokens (secret-safe)
../scripts/stage-setup.sh      # vendor demo @ pinned ref + wire Splunk overrides (idempotent)
../scripts/stage-up.sh         # start full stack (~6 GB RAM); also runs setup for you
#   or: ../scripts/stage-up.sh minimal   # lighter stack (drops Kafka & dependents, ~3 GB)
../scripts/stage-down.sh       # stop; add --volumes to also drop data volumes
```

`stage-up.sh` runs `stage-setup.sh` first, so after editing `.env` you can jump
straight to it. Then open the storefront at <http://localhost:8080/>. Resourcing:
~6 GB RAM full / ~3 GB minimal, ~14 GB disk (demo-design §8.4).

## Verify locally

```sh
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/   # expect 200
docker logs otel-collector 2>&1 | grep -i 'Exporting failed'      # expect only 'opensearch', never otlphttp/splunk
```

A clean collector start ("Everything is ready") with **no `otlphttp/splunk` export errors** (no 401/403) means traces/metrics are flowing to Splunk Observability. Splunk-side confirmation (services/service map/traces visible in APM) is done separately.
