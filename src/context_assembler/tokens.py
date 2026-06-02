"""Token estimation.

Context engineering is budgeting, and a budget needs a unit. Real systems
count tokens with the model's own tokenizer; this reference uses a cheap,
deterministic approximation (~4 characters per token) so the package runs
offline with no dependencies and the demo is reproducible.

Swap `estimate_tokens` for a tiktoken / Anthropic token count in production —
nothing else in the package cares how the number is produced.
"""

from __future__ import annotations

import math

CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Approximate the token cost of a string. Deterministic and offline."""

    if not text:
        return 0
    return max(1, math.ceil(len(text) / CHARS_PER_TOKEN))


def truncate_to_tokens(text: str, max_tokens: int) -> tuple[str, bool]:
    """Truncate text to fit a token cap. Returns (text, was_truncated)."""

    if estimate_tokens(text) <= max_tokens:
        return text, False
    keep_chars = max(0, max_tokens * CHARS_PER_TOKEN - len(" …[truncated]"))
    return text[:keep_chars].rstrip() + " …[truncated]", True
