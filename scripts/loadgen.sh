#!/usr/bin/env bash
# loadgen.sh — drain or restore the Astronomy Shop's Locust load-generator.
#
# Used by the control plane to silence background traffic before driving the
# agent in "quiet_background" scenarios (so telemetry/attribution is clean),
# and to ALWAYS restore it on reset.
#
# Usage:
#   scripts/loadgen.sh quiet     # drain: POST /stop to Locust API
#   scripts/loadgen.sh restore   # restore: POST /swarm with LOCUST_USERS
#
# Idempotent and safe: if the demo or the load-generator container isn't
# running, prints a message and exits 0 (never breaks play/reset when the
# stage is down). Primary path is the Locust web API (no container restart);
# fallback is docker compose stop/start.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

DEMO_DIR="${REPO_ROOT}/stage/opentelemetry-demo"
OVERRIDE_FILE="docker-compose.override.yml"

# --- Resolve compose file list (mirrors scripts/stage-up.sh) ----------------
COMPOSE_MAIN="docker-compose.yml"
COMPOSE_FILES=(-f "${COMPOSE_MAIN}" -f "${OVERRIDE_FILE}")

# --- Read LOCUST_USERS from the demo's .env (default 5) ---------------------
DEMO_ENV="${DEMO_DIR}/.env"
LOCUST_USERS=5
if [[ -f "${DEMO_ENV}" ]]; then
    val="$(grep -E '^LOCUST_USERS=' "${DEMO_ENV}" | head -1 | cut -d= -f2 | tr -d '[:space:]')" || true
    if [[ -n "${val}" && "${val}" =~ ^[0-9]+$ ]]; then
        LOCUST_USERS="${val}"
    fi
fi

# --- Preconditions (soft — exit 0, never crash play/reset) ------------------
if ! command -v docker >/dev/null 2>&1; then
    echo "loadgen: docker not found; skipping (stage probably not running)."
    exit 0
fi
if ! docker info >/dev/null 2>&1; then
    echo "loadgen: Docker daemon not running; skipping."
    exit 0
fi
if [[ ! -d "${DEMO_DIR}" ]]; then
    echo "loadgen: ${DEMO_DIR} not found; skipping (stage not set up)."
    exit 0
fi

# Compose needs SPLUNK_* defined (even empty) to avoid "variable is not set".
export SPLUNK_ACCESS_TOKEN="${SPLUNK_ACCESS_TOKEN:-}" SPLUNK_REALM="${SPLUNK_REALM:-}"

is_container_running() {
    cd "${DEMO_DIR}"
    docker compose "${COMPOSE_FILES[@]}" ps --status running load-generator 2>/dev/null | grep -q load-generator
}

# --- Locust API helpers (via docker compose exec, so it uses the compose
#     network — no host-port assumption) -------------------------------------
locust_api() {
    local method="$1" path="$2"
    shift 2
    cd "${DEMO_DIR}"
    docker compose "${COMPOSE_FILES[@]}" exec -T load-generator \
        curl -s -o /dev/null -w '%{http_code}' -X "${method}" "http://localhost:8089${path}" "$@"
}

# --- Actions ----------------------------------------------------------------
do_quiet() {
    if ! is_container_running; then
        echo "loadgen: load-generator container not running; nothing to drain."
        exit 0
    fi

    echo "loadgen: draining load-generator (Locust API /stop)..."
    http_code="$(locust_api POST /stop 2>/dev/null)" || http_code=""

    if [[ "${http_code}" == "200" ]]; then
        echo "loadgen: drained — active users ramping to 0."
        return 0
    fi

    echo "loadgen: Locust API returned '${http_code}'; falling back to docker compose stop..."
    cd "${DEMO_DIR}"
    docker compose "${COMPOSE_FILES[@]}" stop load-generator 2>/dev/null || true
    echo "loadgen: load-generator stopped (fallback). Note: ~30-60s warm-up on restore."
}

do_restore() {
    cd "${DEMO_DIR}"

    if ! is_container_running; then
        echo "loadgen: load-generator container not running; attempting docker compose start..."
        docker compose "${COMPOSE_FILES[@]}" start load-generator 2>/dev/null || {
            echo "loadgen: could not start load-generator (stage may be down); skipping."
            exit 0
        }
        echo "loadgen: load-generator started; waiting for Locust to initialise..."
        sleep 5
    fi

    # Best-effort Locust API call — LOCUST_AUTOSTART=true means the
    # container auto-swarms on start, so a running container is already
    # success. The API call is a nicety to ensure immediate swarming if
    # the container was only API-stopped (not restarted).
    echo "loadgen: restoring load-generator (LOCUST_AUTOSTART=true)..."
    http_code="$(locust_api POST /swarm \
        -d "user_count=${LOCUST_USERS}" \
        -d "spawn_rate=${LOCUST_USERS}" 2>/dev/null)" || http_code=""

    if [[ "${http_code}" == "200" ]]; then
        echo "loadgen: restored — ${LOCUST_USERS} user(s) swarming."
        return 0
    fi

    # Container is running + LOCUST_AUTOSTART=true → Locust will auto-swarm.
    # The API returning empty/non-200 is expected in some environments.
    if is_container_running; then
        echo "loadgen: load-generator restored — autostart will resume ~${LOCUST_USERS} users within ~30-60s."
        return 0
    fi

    echo "loadgen: warning — load-generator container is not running after restore attempt."
}

# --- Dispatch ---------------------------------------------------------------
case "${1:-}" in
    quiet)   do_quiet ;;
    restore) do_restore ;;
    *)
        echo "Usage: scripts/loadgen.sh {quiet|restore}" >&2
        exit 2
        ;;
esac
