#!/usr/bin/env bash
# Per-scenario reset hook for the feature_flag harness stub.
#
# The trigger-level reset (control_plane) is AUTHORITATIVE: it restores the
# flagd flag's original defaultVariant deterministically. This script is the
# per-scenario `reset.sh` contract hook for any extra cleanup a real vignette
# would add (e.g. pre-warming a dashboard). The stub has none.
set -euo pipefail
echo "stub-feature-flag: trigger-level reset restored the flagd flag; no extra cleanup needed."
