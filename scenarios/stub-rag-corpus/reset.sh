#!/usr/bin/env bash
# Per-scenario reset hook for the rag_corpus harness stub.
# Trigger-level reset (control_plane) is authoritative: it removes the corpus
# overlay (agent/_overlay/knowledge/). No extra cleanup needed for the stub.
set -euo pipefail
echo "stub-rag-corpus: trigger-level reset removed the corpus overlay; baseline restored."
