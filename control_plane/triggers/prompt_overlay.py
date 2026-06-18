"""``prompt_overlay`` trigger — inject SE-controlled text into the agent context.

Primary layer: **Galileo** (guardrails). The scenario ships an overlay payload
(e.g. a poisoned product review / prompt-injection string, or PII bait);
``apply`` writes it to TWO overlay seams:

1. ``agent/_overlay/prompt_overlay.txt`` — appended to the system prompt
   (provides context for the model's behavior).
2. ``agent/_overlay/knowledge/<scenario-id>-overlay.md`` — seeded into the RAG
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

from pathlib import Path

from agent.overlay import overlay_dir

from ..manifest import Scenario
from .base import Trigger, TriggerError, TriggerResult


class PromptOverlayTrigger(Trigger):
    type = "prompt_overlay"

    def _overlay_file(self) -> Path:
        return overlay_dir() / "prompt_overlay.txt"

    def _knowledge_overlay_file(self, scenario: Scenario) -> Path:
        return overlay_dir() / "knowledge" / f"{scenario.id}-overlay.md"

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

        # 1. Write to system-prompt overlay (model context).
        dest = self._overlay_file()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(payload + "\n", encoding="utf-8")

        # 2. Also seed into the RAG knowledge overlay so the payload surfaces
        #    as a tool output in conversation messages (the channel Galileo's
        #    prompt_injection scorer evaluates).
        knowledge_dest = self._knowledge_overlay_file(scenario)
        knowledge_dest.parent.mkdir(parents=True, exist_ok=True)
        knowledge_dest.write_text(payload + "\n", encoding="utf-8")

        preview = payload.splitlines()[0][:80] if payload else ""
        return TriggerResult(
            action="apply",
            type=self.type,
            ref=scenario.trigger.ref,
            summary=(
                f"injected prompt overlay ({len(payload)} chars) into system prompt "
                f"+ RAG knowledge overlay (dual-channel for scorer coverage)."
            ),
            before="(no overlay)",
            after=f"overlay active — starts: {preview!r}",
            details=[f"prompt overlay: {dest}", f"knowledge overlay: {knowledge_dest}"],
        )

    def reset(self, scenario: Scenario) -> TriggerResult:
        dest = self._overlay_file()
        knowledge_dest = self._knowledge_overlay_file(scenario)
        existed = dest.is_file() or knowledge_dest.is_file()
        dest.unlink(missing_ok=True)
        knowledge_dest.unlink(missing_ok=True)
        return TriggerResult(
            action="reset",
            type=self.type,
            ref=scenario.trigger.ref,
            summary="cleared prompt + knowledge overlay; baseline restored."
            if existed
            else "no prompt overlay was active (already baseline).",
            before="overlay active" if existed else "(no overlay)",
            after="(no overlay)",
            details=[f"prompt overlay: {dest}", f"knowledge overlay: {knowledge_dest}"],
        )
