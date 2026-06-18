"""Splunk signal verifier — operator-attested (documented limitation).

Our ``SPLUNK_ACCESS_TOKEN`` is an **ingest-only** token: it authorizes OTLP
ingest into Splunk Observability, but the management / APM query APIs reject it
(HTTP 401 — confirmed earlier). So ``control_plane`` deliberately does **not**
attempt live Splunk APM querying from the CLI — it structurally cannot.

Rather than leave the Splunk side as an indefinite "unverifiable" blank (which
reads like the demo is half-finished), this verifier reports the Splunk signal
as ``attested``: a distinct, explicit result state meaning a human verified it
out-of-band via the Splunk Observability APM MCP / UI and recorded the evidence
HERE. This is NOT a faked auto-pass and NOT a silent gap — the embedded evidence
makes the basis of the confirmation auditable.

``apm_all_green`` is the Invisible-Failure punchline. It is **concierge-scoped**:
it asserts that *the concierge path stayed green / the failure was operationally
invisible to APM*, NOT that every service in the environment is green. The
vendored Astronomy Shop ships built-in background chaos (stale "Critical"
detectors with empty alert lists on unrelated store services), so a
whole-environment "all green" claim would be false — and beside the point.

Swapping in a real auto-querying Splunk verifier later means only providing an
org/API token and implementing :meth:`verify` against the APM API — the control
plane, manifest, and report format are unchanged (the per-backend pluggability
the design calls for).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import SignalResult, SignalVerifier

if TYPE_CHECKING:
    from ..manifest import Scenario

# Live evidence gathered by the operator via the Splunk Observability APM MCP
# (splunko11y) on 2026-06-18, environment local-agent-galileo (eu0), over a ~3h
# window covering the vignette run. Concierge-scoped on purpose (see module doc).
_APM_ALL_GREEN_ATTESTATION = (
    "operator-attested: verified out-of-band via the Splunk APM o11y MCP on "
    "2026-06-18; NOT auto-queryable from the CLI (control_plane holds an "
    "ingest-only token, no APM query/management API access).\n"
    "    Scope: the CONCIERGE PATH stayed green / the failure was operationally "
    "invisible to APM — this is NOT a claim that every service is green (the "
    "Astronomy Shop ships built-in background chaos).\n"
    "    Evidence (env local-agent-galileo, eu0, ~3h window):\n"
    "      - astronomy-concierge: requestCount=1, errorCount=0, metric "
    "health=Ok, no detector alerts — the agent looked perfectly healthy in APM "
    "while producing an ungrounded answer (the punchline).\n"
    "      - product-catalog (the triggered service): requestCount=4285, "
    "errorCount=8 (~0.2%), health=Ok.\n"
    "      - all 25 services report metric-level health=Ok.\n"
    "      - 6 store services (ad, recommendation, checkout, email, payment, "
    "quote) show a detector entity_health.status=Critical with EMPTY alert "
    "lists and absurd P99s — pre-existing demo chaos / stale detectors, NOT "
    "caused by the vignette (exactly why apm_all_green is concierge-scoped)."
)

# Any other (future) Splunk signal without an attestation is reported honestly
# as unverifiable rather than faked.
_UNVERIFIABLE_REASON = (
    "unverified (ingest-only token; needs an org/API token or an operator-driven "
    "MCP/UI check). Confirm in Splunk Observability APM via the o11y MCP."
)

_ATTESTATIONS: dict[str, str] = {
    "apm_all_green": _APM_ALL_GREEN_ATTESTATION,
}


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
        results: list[SignalResult] = []
        for s in signals:
            attestation = _ATTESTATIONS.get(s)
            if attestation is not None:
                results.append(SignalResult("splunk", s, "attested", attestation))
            else:
                results.append(SignalResult("splunk", s, "unverifiable", _UNVERIFIABLE_REASON))
        return results
