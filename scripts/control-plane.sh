#!/usr/bin/env bash
# control-plane.sh — Phase-3 SE control-plane launcher (self-bootstrapping).
#
# Creates/reuses the local virtualenv, installs the project's dependencies from
# pyproject.toml (idempotent), and runs the scenario-harness control plane:
#
#   scripts/control-plane.sh list
#   scripts/control-plane.sh play  <scenario-id> [--prompt "..."] [--no-drive]
#   scripts/control-plane.sh reset <scenario-id>
#   scripts/control-plane.sh verify <scenario-id> [--timeout 30] [--interval 3]
#   scripts/control-plane.sh playlist [--message <pillar>]... [--budget <min>]
#
# Adding a scenario is a drop-in folder under scenarios/ — this script and the
# control plane never change (demo-design §7.2). All arguments pass through to
# `python -m control_plane`.
#
# SECURITY: all credentials are read from the gitignored .env by the app at
# runtime. This script never echoes, logs, or writes secret values.
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
  echo "control-plane: creating virtualenv at ${VENV_DIR} (using ${PY})"
  "${PY}" -m venv "${VENV_DIR}"
fi
VENV_PY="${VENV_DIR}/bin/python"

# Install / refresh dependencies only when pyproject.toml changes (checksum stamp).
PYPROJECT="${REPO_ROOT}/pyproject.toml"
STAMP="${VENV_DIR}/.deps-stamp"
NEW_SUM="$(shasum -a 256 "${PYPROJECT}" | awk '{print $1}')"
if [[ ! -f "${STAMP}" || "$(cat "${STAMP}" 2>/dev/null)" != "${NEW_SUM}" ]]; then
  echo "control-plane: installing dependencies from pyproject.toml (first run or deps changed)"
  "${VENV_PY}" -m pip install --quiet --upgrade pip
  "${VENV_PY}" -m pip install --quiet -e "${REPO_ROOT}"
  echo "${NEW_SUM}" > "${STAMP}"
fi

exec "${VENV_PY}" -m control_plane "$@"
