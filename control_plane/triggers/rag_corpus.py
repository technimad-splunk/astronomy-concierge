"""``rag_corpus`` trigger — overlay the agent's RAG corpus with a variant.

Primary layer: **Galileo** (groundedness). The scenario ships a corpus variant
(stale/poisoned docs); ``apply`` POSTs the docs to the running concierge's
authenticated admin API, which layers them over ``agent/knowledge`` in-memory,
so the concierge retrieves the scenario's docs instead of the baseline ones.
``reset`` drops that in-memory overlay.

Non-destructive: the baseline corpus on disk is never modified — an overlay file
with the same name shadows a baseline doc; new names are added. Reset simply
removes the overlay directory, restoring baseline exactly.

The corpus variant lives in the scenario folder. ``trigger.ref`` names the
subdirectory (default: the value of ``ref``); ``params.source`` can override it.
"""

from __future__ import annotations

from pathlib import Path

from ..concierge_client import post_apply, post_reset
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

    def apply(self, scenario: Scenario) -> TriggerResult:
        src = self._source_dir(scenario)
        docs: dict[str, str] = {}
        for doc in sorted(src.glob("*.md")):
            docs[doc.name] = doc.read_text(encoding="utf-8")
        response = post_apply(
            {
                "scenario_id": scenario.id,
                "trigger_type": self.type,
                "rag_corpus_docs": docs,
            }
        )
        rebuilt = int(response.get("rebuilt_sessions", 0))
        return TriggerResult(
            action="apply",
            type=self.type,
            ref=scenario.trigger.ref,
            summary=(
                f"overlaid {len(docs)} corpus doc(s) via concierge API; "
                f"rebuilt {rebuilt} session(s)."
            ),
            before="(baseline corpus)",
            after=f"overlay active ({len(docs)} doc(s))",
            details=[f"source: {src}", f"concierge: {response.get('status', 'applied')}"],
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
                f"removed RAG corpus overlay via concierge API; "
                f"rebuilt {rebuilt} session(s)."
            ),
            before="overlay active",
            after="(baseline corpus)",
            details=[f"concierge: {response.get('status', 'reset')}"],
        )
