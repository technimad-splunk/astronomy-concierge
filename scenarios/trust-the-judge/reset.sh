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

echo "trust-the-judge/reset: trigger-level API reset is authoritative..."

echo "trust-the-judge/reset: done — baseline restored."
echo "  The control-plane trigger reset already cleared both overlays."
echo "  The agent is back to its normal system prompt and baseline RAG corpus."
