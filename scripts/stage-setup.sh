#!/usr/bin/env bash
# stage-setup.sh — Phase-1 stage bootstrap (idempotent).
#
# Makes the stage reproducible from a fresh clone of THIS repo: it vendors the
# upstream OpenTelemetry "Astronomy Shop" at a pinned tag and wires in our
# tracked Splunk overrides, with no manual steps. Safe to run repeatedly.
#
# What it does:
#   1. Reads the pinned demo ref from the single source of truth: stage/demo.ref
#   2. Shallow-clones open-telemetry/opentelemetry-demo at that exact tag into
#      stage/opentelemetry-demo/ (no-op if already present at the correct version;
#      errors if present at a different version so we never silently mix).
#   3. Materializes our tracked Splunk overrides INTO the clone so it exports to
#      Splunk Observability with no manual edits:
#        - stage/splunk-otel/otelcol-config-extras.yml
#            -> <clone>/src/otel-collector/otelcol-config-extras.yml  (the demo's
#               default collector "extras" config the collector already loads)
#        - stage/splunk-otel/docker-compose.override.yml
#            -> <clone>/docker-compose.override.yml
#
# Requires: git + network (clone only; re-runs with the clone present need neither
# network nor a fresh fetch).
#
# SECURITY: reads NO secrets. Tokens are injected later, at run time, by
# stage-up.sh; nothing here touches SPLUNK_ACCESS_TOKEN.
set -euo pipefail

# --- Locate repo, ref file, demo, and our tracked overrides -----------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REF_FILE="${REPO_ROOT}/stage/demo.ref"
DEMO_DIR="${REPO_ROOT}/stage/opentelemetry-demo"
OVERRIDE_DIR="${REPO_ROOT}/stage/splunk-otel"
EXTRAS_SRC="${OVERRIDE_DIR}/otelcol-config-extras.yml"
OVERRIDE_SRC="${OVERRIDE_DIR}/docker-compose.override.yml"

# --- Preconditions ----------------------------------------------------------
command -v git >/dev/null 2>&1 || { echo "FATAL: git not found on PATH." >&2; exit 2; }
[[ -f "${REF_FILE}" ]]     || { echo "FATAL: ${REF_FILE} missing (the pinned-ref source of truth)." >&2; exit 2; }
[[ -f "${EXTRAS_SRC}" ]]   || { echo "FATAL: tracked override ${EXTRAS_SRC} missing." >&2; exit 2; }
[[ -f "${OVERRIDE_SRC}" ]] || { echo "FATAL: tracked override ${OVERRIDE_SRC} missing." >&2; exit 2; }

# --- Read the pinned ref (single source of truth) ---------------------------
# shellcheck disable=SC1090
source "${REF_FILE}"
: "${DEMO_REPO:?DEMO_REPO not set in ${REF_FILE}}"
: "${DEMO_REF:?DEMO_REF not set in ${REF_FILE}}"

clone_version() {
  # Echo the IMAGE_VERSION baked into a clone's .env (the demo tags it = release).
  grep -E '^IMAGE_VERSION=' "${DEMO_DIR}/.env" 2>/dev/null | head -1 \
    | cut -d= -f2- | sed -e 's/[[:space:]]\{1,\}#.*$//' -e 's/[[:space:]]*$//'
}

# --- Step 1: ensure the clone exists at the pinned ref (idempotent) ----------
if [[ -d "${DEMO_DIR}" ]]; then
  if [[ ! -f "${DEMO_DIR}/.env" || ! -f "${DEMO_DIR}/docker-compose.yml" ]]; then
    echo "FATAL: ${DEMO_DIR} exists but doesn't look like the demo clone." >&2
    echo "       Remove it and re-run: rm -rf '${DEMO_DIR}'" >&2
    exit 2
  fi
  HAVE_VERSION="$(clone_version)"
  if [[ "${HAVE_VERSION}" != "${DEMO_REF}" ]]; then
    echo "FATAL: ${DEMO_DIR} is version '${HAVE_VERSION}', but stage/demo.ref pins '${DEMO_REF}'." >&2
    echo "       Remove it and re-run setup: rm -rf '${DEMO_DIR}'" >&2
    exit 2
  fi
  echo "stage-setup: demo clone present at ${DEMO_REF} (no clone needed)."
else
  echo "stage-setup: cloning ${DEMO_REPO} @ ${DEMO_REF} (shallow) ..."
  git clone --depth 1 --branch "${DEMO_REF}" "${DEMO_REPO}" "${DEMO_DIR}"
  # Verify the tag actually resolved to the expected release.
  HAVE_VERSION="$(clone_version)"
  if [[ "${HAVE_VERSION}" != "${DEMO_REF}" ]]; then
    echo "FATAL: cloned tree reports version '${HAVE_VERSION}', expected '${DEMO_REF}'." >&2
    echo "       The tag may not have resolved correctly. Remove ${DEMO_DIR} and retry." >&2
    exit 2
  fi
  echo "stage-setup: cloned and verified version ${HAVE_VERSION}."
fi

# --- Step 2: wire in our tracked Splunk overrides (idempotent re-sync) -------
install -m 0644 "${EXTRAS_SRC}" "${DEMO_DIR}/src/otel-collector/otelcol-config-extras.yml"
install -m 0644 "${OVERRIDE_SRC}" "${DEMO_DIR}/docker-compose.override.yml"
echo "stage-setup: wired Splunk overrides into the clone (collector extras + compose override)."

echo "stage-setup: done. Next: scripts/stage-up.sh"
