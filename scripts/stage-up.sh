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
#   scripts/stage-up.sh [full|minimal] [--build] [--pull]   # default: full
#     --build  force-rebuild ONLY locally-built override services (e.g. concierge-web)
#     --pull   re-fetch upstream demo images (pinned version) before up
#              (with --pull --build: pull upstream, then build local-only images)
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

# Parse args: a mode (full|minimal) and optional --build / --pull, in any order.
MODE="full"
DO_BUILD=0
DO_PULL=0
for arg in "$@"; do
  case "${arg}" in
    full|minimal) MODE="${arg}" ;;
    --build)      DO_BUILD=1 ;;
    --pull)       DO_PULL=1 ;;
    -h|--help)
      cat <<'EOF'
Usage: scripts/stage-up.sh [full|minimal] [--build] [--pull]
  --build  rebuild ONLY locally-built override service images (e.g. concierge-web)
  --pull   re-fetch pullable upstream demo images before up
           (with --pull --build: pull upstream first, then build local-only images)
EOF
      exit 0
      ;;
    *) echo "FATAL: unknown argument '${arg}' (use: full | minimal [--build] [--pull])" >&2; exit 2 ;;
  esac
done
case "${MODE}" in
  full)    COMPOSE_MAIN="docker-compose.yml" ;;
  minimal) COMPOSE_MAIN="docker-compose.minimal.yml" ;;
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

# Return 0 if something is already listening on the given TCP port (loopback).
# Prefer lsof (reliable on macOS); fall back to bash /dev/tcp if lsof is absent.
port_in_use() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
    return $?
  fi
  if (exec 3<>"/dev/tcp/127.0.0.1/${port}") >/dev/null 2>&1; then
    exec 3>&- 3<&- 2>/dev/null || true
    return 0
  fi
  return 1
}

# Generate a 64-hex-char admin token using whatever CSPRNG tool is available.
# Order: openssl (preferred) -> xxd over /dev/urandom -> python secrets.
generate_admin_token() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  elif command -v xxd >/dev/null 2>&1; then
    head -c32 /dev/urandom | xxd -p -c256
  else
    python3 -c 'import secrets;print(secrets.token_hex(32))'
  fi
}

# Persist CONCIERGE_ADMIN_TOKEN into an env file, secret-safe and portable.
# Replaces an existing `CONCIERGE_ADMIN_TOKEN=` line in place (even if empty),
# else appends the line. Uses a temp-file rewrite (NOT `sed -i`, which differs on
# BSD/macOS vs GNU). The token VALUE is never printed.
persist_admin_token() {
  local file="$1" value="$2" tmp line
  tmp="$(mktemp "${file}.tofu.XXXXXX")"
  if grep -qE '^CONCIERGE_ADMIN_TOKEN=' "${file}"; then
    while IFS= read -r line || [[ -n "${line}" ]]; do
      if [[ "${line}" == CONCIERGE_ADMIN_TOKEN=* ]]; then
        printf 'CONCIERGE_ADMIN_TOKEN=%s\n' "${value}"
      else
        printf '%s\n' "${line}"
      fi
    done <"${file}" >"${tmp}"
  else
    cat "${file}" >"${tmp}"
    printf 'CONCIERGE_ADMIN_TOKEN=%s\n' "${value}" >>"${tmp}"
  fi
  chmod 600 "${tmp}" 2>/dev/null || true
  mv "${tmp}" "${file}"
}

SPLUNK_ACCESS_TOKEN="$(read_env_var SPLUNK_ACCESS_TOKEN)"
SPLUNK_REALM="$(read_env_var SPLUNK_REALM)"
[[ -n "${SPLUNK_ACCESS_TOKEN}" ]] || { echo "FATAL: SPLUNK_ACCESS_TOKEN is empty in ${ENV_FILE}." >&2; exit 2; }
[[ -n "${SPLUNK_REALM}" ]] || { echo "FATAL: SPLUNK_REALM is empty in ${ENV_FILE}." >&2; exit 2; }
export SPLUNK_ACCESS_TOKEN SPLUNK_REALM

