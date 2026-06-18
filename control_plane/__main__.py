"""Entry point so ``python -m control_plane`` runs the SE control-plane CLI."""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
