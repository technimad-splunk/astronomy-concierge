"""Enable ``python -m agent`` to launch the concierge."""

from .main import main

if __name__ == "__main__":
    raise SystemExit(main())
