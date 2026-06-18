"""``tool_fault`` trigger — fault one of the agent's tools.

Primary layer: **Galileo** (tool selection) + **Splunk**. The scenario names a
tool to fault; ``apply`` records it in the stable overlay seam
(``agent/_overlay/tool_faults.json``), which ``agent/tools.py`` reads when it
builds the tool set:

- ``mode=error``  (default) — the tool stays available but every call returns an
  error, inducing recovery/retry behaviour Galileo surfaces (Tool Selection
  Quality, loop clustering).
- ``mode=remove``           — the tool is withheld from the agent, constraining
  its available tools.

``reset`` removes just this scenario's fault entry (leaving any others intact).

``trigger.ref`` is the tool name (e.g. ``get_recommendations``). Optional
``params.mode`` (error|remove) and ``params.message`` (custom error text).
This faults the agent directly and deterministically, so it proves apply/reset
without depending on stage internals; demo backend-failure flags remain
reachable via the ``feature_flag`` trigger when a Splunk-layer fault is wanted.
"""

from __future__ import annotations

import json
from pathlib import Path

from agent.overlay import overlay_dir

from ..manifest import Scenario
from .base import Trigger, TriggerError, TriggerResult

_KNOWN_TOOLS = (
    "search_knowledge_base",
    "search_products",
    "get_product_details",
    "get_recommendations",
    "add_to_cart",
    "view_cart",
    "list_currencies",
)
_MODES = ("error", "remove")


class ToolFaultTrigger(Trigger):
    type = "tool_fault"

    def _faults_file(self) -> Path:
        return overlay_dir() / "tool_faults.json"

    def _read(self, path: Path) -> dict:
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write(self, path: Path, data: dict) -> None:
        if data:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        else:
            path.unlink(missing_ok=True)

    def apply(self, scenario: Scenario) -> TriggerResult:
        ref = scenario.trigger.ref
        if ref not in _KNOWN_TOOLS:
            raise TriggerError(
                f"unknown tool '{ref}'. The concierge's tools are: {', '.join(_KNOWN_TOOLS)}."
            )
        mode = str(scenario.trigger.params.get("mode", "error"))
        if mode not in _MODES:
            raise TriggerError(f"trigger.params.mode must be one of {_MODES}, got '{mode}'.")
        message = str(scenario.trigger.params.get("message", ""))

        path = self._faults_file()
        data = self._read(path)
        data[ref] = {"mode": mode, "message": message}
        self._write(path, data)
        return TriggerResult(
            action="apply",
            type=self.type,
            ref=ref,
            summary=f"faulted tool '{ref}' (mode={mode}); agent picks it up on next run.",
            before="(tool healthy)",
            after=f"faulted (mode={mode})",
            details=[f"overlay: {path}"],
        )

    def reset(self, scenario: Scenario) -> TriggerResult:
        ref = scenario.trigger.ref
        path = self._faults_file()
        data = self._read(path)
        existed = ref in data
        data.pop(ref, None)
        self._write(path, data)
        return TriggerResult(
            action="reset",
            type=self.type,
            ref=ref,
            summary=f"cleared fault on tool '{ref}'; tool healthy again."
            if existed
            else f"no fault was active on tool '{ref}' (already healthy).",
            before="faulted" if existed else "(tool healthy)",
            after="(tool healthy)",
            details=[f"overlay: {path}"],
        )
