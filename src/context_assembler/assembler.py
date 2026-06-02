"""The context assembler: build the window from typed segments under a budget.

This is the artifact the article argues you should build first — one place that
assembles the window from typed segments, each with a token cap, and *enforces*
a total budget instead of letting the window grow until it thrashes.

What it does, in order:

1. Truncate any segment over its own `max_tokens` cap.
2. Order segments stable-first (cacheable head, then by priority) so the
   prompt-cacheable prefix is as long as possible.
3. Enforce the total budget: reserve headroom for the model's reply, then admit
   segments in priority order, evicting the lowest-priority ones that don't fit.
4. Render the window and a `BudgetReport` you can log, assert on, or print as
   the allocation table from the post.

The model never sees any of this machinery — it sees a clean window. The point
is that the window became a *measured, enforced* artifact instead of a junk
drawer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .segments import Segment
from .tokens import estimate_tokens, truncate_to_tokens


@dataclass
class SegmentReport:
    name: str
    source: str
    tokens: int
    cap: int
    status: str  # "included" | "truncated" | "evicted"


@dataclass
class BudgetReport:
    window: int
    reserved_reply: int
    used: int
    segments: list[SegmentReport] = field(default_factory=list)

    @property
    def available(self) -> int:
        return self.window - self.reserved_reply

    @property
    def utilization(self) -> float:
        return self.used / self.available if self.available else 0.0

    def as_table(self) -> str:
        rows = [
            f"  {'SEGMENT':<18} {'SOURCE':<22} {'TOKENS':>7}  {'CAP':>6}  STATUS",
            f"  {'-' * 18} {'-' * 22} {'-' * 7}  {'-' * 6}  {'-' * 8}",
        ]
        for s in self.segments:
            rows.append(
                f"  {s.name:<18} {s.source:<22} {s.tokens:>7}  {s.cap:>6}  {s.status}"
            )
        rows.append(
            f"\n  window={self.window}  reserved_reply={self.reserved_reply}  "
            f"available={self.available}  used={self.used}  "
            f"utilization={self.utilization:.0%}"
        )
        return "\n".join(rows)


class ContextAssembler:
    """Assemble a context window from typed segments under a fixed budget."""

    def __init__(self, window: int = 200_000, reserved_reply: int = 8_000) -> None:
        if reserved_reply >= window:
            raise ValueError("reserved_reply must be smaller than window")
        self.window = window
        self.reserved_reply = reserved_reply

    def assemble(self, segments: list[Segment]) -> tuple[str, BudgetReport]:
        available = self.window - self.reserved_reply

        # 1. Apply per-segment caps (truncate oversized content).
        capped: list[tuple[Segment, str, bool]] = []
        for seg in segments:
            text, truncated = truncate_to_tokens(seg.content, seg.max_tokens)
            capped.append((seg, text, truncated))

        # 2. Render order: cacheable head first (longest cache prefix), then by
        #    declared priority, then stable by original position.
        order = sorted(
            range(len(capped)),
            key=lambda i: (not capped[i][0].cacheable, capped[i][0].priority, i),
        )

        # 3. Admit in priority order until the budget is exhausted; evict the
        #    rest. Priority 0 segments are load-bearing and admitted first.
        admit = sorted(range(len(capped)), key=lambda i: (capped[i][0].priority, i))
        used = 0
        included: set[int] = set()
        for i in admit:
            cost = estimate_tokens(capped[i][1])
            if used + cost <= available:
                used += cost
                included.add(i)

        # 4. Build the window (in render order) and the report (in render order).
        parts: list[str] = []
        reports: list[SegmentReport] = []
        for i in order:
            seg, text, truncated = capped[i]
            if i in included:
                parts.append(f"### {seg.name}\n{text}")
                status = "truncated" if truncated else "included"
            else:
                status = "evicted"
            reports.append(
                SegmentReport(
                    name=seg.name,
                    source=seg.source,
                    tokens=estimate_tokens(text) if i in included else 0,
                    cap=seg.max_tokens,
                    status=status,
                )
            )

        report = BudgetReport(
            window=self.window,
            reserved_reply=self.reserved_reply,
            used=used,
            segments=reports,
        )
        return "\n\n".join(parts), report
