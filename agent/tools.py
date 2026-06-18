"""LangChain tools for the concierge — the agent's two capabilities as tools.

- **Capability (a) — answer:** ``search_knowledge_base`` does RAG over the curated
  corpus (``agent/rag.py``).
- **Capability (b) — act:** the remaining tools call the Astronomy Shop's real
  microservice APIs through the frontend-proxy (``agent/store_client.py``), so the
  agent's tool calls become genuine traffic into the store's services.

Tools are built per conversation via :func:`make_tools` so cart operations are
scoped to one shopper session. OpenInference instruments these as tool spans, so
each action is legible in both Galileo and Splunk.
"""

from __future__ import annotations

from typing import Any, Optional

from langchain_core.tools import BaseTool, StructuredTool, tool

from . import rag
from .overlay import faulted_tools
from .store_client import StoreClient, StoreError


def _format_money(money: dict[str, Any] | None) -> str:
    if not money:
        return "price unavailable"
    units = money.get("units", 0) or 0
    nanos = money.get("nanos", 0) or 0
    code = money.get("currencyCode", "USD")
    amount = int(units) + int(nanos) / 1_000_000_000
    return f"{amount:.2f} {code}"


def _format_product(p: dict[str, Any], *, full: bool = False) -> str:
    if not isinstance(p, dict) or not p.get("id"):
        return ""
    price = _format_money(p.get("priceUsd"))
    cats = ", ".join(p.get("categories", []) or [])
    line = f"- {p.get('name', 'Unknown')} (id: {p['id']}) — {price}"
    if cats:
        line += f" [categories: {cats}]"
    if full:
        desc = (p.get("description") or "").strip()
        if desc:
            line += f"\n  {desc}"
    return line


def _format_products(products: list[dict[str, Any]], *, full: bool = False) -> str:
    lines = [_format_product(p, full=full) for p in products]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines) if lines else "No products found."


def make_tools(store: StoreClient) -> list[BaseTool]:
    """Build the concierge's tool set bound to one shopper ``store`` session."""

    @tool
    def search_knowledge_base(query: str) -> str:
        """Search the Astronomy Shop knowledge base (shipping, returns, warranty,
        payment, and buying-guide policy docs) for grounded answers. Use this for
        any question about policies, shipping, returns, warranty, or general
        buying advice. Returns relevant excerpts with their source document."""
        results = rag.search(query, k=3)
        return rag.format_results(results)

    @tool
    def search_products(query: str) -> str:
        """Search the live product catalog by keyword (matches product name,
        description, and category). Use this to find telescopes and accessories
        and to get their catalog ids and current prices."""
        try:
            products = store.list_products()
        except StoreError as exc:
            return f"Error: {exc}"
        q = query.lower().strip()
        if q:
            matched = [
                p for p in products
                if q in p.get("name", "").lower()
                or q in p.get("description", "").lower()
                or any(q in c.lower() for c in p.get("categories", []) or [])
            ]
        else:
            matched = products
        if not matched:
            matched = products[:5]
            header = f"No exact matches for {query!r}. Showing some catalog items:\n"
        else:
            header = ""
        return header + _format_products(matched[:8], full=True)

    @tool
    def get_product_details(product_id: str) -> str:
        """Get full details (name, description, price, categories) for one product
        by its catalog id (e.g. '0PUK6V6EV0'). Find ids with search_products."""
        try:
            product = store.get_product(product_id)
        except StoreError as exc:
            return f"Error: {exc}"
        return _format_product(product, full=True) or "Product not found."

    @tool
    def get_recommendations(product_id: Optional[str] = None) -> str:
        """Get product recommendations from the store's recommendation service.
        Optionally pass a product_id to anchor recommendations to that item;
        otherwise call with no arguments for general recommendations."""
        anchor = product_id if (product_id and product_id.strip()) else None
        try:
            recs = store.list_recommendations(anchor)
        except StoreError as exc:
            return f"Error: {exc}"
        return _format_products(recs, full=True)

    @tool
    def add_to_cart(product_id: str, quantity: int = 1) -> str:
        """Add a product to the shopper's cart by catalog id and quantity. Always
        confirm the product id with search_products or get_product_details first."""
        try:
            store.add_to_cart(product_id, quantity)
            cart = store.get_cart()
        except StoreError as exc:
            return f"Error: {exc}"
        items = cart.get("items", [])
        summary = ", ".join(
            f"{it.get('quantity', 0)}x {it.get('product', {}).get('name', it.get('productId'))}"
            for it in items
        )
        return f"Added. Cart now contains: {summary or 'nothing'}."

    @tool
    def view_cart() -> str:
        """Show the current contents of the shopper's cart with prices."""
        try:
            cart = store.get_cart()
        except StoreError as exc:
            return f"Error: {exc}"
        items = cart.get("items", [])
        if not items:
            return "The cart is empty."
        lines = []
        for it in items:
            prod = it.get("product", {})
            lines.append(
                f"- {it.get('quantity', 0)}x {prod.get('name', it.get('productId'))} "
                f"@ {_format_money(prod.get('priceUsd'))}"
            )
        return "Cart contents:\n" + "\n".join(lines)

    @tool
    def list_currencies() -> str:
        """List the currency codes the store supports."""
        try:
            currencies = store.list_currencies()
        except StoreError as exc:
            return f"Error: {exc}"
        return "Supported currencies: " + ", ".join(currencies)

    all_tools = [
        search_knowledge_base,
        search_products,
        get_product_details,
        get_recommendations,
        add_to_cart,
        view_cart,
        list_currencies,
    ]
    return _apply_tool_faults(all_tools)


_DEFAULT_FAULT_MESSAGE = (
    "this capability is temporarily unavailable due to a service fault"
)


def _apply_tool_faults(tools: list[BaseTool]) -> list[BaseTool]:
    """Apply any active scenario ``tool_fault`` overlay to the tool set.

    A faulted tool with ``mode=remove`` is dropped from the set (constrains the
    agent's available tools), while ``mode=error`` keeps the tool present but
    makes every call return an error (induces tool-selection/recovery behaviour
    that Galileo surfaces). Absent any overlay this returns ``tools`` unchanged —
    a stable seam, so scenarios never edit core.
    """
    faults = faulted_tools()
    if not faults:
        return tools

    out: list[BaseTool] = []
    for t in tools:
        spec = faults.get(t.name)
        if spec is None:
            out.append(t)
            continue
        if spec.get("mode") == "remove":
            continue  # tool withheld from the agent entirely
        message = spec.get("message") or _DEFAULT_FAULT_MESSAGE

        def _faulted(_tool_name: str = t.name, _msg: str = message, **_kwargs: Any) -> str:
            return f"Error: {_tool_name} failed — {_msg}."

        out.append(
            StructuredTool.from_function(
                func=_faulted,
                name=t.name,
                description=t.description,
                args_schema=t.args_schema,
            )
        )
    return out
