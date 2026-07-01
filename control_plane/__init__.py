"""The SE control plane + scenario harness (Phase 3).

This package is the **stable extensibility machinery** that makes vignettes
drop-in folders under ``scenarios/`` — never core edits (demo-design §7):

- :mod:`control_plane.manifest`   — the declarative ``scenario.yaml`` contract
  (loader + validator), matching demo-design §7.1 exactly.
- :mod:`control_plane.registry`   — auto-discovers ``scenarios/*/scenario.yaml``.
- :mod:`control_plane.triggers`   — the four FIXED trigger mechanisms
  (``feature_flag | rag_corpus | tool_fault | prompt_overlay``), each with
  ``apply()`` + ``reset()``.
- :mod:`control_plane.verification` — pluggable per-backend ``expected_signals``
  verifiers (Galileo real; Splunk unverified-by-design — ingest-only token).
- :mod:`control_plane.cli`        — the SE CLI: ``list / play / reset / verify``.
  Run via ``python -m control_plane`` or ``scripts/control-plane.sh``.

The trigger set is fixed on purpose: scope creep there erodes the "drop-in
folder" guarantee (demo-design §7.3).
"""

__all__ = ["manifest", "registry", "triggers", "verification", "paths"]
