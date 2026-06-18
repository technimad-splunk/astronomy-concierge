"""The LangGraph concierge graph.

Builds a ReAct-style agent (LangGraph's ``create_react_agent``) wired to:

- the model from :func:`agent.config.get_chat_model` (provider-agnostic — Ollama
  today, OpenAI later, switched purely by ``MODEL_PROVIDER`` with no code change),
- the per-session tools from :func:`agent.tools.make_tools` (RAG + store actions).

The graph itself is the same regardless of provider or backend; instrumentation
is applied separately (``agent/telemetry.py``), keeping the "instrument once"
property intact.
"""

from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from .config import get_chat_model
from .overlay import prompt_overlay_text
from .store_client import StoreClient
from .tools import make_tools

SYSTEM_PROMPT = """\
You are the AI shopping concierge for the Astronomy Shop, an online store that \
sells telescopes and astronomy accessories. You help shoppers in two ways:

1. Answer questions about products, shipping, returns, warranty, and buying \
advice. For any policy or guidance question, call `search_knowledge_base` and \
ground your answer ONLY in what it returns. Do not invent policies.

2. Take actions on the store: search the live catalog, look up product details \
and prices, get recommendations, and manage the shopper's cart using the store \
tools.

Important rules:
- You must ACTUALLY CALL tools using the tool-calling mechanism. Never write a \
tool call as text in your reply (e.g. do not type JSON like {"name": ...}). If you \
need data or an action, emit a real tool call and wait for the result.
- For product names, prices, availability, and recommendations, ALWAYS use the \
store tools — never guess or rely on memory. Prices change and the catalog is live. \
Never invent a product name or product id.
- Before adding something to the cart, confirm the exact product id via \
`search_products` or `get_product_details`, then call `add_to_cart`.
- Complete every part of a multi-step request before giving your final answer \
(e.g. if asked to recommend AND add to cart, do both).
- Be concise and helpful. Cite the source document when you answer a policy \
question. If the tools don't have an answer, say so rather than guessing.
"""


def build_concierge(session_id: str, store: StoreClient | None = None):
    """Return a compiled LangGraph concierge for one shopper ``session_id``.

    If ``store`` is omitted, a new :class:`StoreClient` is created for the session.
    """
    store = store or StoreClient(session_id=session_id)
    tools = make_tools(store)
    model = get_chat_model()
    # A scenario `prompt_overlay` trigger appends SE-controlled text here (e.g. a
    # poisoned review / PII bait). Absent any overlay this is a no-op and the
    # agent runs at baseline. This is a stable seam — scenarios never edit core.
    overlay = prompt_overlay_text()
    prompt = f"{SYSTEM_PROMPT}\n\n{overlay}" if overlay else SYSTEM_PROMPT
    return create_react_agent(model, tools, prompt=prompt)
