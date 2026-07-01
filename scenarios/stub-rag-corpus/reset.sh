#!/usr/bin/env bash
# Per-scenario reset hook for the rag_corpus harness stub.
# Trigger-level reset (control_plane) is authoritative for in-memory corpus
# overlays in the running concierge service. No extra cleanup needed.
set -euo pipefail
echo "stub-rag-corpus: trigger-level reset cleared corpus overlay state; baseline restored."
