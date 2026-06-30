"""Runnable entrypoint for the Astronomy Shop concierge.

Usage::

    python -m agent --prompt "recommend a beginner telescope and add it to my cart"
    python -m agent                      # interactive conversation (Ctrl-D to exit)
    python -m agent --interactive

The flow: load config -> set up the single OTel instrumentation with dual
fan-out (Galileo + Splunk) -> build the LangGraph concierge -> run one or more
turns. Each turn is wrapped in an OpenInference session so a whole conversation
is legible as Sessions -> Traces -> Spans in Galileo. Spans are flushed to both
backends on exit.

No secrets are printed; only which backends were enabled and where.
"""

from __future__ import annotations

import argparse
import sys
import uuid

from dotenv import load_dotenv

load_dotenv()

from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402
from openinference.instrumentation import using_session  # noqa: E402

from .config import get_model_provider  # noqa: E402
from .graph import build_concierge  # noqa: E402
from .store_client import StoreClient  # noqa: E402
from .telemetry import setup_telemetry  # noqa: E402


def _print_telemetry_status(status) -> None:
    print("=" * 70)
    print("Telemetry (instrument once -> fan out to both backends):")
    print(f"  service.name            = {status.service_name}")
    print(f"  deployment.environment  = {status.deployment_environment}")
    g = "ENABLED" if status.galileo_enabled else "OFF"
    s = "ENABLED" if status.splunk_enabled else "OFF"
    m = "ENABLED" if status.metrics_enabled else "OFF"
    print(f"  instrumentation         = {status.instrumentation}")
    t = "ENABLED" if status.translator_enabled else "OFF"
    print(f"  genai translator [{t}]: {status.translator_detail}")
    print(f"  Galileo  [{g}] ({status.galileo_mode}): {status.galileo_detail}")
    print(f"  Splunk   [{s}]: {status.splunk_detail} ({status.splunk_endpoint})")
    print(f"  Splunk metrics [{m}]: {status.metrics_detail}")
    print(f"  model provider          = {get_model_provider()}")
    print("=" * 70)


def _extract_reply(result: dict) -> str:
    messages = result.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and isinstance(msg.content, str) and msg.content.strip():
            return msg.content.strip()
    return "(no text reply)"


def _run_turn(agent, history: list, user_text: str, session_id: str, callbacks: list) -> str:
    history.append(HumanMessage(content=user_text))
    config = {"callbacks": callbacks} if callbacks else {}
    with using_session(session_id):
        result = agent.invoke({"messages": history}, config=config)
    history[:] = result.get("messages", history)
    return _extract_reply(result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Astronomy Shop AI concierge")
    parser.add_argument("--prompt", help="Run a single prompt and exit.")
    parser.add_argument(
        "--interactive", action="store_true", help="Force interactive mode."
    )
    parser.add_argument(
        "--session-id",
        default=f"concierge-{uuid.uuid4().hex[:12]}",
        help="Session id used for cart scoping and Galileo session grouping.",
    )
    args = parser.parse_args(argv)

    telem = setup_telemetry()
    _print_telemetry_status(telem.status)
    print(f"Session id: {args.session_id}\n")
    telem.start_session(args.session_id)
    callbacks = telem.callbacks

    store = StoreClient(session_id=args.session_id)
    agent = build_concierge(args.session_id, store=store)
    history: list = []

    exit_code = 0
    try:
        if args.prompt and not args.interactive:
            print(f"You: {args.prompt}")
            reply = _run_turn(agent, history, args.prompt, args.session_id, callbacks)
            print(f"\nConcierge: {reply}")
        else:
            if args.prompt:
                print(f"You: {args.prompt}")
                reply = _run_turn(agent, history, args.prompt, args.session_id, callbacks)
                print(f"\nConcierge: {reply}\n")
            print("Interactive concierge — type a message, Ctrl-D / Ctrl-C to exit.\n")
            while True:
                try:
                    user_text = input("You: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\nGoodbye.")
                    break
                if not user_text:
                    continue
                if user_text.lower() in {"exit", "quit"}:
                    print("Goodbye.")
                    break
                reply = _run_turn(agent, history, user_text, args.session_id, callbacks)
                print(f"\nConcierge: {reply}\n")
    except Exception as exc:  # surface errors but still flush telemetry
        print(f"\nError during conversation: {exc}", file=sys.stderr)
        exit_code = 1
    finally:
        store.close()
        print("\nFlushing telemetry to Galileo + Splunk...")
        telem.shutdown()
        print("Done.")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
