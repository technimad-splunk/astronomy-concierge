"""Lightweight RAG retriever over the curated knowledge corpus.

Capability (a) of the concierge (demo-design §4): answer shopper questions from a
small, curated corpus of policy/guide documents under ``agent/knowledge/``. This
exposes the *groundedness / hallucination* failure surface that Galileo measures.

The retriever is intentionally dependency-free and deterministic: it splits each
markdown file into heading-delimited chunks and ranks them by term-overlap
(a TF-style lexical score). This keeps the agent fully offline-capable (no
embedding model or vector DB needed for the MVP) and reproducible — richer
embedding retrieval can replace it later without changing the tool surface.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .overlay import knowledge_overlay_docs

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"
_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "is", "are", "for", "on",
    "with", "do", "does", "i", "you", "my", "it", "this", "that", "how", "what",
    "can", "we", "our", "your", "be", "as", "at", "by", "from", "if", "not",
}


@dataclass
class Chunk:
    source: str
    heading: str
    text: str
    _terms: Counter


def _tokenize(text: str) -> list[str]:
    return [w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS]


def _split_into_chunks(source: str, content: str) -> list[Chunk]:
    """Split a markdown doc into chunks at ``##``/``###`` headings."""
    chunks: list[Chunk] = []
    heading = source
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            combined = f"{heading}\n{body}"
            chunks.append(Chunk(source, heading, combined, Counter(_tokenize(combined))))

    for line in content.splitlines():
        if line.startswith("## "):
            flush()
            heading = line.lstrip("# ").strip()
            buf = []
        else:
            buf.append(line)
    flush()
    return chunks


@lru_cache(maxsize=1)
def _load_corpus() -> tuple[list[Chunk], Counter]:
    """Load + chunk every markdown file once; also compute document frequency.

    A scenario overlay is layered on top of the baseline corpus: an overlay
    document with the *same* name replaces the baseline doc (e.g. a
    stale/poisoned variant), and new names are added. The baseline corpus on
    disk is never mutated.
    """
    # filename -> markdown content, baseline first then overlay (overlay wins).
    sources: dict[str, str] = {}
    if KNOWLEDGE_DIR.is_dir():
        for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
            sources[path.name] = path.read_text(encoding="utf-8")
    for name, content in knowledge_overlay_docs().items():
        sources[name] = content

    chunks: list[Chunk] = []
    for name in sorted(sources):
        chunks.extend(_split_into_chunks(name, sources[name]))
    doc_freq: Counter = Counter()
    for chunk in chunks:
        doc_freq.update(set(chunk._terms))
    return chunks, doc_freq


def clear_corpus_cache() -> None:
    """Invalidate the memoized corpus so overlays are re-read on next search."""
    _load_corpus.cache_clear()


def search(query: str, k: int = 3) -> list[Chunk]:
    """Return the top-``k`` chunks most relevant to ``query`` (TF-IDF cosine-ish)."""
    chunks, doc_freq = _load_corpus()
    if not chunks:
        return []
    n_docs = len(chunks)
    q_terms = Counter(_tokenize(query))
    if not q_terms:
        return []

    def score(chunk: Chunk) -> float:
        total = 0.0
        for term, q_count in q_terms.items():
            if term in chunk._terms:
                idf = math.log((n_docs + 1) / (doc_freq.get(term, 0) + 1)) + 1.0
                total += q_count * chunk._terms[term] * (idf ** 2)
        return total

    ranked = sorted(chunks, key=score, reverse=True)
    return [c for c in ranked if score(c) > 0][:k]


def format_results(chunks: list[Chunk]) -> str:
    if not chunks:
        return "No relevant information found in the knowledge base."
    blocks = [f"[source: {c.source} — {c.heading}]\n{c.text}" for c in chunks]
    return "\n\n---\n\n".join(blocks)
