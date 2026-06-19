#!/usr/bin/env bash
# control-plane-web.sh — Phase-7.4 SE control-plane web UI launcher.
#
# Self-bootstrapping like control-plane.sh / agent-run.sh:
#   - creates/reuses .venv
#   - installs deps from pyproject.toml when changed
#   - launches the web UI at 127.0.0.1:${CONTROL_PLANE_WEB_PORT:-8099}
#
# SECURITY: this launcher is localhost-only by design. The Python entrypoint
# rejects non-loopback hosts (including 0.0.0.0) and exits.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${ENV_FILE:-${REPO_ROOT}/.env}"
VENV_DIR="${VENV_DIR:-${REPO_ROOT}/.venv}"

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
  PY="$(pick_python)" || { echo "FATAL: need Python >= 3.12 on PATH (try: brew install python@3.13)." >&2; exit 2; }
  echo "control-plane-web: creating virtualenv at ${VENV_DIR} (using ${PY})"
  "${PY}" -m venv "${VENV_DIR}"
fi
VENV_PY="${VENV_DIR}/bin/python"

PYPROJECT="${REPO_ROOT}/pyproject.toml"
STAMP="${VENV_DIR}/.deps-stamp"
NEW_SUM="$(shasum -a 256 "${PYPROJECT}" | awk '{print $1}')"
if [[ ! -f "${STAMP}" || "$(cat "${STAMP}" 2>/dev/null)" != "${NEW_SUM}" ]]; then
  echo "control-plane-web: installing dependencies from pyproject.toml (first run or deps changed)"
  "${VENV_PY}" -m pip install --quiet --upgrade pip
  "${VENV_PY}" -m pip install --quiet -e "${REPO_ROOT}"
  echo "${NEW_SUM}" > "${STAMP}"
else
  echo "control-plane-web: dependencies up to date (skipping install)"
fi

echo "control-plane-web: starting localhost UI"
exec "${VENV_PY}" -m web.control_plane "$@"
