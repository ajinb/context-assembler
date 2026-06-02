"""context-assembler: a minimal, runnable reference for context engineering.

Four operations on the context window — write, select, compress, isolate —
plus the thing that ties them together: a budget you actually allocate.

- select   -> rerank.rerank
- compress -> compaction.compact_observations
- isolate  -> examples/triage_demo.py (sub-agent returns a summary, not spew)
- budget   -> assembler.ContextAssembler
"""

from .assembler import BudgetReport, ContextAssembler, SegmentReport
from .compaction import CompactionResult, compact_observations
from .rerank import Candidate, rerank, score
from .segments import Segment
from .tokens import estimate_tokens, truncate_to_tokens

__all__ = [
    "BudgetReport",
    "Candidate",
    "CompactionResult",
    "ContextAssembler",
    "Segment",
    "SegmentReport",
    "compact_observations",
    "estimate_tokens",
    "rerank",
    "score",
    "truncate_to_tokens",
]
