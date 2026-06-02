"""Compress: keep the resident set small without losing what's load-bearing.

When the working set genuinely has to stay large — a long incident thread, a
multi-hour run — you compact rather than evict. Compaction is lossy *on
purpose*: you decide what survives (decisions, ruled-out hypotheses, the
current hypothesis) and what's disposable (the play-by-play that got you here).

`compact_observations` rolls everything older than the most recent `keep_recent`
into a one-line summary, triggered only once the list crosses `trigger_at`.
The summarizer here is extractive and deterministic; in production it's an LLM
summarization call. The trigger-and-keep-recent shape is what matters.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CompactionResult:
    observations: list[str]
    summary: str | None
    dropped: int


def compact_observations(
    observations: list[str],
    *,
    keep_recent: int = 3,
    trigger_at: int = 6,
) -> CompactionResult:
    """Roll older observations into a summary once the list gets long.

    Returns the post-compaction observation list (summary first, if any),
    the summary line, and how many raw observations were folded away.
    """

    if len(observations) <= trigger_at:
        return CompactionResult(observations=list(observations), summary=None, dropped=0)

    older = observations[:-keep_recent]
    recent = observations[-keep_recent:]
    summary = _summarize(older)
    return CompactionResult(
        observations=[summary, *recent],
        summary=summary,
        dropped=len(older),
    )


def _summarize(observations: list[str]) -> str:
    """Deterministic extractive summary. Stands in for an LLM summarizer."""

    # Preserve anything that reads like a decision or an elimination — those are
    # the load-bearing lines a later turn still needs.
    keywords = ("ruled out", "decision", "confirmed", "cause", "rejected", "approved")
    kept = [o for o in observations if any(k in o.lower() for k in keywords)]
    head = "; ".join(kept) if kept else f"{len(observations)} earlier steps"
    return f"[compacted {len(observations)} observations] {head}"
