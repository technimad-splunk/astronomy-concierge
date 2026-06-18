"""Stable scenario-overlay seam for the concierge.

This is the one small, *stable* hook the scenario harness (Phase 3) uses to bend
the agent's behaviour **without ever editing the agent's core logic**. Triggers
write into a runtime overlay directory; the agent reads it on startup. When no
scenario is active the overlay is absent and the agent runs at baseline.

Three overlay surfaces, one per agent-side trigger mechanism (demo-design §7.3):

- ``knowledge/``           — ``rag_corpus`` swaps/seeds the RAG corpus. Files here
                             are layered over ``agent/knowledge`` (same filename
                             replaces a baseline doc; new filenames are added).
- ``prompt_overlay.txt``   — ``prompt_overlay`` injects SE-controlled text that is
                             appended to the system prompt (e.g. an injection
                             payload or PII bait).
- ``tool_faults.json``     — ``tool_fault`` faults named tools: ``{"<tool>":
                             {"mode": "error"|"remove", "message": "..."}}``.

The overlay directory is runtime state (gitignored). Its location can be
overridden with ``AGENT_OVERLAY_DIR`` for tests. Reads are defensive: a missing
or malformed overlay degrades to baseline rather than breaking the agent.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_DEFAULT_OVERLAY_DIR = Path(__file__).parent / "_overlay"


def overlay_dir() -> Path:
    """Runtime overlay directory (``AGENT_OVERLAY_DIR`` overrides the default)."""
    env = os.getenv("AGENT_OVERLAY_DIR")
    return Path(env) if env else _DEFAULT_OVERLAY_DIR


def knowledge_overlay_dir() -> Path | None:
    """Return the corpus-overlay directory iff it exists and holds ``*.md``."""
    d = overlay_dir() / "knowledge"
    if d.is_dir() and any(d.glob("*.md")):
        return d
    return None


def prompt_overlay_text() -> str:
    """Return the prompt-overlay text to append to the system prompt (or "")."""
    f = overlay_dir() / "prompt_overlay.txt"
    if f.is_file():
        try:
            return f.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    return ""


def faulted_tools() -> dict[str, dict[str, str]]:
    """Return the active tool-fault map ``{tool_name: {mode, message}}`` (or {})."""
    f = overlay_dir() / "tool_faults.json"
    if not f.is_file():
        return {}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for name, spec in data.items():
        if isinstance(spec, dict):
            out[str(name)] = {
                "mode": str(spec.get("mode", "error")),
                "message": str(spec.get("message", "")),
            }
        else:
            out[str(name)] = {"mode": "error", "message": ""}
    return out
