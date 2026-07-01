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

echo "compounding-error/reset: trigger-level API reset is authoritative..."

echo "compounding-error/reset: done — baseline restored."
echo "  The control-plane trigger reset already restored the flagd paymentFailure"
echo "  flag to 'off'. The payment service will resume normal operation."
