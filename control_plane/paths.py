"""Repo-relative path helpers shared across the harness.

Everything is anchored to the repository root (the parent of this package), so
the control plane works from any CWD and stays reproducible from a fresh clone.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def scenarios_dir() -> Path:
    """Directory holding the drop-in vignette folders."""
    env = os.getenv("SCENARIOS_DIR")
    return Path(env) if env else REPO_ROOT / "scenarios"


def state_dir() -> Path:
    """Gitignored runtime state (e.g. saved feature-flag variants for reset)."""
    env = os.getenv("HARNESS_STATE_DIR")
    d = Path(env) if env else REPO_ROOT / ".harness" / "state"
    d.mkdir(parents=True, exist_ok=True)
    return d


def flagd_config_path() -> Path:
    """Path to the vendored demo's flagd feature-flag config (hot-reloaded)."""
    env = os.getenv("FLAGD_CONFIG_PATH")
    if env:
        return Path(env)
    return REPO_ROOT / "stage" / "opentelemetry-demo" / "src" / "flagd" / "demo.flagd.json"
