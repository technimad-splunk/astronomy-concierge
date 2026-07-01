"""``prompt_overlay`` trigger — inject SE-controlled text into the agent context.

Primary layer: **Galileo** (guardrails). The scenario ships an overlay payload
(e.g. a poisoned product review / prompt-injection string, or PII bait);
``apply`` POSTs it to the running concierge service, which stores it in-memory
across TWO overlay seams:

1. prompt overlay text — appended to the system prompt (provides model context).
2. ``<scenario-id>-overlay.md`` — seeded into the RAG
   corpus overlay so the payload appears as a **tool output** in the
   conversation messages when the agent calls ``search_knowledge_base``.

The dual-channel delivery is critical for Galileo's ``prompt_injection`` scorer:
the scorer evaluates the conversation INPUT messages (including tool results),
NOT the hidden system prompt. By seeding the payload into RAG, it appears in a
tool output that the scorer inspects.

``reset`` clears both overlay files.

The payload source: ``trigger.ref`` is a path (relative to the scenario folder)
to a text/markdown file; alternatively ``params.text`` provides inline text.
"""

from __future__ import annotations

from ..concierge_client import post_apply, post_reset
from ..manifest import Scenario
from .base import Trigger, TriggerError, TriggerResult


class PromptOverlayTrigger(Trigger):
    type = "prompt_overlay"

    def _payload(self, scenario: Scenario) -> str:
        inline = scenario.trigger.params.get("text")
        if isinstance(inline, str) and inline.strip():
            return inline
        ref = scenario.trigger.ref
        src = (scenario.dir / ref).resolve()
        if not src.is_file():
            raise TriggerError(
                f"prompt_overlay payload not found at {src}. Provide a text file "
                "(trigger.ref, relative to the scenario folder) or trigger.params.text."
            )
        text = src.read_text(encoding="utf-8").strip()
        if not text:
            raise TriggerError(f"prompt_overlay payload {src} is empty.")
        return text

    def apply(self, scenario: Scenario) -> TriggerResult:
        payload = self._payload(scenario)
        response = post_apply(
            {
                "scenario_id": scenario.id,
                "trigger_type": self.type,
                "prompt_overlay_text": payload,
            }
        )
        rebuilt = int(response.get("rebuilt_sessions", 0))

        preview = payload.splitlines()[0][:80] if payload else ""
        return TriggerResult(
            action="apply",
            type=self.type,
            ref=scenario.trigger.ref,
            summary=(
                f"injected prompt overlay ({len(payload)} chars) via concierge API; "
                f"rebuilt {rebuilt} session(s) with dual-channel injection coverage."
            ),
            before="(no overlay)",
            after=f"overlay active — starts: {preview!r}",
            details=[f"concierge: {response.get('status', 'applied')}"],
        )

    def reset(self, scenario: Scenario) -> TriggerResult:
        response = post_reset(
            {
                "scenario_id": scenario.id,
                "trigger_type": self.type,
            }
        )
        rebuilt = int(response.get("rebuilt_sessions", 0))
        return TriggerResult(
            action="reset",
            type=self.type,
            ref=scenario.trigger.ref,
            summary=(
                f"cleared prompt + knowledge overlay via concierge API; "
                f"rebuilt {rebuilt} session(s)."
            ),
            before="overlay active",
            after="(no overlay)",
            details=[f"concierge: {response.get('status', 'reset')}"],
        )
