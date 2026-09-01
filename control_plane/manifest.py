"""The declarative scenario contract: ``scenario.yaml`` loader + validator.

Matches demo-design §7.1 / the reference ``scenarios/invisible-failure/scenario.yaml``
EXACTLY. A manifest is intentionally declarative so the harness can auto-discover,
play, reset, and *auto-verify* every vignette with no core edits.

Fields (all required unless noted):

- ``id``               — unique scenario id (matches the folder name).
- ``title``            — human-readable name shown in the control plane.
- ``message``          — scenario metadata label shown in control-plane listings.
- ``duration_min``     — approximate runtime in minutes shown by ``list``.
- ``trigger``          — how the failure is INDUCED (single-trigger form):
    - ``type``         — one of the four FIXED mechanisms (demo-design §7.3).
    - ``ref``          — the flag / corpus / tool / overlay the trigger acts on.
    - ``params``       — optional handler-specific knobs (mapping).
- ``triggers``         — optional multi-trigger form (list of trigger objects).
                         Use when one scenario must compose overlays (e.g.
                         ``tool_fault`` + ``prompt_overlay``). Backward-compatible:
                         existing ``trigger`` manifests continue to work.
- ``expected_signals`` — ``galileo: [...]`` and ``splunk: [...]`` signal lists
                         the vignette promises will fire (for auto-verification).
- ``talk_track``       — path (relative to the scenario folder) to the caption file.
- ``reset``            — path (repo-root relative) to the per-scenario reset script.
- ``quiet_background`` — optional boolean (default ``false``). When true, the
                         control plane drains the demo's load-generator before
                         driving the agent and restores it on reset.

Validation is strict and gives a clear, path-prefixed error on any malformed
manifest, so a bad drop-in folder is reported — not silently mis-run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# The trigger set is FIXED on purpose (demo-design §7.3). Do not extend.
TRIGGER_TYPES = ("feature_flag", "rag_corpus", "tool_fault", "prompt_overlay")


class ManifestError(ValueError):
    """Raised when a ``scenario.yaml`` is missing or malformed."""


@dataclass(frozen=True)
class Trigger:
    type: str
    ref: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExpectedSignals:
    galileo: list[str] = field(default_factory=list)
    splunk: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.galileo and not self.splunk


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    message: str
    order: int | None
    duration_min: int
    trigger: Trigger
    expected_signals: ExpectedSignals
    talk_track: str
    reset: str
    quiet_background: bool = False
    also_triggers: list[Trigger] = field(default_factory=list)
    # Locations resolved at load time (not part of the YAML contract).
    dir: Path = field(default=Path("."))
    manifest_path: Path = field(default=Path("."))

    @property
    def talk_track_path(self) -> Path:
        """Absolute path to the caption file (talk_track is folder-relative)."""
        return self.dir / self.talk_track

    @property
    def triggers(self) -> list[Trigger]:
        """All declared triggers in apply order (primary + optional siblings)."""
        return [self.trigger, *self.also_triggers]

    def reset_path(self, repo_root: Path) -> Path:
        """Absolute path to the reset script (reset is repo-root relative)."""
        p = Path(self.reset)
        return p if p.is_absolute() else repo_root / p


def _require(data: dict, key: str, where: str, *, types: tuple[type, ...]) -> Any:
    if key not in data:
        raise ManifestError(f"{where}: missing required field '{key}'.")
    val = data[key]
    names = " or ".join(t.__name__ for t in types)
    # bool is a subclass of int — reject it where a real int/str is expected
    # (e.g. duration_min: true) unless bool was explicitly requested.
    if isinstance(val, bool) and bool not in types:
        raise ManifestError(f"{where}: field '{key}' must be {names}, got bool.")
    if not isinstance(val, types):
        raise ManifestError(f"{where}: field '{key}' must be {names}, got {type(val).__name__}.")
    return val


def _str_list(val: Any, key: str, where: str) -> list[str]:
    if val is None:
        return []
    if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
        raise ManifestError(f"{where}: '{key}' must be a list of strings.")
    return list(val)


def _parse_trigger(raw: Any, where: str) -> Trigger:
    if not isinstance(raw, dict):
        raise ManifestError(f"{where}: trigger entry must be a mapping.")
    trig_type = _require(raw, "type", where, types=(str,))
    if trig_type not in TRIGGER_TYPES:
        raise ManifestError(
            f"{where}: unknown type '{trig_type}'. "
            f"The trigger set is fixed: {', '.join(TRIGGER_TYPES)}."
        )
    trig_ref = _require(raw, "ref", where, types=(str,))
    params = raw.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ManifestError(f"{where}: 'params' must be a mapping if present.")
    return Trigger(type=trig_type, ref=trig_ref, params=dict(params))


def parse_manifest(data: Any, *, scenario_dir: Path, manifest_path: Path) -> Scenario:
    """Validate a parsed mapping and build a :class:`Scenario` (no I/O)."""
    where = str(manifest_path)
    if not isinstance(data, dict):
        raise ManifestError(f"{where}: top-level YAML must be a mapping.")

    scenario_id = _require(data, "id", where, types=(str,)).strip()
    if not scenario_id:
        raise ManifestError(f"{where}: 'id' must be non-empty.")
    title = _require(data, "title", where, types=(str,))
    message = _require(data, "message", where, types=(str,))
    order = data.get("order")
    if order is not None:
        if isinstance(order, bool) or not isinstance(order, int):
            raise ManifestError(f"{where}: 'order' must be an integer if present.")
        if order <= 0:
            raise ManifestError(f"{where}: 'order' must be a positive integer if present.")
    duration_min = _require(data, "duration_min", where, types=(int,))
    if duration_min <= 0:
        raise ManifestError(f"{where}: 'duration_min' must be a positive integer.")

    if "trigger" in data and "triggers" in data:
        raise ManifestError(
            f"{where}: declare either 'trigger' or 'triggers', not both."
        )

    trigger_list: list[Trigger]
    if "triggers" in data:
        triggers_raw = data.get("triggers")
        if not isinstance(triggers_raw, list) or not triggers_raw:
            raise ManifestError(f"{where}: 'triggers' must be a non-empty list.")
        trigger_list = [
            _parse_trigger(raw, f"{where} -> triggers[{idx}]")
            for idx, raw in enumerate(triggers_raw)
        ]
    else:
        trig_raw = _require(data, "trigger", where, types=(dict,))
        trigger_list = [_parse_trigger(trig_raw, f"{where} -> trigger")]

    sig_raw = _require(data, "expected_signals", where, types=(dict,))
    expected = ExpectedSignals(
        galileo=_str_list(sig_raw.get("galileo"), "galileo", f"{where} -> expected_signals"),
        splunk=_str_list(sig_raw.get("splunk"), "splunk", f"{where} -> expected_signals"),
    )

    talk_track = _require(data, "talk_track", where, types=(str,))
    reset = _require(data, "reset", where, types=(str,))

    quiet_bg = data.get("quiet_background", False)
    if not isinstance(quiet_bg, bool):
        raise ManifestError(f"{where}: 'quiet_background' must be a boolean if present.")

    return Scenario(
        id=scenario_id,
        title=title,
        message=message,
        order=order,
        duration_min=int(duration_min),
        trigger=trigger_list[0],
        also_triggers=trigger_list[1:],
        expected_signals=expected,
        talk_track=talk_track,
        reset=reset,
        quiet_background=quiet_bg,
        dir=scenario_dir,
        manifest_path=manifest_path,
    )


def load_manifest(manifest_path: Path) -> Scenario:
    """Read, parse, and validate a ``scenario.yaml`` into a :class:`Scenario`."""
    manifest_path = Path(manifest_path)
    if not manifest_path.is_file():
        raise ManifestError(f"{manifest_path}: file not found.")
    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ManifestError(f"{manifest_path}: invalid YAML — {exc}") from exc
    return parse_manifest(raw, scenario_dir=manifest_path.parent, manifest_path=manifest_path)
