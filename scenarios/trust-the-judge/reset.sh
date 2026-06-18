#!/usr/bin/env bash
# Reset "Trust the Judge" vignette back to baseline.
#
# The control-plane `reset` command handles the authoritative trigger-level
# reset (clearing the prompt overlay + knowledge overlay). This per-scenario
# script handles any additional cleanup as defense-in-depth.
#
# Usage (called by `scripts/control-plane.sh reset trust-the-judge`):
#   bash scenarios/trust-the-judge/reset.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "trust-the-judge/reset: clearing prompt + knowledge overlay state..."
rm -f "${REPO_ROOT}/agent/_overlay/prompt_overlay.txt" 2>/dev/null || true
rm -f "${REPO_ROOT}/agent/_overlay/knowledge/trust-the-judge-overlay.md" 2>/dev/null || true

echo "trust-the-judge/reset: done — baseline restored."
echo "  The control-plane trigger reset already cleared both overlays."
echo "  The agent is back to its normal system prompt and baseline RAG corpus."
