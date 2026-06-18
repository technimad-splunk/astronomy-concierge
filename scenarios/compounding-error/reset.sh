#!/usr/bin/env bash
# Reset "The Compounding Error" vignette back to baseline.
#
# The control-plane `reset` command handles the authoritative trigger-level
# reset (restoring the flagd `paymentFailure` flag to "off"), so this
# per-scenario script handles any ADDITIONAL cleanup specific to this vignette.
#
# Usage (called by `scripts/control-plane.sh reset compounding-error`):
#   bash scenarios/compounding-error/reset.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "compounding-error/reset: clearing any residual agent overlay state..."
rm -f "${REPO_ROOT}/agent/_overlay/tool_faults.json" 2>/dev/null || true

echo "compounding-error/reset: done — baseline restored."
echo "  The control-plane trigger reset already restored the flagd paymentFailure"
echo "  flag to 'off'. The payment service will resume normal operation."
