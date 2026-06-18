#!/usr/bin/env bash
# Per-scenario reset hook for the tool_fault harness stub.
# Trigger-level reset (control_plane) is authoritative: it clears the tool-fault
# overlay entry. No extra cleanup needed for the stub.
set -euo pipefail
echo "stub-tool-fault: trigger-level reset cleared the tool fault; tool healthy again."
