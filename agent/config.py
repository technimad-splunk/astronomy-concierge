"""Chat-model provider abstraction for the Astronomy Shop concierge.

Selects a LangChain chat model from the ``MODEL_PROVIDER`` environment variable
(decision D6 in docs/implementation-plan.md). This is the one piece of real code
in the Phase-0 scaffold because the provider swap is central to the two-runtime
design (Apple-silicon/Ollama vs EC2/OpenAI; demo-design §8.1-8.2).

No credentials are embedded here: every value is read from the environment,
loaded from a gitignored ``.env`` via python-dotenv. See ``.env.example`` for the
required keys.
"""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ModuleNotFoundError:
    # python-dotenv is a declared dependency, but before the Phase-0 install it
    # may be absent. Fall back to the process environment so this module stays
    # importable for early scaffolding checks.
    pass


# Non-secret defaults only. Hosts/model names are safe to default; credentials
# (API keys/tokens) are never defaulted and must come from the environment.
DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "llama3.1:8b"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
# Low temperature improves tool-calling reliability for the agent loop. Override
# with MODEL_TEMPERATURE if a chattier persona is wanted.
DEFAULT_TEMPERATURE = 0.0


def _temperature() -> float:
    try:
        return float(os.getenv("MODEL_TEMPERATURE", DEFAULT_TEMPERATURE))
    except ValueError:
        return DEFAULT_TEMPERATURE


class ConfigError(RuntimeError):
    """Raised when model-provider configuration is missing or unsupported."""


def get_model_provider() -> str:
    """Return the normalized ``MODEL_PROVIDER`` (defaults to ``ollama``)."""
    return os.getenv("MODEL_PROVIDER", "ollama").strip().lower()


def get_chat_model():
    """Return a configured LangChain chat model for the selected provider.

    ``MODEL_PROVIDER=ollama`` -> ``ChatOllama`` (local, Apple-silicon runtime).
    ``MODEL_PROVIDER=openai`` -> ``ChatOpenAI`` (EC2 runtime).

    The LangChain integrations are imported lazily so this module is importable
    before the Phase-0 dependency install completes.
    """
    provider = get_model_provider()

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
            base_url=os.getenv("OLLAMA_HOST", DEFAULT_OLLAMA_HOST),
            temperature=_temperature(),
        )

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ConfigError(
                "MODEL_PROVIDER=openai requires OPENAI_API_KEY to be set "
                "(see .env.example)."
            )
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
            api_key=api_key,
            temperature=_temperature(),
        )

    raise ConfigError(
        f"Unsupported MODEL_PROVIDER={provider!r}; expected 'ollama' or 'openai'."
    )
