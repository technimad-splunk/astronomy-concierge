#!/usr/bin/env bash
# stage-up.sh — Phase-1 stage launcher (self-bootstrapping).
#
# Brings up the vendored OpenTelemetry "Astronomy Shop" (stage/opentelemetry-demo)
# via docker-compose, exporting traces and metrics to Splunk Observability Cloud
# over OTLP/HTTP. It first runs scripts/stage-setup.sh (idempotent) so a fresh
# checkout of THIS repo can go straight to stage-up.sh with no manual clone:
# setup vendors the demo at the pinned ref (stage/demo.ref) and wires in our
# tracked Splunk overrides (stage/splunk-otel/).
#
# Usage:
#   scripts/stage-up.sh [full|minimal]      # default: full
#
# Transport is OTLP only — never the deprecated `sapm` exporter (demo-design
# §3/§9.3). APM environment is set to "local-agent-galileo".
#
# SECURITY: SPLUNK_ACCESS_TOKEN / SPLUNK_REALM are read from the gitignored .env
# and passed to docker compose via the environment only. The token is NEVER
# echoed, logged, or written to any tracked file.
set -euo pipefail

# --- Locate repo, .env, ref, demo -------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${ENV_FILE:-${REPO_ROOT}/.env}"
REF_FILE="${REPO_ROOT}/stage/demo.ref"
DEMO_DIR="${REPO_ROOT}/stage/opentelemetry-demo"
OVERRIDE_FILE="docker-compose.override.yml"   # materialized into the clone by stage-setup.sh

MODE="${1:-full}"
case "${MODE}" in
  full)    COMPOSE_MAIN="docker-compose.yml" ;;
  minimal) COMPOSE_MAIN="docker-compose.minimal.yml" ;;
  *) echo "FATAL: unknown mode '${MODE}' (use: full | minimal)" >&2; exit 2 ;;
esac

# --- Preconditions ----------------------------------------------------------
command -v docker >/dev/null 2>&1 || { echo "FATAL: docker not found on PATH." >&2; exit 2; }
docker info >/dev/null 2>&1 || { echo "FATAL: Docker daemon not running. Start Docker Desktop and retry." >&2; exit 2; }
[[ -f "${ENV_FILE}" ]] || { echo "FATAL: ${ENV_FILE} not found. Copy .env.example to .env and fill in tokens." >&2; exit 2; }
[[ -f "${REF_FILE}" ]] || { echo "FATAL: ${REF_FILE} missing (the pinned-ref source of truth)." >&2; exit 2; }

# --- Bootstrap: vendor the demo + wire overrides (idempotent) ----------------
"${SCRIPT_DIR}/stage-setup.sh"

# --- Read ONLY the Splunk vars from .env (inline-comment + whitespace safe) --
read_env_var() {
  local name="$1" line val
  line="$(grep -E "^${name}=" "${ENV_FILE}" | head -1 || true)"
  val="${line#*=}"
  val="$(printf '%s' "${val}" | sed -e 's/[[:space:]]\{1,\}#.*$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
  printf '%s' "${val}"
}

SPLUNK_ACCESS_TOKEN="$(read_env_var SPLUNK_ACCESS_TOKEN)"
SPLUNK_REALM="$(read_env_var SPLUNK_REALM)"
[[ -n "${SPLUNK_ACCESS_TOKEN}" ]] || { echo "FATAL: SPLUNK_ACCESS_TOKEN is empty in ${ENV_FILE}." >&2; exit 2; }
[[ -n "${SPLUNK_REALM}" ]] || { echo "FATAL: SPLUNK_REALM is empty in ${ENV_FILE}." >&2; exit 2; }
export SPLUNK_ACCESS_TOKEN SPLUNK_REALM

# Pin the demo IMAGES to the same version as the vendored SOURCE (single source
# of truth: stage/demo.ref). The demo ships DEMO_VERSION=latest, which pulls
# images newer than our pinned clone and breaks the frontend-proxy (its envoy
# template gains clusters whose env vars don't exist in the pinned .env).
# shellcheck disable=SC1090
source "${REF_FILE}"
export DEMO_VERSION="${DEMO_REF}"

echo "stage-up: mode=${MODE}  realm=${SPLUNK_REALM}  token=<hidden>"
echo "stage-up: pinning demo images to DEMO_VERSION=${DEMO_VERSION} (matches vendored source)"
echo "stage-up: APM environment = local-agent-galileo  (transport: OTLP/HTTP)"

# --- Up ---------------------------------------------------------------------
cd "${DEMO_DIR}"
docker compose -f "${COMPOSE_MAIN}" -f "${OVERRIDE_FILE}" up -d --remove-orphans

cat <<EOF

stage-up: containers starting. Useful next steps:
  - Storefront:        http://localhost:8080/
  - Collector logs:    docker logs otel-collector --since 2m | grep -i -E 'splunk|export|error|permission'
  - Stop the stage:    scripts/stage-down.sh ${MODE}
EOF
