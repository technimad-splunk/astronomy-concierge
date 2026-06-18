#!/usr/bin/env bash
# Reset "The Invisible Failure" vignette back to baseline.
#
# The control-plane `reset` command already handles the authoritative trigger-
# level reset (restoring the flagd feature flag to its original variant), so
# this per-scenario script handles any ADDITIONAL cleanup specific to this
# vignette.  Currently that means clearing the RAG corpus cache so the agent
# doesn't serve stale search results from a previous run.
#
# Usage (called by `scripts/control-plane.sh reset invisible-failure`):
#   bash scenarios/invisible-failure/reset.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "invisible-failure/reset: clearing agent overlay state (if any)..."
rm -rf "${REPO_ROOT}/agent/_overlay/knowledge" 2>/dev/null || true

echo "invisible-failure/reset: done — baseline restored."
echo "  The control-plane trigger reset already restored the flagd flag."
echo "  The agent's next run will use the live product catalog (no faults)."
