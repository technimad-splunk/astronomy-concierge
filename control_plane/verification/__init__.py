"""Pluggable verification registry + the run entry point.

Verifiers are keyed by backend ("galileo", "splunk"), matching the
``expected_signals`` sections of a manifest. Registering a new backend here is
the only change needed to verify a new signal source — the control plane and
manifest contract are untouched (demo-design §7.4 pluggability).
"""

from __future__ import annotations

from ..manifest import Scenario
from .base import SignalResult, SignalVerifier, VerificationReport
from .galileo_verifier import GalileoVerifier
from .splunk_verifier import SplunkVerifier

DEFAULT_TIMEOUT_S = 30.0
DEFAULT_INTERVAL_S = 3.0

_VERIFIERS: dict[str, SignalVerifier] = {
    GalileoVerifier.backend: GalileoVerifier(),
    SplunkVerifier.backend: SplunkVerifier(),
}


def run_verification(
    scenario: Scenario,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    interval_s: float = DEFAULT_INTERVAL_S,
) -> VerificationReport:
    """Verify a scenario's ``expected_signals`` across all backends."""
    report = VerificationReport(scenario_id=scenario.id)
    sections = {
        "galileo": scenario.expected_signals.galileo,
        "splunk": scenario.expected_signals.splunk,
    }
    for backend, signals in sections.items():
        if not signals:
            continue
        verifier = _VERIFIERS.get(backend)
        if verifier is None:
            report.results.extend(
                SignalResult(backend, s, "unverifiable", f"no verifier registered for '{backend}'.")
                for s in signals
            )
            continue
        report.results.extend(
            verifier.verify(signals, scenario, timeout_s=timeout_s, interval_s=interval_s)
        )
    return report


__all__ = [
    "SignalResult",
    "SignalVerifier",
    "VerificationReport",
    "run_verification",
    "DEFAULT_TIMEOUT_S",
    "DEFAULT_INTERVAL_S",
]
