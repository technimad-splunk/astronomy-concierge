#!/usr/bin/env bash
# check-connectivity.sh — Phase-0 connectivity check.
#
# Verifies reachability of the demo's external backends and provider
# prerequisites before building, so a cold setup fails fast with a clear message
# instead of deep inside a vignette. Reads config from the environment (.env);
# never prints secret values.
#
# Checks (see docs/implementation-plan.md Phase 0 exit criteria):
#   - Model provider responds:
#       * ollama  — GET ${OLLAMA_HOST}/api/tags        (and reports OLLAMA_MODEL presence)
#       * openai  — GET https://api.openai.com/v1/models (bearer auth)
#   - Splunk INGEST token accepted (SPLUNK_ACCESS_TOKEN / SPLUNK_REALM, X-SF-Token)
#   - Galileo deployment reachable + key valid (GALILEO_API_KEY / GALILEO_CONSOLE_URL)
#
# SECURITY: token-validation checks only. The model-provider and Galileo checks are
# read-only GETs. The Splunk check validates an INGEST token the same way the Phase-1
# Splunk OTel Collector will use it — a POST to the ingest endpoint with an EMPTY
# datapoint payload, so it authenticates without sending any real telemetry. Secrets
# are passed to curl via expanded env vars in headers and are NEVER echoed, logged, or
# printed. Only pass/fail, HTTP status codes, and non-secret config (realm/host/
# provider) are shown.
set -euo pipefail

# --- Locate and load .env (repo root is the parent of scripts/) -------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${ENV_FILE:-${REPO_ROOT}/.env}"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
else
  echo "FATAL: ${ENV_FILE} not found. Copy .env.example to .env and fill in tokens." >&2
  exit 2
fi

# --- Output helpers ---------------------------------------------------------
if [[ -t 1 ]]; then
  C_GREEN=$'\033[0;32m'; C_RED=$'\033[0;31m'; C_YELLOW=$'\033[0;33m'
  C_BOLD=$'\033[1m'; C_RESET=$'\033[0m'
else
  C_GREEN=""; C_RED=""; C_YELLOW=""; C_BOLD=""; C_RESET=""
fi

FAILURES=0
WARNINGS=0

pass() { printf '%s[PASS]%s %s\n' "${C_GREEN}" "${C_RESET}" "$*"; }
fail() { printf '%s[FAIL]%s %s\n' "${C_RED}"   "${C_RESET}" "$*"; FAILURES=$((FAILURES + 1)); }
warn() { printf '%s[WARN]%s %s\n' "${C_YELLOW}" "${C_RESET}" "$*"; WARNINGS=$((WARNINGS + 1)); }
hint() { printf '       %s↳ %s%s\n' "${C_YELLOW}" "$*" "${C_RESET}"; }
note() { printf '       ↳ %s\n' "$*"; }
section() { printf '\n%s== %s ==%s\n' "${C_BOLD}" "$*" "${C_RESET}"; }

# http_status URL [extra curl args...]
# Echoes the HTTP status code (000 on connection failure). Body is discarded.
http_status() {
  local url="$1"; shift
  curl -s -o /dev/null -w '%{http_code}' --max-time 12 "$@" "${url}" 2>/dev/null || echo "000"
}

is_2xx() { [[ "$1" =~ ^2[0-9][0-9]$ ]]; }

# ============================================================================
# 1. Model provider
# ============================================================================
section "Model provider"
PROVIDER="$(printf '%s' "${MODEL_PROVIDER:-ollama}" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"

