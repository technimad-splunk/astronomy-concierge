"""``prompt_overlay`` trigger — inject SE-controlled text into the agent prompt.

Primary layer: **Galileo** (guardrails). The scenario ships an overlay payload
(e.g. a poisoned product review / prompt-injection string, or PII bait);
``apply`` writes it to the stable overlay seam (``agent/_overlay/prompt_overlay.txt``),
which ``agent/graph.py`` appends to the system prompt on startup. ``reset`` clears it.

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
        dest = self._overlay_file()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(payload + "\n", encoding="utf-8")
        preview = payload.splitlines()[0][:80] if payload else ""
        return TriggerResult(
            action="apply",
            type=self.type,
            ref=scenario.trigger.ref,
            summary=f"injected prompt overlay ({len(payload)} chars) into the agent system prompt.",
            before="(no overlay)",
            after=f"overlay active — starts: {preview!r}",
            details=[f"overlay: {dest}"],
        )

    def reset(self, scenario: Scenario) -> TriggerResult:
        dest = self._overlay_file()
        existed = dest.is_file()
        dest.unlink(missing_ok=True)
        return TriggerResult(
            action="reset",
            type=self.type,
            ref=scenario.trigger.ref,
            summary="cleared prompt overlay; baseline system prompt restored."
            if existed
            else "no prompt overlay was active (already baseline).",
            before="overlay active" if existed else "(no overlay)",
            after="(no overlay)",
            details=[f"overlay: {dest}"],
        )
