#!/usr/bin/env bash
# Per-scenario reset hook for the prompt_overlay harness stub.
# Trigger-level reset (control_plane) is authoritative: it clears the prompt
# overlay file. No extra cleanup needed for the stub.
set -euo pipefail
echo "stub-prompt-overlay: trigger-level reset cleared the prompt overlay; baseline prompt restored."