case "${PROVIDER}" in
  ollama)
    OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
    OLLAMA_MODEL="${OLLAMA_MODEL:-llama3.1:8b}"
    note "provider=ollama  host=${OLLAMA_HOST}  model=${OLLAMA_MODEL}"
    tags_url="${OLLAMA_HOST%/}/api/tags"
    code="$(http_status "${tags_url}")"
    if is_2xx "${code}"; then
      pass "Ollama reachable (HTTP ${code}) at ${OLLAMA_HOST}/api/tags"
      # Read-only: fetch the tag list and check for the configured model.
      if body="$(curl -s --max-time 12 "${tags_url}" 2>/dev/null)" \
         && printf '%s' "${body}" | grep -q "\"${OLLAMA_MODEL}\""; then
        pass "Model '${OLLAMA_MODEL}' is present locally"
      else
        warn "Model '${OLLAMA_MODEL}' not found in local tag list"
        hint "Pull it (non-fatal): ollama pull ${OLLAMA_MODEL}"
      fi
    else
      fail "Ollama not reachable (HTTP ${code}) at ${OLLAMA_HOST}/api/tags"
      hint "Start Ollama (native, not Docker on macOS): 'ollama serve', then 'ollama pull ${OLLAMA_MODEL}'"
    fi
    ;;
  openai)
    note "provider=openai  endpoint=https://api.openai.com/v1/models"
    if [[ -z "${OPENAI_API_KEY:-}" ]]; then
      fail "OPENAI_API_KEY is not set (required when MODEL_PROVIDER=openai)"
      hint "Set OPENAI_API_KEY in .env"
    else
      code="$(http_status "https://api.openai.com/v1/models" -H "Authorization: Bearer ${OPENAI_API_KEY}")"
      if is_2xx "${code}"; then
        pass "OpenAI key authorizes (HTTP ${code})"
      elif [[ "${code}" == "401" || "${code}" == "403" ]]; then
        fail "OpenAI rejected the key (HTTP ${code})"
        hint "Verify OPENAI_API_KEY is valid and active"
      else
        fail "OpenAI check inconclusive (HTTP ${code})"
        hint "Check network / OpenAI status; expected 2xx"
      fi
    fi
    ;;
  *)
    fail "Unsupported MODEL_PROVIDER='${PROVIDER}' (expected 'ollama' or 'openai')"
    hint "Set MODEL_PROVIDER=ollama or MODEL_PROVIDER=openai in .env"
    ;;
esac

# ============================================================================
# 2. Splunk Observability Cloud
# ============================================================================
section "Splunk Observability"
SPLUNK_REALM="${SPLUNK_REALM:-}"
SPLUNK_INGEST_HOST="https://ingest.${SPLUNK_REALM}.signalfx.com"
note "realm=${SPLUNK_REALM:-<unset>}  ingest_host=${SPLUNK_INGEST_HOST}"
note "SPLUNK_ACCESS_TOKEN is an INGEST token (used by the Phase-1 Splunk OTel Collector)"

if [[ -z "${SPLUNK_REALM}" ]]; then
  fail "SPLUNK_REALM is not set"
  hint "Set SPLUNK_REALM (e.g. us0|us1|eu0|ap0) in .env"
elif [[ -z "${SPLUNK_ACCESS_TOKEN:-}" ]]; then
  fail "SPLUNK_ACCESS_TOKEN is not set"
  hint "Set SPLUNK_ACCESS_TOKEN in .env"
else
  # Validate the INGEST token the way it is actually used: POST to the ingest
  # datapoint endpoint. The body is an EMPTY payload (no datapoints), so the token
  # authenticates WITHOUT ingesting any real telemetry.
  #
  # Heuristic: this is an *auth* check, not a payload check.
  #   - 2xx        => token accepted (authenticated) -> PASS
  #   - 400        => request reached auth-passed processing and was rejected only
  #                   at the payload level, which still PROVES the token authenticated
  #                   -> PASS
  #   - 401 / 403  => token/realm rejected at auth -> FAIL
  #   - other      => inconclusive (network/realm) -> FAIL
  code="$(http_status "${SPLUNK_INGEST_HOST}/v2/datapoint" \
    -X POST \
    -H "X-SF-Token: ${SPLUNK_ACCESS_TOKEN}" \
    -H "Content-Type: application/json" \
    --data '{"gauge":[],"counter":[],"cumulative_counter":[]}')"
  if is_2xx "${code}" || [[ "${code}" == "400" ]]; then
    pass "Splunk ingest token accepted (HTTP ${code}) for realm '${SPLUNK_REALM}'"
    [[ "${code}" == "400" ]] && note "HTTP 400 is payload-level (empty body); token still authenticated"
  elif [[ "${code}" == "401" || "${code}" == "403" ]]; then
    fail "Splunk rejected the ingest token (HTTP ${code}) — invalid token or wrong realm"
    hint "Confirm SPLUNK_ACCESS_TOKEN and that SPLUNK_REALM='${SPLUNK_REALM}' matches the token's org"
  else
    fail "Splunk check inconclusive (HTTP ${code})"
    hint "Check network / realm '${SPLUNK_REALM}'; expected 2xx/400 from ${SPLUNK_INGEST_HOST}"
  fi
