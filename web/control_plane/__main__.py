from __future__ import annotations

import argparse
import ipaddress
import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8099


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _require_loopback_bind(host: str) -> None:
    if _is_loopback(host):
        return
    raise SystemExit(
        "FATAL: control-plane web UI refuses non-loopback binds. "
        f"Got host={host!r}; use 127.0.0.1."
    )


def main(argv: list[str] | None = None) -> int:
    load_dotenv(dotenv_path=REPO_ROOT / ".env")

    parser = argparse.ArgumentParser(
        prog="web.control_plane",
        description="SE control-plane web UI (localhost only).",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("CONTROL_PLANE_WEB_HOST", DEFAULT_HOST),
        help="bind host (must be loopback; default 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("CONTROL_PLANE_WEB_PORT", str(DEFAULT_PORT))),
        help="bind port (default CONTROL_PLANE_WEB_PORT or 8099)",
    )
    args = parser.parse_args(argv)

    _require_loopback_bind(args.host)
    uvicorn.run(
        "web.control_plane.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
