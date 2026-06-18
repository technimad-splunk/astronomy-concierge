"""Pluggable trigger layer — shared contract.

Every trigger is a handler with two operations (demo-design §7.3):

- ``apply(scenario)``  — INDUCE the failure (turn the fault on).
- ``reset(scenario)``  — restore baseline deterministically (turn it off).

The trigger set is FIXED — ``feature_flag | rag_corpus | tool_fault |
prompt_overlay`` — and must not be extended (scope guard). Handlers report what
they changed via :class:`TriggerResult` so the control plane can show the SE that
``apply`` changed state and ``reset`` restored it, without printing secrets.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoid a runtime import cycle
    from ..manifest import Scenario


class TriggerError(RuntimeError):
    """Raised when a trigger cannot apply or reset (with a clear, actionable msg)."""


@dataclass
class TriggerResult:
    """Outcome of an ``apply``/``reset`` call — surfaced to the SE, no secrets."""

    action: str          # "apply" | "reset"
    type: str            # the trigger type
    ref: str             # what it acted on
    summary: str         # human-readable description of the state change
    before: str = ""     # observed state before (best-effort)
    after: str = ""      # observed state after (best-effort)
    details: list[str] = field(default_factory=list)


class Trigger(ABC):
    """Base class for the four fixed trigger mechanisms."""

    #: the manifest ``trigger.type`` this handler implements
    type: str = ""

    @abstractmethod
    def apply(self, scenario: "Scenario") -> TriggerResult:
        ...

    @abstractmethod
    def reset(self, scenario: "Scenario") -> TriggerResult:
        ...
