"""The fixed trigger registry (demo-design §7.3).

Maps each manifest ``trigger.type`` to its handler. The set is intentionally
**closed**: ``feature_flag | rag_corpus | tool_fault | prompt_overlay``. Adding
new types here would erode the "drop-in folder, no core edits" guarantee, so the
manifest validator also rejects unknown types.
"""

from __future__ import annotations

from ..manifest import Scenario
from .base import Trigger, TriggerError, TriggerResult
from .feature_flag import FeatureFlagTrigger
from .prompt_overlay import PromptOverlayTrigger
from .rag_corpus import RagCorpusTrigger
from .tool_fault import ToolFaultTrigger

_REGISTRY: dict[str, Trigger] = {
    FeatureFlagTrigger.type: FeatureFlagTrigger(),
    RagCorpusTrigger.type: RagCorpusTrigger(),
    ToolFaultTrigger.type: ToolFaultTrigger(),
    PromptOverlayTrigger.type: PromptOverlayTrigger(),
}

TRIGGER_TYPES = tuple(_REGISTRY)


def get_trigger(trigger_type: str) -> Trigger:
    """Return the handler for ``trigger_type`` (or raise :class:`TriggerError`)."""
    try:
        return _REGISTRY[trigger_type]
    except KeyError:
        raise TriggerError(
            f"no handler for trigger type '{trigger_type}'. Fixed set: {', '.join(TRIGGER_TYPES)}."
        ) from None


def apply_trigger(scenario: Scenario) -> TriggerResult:
    return get_trigger(scenario.trigger.type).apply(scenario)


def reset_trigger(scenario: Scenario) -> TriggerResult:
    return get_trigger(scenario.trigger.type).reset(scenario)


__all__ = [
    "Trigger",
    "TriggerError",
    "TriggerResult",
    "TRIGGER_TYPES",
    "get_trigger",
    "apply_trigger",
    "reset_trigger",
]
