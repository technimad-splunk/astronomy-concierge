"""``feature_flag`` trigger — flip a flagd feature flag in the running stage.

Primary layer: **Splunk** (breaks a backend service → feeds bad data to the
agent). The vendored OpenTelemetry demo runs **flagd**, which watches its config
file (``stage/opentelemetry-demo/src/flagd/demo.flagd.json``) and **hot-reloads**
on change — no container restart needed. So we induce/clear a fault by editing
that file's ``defaultVariant`` for the named flag.

``apply``  → set the flag's ``defaultVariant`` to its "on" variant.
``reset``  → restore the original variant (saved on apply; falls back to "off").

Non-destructive: the original variant is recorded under ``.harness/state/`` so
reset is deterministic even from a fresh process. The token/realm are never
touched — this only edits a local JSON file the demo already mounts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..manifest import Scenario
from ..paths import flagd_config_path, state_dir
from .base import Trigger, TriggerError, TriggerResult

# Variant names commonly meaning "off" in the demo's flag set.
_OFF_NAMES = ("off", "false", "0%", "disabled")


class FeatureFlagTrigger(Trigger):
    type = "feature_flag"

    def _config_path(self) -> Path:
        path = flagd_config_path()
        if not path.is_file():
            raise TriggerError(
                f"flagd config not found at {path}. Is the stage vendored/up? "
                "Run scripts/stage-setup.sh (or scripts/stage-up.sh)."
            )
        return path

    def _load(self, path: Path) -> dict[str, Any]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TriggerError(f"could not read flagd config {path}: {exc}") from exc

    def _flag(self, config: dict[str, Any], ref: str, path: Path) -> dict[str, Any]:
        flags = config.get("flags", {})
        if ref not in flags:
            available = ", ".join(sorted(flags)) or "(none)"
            raise TriggerError(
                f"feature flag '{ref}' is not defined in {path}. "
                f"Available flags: {available}."
            )
        return flags[ref]

    def _on_variant(self, flag: dict[str, Any], override: str | None) -> str:
        variants = flag.get("variants", {})
        if override:
            if override not in variants:
                raise TriggerError(
                    f"requested variant '{override}' is not one of: {', '.join(variants)}."
                )
            return override
        if "on" in variants:
            return "on"
        # Otherwise pick the first variant that is not an "off"-like value.
        for name, value in variants.items():
            if name.lower() in _OFF_NAMES:
                continue
            if value in (False, 0, "0", "", None):
                continue
            return name
        raise TriggerError(
            f"could not infer an 'on' variant from {list(variants)}; "
            "set trigger.params.variant explicitly."
        )

    def _off_variant(self, flag: dict[str, Any]) -> str:
        variants = flag.get("variants", {})
        for name in variants:
            if name.lower() in _OFF_NAMES:
                return name
        for name, value in variants.items():
            if value in (False, 0, "0", "", None):
                return name
        return next(iter(variants), "off")

    def _state_file(self, scenario: Scenario) -> Path:
        return state_dir() / f"feature_flag__{scenario.id}__{scenario.trigger.ref}.json"

    def _write(self, path: Path, config: dict[str, Any]) -> None:
        # flagd watches the file; a normal write triggers a hot reload.
        path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    def apply(self, scenario: Scenario) -> TriggerResult:
        ref = scenario.trigger.ref
        path = self._config_path()
        config = self._load(path)
        flag = self._flag(config, ref, path)
        before = flag.get("defaultVariant", "")
        on_variant = self._on_variant(flag, scenario.trigger.params.get("variant"))

        self._state_file(scenario).write_text(
            json.dumps({"ref": ref, "original_default_variant": before}), encoding="utf-8"
        )
        flag["defaultVariant"] = on_variant
        self._write(path, config)
        return TriggerResult(
            action="apply",
            type=self.type,
            ref=ref,
            summary=f"flagd flag '{ref}' set to '{on_variant}' (was '{before}'); flagd hot-reloads.",
            before=before,
            after=on_variant,
            details=[f"config: {path}"],
        )

    def reset(self, scenario: Scenario) -> TriggerResult:
        ref = scenario.trigger.ref
        path = self._config_path()
        config = self._load(path)
        flag = self._flag(config, ref, path)
        before = flag.get("defaultVariant", "")

        state_file = self._state_file(scenario)
        restore = None
        if state_file.is_file():
            try:
                restore = json.loads(state_file.read_text(encoding="utf-8")).get(
                    "original_default_variant"
                )
            except (OSError, json.JSONDecodeError):
                restore = None
        if not restore:
            restore = self._off_variant(flag)

        flag["defaultVariant"] = restore
        self._write(path, config)
        state_file.unlink(missing_ok=True)
        return TriggerResult(
            action="reset",
            type=self.type,
            ref=ref,
            summary=f"flagd flag '{ref}' restored to '{restore}' (was '{before}').",
            before=before,
            after=restore,
            details=[f"config: {path}"],
        )
