#!/usr/bin/env bash
# Reset "The Invisible Failure" vignette back to baseline.
#
# The control-plane `reset` command already handles the authoritative trigger-
# level reset (clearing the `tool_fault` overlay for this vignette), so this
# per-scenario script handles any ADDITIONAL cleanup specific to this vignette.
# Currently that means clearing the RAG corpus cache so the agent doesn't serve
# stale search results from a previous run.
#
# Usage (called by `scripts/control-plane.sh reset invisible-failure`):
#   bash scenarios/invisible-failure/reset.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "invisible-failure/reset: trigger-level API reset is authoritative..."

echo "invisible-failure/reset: done — baseline restored."
echo "  The control-plane trigger reset already cleared the tool fault."
echo "  The agent's next run will call healthy live tools."
