"""Verification contract — pluggable per-backend signal verifiers.

``expected_signals`` is declarative so the harness can **auto-verify** each
vignette (demo-design §7.4): confirm the promised Galileo/Splunk signals actually
fired, instead of discovering a dead demo live. The design constraint is that
verifiers are **pluggable per backend** — each backend implements the same
:class:`SignalVerifier` interface, so adding/swapping a backend never touches the
control plane.

A signal resolves to one of five statuses:

- ``pass``         — the signal fired and was confirmed by a live query.
- ``fail``         — the signal was checkable but did NOT fire.
- ``attested``     — confirmed out-of-band by the operator (not auto-queryable
                     from the CLI) and recorded with explicit, embedded evidence.
                     This is NOT a faked auto-pass and NOT an indefinite
                     "unverifiable": it is a deliberate, human-verified result
                     for a check the CLI structurally cannot self-run (e.g. the
                     ingest-only Splunk token can't query the APM API).
- ``unverifiable`` — cannot be checked yet (metric not queryable, no data) —
                     reported honestly, never faked as a pass.
- ``error``        — the verifier itself errored (e.g. auth/network).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from ..manifest import Scenario

Status = Literal["pass", "fail", "attested", "unverifiable", "error"]


@dataclass
class SignalResult:
    backend: str
    signal: str
    status: Status
    detail: str = ""


@dataclass
class VerificationReport:
    scenario_id: str
    results: list[SignalResult] = field(default_factory=list)

    @property
    def passed(self) -> list[SignalResult]:
        return [r for r in self.results if r.status == "pass"]

    @property
    def attested(self) -> list[SignalResult]:
        return [r for r in self.results if r.status == "attested"]

    @property
    def failed(self) -> list[SignalResult]:
        return [r for r in self.results if r.status in ("fail", "error")]

    @property
    def unverifiable(self) -> list[SignalResult]:
        return [r for r in self.results if r.status == "unverifiable"]

    @property
    def overall_pass(self) -> bool:
        """A run passes when nothing FAILED or ERRORED.

        ``attested`` signals (operator-verified out-of-band with embedded
        evidence) and ``unverifiable`` signals (e.g. a Galileo metric not yet
        configured) are reported transparently and do not by themselves fail the
        run — ``attested`` is an affirmative human confirmation, ``unverifiable``
        flags a gap.
        """
        return not self.failed


class SignalVerifier(ABC):
    """Per-backend verifier. Implement :meth:`verify` for one backend."""

    #: backend key matching an ``expected_signals`` section ("galileo"/"splunk")
    backend: str = ""

    @abstractmethod
    def verify(
        self,
        signals: list[str],
        scenario: "Scenario",
        *,
        timeout_s: float,
        interval_s: float,
    ) -> list[SignalResult]:
        ...