# --- Export concierge-web vars so compose ${...} substitution sees them -------
# The concierge-web service in docker-compose.override.yml references these via
# ${VAR} interpolation, which compose resolves from the SHELL environment — not
# from the demo's auto-loaded .env. Without exporting them here, compose
# substitutes empty strings (e.g. GALILEO_API_KEY=""), leaving Galileo entirely
# unconfigured INSIDE the container regardless of any per-turn flush. Galileo is
# OPTIONAL: export whatever is present (empty is fine) and never hard-fail on it;
# only SPLUNK_* stays required (handled above). Secret VALUES are never printed.

# --- TOFU: ensure a CONCIERGE_ADMIN_TOKEN exists (trust-on-first-use) ---------
# The concierge admin endpoints (/admin/scenario/*, /admin/reload) enforce a
# fail-closed bearer-token gate. To avoid a manual setup step, auto-generate the
# token on first bring-up and persist it to .env, so the containerized concierge
# and the host control-plane automatically share the SAME token. If a token is
# already present we leave it untouched. The token VALUE is never printed; it is
# exported below (with the other concierge vars) for compose ${...} substitution.
if [[ -z "$(read_env_var CONCIERGE_ADMIN_TOKEN)" ]]; then
  persist_admin_token "${ENV_FILE}" "$(generate_admin_token)"
  echo "stage-up: generated CONCIERGE_ADMIN_TOKEN and saved to ${ENV_FILE} (value hidden)"
else
  echo "stage-up: CONCIERGE_ADMIN_TOKEN present (hidden)"
fi

CONCIERGE_ENV_VARS=(
  GALILEO_API_KEY
  GALILEO_PROJECT
  GALILEO_LOG_STREAM
  GALILEO_CONSOLE_URL
  GALILEO_OTEL_EXPORT
  MODEL_PROVIDER
  MODEL_TEMPERATURE
  OLLAMA_MODEL
  OPENAI_API_KEY
  OPENAI_MODEL
  OTEL_SERVICE_NAME
  DEPLOYMENT_ENVIRONMENT
  WEB_ALLOWED_ORIGIN
  CONCIERGE_API_URL
  CONCIERGE_WEB_PORT
  CONCIERGE_ADMIN_TOKEN
)
for _cw_var in "${CONCIERGE_ENV_VARS[@]}"; do
  printf -v "${_cw_var}" '%s' "$(read_env_var "${_cw_var}")"
  export "${_cw_var}"
done
if [[ -z "${GALILEO_API_KEY}" ]]; then
  echo "stage-up: WARNING — GALILEO_API_KEY is empty in ${ENV_FILE}; concierge-web will run WITHOUT Galileo export (Splunk unaffected)." >&2
fi

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

# Optional: re-fetch upstream images for the pinned version before bringing up.
# --ignore-pull-failures skips the locally-built concierge-web (no remote image).
if [[ "${DO_PULL}" -eq 1 ]]; then
  echo "stage-up: --pull set; re-fetching upstream images (DEMO_VERSION=${DEMO_VERSION}) ..."
  docker compose -f "${COMPOSE_MAIN}" -f "${OVERRIDE_FILE}" pull --ignore-pull-failures
fi

