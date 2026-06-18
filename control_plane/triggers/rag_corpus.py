"""``rag_corpus`` trigger — overlay the agent's RAG corpus with a variant.

Primary layer: **Galileo** (groundedness). The scenario ships a corpus variant
(stale/poisoned docs); ``apply`` layers it over ``agent/knowledge`` via the stable
overlay seam (``agent/_overlay/knowledge/``), so the concierge retrieves the
scenario's docs instead of the baseline ones. ``reset`` drops the overlay.

Non-destructive: the baseline corpus on disk is never modified — an overlay file
with the same name shadows a baseline doc; new names are added. Reset simply
removes the overlay directory, restoring baseline exactly.

The corpus variant lives in the scenario folder. ``trigger.ref`` names the
subdirectory (default: the value of ``ref``); ``params.source`` can override it.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from agent.overlay import overlay_dir

from ..manifest import Scenario
from .base import Trigger, TriggerError, TriggerResult


class RagCorpusTrigger(Trigger):
    type = "rag_corpus"

    def _source_dir(self, scenario: Scenario) -> Path:
        source = scenario.trigger.params.get("source") or scenario.trigger.ref
        src = (scenario.dir / source).resolve()
        if not src.is_dir():
            raise TriggerError(
                f"rag_corpus source '{source}' not found at {src}. Provide a "
                "directory of .md docs in the scenario folder (trigger.ref or "
                "trigger.params.source)."
            )
        docs = sorted(src.glob("*.md"))
        if not docs:
            raise TriggerError(f"rag_corpus source {src} contains no .md documents.")
        return src

    def _overlay_knowledge(self) -> Path:
        return overlay_dir() / "knowledge"

    def apply(self, scenario: Scenario) -> TriggerResult:
        src = self._source_dir(scenario)
        dest = self._overlay_knowledge()
        dest.mkdir(parents=True, exist_ok=True)
        copied = []
        for doc in sorted(src.glob("*.md")):
            shutil.copy2(doc, dest / doc.name)
            copied.append(doc.name)
        return TriggerResult(
            action="apply",
            type=self.type,
            ref=scenario.trigger.ref,
            summary=f"overlaid {len(copied)} corpus doc(s) onto agent/knowledge: {', '.join(copied)}.",
            before="(baseline corpus)",
            after=f"overlay active ({len(copied)} doc(s))",
            details=[f"overlay: {dest}", f"source: {src}"],
        )

    def reset(self, scenario: Scenario) -> TriggerResult:
        dest = self._overlay_knowledge()
        existed = dest.is_dir()
        if existed:
            shutil.rmtree(dest)
        return TriggerResult(
            action="reset",
            type=self.type,
            ref=scenario.trigger.ref,
            summary="removed RAG corpus overlay; baseline corpus restored."
            if existed
            else "no RAG corpus overlay was active (already baseline).",
            before="overlay active" if existed else "(baseline corpus)",
            after="(baseline corpus)",
            details=[f"overlay: {dest}"],
        )
