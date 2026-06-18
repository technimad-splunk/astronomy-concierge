"""Splunk signal verifier — unverified-by-design (documented limitation).

Our ``SPLUNK_ACCESS_TOKEN`` is an **ingest-only** token: it authorizes OTLP
ingest into Splunk Observability, but the management / APM query APIs reject it
(HTTP 401 — confirmed earlier). So this repo deliberately does **not** attempt
live Splunk APM querying. Instead this verifier implements the standard
:class:`SignalVerifier` interface and reports every Splunk signal as
``unverifiable`` with a clear, honest reason.

Splunk-side confirmation (e.g. ``apm_all_green`` — the Invisible-Failure
punchline) is performed by the SE out-of-band via the Splunk Observability MCP /
UI. Swapping in a real Splunk verifier later means only providing an org/API
token and implementing :meth:`verify` against the APM API — the control plane,
manifest, and report format are unchanged (the per-backend pluggability the
design calls for).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import SignalResult, SignalVerifier

if TYPE_CHECKING:
    from ..manifest import Scenario

_REASON = (
    "unverified (ingest-only token; needs an org/API token or SE-driven "
    "MCP/UI check). Confirm in Splunk Observability APM via the o11y MCP."
)


class SplunkVerifier(SignalVerifier):
    backend = "splunk"

    def verify(
        self,
        signals: list[str],
        scenario: "Scenario",
        *,
        timeout_s: float,
        interval_s: float,
    ) -> list[SignalResult]:
        return [SignalResult("splunk", s, "unverifiable", _REASON) for s in signals]
