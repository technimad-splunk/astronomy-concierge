"""``tool_fault`` trigger — fault one of the agent's tools.

Primary layer: **Galileo** (tool selection) + **Splunk**. The scenario names a
tool to fault; ``apply`` sends the fault spec to the running concierge service's
authenticated admin API, which updates in-memory overlay state that
``agent/tools.py`` reads when it builds the tool set:

- ``mode=error``  (default) — the tool stays available but every call returns an
  error, inducing recovery/retry behaviour Galileo surfaces (Tool Selection
  Quality, loop clustering).
- ``mode=remove``           — the tool is withheld from the agent, constraining
  its available tools.
- ``mode=stale``            — the tool returns a scripted stale/incomplete
  snapshot as a normal successful result (no backend call).

``reset`` removes just this scenario's fault entries (leaving any others intact).

``trigger.ref`` is the primary tool name (e.g. ``get_recommendations``). Optional
``params.mode`` (error|remove|stale), ``params.message`` (custom error text for
``mode=error``), ``params.data`` (scripted stale payload for ``mode=stale``), and
``params.also_fault`` (a list of SIBLING tools to fault with the same spec, so
the agent can't route around a single faulted tool via a tool that exposes the
same data — e.g. the product-read family share live catalog price/description).
This faults the agent directly and deterministically, so it proves apply/reset
without depending on stage internals; demo backend-failure flags remain
reachable via the ``feature_flag`` trigger when a Splunk-layer fault is wanted.
"""

from __future__ import annotations

from ..concierge_client import post_apply, post_reset
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
_MODES = ("error", "remove", "stale")


class ToolFaultTrigger(Trigger):
    type = "tool_fault"

    def _fault_tools(self, scenario: Scenario) -> list[str]:
        """Resolve the full set of tools to fault: ``ref`` + ``params.also_fault``.

        ``also_fault`` lets one scenario fault a FAMILY of tools that expose the
        same data (e.g. the product-read tools) so the agent cannot route around
        a single faulted tool via a sibling. Order-preserving and de-duplicated.
        """
        ref = scenario.trigger.ref
        also = scenario.trigger.params.get("also_fault", []) or []
        if not isinstance(also, list) or not all(isinstance(t, str) for t in also):
            raise TriggerError("trigger.params.also_fault must be a list of tool names.")
        tools: list[str] = []
        for tool in [ref, *also]:
            if tool not in _KNOWN_TOOLS:
                raise TriggerError(
                    f"unknown tool '{tool}'. The concierge's tools are: "
                    f"{', '.join(_KNOWN_TOOLS)}."
                )
            if tool not in tools:
                tools.append(tool)
        return tools

    def apply(self, scenario: Scenario) -> TriggerResult:
        tools = self._fault_tools(scenario)
        ref = scenario.trigger.ref
        mode = str(scenario.trigger.params.get("mode", "error"))
        if mode not in _MODES:
            raise TriggerError(f"trigger.params.mode must be one of {_MODES}, got '{mode}'.")
        message = str(scenario.trigger.params.get("message", ""))
        stale_data = str(scenario.trigger.params.get("data", ""))
        if mode == "stale" and not stale_data.strip():
            raise TriggerError("trigger.params.data is required when trigger.params.mode='stale'.")
        spec = {"mode": mode, "message": message}
        if mode == "stale":
            spec["data"] = stale_data
        # Each apply accumulates one tool entry in the concierge overlay map and
        # rebuilds sessions; the final rebuilt count reflects the live state.
        rebuilt = 0
        status = "applied"
        for tool in tools:
            response = post_apply(
                {
                    "scenario_id": scenario.id,
                    "trigger_type": self.type,
                    "tool_fault": {"tool": tool, **spec},
                }
            )
            rebuilt = int(response.get("rebuilt_sessions", rebuilt))
            status = str(response.get("status", status))
        label = ", ".join(tools)
        return TriggerResult(
            action="apply",
            type=self.type,
            ref=ref,
            summary=(
                f"faulted tool(s) '{label}' (mode={mode}) via concierge API; "
                f"rebuilt {rebuilt} session(s)."
            ),
            before="(tool healthy)",
            after=f"faulted (mode={mode})",
            details=[f"concierge: {status}", f"tools: {label}"],
        )

    def reset(self, scenario: Scenario) -> TriggerResult:
        tools = self._fault_tools(scenario)
        ref = scenario.trigger.ref
        rebuilt = 0
        status = "reset"
        for tool in tools:
            response = post_reset(
                {
                    "scenario_id": scenario.id,
                    "trigger_type": self.type,
                    "ref": tool,
                }
            )
            rebuilt = int(response.get("rebuilt_sessions", rebuilt))
            status = str(response.get("status", status))
        label = ", ".join(tools)
        return TriggerResult(
            action="reset",
            type=self.type,
            ref=ref,
            summary=(
                f"cleared fault on tool(s) '{label}' via concierge API; "
                f"rebuilt {rebuilt} session(s)."
            ),
            before="faulted",
            after="(tool healthy)",
            details=[f"concierge: {status}", f"tools: {label}"],
        )
