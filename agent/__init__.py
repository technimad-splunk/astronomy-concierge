"""Astronomy Shop AI shopping concierge (LangGraph).

A LangGraph ReAct agent that (a) answers shopper questions via RAG over a curated
corpus and (b) acts on the store by calling the Astronomy Shop's APIs as tools.
It is instrumented once with OpenTelemetry GenAI conventions and fanned out to
both Galileo and Splunk (see ``agent.telemetry``). Run with ``python -m agent``.
"""

__all__ = ["config", "graph", "tools", "rag", "store_client", "telemetry", "overlay", "main"]
