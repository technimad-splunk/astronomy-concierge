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
ENVOY_PORT=8080
if [[ -f "${DEMO_ENV}" ]]; then
    val="$(grep -E '^LOCUST_USERS=' "${DEMO_ENV}" | head -1 | cut -d= -f2 | tr -d '[:space:]')" || true
    if [[ -n "${val}" && "${val}" =~ ^[0-9]+$ ]]; then
        LOCUST_USERS="${val}"
    fi
    envoy_val="$(grep -E '^ENVOY_PORT=' "${DEMO_ENV}" | head -1 | cut -d= -f2 | tr -d '[:space:]')" || true
    if [[ -n "${envoy_val}" && "${envoy_val}" =~ ^[0-9]+$ ]]; then
        ENVOY_PORT="${envoy_val}"
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

# --- Locust API helpers (host-side; no in-container curl dependency) ---------
resolve_locust_host_port() {
    local container_id="" mapping="" port=""
    cd "${DEMO_DIR}"
    container_id="$(docker compose "${COMPOSE_FILES[@]}" ps -q load-generator 2>/dev/null | awk 'NR==1 { print $0 }')" || container_id=""
    if [[ -z "${container_id}" ]]; then
        return 1
    fi
    mapping="$(docker port "${container_id}" 8089 2>/dev/null | awk 'NR==1 { print $0 }')" || mapping=""
    if [[ -z "${mapping}" ]]; then
        return 1
    fi
    port="${mapping##*:}"
    port="${port//[[:space:]]/}"
    if [[ "${port}" =~ ^[0-9]+$ ]]; then
        printf '%s' "${port}"
        return 0
    fi
    return 1
}

locust_api() {
    local method="$1" path="$2" http_code="" mapped_port=""
    shift 2
    http_code="$(curl -s -o /dev/null -w '%{http_code}' -X "${method}" \
        "http://localhost:${ENVOY_PORT}/loadgen${path}" "$@" 2>/dev/null)" || http_code=""
    if [[ "${method}" == "POST" && "${http_code}" == "405" ]]; then
        http_code="$(curl -s -o /dev/null -w '%{http_code}' \
            "http://localhost:${ENVOY_PORT}/loadgen${path}" 2>/dev/null)" || http_code=""
    fi
    if [[ "${http_code}" == "200" ]]; then
        printf '%s' "${http_code}"
        return 0
    fi

    mapped_port="$(resolve_locust_host_port)" || mapped_port=""
    if [[ -n "${mapped_port}" ]]; then
        http_code="$(curl -s -o /dev/null -w '%{http_code}' -X "${method}" \
            "http://localhost:${mapped_port}${path}" "$@" 2>/dev/null)" || http_code=""
        if [[ "${method}" == "POST" && "${http_code}" == "405" ]]; then
            http_code="$(curl -s -o /dev/null -w '%{http_code}' \
                "http://localhost:${mapped_port}${path}" 2>/dev/null)" || http_code=""
        fi
    fi
    printf '%s' "${http_code}"
}

