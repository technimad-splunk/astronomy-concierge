"""HTTP client for concierge admin scenario endpoints."""

from __future__ import annotations

import os

import httpx


def _base_url() -> str:
    return os.getenv("CONCIERGE_API_URL", "http://localhost:8090").rstrip("/")


def _token() -> str:
    return os.getenv("CONCIERGE_ADMIN_TOKEN", "").strip()


def _trigger_error(message: str):
    from .triggers.base import TriggerError

    return TriggerError(message)


def _post(path: str, payload: dict) -> dict:
    url = f"{_base_url()}{path}"
    headers = {"Content-Type": "application/json"}
    token = _token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=10.0)
    except httpx.ConnectError as exc:
        raise _trigger_error(
            f"concierge not reachable at {_base_url()} — is concierge-web up? "
            "run scripts/stage-up.sh"
        ) from exc
    except httpx.RequestError as exc:
        raise _trigger_error(f"failed to call concierge admin API at {url}: {exc}") from exc
    if response.status_code >= 400:
        raise _trigger_error(
            f"concierge admin API call failed ({response.status_code}) at {url}: "
            f"{response.text.strip() or 'no response body'}; concierge not reachable "
            f"at {_base_url()} — is concierge-web up? run scripts/stage-up.sh"
        )
    data = response.json()
    if not isinstance(data, dict):
        raise _trigger_error(f"unexpected concierge admin response from {url}")
    return data


def post_apply(payload: dict) -> dict:
    return _post("/admin/scenario/apply", payload)


def post_reset(payload: dict) -> dict:
    return _post("/admin/scenario/reset", payload)
