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

echo "firewall/reset: trigger-level API reset is authoritative..."

echo "firewall/reset: done — baseline restored."
echo "  The control-plane trigger reset already cleared both overlays."
echo "  The agent's next run will use its clean system prompt and baseline RAG corpus."
