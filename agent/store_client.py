"""HTTP client for the Astronomy Shop's frontend-proxy API.

The concierge runs on the host, so it talks to the store the same way a browser
does: through the **frontend-proxy** at ``http://localhost:8080/api/...`` (the
demo's public HTTP surface). Endpoints and request shapes were discovered from
the running demo and the upstream ``src/frontend/pages/api/*`` handlers:

- ``GET  /api/products?currencyCode=USD``                       -> list products
- ``GET  /api/products/{id}?currencyCode=USD``                  -> one product
- ``GET  /api/recommendations?productIds=&sessionId=&currencyCode=`` -> recs
- ``GET  /api/currency``                                        -> currency codes
- ``GET  /api/cart?sessionId=&currencyCode=``                   -> read cart
- ``POST /api/cart``  body ``{userId, item:{productId, quantity}}`` -> add item
- ``DELETE /api/cart`` body ``{userId}``                        -> empty cart

No credentials are involved; the base URL is read from the environment so the
agent can point at a remote stage if needed. All inputs are validated before use
(IDs/quantities) and requests are bounded by an explicit timeout.
"""

from __future__ import annotations

import os
import re
from typing import Any

import httpx

DEFAULT_BASE_URL = "http://localhost:8080"
DEFAULT_CURRENCY = "USD"
_REQUEST_TIMEOUT_S = 15.0

# Product IDs in the demo are short uppercase alphanumeric tokens (e.g.
# "0PUK6V6EV0"). Validate against an allow-list pattern to avoid passing
# arbitrary strings into URLs.
_PRODUCT_ID_RE = re.compile(r"^[A-Z0-9]{6,16}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


class StoreError(RuntimeError):
    """Raised when a store API call fails or returns an unexpected payload."""


def _base_url() -> str:
    return os.getenv("STORE_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _validate_product_id(product_id: str) -> str:
    pid = (product_id or "").strip().upper()
    if not _PRODUCT_ID_RE.match(pid):
        raise StoreError(
            f"Invalid product id {product_id!r}; expected a catalog id like "
            "'0PUK6V6EV0'. Use search_products to find one."
        )
    return pid


def _validate_currency(currency: str | None) -> str:
    cur = (currency or DEFAULT_CURRENCY).strip().upper()
    if not _CURRENCY_RE.match(cur):
        raise StoreError(f"Invalid currency code {currency!r}; expected 3 letters like 'USD'.")
    return cur


class StoreClient:
    """Thin, validated wrapper over the frontend-proxy API.

    A ``session_id`` ties cart reads/writes to a single shopper conversation.
    """

    def __init__(self, session_id: str, base_url: str | None = None) -> None:
        self.session_id = session_id
        self.base_url = (base_url or _base_url()).rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=_REQUEST_TIMEOUT_S)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "StoreClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            resp = self._client.get(path, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            raise StoreError(f"GET {path} failed: {exc}") from exc

    def _post(self, path: str, json_body: dict[str, Any], params: dict[str, Any] | None = None) -> Any:
        try:
            resp = self._client.post(path, json=json_body, params=params)
            resp.raise_for_status()
            if resp.status_code == 204 or not resp.content:
                return {}
            return resp.json()
        except httpx.HTTPError as exc:
            raise StoreError(f"POST {path} failed: {exc}") from exc

    # --- catalog -----------------------------------------------------------
    def list_products(self, currency: str | None = None) -> list[dict[str, Any]]:
        cur = _validate_currency(currency)
        data = self._get("/api/products", {"currencyCode": cur})
        return data if isinstance(data, list) else []

    def get_product(self, product_id: str, currency: str | None = None) -> dict[str, Any]:
        pid = _validate_product_id(product_id)
        cur = _validate_currency(currency)
        return self._get(f"/api/products/{pid}", {"currencyCode": cur})

    def list_recommendations(
        self, product_id: str | None = None, currency: str | None = None
    ) -> list[dict[str, Any]]:
        cur = _validate_currency(currency)
        params: dict[str, Any] = {"sessionId": self.session_id, "currencyCode": cur}
        if product_id:
            params["productIds"] = _validate_product_id(product_id)
        data = self._get("/api/recommendations", params)
        return data if isinstance(data, list) else []

    def list_currencies(self) -> list[str]:
        data = self._get("/api/currency")
        return data if isinstance(data, list) else []

    # --- cart --------------------------------------------------------------
    def get_cart(self, currency: str | None = None) -> dict[str, Any]:
        cur = _validate_currency(currency)
        return self._get("/api/cart", {"sessionId": self.session_id, "currencyCode": cur})

    def add_to_cart(self, product_id: str, quantity: int = 1) -> dict[str, Any]:
        pid = _validate_product_id(product_id)
        try:
            qty = int(quantity)
        except (TypeError, ValueError) as exc:
            raise StoreError(f"Invalid quantity {quantity!r}; expected an integer.") from exc
        if qty < 1 or qty > 100:
            raise StoreError("Quantity must be between 1 and 100.")
        return self._post(
            "/api/cart",
            {"userId": self.session_id, "item": {"productId": pid, "quantity": qty}},
        )

    def place_order(
        self,
        email: str = "concierge-shopper@example.com",
        currency: str | None = None,
    ) -> dict[str, Any]:
        """Place an order (checkout) for everything currently in the cart.

        Calls ``POST /api/checkout`` with the session's userId, a synthetic
        shipping address and credit card (the demo validates format, not real
        payment). This exercises the full checkout→payment service path so
        flagd faults on the payment service propagate into the agent's flow.

        Verifies the cart is non-empty before calling checkout — an empty cart
        would bypass the payment service entirely (charging $0 shipping) and
        the ``paymentFailure`` flag would never fire.
        """
        cur = _validate_currency(currency)
        cart = self.get_cart(currency=cur)
        items = cart.get("items", [])
        if not items:
            raise StoreError(
                "Cart is empty — nothing to check out. Add items with "
                "add_to_cart before calling checkout."
            )
        body = {
            "userId": self.session_id,
            "email": email,
            "userCurrency": cur,
            "address": {
                "streetAddress": "1600 Amphitheatre Parkway",
                "city": "Mountain View",
                "state": "CA",
                "country": "US",
                "zipCode": "94043",
            },
            "creditCard": {
                "creditCardNumber": "4432801561520454",
                "creditCardCvv": 672,
                "creditCardExpirationYear": 2030,
                "creditCardExpirationMonth": 1,
            },
        }
        return self._post("/api/checkout", body, params={"currencyCode": cur})
