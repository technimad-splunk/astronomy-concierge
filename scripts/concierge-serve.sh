#!/usr/bin/env bash
# concierge-serve.sh — self-bootstrapping local launcher for the concierge web app.
#
# Creates/reuses a local virtualenv, installs Python dependencies from
# pyproject.toml, optionally builds the standalone frontend bundle, then runs the
# FastAPI concierge service.
#
# Usage:
#   scripts/concierge-serve.sh
#
# SECURITY: reads env from the gitignored .env file; does not print or persist
# secret values.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${ENV_FILE:-${REPO_ROOT}/.env}"
VENV_DIR="${VENV_DIR:-${REPO_ROOT}/.venv}"
FRONTEND_DIR="${REPO_ROOT}/web/concierge/frontend"

cd "${REPO_ROOT}"

[[ -f "${ENV_FILE}" ]] || {
  echo "FATAL: ${ENV_FILE} not found. Run: cp .env.example .env  (then fill in tokens)." >&2
  exit 2
}

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

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  PY="$(pick_python)" || { echo "FATAL: need Python >= 3.12 on PATH." >&2; exit 2; }
  echo "concierge-serve: creating virtualenv at ${VENV_DIR} (using ${PY})"
  "${PY}" -m venv "${VENV_DIR}"
fi
VENV_PY="${VENV_DIR}/bin/python"

PYPROJECT="${REPO_ROOT}/pyproject.toml"
STAMP="${VENV_DIR}/.deps-stamp"
NEW_SUM="$(shasum -a 256 "${PYPROJECT}" | awk '{print $1}')"
if [[ ! -f "${STAMP}" || "$(cat "${STAMP}" 2>/dev/null)" != "${NEW_SUM}" ]]; then
  echo "concierge-serve: installing dependencies from pyproject.toml"
  "${VENV_PY}" -m pip install --quiet --upgrade pip
  "${VENV_PY}" -m pip install --quiet -e "${REPO_ROOT}"
  echo "${NEW_SUM}" > "${STAMP}"
else
  echo "concierge-serve: dependencies up to date (skipping install)"
fi

if [[ ! -d "${FRONTEND_DIR}/dist" ]]; then
  if command -v npm >/dev/null 2>&1; then
    echo "concierge-serve: building frontend bundle"
    (
      cd "${FRONTEND_DIR}"
      npm ci --no-audit --no-fund
      npm run build
    )
  else
    echo "concierge-serve: WARNING — npm not found; serving API + fallback index only." >&2
  fi
fi

read_env_var() {
  local name="$1" line val
  line="$(grep -E "^${name}=" "${ENV_FILE}" | head -1 || true)"
  val="${line#*=}"
  val="$(printf '%s' "${val}" | sed -e 's/[[:space:]]\{1,\}#.*$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
  printf '%s' "${val}"
}

PORT="$(read_env_var CONCIERGE_WEB_PORT)"
PORT="${PORT:-8090}"
export WEB_ALLOWED_ORIGIN="${WEB_ALLOWED_ORIGIN:-$(read_env_var WEB_ALLOWED_ORIGIN)}"
export WEB_ALLOWED_ORIGIN="${WEB_ALLOWED_ORIGIN:-http://localhost:8080}"

echo "concierge-serve: starting FastAPI on 127.0.0.1:${PORT}"
exec "${VENV_PY}" -m uvicorn web.concierge.app:app --host 127.0.0.1 --port "${PORT}"