# Optional: --build rebuilds ONLY locally-built services declared in OUR override.
# We intentionally never force-build upstream demo services from COMPOSE_MAIN.
#
# Parsing note: this reads service names under `services:` that declare `build:`
# in docker-compose.override.yml (materialized by stage-setup.sh). If parsing
# ever yields none, fall back to the known local service name concierge-web.
UP_ARGS=(-d --remove-orphans)
if [[ "${DO_BUILD}" -eq 1 ]]; then
  LOCAL_BUILD_SERVICES=()
  while IFS= read -r _local_service; do
    [[ -n "${_local_service}" ]] && LOCAL_BUILD_SERVICES+=("${_local_service}")
  done < <(
    awk '
      BEGIN { in_services = 0; service = "" }
      /^[[:space:]]*#/ { next }
      /^services:[[:space:]]*$/ { in_services = 1; next }
      in_services && /^[^[:space:]]/ { in_services = 0 }
      !in_services { next }
      /^  [A-Za-z0-9_.-]+:[[:space:]]*$/ {
        service = $0
        sub(/^[[:space:]]*/, "", service)
        sub(/:[[:space:]]*$/, "", service)
        next
      }
      service != "" && /^    build:[[:space:]]*($|#)/ { print service }
    ' "${OVERRIDE_FILE}" | awk '!seen[$0]++'
  )
  if [[ "${#LOCAL_BUILD_SERVICES[@]}" -eq 0 ]]; then
    LOCAL_BUILD_SERVICES=(concierge-web)
  fi

  echo "stage-up: --build set; rebuilding local override service image(s): ${LOCAL_BUILD_SERVICES[*]}"
  docker compose -f "${COMPOSE_MAIN}" -f "${OVERRIDE_FILE}" build "${LOCAL_BUILD_SERVICES[@]}"
fi
docker compose -f "${COMPOSE_MAIN}" -f "${OVERRIDE_FILE}" up "${UP_ARGS[@]}"

# --- Also launch the SE control-plane web UI (host process, NOT a container) --
# The SE console needs HOST access (the running stage's flagd config, Galileo, the
# repo .venv) so it runs as a backgrounded host Python/uvicorn process — never a
# container. It is loopback-only (127.0.0.1) by design. We background it so
# stage-up returns immediately, record its PID under the gitignored .harness/
# dir, and tee its output to a log file there. Idempotent: if the port is already
# in use we assume it's already running and skip a second launch.
CONTROL_PLANE_WEB_HOST="127.0.0.1"
CONTROL_PLANE_WEB_PORT="8099"
HARNESS_DIR="${REPO_ROOT}/.harness"
CP_PID_FILE="${HARNESS_DIR}/control-plane-web.pid"
CP_LOG_FILE="${HARNESS_DIR}/control-plane-web.log"
mkdir -p "${HARNESS_DIR}"

if port_in_use "${CONTROL_PLANE_WEB_PORT}"; then
  echo "stage-up: SE console port ${CONTROL_PLANE_WEB_PORT} already in use — assuming it's already running; skipping launch."
else
  echo "stage-up: launching SE control-plane web UI (host process, loopback-only) ..."
  # control-plane-web.sh execs uvicorn, so the recorded PID is the server itself
  # (stage-down.sh kills it directly). First-run venv/dep bootstrap streams to the
  # log file; the server may take a few seconds to start listening on first run.
  nohup "${SCRIPT_DIR}/control-plane-web.sh" --host "${CONTROL_PLANE_WEB_HOST}" --port "${CONTROL_PLANE_WEB_PORT}" >"${CP_LOG_FILE}" 2>&1 &
  CP_PID=$!
  echo "${CP_PID}" >"${CP_PID_FILE}"
  echo "stage-up: SE console starting (pid ${CP_PID}); logs: ${CP_LOG_FILE}"
fi

cat <<EOF

stage-up: containers starting. Interfaces:
  - Astronomy Shop storefront:   http://localhost:8080/
  - Astronomy Concierge chat:    http://localhost:${CONCIERGE_WEB_PORT:-8090}/   (container)
  - SE Control-Plane web UI:     http://${CONTROL_PLANE_WEB_HOST}:${CONTROL_PLANE_WEB_PORT}/   (host process, loopback-only)

Useful next steps:
  - Collector logs:    docker logs otel-collector --since 2m | grep -i -E 'splunk|export|error|permission'
  - SE console logs:   tail -f ${CP_LOG_FILE}
  - Stop everything:   scripts/stage-down.sh ${MODE}
EOF
