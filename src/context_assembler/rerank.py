"""Select: rerank retrieved candidates and keep only what earns its tokens.

The single highest-leverage change for most RAG-backed agents is putting a
reranker between retrieval and the window. Retrieval optimizes recall and
hands you more than you can afford; the reranker restores precision so the
window gets the few chunks that matter, not the top-N by raw similarity.

This reference uses a deterministic lexical scorer (query/term overlap) so it
runs offline. In production this is a cross-encoder or a hosted rerank API —
the shape (`rerank(query, candidates, keep) -> kept`) is identical.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Candidate:
    """A retrieved chunk awaiting selection."""

    text: str
    source: str = "retrieval"


def _terms(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def score(query: str, candidate: str) -> float:
    """Lexical overlap score in [0, 1]. Stand-in for a real reranker."""

    q = set(_terms(query))
    if not q:
        return 0.0
    c = _terms(candidate)
    if not c:
        return 0.0
    hits = sum(1 for term in c if term in q)
    # Reward overlap density, lightly normalized by candidate length so a long
    # off-topic chunk can't win on raw keyword count alone.
    return hits / (len(c) ** 0.5)


def rerank(query: str, candidates: list[Candidate], keep: int) -> list[Candidate]:
    """Return the top `keep` candidates by relevance to `query`."""

    ranked = sorted(candidates, key=lambda c: score(query, c.text), reverse=True)
    return ranked[:keep]
