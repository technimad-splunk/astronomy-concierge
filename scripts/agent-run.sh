#!/usr/bin/env bash
# agent-run.sh — Phase-2 concierge launcher (self-bootstrapping, idempotent).
#
# Creates/reuses a local virtualenv, installs the agent's dependencies from
# pyproject.toml, and runs the LangGraph shopping concierge. The agent is
# instrumented ONCE with OpenTelemetry GenAI (OpenInference) and fans telemetry
# out to BOTH Galileo (GalileoCallback) and Splunk (OTLP/gRPC -> the local
# Splunk OTel Collector, which forwards to Splunk Observability — never sapm).
#
# Usage:
#   scripts/agent-run.sh                                   # interactive chat
#   scripts/agent-run.sh --prompt "recommend a beginner telescope"   # one-shot
#   scripts/agent-run.sh --session-id demo-001 --prompt "..."        # fixed session
# Any arguments are passed straight through to `python -m agent`.
#
# Prereqs (see README): the stage is up (scripts/stage-up.sh) and a model
# provider is reachable (native Ollama serving OLLAMA_MODEL, or OPENAI_API_KEY).
#
# SECURITY: all credentials are read from the gitignored .env by the app at
# runtime. This script never echoes, logs, or writes secret values.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${ENV_FILE:-${REPO_ROOT}/.env}"
VENV_DIR="${VENV_DIR:-${REPO_ROOT}/.venv}"

cd "${REPO_ROOT}"

# --- Preconditions ----------------------------------------------------------
[[ -f "${ENV_FILE}" ]] || {
  echo "FATAL: ${ENV_FILE} not found. Run: cp .env.example .env  (then fill in tokens)." >&2
  exit 2
}

# Find a Python >= 3.12 interpreter (pyproject requires-python = >=3.12).
pick_python() {
  for cand in python3.13 python3.12 python3; do
    if command -v "${cand}" >/dev/null 2>&1; then
      if "${cand}" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,12) else 1)' 2>/dev/null; then
        echo "${cand}"; return 0
      fi
    fi
  done
  return 1
}

# --- Create / reuse the virtualenv ------------------------------------------
if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  PY="$(pick_python)" || { echo "FATAL: need Python >= 3.12 on PATH (try Homebrew: brew install python@3.13)." >&2; exit 2; }
  echo "agent-run: creating virtualenv at ${VENV_DIR} (using ${PY})"
  "${PY}" -m venv "${VENV_DIR}"
fi
VENV_PY="${VENV_DIR}/bin/python"

# --- Install / refresh dependencies (idempotent) ----------------------------
# A marker file keyed to pyproject.toml's checksum lets us skip reinstalling
# when nothing changed, while still re-syncing after a dependency bump.
PYPROJECT="${REPO_ROOT}/pyproject.toml"
STAMP="${VENV_DIR}/.deps-stamp"
NEW_SUM="$(shasum -a 256 "${PYPROJECT}" | awk '{print $1}')"
if [[ ! -f "${STAMP}" || "$(cat "${STAMP}" 2>/dev/null)" != "${NEW_SUM}" ]]; then
  echo "agent-run: installing dependencies from pyproject.toml (first run or deps changed)"
  "${VENV_PY}" -m pip install --quiet --upgrade pip
  "${VENV_PY}" -m pip install --quiet -e "${REPO_ROOT}"
  echo "${NEW_SUM}" > "${STAMP}"
else
  echo "agent-run: dependencies up to date (skipping install)"
fi

# --- Non-fatal preflight (helpful hints; secret-safe) -----------------------
STORE_URL="$(grep -E '^STORE_BASE_URL=' "${ENV_FILE}" | head -1 | sed -e 's/^STORE_BASE_URL=//' -e 's/[[:space:]]*#.*$//' -e 's/[[:space:]]*$//')"
STORE_URL="${STORE_URL:-http://localhost:8080}"
if ! curl -fs -o /dev/null --max-time 3 "${STORE_URL}/api/products?currencyCode=USD" 2>/dev/null; then
  echo "agent-run: WARNING — store API not reachable at ${STORE_URL} (is the stage up? scripts/stage-up.sh)" >&2
fi

# --- Run --------------------------------------------------------------------
echo "agent-run: starting concierge (python -m agent)"
exec "${VENV_PY}" -m agent "$@"
