"""Galileo signal verifier — REAL queries against the Galileo SDK/API.

Reads ``GALILEO_*`` from the environment, resolves the project + log stream, and
polls recent traces (with retry/timeout to tolerate ingestion lag — L2). Each
named ``expected_signals.galileo`` entry maps to a concrete check over the
traces' AI metrics where one is queryable; where a metric isn't present yet
(scorer not enabled / no matching data), the signal is reported as
``unverifiable`` with a clear reason rather than faked as a pass.

Named-signal → metric mapping (demo-design §6/Appendix A):

| signal                      | Galileo metric key(s)                          | check        |
|-----------------------------|------------------------------------------------|--------------|
| ``context_adherence_low``   | context_adherence / _luna / _plus, groundedness| value < thr  |
| ``ungrounded_claim``        | completeness(_luna), chunk_attribution_*        | value < thr  |
| ``tool_selection_quality_low`` | tool_selection_quality                      | value < thr  |
| ``tool_error``              | tool_error_rate, action_advancement             | value > thr  |
| ``prompt_injection_detected`` | prompt_injection, input_pii, pii              | flag truthy  |

``thr`` is ``GALILEO_METRIC_LOW_THRESHOLD`` (default 0.5). Unknown signals are
reported ``unverifiable`` (not failed), so the hook is honest about coverage.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .base import SignalResult, SignalVerifier

if TYPE_CHECKING:
    from ..manifest import Scenario


@dataclass(frozen=True)
class _SignalSpec:
    metric_keys: tuple[str, ...]
    direction: str  # "low" (value < thr fires) | "high" (value > thr fires) | "flag"


# Map our named signals to Galileo metric keys + the direction that "fires".
_SIGNAL_MAP: dict[str, _SignalSpec] = {
    "context_adherence_low": _SignalSpec(
        ("context_adherence", "context_adherence_luna", "context_adherence_plus", "groundedness"),
        "low",
    ),
    "ungrounded_claim": _SignalSpec(
        ("completeness", "completeness_luna", "chunk_attribution_utilization",
         "chunk_attribution_utilization_luna"),
        "low",
    ),
    "tool_selection_quality_low": _SignalSpec(("tool_selection_quality",), "low"),
    "tool_error": _SignalSpec(("tool_error_rate", "action_advancement", "action_completion"), "high"),
    "prompt_injection_detected": _SignalSpec(("prompt_injection", "input_pii", "pii"), "flag"),
}

_TRUE = {"1", "true", "yes", "on"}


def _threshold() -> float:
    try:
        return float(os.getenv("GALILEO_METRIC_LOW_THRESHOLD", "0.5"))
    except ValueError:
        return 0.5


def _coerce_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in ("value", "score", "result"):
            if key in value:
                return _coerce_number(value[key])
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _metrics_to_dict(record: Any) -> dict[str, Any]:
    """Best-effort extraction of a trace record's metric map."""
    metrics = getattr(record, "metrics", None)
    if metrics is None:
        return {}
    for attr in ("to_dict", "additional_properties"):
        obj = getattr(metrics, attr, None)
        if callable(obj):
            try:
                d = obj()
                if isinstance(d, dict):
                    return d
            except Exception:  # pragma: no cover - defensive
                pass
        elif isinstance(obj, dict):
            return obj
    if isinstance(metrics, dict):
        return metrics
    return {}


class GalileoVerifier(SignalVerifier):
    backend = "galileo"

    def verify(
        self,
        signals: list[str],
        scenario: "Scenario",
        *,
        timeout_s: float,
        interval_s: float,
    ) -> list[SignalResult]:
        if not signals:
            return []
        if not os.getenv("GALILEO_API_KEY"):
            return [
                SignalResult("galileo", s, "unverifiable", "GALILEO_API_KEY not set in environment.")
                for s in signals
            ]
        try:
            records = self._poll_traces(timeout_s=timeout_s, interval_s=interval_s)
        except Exception as exc:  # network/auth/SDK error — report, do not fake
            return [
                SignalResult("galileo", s, "error", f"Galileo query failed: {exc}")
                for s in signals
            ]

        if records is None:
            return [
                SignalResult("galileo", s, "error", "could not resolve Galileo project/log stream.")
                for s in signals
            ]

        # Aggregate metric values seen across recent traces.
        seen: dict[str, list[float]] = {}
        for rec in records:
            for key, val in _metrics_to_dict(rec).items():
                num = _coerce_number(val)
                if num is not None:
                    seen.setdefault(key, []).append(num)

        thr = _threshold()
        n = len(records)
        results: list[SignalResult] = []
        for signal in signals:
            results.append(self._check_signal(signal, seen, thr, n))
        return results

    def _check_signal(
        self, signal: str, seen: dict[str, list[float]], thr: float, n_traces: int
    ) -> SignalResult:
        spec = _SIGNAL_MAP.get(signal)
        if spec is None:
            return SignalResult(
                "galileo", signal, "unverifiable",
                "no metric mapping for this signal yet (needs Phase-4 scorer config).",
            )
        present = [k for k in spec.metric_keys if seen.get(k)]
        if not present:
            return SignalResult(
                "galileo", signal, "unverifiable",
                f"none of {list(spec.metric_keys)} present on {n_traces} recent trace(s); "
                "enable the scorer on the log stream and run the vignette (Phase 4).",
            )
        key = present[0]
        values = seen[key]
        worst = min(values) if spec.direction == "low" else max(values)
        if spec.direction == "low":
            fired = worst < thr
            cmp = f"{worst:.3f} < {thr:.3f}"
        elif spec.direction == "high":
            fired = worst > thr
            cmp = f"{worst:.3f} > {thr:.3f}"
        else:  # flag
            fired = worst >= 1.0
            cmp = f"{key}={worst:.0f}"
        status = "pass" if fired else "fail"
        return SignalResult(
            "galileo", signal, status,
            f"metric '{key}' {cmp} over {len(values)} value(s) in {n_traces} trace(s).",
        )

    def _poll_traces(self, *, timeout_s: float, interval_s: float) -> list[Any] | None:
        from galileo import log_streams, projects, search

        project_name = os.getenv("GALILEO_PROJECT")
        log_stream_name = os.getenv("GALILEO_LOG_STREAM", "default")

        project = projects.get_project(name=project_name)
        if project is None:
            return None
        project_id = getattr(project, "id", None)
        if not project_id:
            return None

        log_stream = log_streams.get_log_stream(name=log_stream_name, project_id=project_id)
        log_stream_id = getattr(log_stream, "id", None) if log_stream else None

        deadline = time.monotonic() + max(timeout_s, 0.0)
        records: list[Any] = []
        while True:
            resp = search.get_traces(
                project_id=project_id,
                log_stream_id=log_stream_id,
                limit=50,
            )
            records = list(getattr(resp, "records", []) or [])
            if records or time.monotonic() >= deadline:
                break
            time.sleep(max(interval_s, 0.1))
        return records
