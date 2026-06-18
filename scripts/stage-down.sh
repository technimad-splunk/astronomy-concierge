#!/usr/bin/env bash
# stage-down.sh — Phase-1 stage teardown.
#
# Stops and removes the vendored Astronomy Shop stack started by stage-up.sh.
# Pass the same mode you brought it up with (default: full). Add `--volumes` to
# also drop named volumes (OpenSearch/Postgres/Valkey data).
#
# Usage:
#   scripts/stage-down.sh [full|minimal] [--volumes]
#
# SECURITY: no secrets are read or printed here; teardown needs none.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEMO_DIR="${REPO_ROOT}/stage/opentelemetry-demo"
OVERRIDE_FILE="docker-compose.override.yml"   # materialized into the clone by stage-setup.sh

MODE="full"
DOWN_ARGS=()
for arg in "$@"; do
  case "${arg}" in
    full)      MODE="full" ;;
    minimal)   MODE="minimal" ;;
    --volumes) DOWN_ARGS+=("--volumes") ;;
    *) echo "FATAL: unknown arg '${arg}' (use: full | minimal | --volumes)" >&2; exit 2 ;;
  esac
done
case "${MODE}" in
  full)    COMPOSE_MAIN="docker-compose.yml" ;;
  minimal) COMPOSE_MAIN="docker-compose.minimal.yml" ;;
esac

command -v docker >/dev/null 2>&1 || { echo "FATAL: docker not found on PATH." >&2; exit 2; }
docker info >/dev/null 2>&1 || { echo "FATAL: Docker daemon not running." >&2; exit 2; }
[[ -d "${DEMO_DIR}" ]] || { echo "FATAL: ${DEMO_DIR} missing." >&2; exit 2; }
[[ -f "${DEMO_DIR}/${OVERRIDE_FILE}" ]] || { echo "FATAL: ${DEMO_DIR}/${OVERRIDE_FILE} missing. Run scripts/stage-setup.sh." >&2; exit 2; }

# The compose override references SPLUNK_* only to inject them into the collector
# at run time; teardown doesn't need real values, so define empties (no secrets
# read here) to silence compose's "variable is not set" warnings.
export SPLUNK_ACCESS_TOKEN="${SPLUNK_ACCESS_TOKEN:-}" SPLUNK_REALM="${SPLUNK_REALM:-}"

cd "${DEMO_DIR}"
docker compose -f "${COMPOSE_MAIN}" -f "${OVERRIDE_FILE}" down --remove-orphans ${DOWN_ARGS[@]+"${DOWN_ARGS[@]}"}
echo "stage-down: stage stopped (mode=${MODE})."
