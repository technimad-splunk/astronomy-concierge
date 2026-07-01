"""In-memory scenario overlay state for the concierge process.

The running concierge process is the authoritative holder for agent-side trigger
state. Reads are used by the agent core (graph/tools/rag) and writes are used by
the concierge service's authenticated admin endpoints.
"""

from __future__ import annotations

from threading import RLock

_LOCK = RLock()
_TOOL_FAULTS: dict[str, dict[str, str]] = {}
_PROMPT_TEXT = ""
_KNOWLEDGE_DOCS: dict[str, str] = {}


def faulted_tools() -> dict[str, dict[str, str]]:
    """Return the active tool-fault map with full per-tool fault specs."""
    with _LOCK:
        return {name: dict(spec) for name, spec in _TOOL_FAULTS.items()}


def prompt_overlay_text() -> str:
    """Return the prompt-overlay text to append to the system prompt (or "")."""
    with _LOCK:
        return _PROMPT_TEXT


def knowledge_overlay_docs() -> dict[str, str]:
    """Return overlay corpus docs as {name -> markdown content}."""
    with _LOCK:
        return dict(_KNOWLEDGE_DOCS)


def set_tool_fault(tool: str, spec: dict[str, str]) -> None:
    with _LOCK:
        normalized = {str(k): str(v) for k, v in spec.items()}
        normalized["mode"] = str(spec.get("mode", "error"))
        normalized["message"] = str(spec.get("message", ""))
        _TOOL_FAULTS[str(tool)] = normalized


def clear_tool_fault(tool: str) -> None:
    with _LOCK:
        _TOOL_FAULTS.pop(str(tool), None)


def set_prompt_overlay(text: str) -> None:
    with _LOCK:
        global _PROMPT_TEXT
        _PROMPT_TEXT = str(text).strip()


def clear_prompt_overlay() -> None:
    with _LOCK:
        global _PROMPT_TEXT
        _PROMPT_TEXT = ""


def set_knowledge_docs(docs: dict[str, str]) -> None:
    with _LOCK:
        global _KNOWLEDGE_DOCS
        _KNOWLEDGE_DOCS = {str(name): str(content) for name, content in docs.items()}


def clear_knowledge_docs() -> None:
    with _LOCK:
        global _KNOWLEDGE_DOCS
        _KNOWLEDGE_DOCS = {}