fi

# ============================================================================
# 3. Galileo
# ============================================================================
section "Galileo"
GALILEO_CONSOLE_URL="${GALILEO_CONSOLE_URL:-}"
GALILEO_PROJECT="${GALILEO_PROJECT:-<unset>}"

# Derive the API base from the console URL: strip any path, then replace the
# leading 'console' host label with 'api' (Galileo enterprise convention).
# e.g. https://console.multitenant.galileocloud.io/splunkse
#   ->  https://api.multitenant.galileocloud.io
derive_galileo_api_base() {
  local url="$1" scheme rest host
  scheme="${url%%://*}"
  rest="${url#*://}"
  host="${rest%%/*}"          # drop path (org slug etc.)
  if [[ "${host}" == console.* ]]; then
    host="api.${host#console.}"
  elif [[ "${host}" == console-* ]]; then
    host="api-${host#console-}"
  else
    host="${host/console/api}"
  fi
  printf '%s://%s' "${scheme}" "${host}"
}

if [[ -z "${GALILEO_CONSOLE_URL}" ]]; then
  # No console URL => default hosted SaaS API base.
  GALILEO_API_BASE="https://api.galileo.ai"
  note "GALILEO_CONSOLE_URL unset; assuming hosted SaaS base ${GALILEO_API_BASE}"
else
  GALILEO_API_BASE="$(derive_galileo_api_base "${GALILEO_CONSOLE_URL}")"
  note "console=${GALILEO_CONSOLE_URL}"
fi
note "api_base=${GALILEO_API_BASE}  project=${GALILEO_PROJECT}"

if [[ -z "${GALILEO_API_KEY:-}" ]]; then
  fail "GALILEO_API_KEY is not set"
  hint "Set GALILEO_API_KEY in .env"
else
  # 3a. Deployment reachability via unauthenticated healthcheck (GET /v2/healthcheck).
  health_url="${GALILEO_API_BASE}/v2/healthcheck"
  hcode="$(http_status "${health_url}")"
  if is_2xx "${hcode}"; then
    pass "Galileo deployment reachable (HTTP ${hcode}) at ${health_url}"
  else
    warn "Galileo healthcheck returned HTTP ${hcode} at ${health_url}"
    hint "If non-2xx, the derived api_base may be wrong for this deployment"
  fi

  # 3b. API key validity via a read-only authenticated GET (/v2/datasets).
  auth_url="${GALILEO_API_BASE}/v2/datasets"
  acode="$(http_status "${auth_url}" -H "Galileo-API-Key: ${GALILEO_API_KEY}")"
  if is_2xx "${acode}"; then
    pass "Galileo API key accepted (HTTP ${acode}) — deployment confirmed reachable"
  elif [[ "${acode}" == "401" || "${acode}" == "403" ]]; then
    fail "Galileo rejected the API key (HTTP ${acode})"
    hint "Verify GALILEO_API_KEY and that it belongs to ${GALILEO_API_BASE}"
  elif [[ "${acode}" == "404" ]]; then
    warn "Galileo auth probe endpoint not found (HTTP ${acode}) — endpoint-unknown"
    note "Tried GET ${auth_url}. Healthcheck above is the reachability signal; the"
    note "auth path may differ on this deployment. Best assessment: see healthcheck result."
  else
    warn "Galileo auth probe inconclusive (HTTP ${acode})"
    note "Tried GET ${auth_url}. Best assessment: reachable=$(is_2xx "${hcode}" && echo yes || echo unknown), auth=unconfirmed."
  fi
fi

# ============================================================================
# Summary
# ============================================================================
section "Summary"
if [[ "${FAILURES}" -eq 0 ]]; then
  if [[ "${WARNINGS}" -gt 0 ]]; then
    printf '%sAll required checks passed%s (with %d warning(s)).\n' "${C_GREEN}" "${C_RESET}" "${WARNINGS}"
  else
    printf '%sAll checks passed.%s\n' "${C_GREEN}" "${C_RESET}"
  fi
  exit 0
else
  printf '%s%d check(s) failed%s, %d warning(s). See hints above.\n' "${C_RED}" "${FAILURES}" "${C_RESET}" "${WARNINGS}"
  exit 1
fi
