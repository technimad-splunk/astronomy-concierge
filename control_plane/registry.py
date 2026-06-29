"""Scenario registry — auto-discovers drop-in vignette folders.

The headline extensibility guarantee (demo-design §7.2): dropping a new folder
under ``scenarios/`` with a ``scenario.yaml`` makes it appear here — and thus in
the control plane — with **no core edits**. Discovery is resilient: a single
malformed manifest is surfaced as a load error rather than breaking the listing
of every other scenario.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .manifest import ManifestError, Scenario, load_manifest
from .paths import scenarios_dir


@dataclass(frozen=True)
class DiscoveryError:
    """A folder under ``scenarios/`` whose manifest failed to load."""

    folder: Path
    error: str


@dataclass(frozen=True)
class Registry:
    scenarios: list[Scenario]
    errors: list[DiscoveryError]

    def get(self, scenario_id: str) -> Scenario:
        for s in self.scenarios:
            if s.id == scenario_id:
                return s
        known = ", ".join(s.id for s in self.scenarios) or "(none discovered)"
        raise KeyError(f"Unknown scenario '{scenario_id}'. Known scenarios: {known}.")

    def ids(self) -> list[str]:
        return [s.id for s in self.scenarios]


def discover(root: Path | None = None) -> Registry:
    """Scan ``scenarios/*/scenario.yaml`` and load every manifest it finds."""
    base = Path(root) if root else scenarios_dir()
    scenarios: list[Scenario] = []
    errors: list[DiscoveryError] = []
    if not base.is_dir():
        return Registry(scenarios=[], errors=[])

    for manifest_path in sorted(base.glob("*/scenario.yaml")):
        try:
            scenarios.append(load_manifest(manifest_path))
        except ManifestError as exc:
            errors.append(DiscoveryError(folder=manifest_path.parent, error=str(exc)))

    scenarios.sort(key=lambda s: (s.order is None, s.order if s.order is not None else 0, s.title))
    return Registry(scenarios=scenarios, errors=errors)
