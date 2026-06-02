"""Segments: the typed pieces a context window is assembled from.

The core idea of context engineering is that the window is not a string you
concatenate — it's a set of *typed segments*, each with a token cap, a
priority, a cacheability flag, and a provenance. The assembler then enforces
the budget across them. Making the segment the unit (not the raw string) is
what turns "stuff things into the prompt" into something you can measure,
evict, and audit.
"""

from __future__ import annotations

from dataclasses import dataclass

from .tokens import estimate_tokens


@dataclass(frozen=True)
class Segment:
    """One typed piece of the context window.

    Attributes:
        name: Stable identifier, e.g. "system", "runbook", "tool_results".
        content: The text that would land in the window.
        max_tokens: Per-segment cap. Content over this is truncated.
        priority: Lower is kept first when the total budget is tight.
            By convention: 0 = never evict (system, task), higher = first to go.
        cacheable: True for the static head (system prompt, tool catalog) that
            should sort to the front of the window for prompt-cache hits.
        source: Provenance — where this content came from. The thing you want
            on the day you debug a context-poisoning bug.
    """

    name: str
    content: str
    max_tokens: int
    priority: int = 50
    cacheable: bool = False
    source: str = "unknown"

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.content)
