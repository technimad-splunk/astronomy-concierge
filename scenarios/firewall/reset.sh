#!/usr/bin/env bash
# Reset "The Firewall" vignette back to baseline.
#
# The control-plane `reset` command handles the authoritative trigger-level
# reset (clearing both the prompt overlay and knowledge overlay), so this
# per-scenario script handles any ADDITIONAL cleanup as defense-in-depth.
#
# Usage (called by `scripts/control-plane.sh reset firewall`):
#   bash scenarios/firewall/reset.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "firewall/reset: clearing prompt + knowledge overlay state..."
rm -f "${REPO_ROOT}/agent/_overlay/prompt_overlay.txt" 2>/dev/null || true
rm -f "${REPO_ROOT}/agent/_overlay/knowledge/firewall-overlay.md" 2>/dev/null || true

echo "firewall/reset: done — baseline restored."
echo "  The control-plane trigger reset already cleared both overlays."
echo "  The agent's next run will use its clean system prompt and baseline RAG corpus."
