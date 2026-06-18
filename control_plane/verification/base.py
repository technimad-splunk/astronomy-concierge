"""Verification contract — pluggable per-backend signal verifiers.

``expected_signals`` is declarative so the harness can **auto-verify** each
vignette (demo-design §7.4): confirm the promised Galileo/Splunk signals actually
fired, instead of discovering a dead demo live. The design constraint is that
verifiers are **pluggable per backend** — each backend implements the same
:class:`SignalVerifier` interface, so adding/swapping a backend never touches the
control plane.

A signal resolves to one of four statuses:

- ``pass``         — the signal fired and was confirmed.
- ``fail``         — the signal was checkable but did NOT fire.
- ``unverifiable`` — cannot be checked yet (metric not queryable, ingest-only
                     token, no data) — reported honestly, never faked as a pass.
- ``error``        — the verifier itself errored (e.g. auth/network).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from ..manifest import Scenario

Status = Literal["pass", "fail", "unverifiable", "error"]


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
    def failed(self) -> list[SignalResult]:
        return [r for r in self.results if r.status in ("fail", "error")]

    @property
    def unverifiable(self) -> list[SignalResult]:
        return [r for r in self.results if r.status == "unverifiable"]

    @property
    def overall_pass(self) -> bool:
        """Phase-3 semantics: a run passes when nothing FAILED or ERRORED.

        ``unverifiable`` signals (e.g. Splunk via an ingest-only token, or a
        Galileo metric not yet configured) are reported transparently and do not
        by themselves fail the run — they flag work that completes in Phase 4.
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