locust_stats_snapshot() {
    local stats_json="" mapped_port="" state="" user_count=""
    stats_json="$(curl -s "http://localhost:${ENVOY_PORT}/loadgen/stats/requests" 2>/dev/null)" || stats_json=""
    if [[ -z "${stats_json}" ]]; then
        mapped_port="$(resolve_locust_host_port)" || mapped_port=""
        if [[ -n "${mapped_port}" ]]; then
            stats_json="$(curl -s "http://localhost:${mapped_port}/stats/requests" 2>/dev/null)" || stats_json=""
        fi
    fi

    if [[ -z "${stats_json}" ]]; then
        return 1
    fi

    stats_json="${stats_json//$'\n'/ }"
    if [[ "${stats_json}" =~ \"state\"[[:space:]]*:[[:space:]]*\"([^\"]+)\" ]]; then
        state="${BASH_REMATCH[1]}"
    else
        return 1
    fi
    if [[ "${stats_json}" =~ \"user_count\"[[:space:]]*:[[:space:]]*([0-9]+) ]]; then
        user_count="${BASH_REMATCH[1]}"
    else
        return 1
    fi
    printf '%s %s' "${state}" "${user_count}"
    return 0
}

locust_stats_state() {
    local snapshot="" state=""
    snapshot="$(locust_stats_snapshot 2>/dev/null)" || return 1
    state="${snapshot%% *}"
    if [[ -n "${state}" ]]; then
        printf '%s' "${state}"
        return 0
    fi
    return 1
}

locust_status_string() {
    local snapshot="" state="" users=""
    snapshot="$(locust_stats_snapshot 2>/dev/null)" || snapshot=""
    if [[ -z "${snapshot}" ]]; then
        printf '%s' "state=unknown, users=unknown"
        return 0
    fi
    state="${snapshot%% *}"
    users="${snapshot##* }"
    printf 'state=%s, users=%s' "${state}" "${users}"
}

wait_for_locust_healthy() {
    local timeout_s="${1:-15}" start_ts=0 now_ts=0 snapshot="" state="" users=""
    start_ts="$(date +%s)"
    while true; do
        snapshot="$(locust_stats_snapshot 2>/dev/null)" || snapshot=""
        if [[ -n "${snapshot}" ]]; then
            state="${snapshot%% *}"
            users="${snapshot##* }"
            if [[ "${state}" == "running" && "${users}" =~ ^[0-9]+$ ]] && (( users >= 1 )); then
                return 0
            fi
        fi
        now_ts="$(date +%s)"
        if (( now_ts - start_ts >= timeout_s )); then
            return 1
        fi
        sleep 1
    done
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
        local attempt=1 state=""
        while (( attempt <= 10 )); do
            state="$(locust_stats_state 2>/dev/null)" || state=""
            if [[ -n "${state}" && "${state}" != "running" ]]; then
                echo "loadgen: drained — Locust state is '${state}'."
                return 0
            fi
            sleep 1
            ((attempt+=1))
        done
        echo "loadgen: /stop returned 200 but Locust state is still 'running'; using fallback."
    fi

    echo "loadgen: Locust API returned '${http_code}'; falling back to docker compose stop..."
    cd "${DEMO_DIR}"
    docker compose "${COMPOSE_FILES[@]}" stop load-generator 2>/dev/null || true
    echo "loadgen: load-generator stopped (fallback). Note: ~30-60s warm-up on restore."
}

do_restore() {
    local total_budget_s=90 quick_budget_s=15 start_ts=0 now_ts=0 elapsed_s=0 remaining_s=0
    local snapshot="" state="" users="" status_line="" http_code=""
    cd "${DEMO_DIR}"
    start_ts="$(date +%s)"

    if ! is_container_running; then
        echo "loadgen: load-generator container not running; starting container (autostart path, no /swarm)..."
        docker compose "${COMPOSE_FILES[@]}" start load-generator 2>/dev/null || {
            echo "loadgen: could not start load-generator (stage may be down); skipping."
            exit 0
        }
        now_ts="$(date +%s)"
        elapsed_s=$(( now_ts - start_ts ))
        remaining_s=$(( total_budget_s - elapsed_s ))
        if (( remaining_s < 1 )); then
            remaining_s=1
        fi
        if wait_for_locust_healthy "${remaining_s}"; then
            status_line="$(locust_status_string)"
            echo "loadgen: restored — ${status_line}."
            return 0
        fi
        echo "loadgen: start path did not reach healthy state within ${remaining_s}s."
    else
        snapshot="$(locust_stats_snapshot 2>/dev/null)" || snapshot=""
        if [[ -n "${snapshot}" ]]; then
            state="${snapshot%% *}"
            users="${snapshot##* }"
            if [[ "${state}" == "running" && "${users}" =~ ^[0-9]+$ ]] && (( users >= 1 )); then
                echo "loadgen: already healthy — state=running, users=${users}."
                return 0
            fi
            if [[ "${state}" == "stopped" ]]; then
                echo "loadgen: restoring load-generator via Locust API /swarm..."
                http_code="$(locust_api POST /swarm \
                    -d "user_count=${LOCUST_USERS}" \
                    -d "spawn_rate=${LOCUST_USERS}" 2>/dev/null)" || http_code=""
                if [[ "${http_code}" != "200" ]]; then
                    echo "loadgen: /swarm returned '${http_code}'; will verify and self-heal if needed."
                fi
            else
                echo "loadgen: observed state='${state}' users='${users}'; checking for healthy recovery."
            fi
        else
            echo "loadgen: could not read Locust state; checking for healthy recovery."
        fi

        if wait_for_locust_healthy "${quick_budget_s}"; then
            status_line="$(locust_status_string)"
            echo "loadgen: restored — ${status_line}."
            return 0
        fi
    fi

    echo "loadgen: escalating to docker compose restart for a clean Locust process..."
    docker compose "${COMPOSE_FILES[@]}" restart load-generator 2>/dev/null || {
        status_line="$(locust_status_string)"
        echo "loadgen: failed to restart load-generator; observed ${status_line}."
        return 1
    }

    now_ts="$(date +%s)"
    elapsed_s=$(( now_ts - start_ts ))
    remaining_s=$(( total_budget_s - elapsed_s ))
    if (( remaining_s < 1 )); then
        remaining_s=1
    fi

    if wait_for_locust_healthy "${remaining_s}"; then
        status_line="$(locust_status_string)"
        echo "loadgen: restored — ${status_line}."
        return 0
    fi

    status_line="$(locust_status_string)"
    echo "loadgen: restore failed — observed ${status_line}."
    return 1
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
