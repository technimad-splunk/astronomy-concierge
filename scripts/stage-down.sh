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

# --- Stop the backgrounded SE control-plane web UI (host process) ------------
# stage-up.sh launches the SE console as a host Python process (not a container)
# and records its PID under the gitignored .harness/ dir. Stop it here first so
# teardown is symmetric. This is independent of Docker, so we do it BEFORE the
# Docker preconditions — the console should be stopped even if Docker is down.
CP_PID_FILE="${REPO_ROOT}/.harness/control-plane-web.pid"
if [[ -f "${CP_PID_FILE}" ]]; then
  CP_PID="$(cat "${CP_PID_FILE}" 2>/dev/null || true)"
  if [[ -n "${CP_PID}" ]] && kill -0 "${CP_PID}" 2>/dev/null; then
    kill "${CP_PID}" 2>/dev/null || true
    echo "stage-down: stopped SE control-plane web UI (pid ${CP_PID})."
  else
    echo "stage-down: SE console PID file present but process not running (stale) — cleaning up."
  fi
  rm -f "${CP_PID_FILE}"
else
  echo "stage-down: no SE console PID file — nothing to stop."
fi

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
