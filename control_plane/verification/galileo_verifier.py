"""Galileo signal verifier — REAL queries against the Galileo SDK/API.

Reads ``GALILEO_*`` from the environment, resolves the project + log stream, and
polls recent traces (with retry/timeout to tolerate ingestion lag — L2). Each
named ``expected_signals.galileo`` entry maps to a concrete check over the
traces' AI metrics where one is queryable; where a metric isn't present yet
(scorer not enabled / no matching data), the signal is reported as
``unverifiable`` with a clear reason rather than faked as a pass.

Named-signal → scorer mapping (demo-design §6/Appendix A):

| signal                      | Galileo scorer(s)                              | check        |
|-----------------------------|------------------------------------------------|--------------|
| ``context_adherence_low``   | context_adherence / _luna / _plus, groundedness| value < thr  |

``context_adherence_low`` is the signal behind the Galileo alert operators see as
**"Context Adherence (SLM)"** — the SLM/Luna-based context-adherence scorer (V1's
hero signal; when it drops very low it fires a Slack alert). It is matched by both
the base ``context_adherence`` scorer and its Luna variant below.
| ``ungrounded_claim``        | completeness(_luna), chunk_attribution_*        | value < thr  |
| ``tool_selection_quality_low`` | tool_selection_quality                      | value < thr  |
| ``tool_error``              | tool_error_rate, action_advancement             | value > thr  |
| ``prompt_injection_detected`` | prompt_injection, prompt_injection_luna        | flag truthy  |
| ``pii_exposed``             | input_pii, pii, output_pii, pii_luna, input_pii_luna | flag truthy  |

Note: ``prompt_injection_detected`` scopes to the user-input turn (not retrieved
RAG content or system-prompt overlays). For payloads delivered via RAG/tool output,
use ``pii_exposed`` which targets the PII scorers that evaluate retrieved/conversation
content where the sensitive data actually lands.

**UUID → scorer-name resolution.** Galileo returns each trace's scorer metrics
keyed by the scorer's **UUID**, not its human name — e.g. ``context_adherence``'s
values arrive under ``894d889a-…@category_count`` / ``…_multijudge_average`` and
``completeness``'s under ``4f27c2bc-…@average`` / ``…@min``. So a name-only match
(the old behaviour) silently left every Galileo signal "unverified". This
verifier now fetches the project's scorer definitions via the SDK
(``galileo.scorers.Scorers().list()``) and builds a live name→UUID map, then
looks each signal's scorer up by BOTH its name and its resolved UUID, scanning
the value-bearing sub-keys (plain value, ``@average``/``@min``/``@max``,
``_multijudge_average``) that Galileo attaches per scorer.

Each signal has an explicit **direction**, **aggregation**, and **threshold**:

- ``low`` signals (quality metrics): fire when ``MIN(values) < threshold``.
  Threshold: ``GALILEO_METRIC_LOW_THRESHOLD`` (default 0.5).
- ``high`` signals (error metrics): fire when ``MAX(values) > threshold``.
  Threshold: ``GALILEO_METRIC_HIGH_THRESHOLD`` (default 0.0 — any error fires).
- ``detect`` signals (boolean/detection): fire when ``MAX(values) >= 1``
  (any trace has a positive detection).

Unknown signals are reported ``unverifiable`` (not failed), so the hook stays
honest about coverage.
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
    scorer_names: tuple[str, ...]
    direction: str  # "low" | "high" | "detect"
    aggregation: str  # "min" | "max"
    threshold_key: str  # env-var name for the threshold


# Map our named signals to Galileo scorer names + direction/aggregation/threshold.
# Names are resolved to per-project scorer UUIDs at verify time (see module doc).
#
# direction + aggregation semantics:
#   low/min  — quality signal: fire when MIN(values) < threshold (one bad trace)
#   high/max — error signal: fire when MAX(values) > threshold (any elevated error)
#   detect/max — boolean/detection: fire when MAX(values) >= 1 (any positive hit)
_SIGNAL_MAP: dict[str, _SignalSpec] = {
    # Galileo alert name operators recognize: "Context Adherence (SLM)" — the
    # SLM/Luna context-adherence scorer. Kept broad (base + _luna + _plus +
    # groundedness) so it verifies whichever variant is enabled on the log stream.
    "context_adherence_low": _SignalSpec(
        ("context_adherence", "context_adherence_luna", "context_adherence_plus", "groundedness"),
        "low", "min", "GALILEO_METRIC_LOW_THRESHOLD",
    ),
    "ungrounded_claim": _SignalSpec(
        ("completeness", "completeness_luna", "chunk_attribution_utilization",
         "chunk_attribution_utilization_luna"),
        "low", "min", "GALILEO_METRIC_LOW_THRESHOLD",
    ),
    "tool_selection_quality_low": _SignalSpec(
        ("tool_selection_quality", "tool_selection_quality_luna"),
        "low", "min", "GALILEO_METRIC_LOW_THRESHOLD",
    ),
    "tool_error": _SignalSpec(
        ("tool_error_rate", "tool_error_rate_luna", "action_advancement"),
        "high", "max", "GALILEO_METRIC_HIGH_THRESHOLD",
    ),
    "prompt_injection_detected": _SignalSpec(
        ("prompt_injection", "prompt_injection_luna"),
        "detect", "max", "",
    ),
    "pii_exposed": _SignalSpec(
        # Real Galileo PII scorer names (confirmed via Scorers().list()): the Luna
        # variants (input_pii/output_pii) and the GPT variants (input_pii_gpt/
        # output_pii_gpt). We match whichever is enabled on the log stream. input_*
        # comes first because the poisoned PII arrives as retrieved/tool content in
        # the conversation INPUT, which the input PII scorers evaluate.
        ("input_pii", "input_pii_gpt", "output_pii", "output_pii_gpt"),
        "detect", "max", "",
    ),
}

# Galileo encodes a single scorer's value across several sibling keys, all under
# the scorer's base key (name or UUID). We union the numeric ones: the plain
# rolled-up value, the aggregate stats, and the boolean-metric multijudge mean
# (e.g. context_adherence has no plain value, only ``_multijudge_average`` +
# ``@category_count``).
_VALUE_SUFFIXES = ("", "@average", "@min", "@max", "_multijudge_average")

_TRUE = {"1", "true", "yes", "on"}

# Default thresholds:
#   LOW  = 0.5 — quality signals fire when a value drops below this
#   HIGH = 0.0 — error signals fire when a value exceeds this (any error fires)
_DEFAULT_LOW_THRESHOLD = 0.5
_DEFAULT_HIGH_THRESHOLD = 0.0


def _get_threshold(env_key: str, default: float) -> float:
    raw = os.getenv(env_key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _coerce_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, list):
        # Entity/PII scorers (input_pii/output_pii/_gpt) emit a LIST of detected
        # entity types (e.g. ['ssn','email']), empty when nothing is found. Treat
        # the magnitude as the count so a non-empty list reads as a detection.
        return float(len(value))
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

        # Aggregate metric values seen across recent traces. Keys are a mix of
        # scorer UUIDs (the scored metrics) and scorer names (session-level /
        # errored metrics), each with the value sub-keys we union below.
        seen: dict[str, list[float]] = {}
        for rec in records:
            for key, val in _metrics_to_dict(rec).items():
                num = _coerce_number(val)
                if num is not None:
                    seen.setdefault(key, []).append(num)

        # Build a live scorer name → UUID map so UUID-keyed metrics resolve to
        # the human names our signal map uses. Best-effort: if it fails we fall
        # back to name-only matching (still correct for name-keyed metrics).
        name_to_id = self._scorer_name_to_id()

        n = len(records)
        results: list[SignalResult] = []
        for signal in signals:
            results.append(self._check_signal(signal, seen, name_to_id, n))
        return results

    @staticmethod
    def _scorer_name_to_id() -> dict[str, str]:
        """Fetch the project/account scorer definitions and map name → UUID."""
        try:
            from galileo.scorers import Scorers

            mapping: dict[str, str] = {}
            for scorer in Scorers().list():
                name = getattr(scorer, "name", None)
                sid = getattr(scorer, "id", None)
                if name and sid:
                    mapping[str(name).lower()] = str(sid)
            return mapping
        except Exception:  # network/SDK/auth — degrade to name-only matching
            return {}

    def _collect_values(
        self, base_key: str, seen: dict[str, list[float]]
    ) -> list[float]:
        """Union the numeric values Galileo attaches to one scorer base key."""
        values: list[float] = []
        for suffix in _VALUE_SUFFIXES:
            values.extend(seen.get(base_key + suffix, ()))
        return values

    def _check_signal(
        self,
        signal: str,
        seen: dict[str, list[float]],
        name_to_id: dict[str, str],
        n_traces: int,
    ) -> SignalResult:
        spec = _SIGNAL_MAP.get(signal)
        if spec is None:
            return SignalResult(
                "galileo", signal, "unverifiable",
                "no scorer mapping for this signal yet (needs Phase-4 scorer config).",
            )

        # Resolve the threshold for this signal's direction.
        if spec.direction == "low":
            thr = _get_threshold(spec.threshold_key, _DEFAULT_LOW_THRESHOLD)
        elif spec.direction == "high":
            thr = _get_threshold(spec.threshold_key, _DEFAULT_HIGH_THRESHOLD)
        else:
            thr = 1.0  # detect: any positive hit (>= 1)

        # Detection signals (e.g. PII) may be served by SEVERAL scorers at once
        # (input_pii AND output_pii) and a given scorer can be present-but-empty
        # on a trace (e.g. input_pii == [] while output_pii caught the leak).
        # Union values across ALL mapped scorers and fire if ANY of them detected
        # something — never early-return on the first present-but-empty scorer.
        if spec.direction == "detect":
            all_values: list[float] = []
            hit: list[str] = []
            for scorer_name in spec.scorer_names:
                uuid = name_to_id.get(scorer_name.lower())
                bases = [scorer_name] + ([uuid] if uuid else [])
                vals: list[float] = []
                for base in bases:
                    vals.extend(self._collect_values(base, seen))
                if vals:
                    all_values.extend(vals)
                    if max(vals) >= 1.0:
                        hit.append(scorer_name)
            if not all_values:
                return SignalResult(
                    "galileo", signal, "unverifiable",
                    f"none of scorers {list(spec.scorer_names)} present on {n_traces} "
                    "recent trace(s) (by name or resolved UUID); enable the scorer on "
                    "the log stream and run the vignette.",
                )
            agg_val = max(all_values)
            fired = agg_val >= 1.0
            where = f"detected by {hit}" if fired else "no detections"
            return SignalResult(
                "galileo", signal, "pass" if fired else "fail",
                f"{where}: peak {agg_val:.0f} >= 1 across {list(spec.scorer_names)} "
                f"over {len(all_values)} value(s) in {n_traces} trace(s).",
            )

        for scorer_name in spec.scorer_names:
            base_keys = [scorer_name]
            uuid = name_to_id.get(scorer_name.lower())
            if uuid:
                base_keys.append(uuid)
            values: list[float] = []
            for base in base_keys:
                values.extend(self._collect_values(base, seen))
            if not values:
                continue

            uuid_note = f" [{uuid[:8]}]" if uuid else ""
            if spec.direction == "low":
                agg_val = min(values)
                fired = agg_val < thr
                agg_label = "min"
                cmp = f"{agg_val:.3f} < {thr:.3f}"
            elif spec.direction == "high":
                agg_val = max(values)
                fired = agg_val > thr
                agg_label = "peak"
                cmp = f"{agg_val:.3f} > {thr:.3f}"
            else:  # detect
                agg_val = max(values)
                fired = agg_val >= 1.0
                agg_label = "max"
                cmp = f"{agg_val:.0f} >= 1"
            status = "pass" if fired else "fail"
            return SignalResult(
                "galileo", signal, status,
                f"scorer '{scorer_name}'{uuid_note} {agg_label} {cmp} over "
                f"{len(values)} value(s) in {n_traces} trace(s).",
            )

        return SignalResult(
            "galileo", signal, "unverifiable",
            f"none of scorers {list(spec.scorer_names)} present on {n_traces} "
            "recent trace(s) (by name or resolved UUID); enable the scorer on the "
            "log stream and run the vignette.",
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
