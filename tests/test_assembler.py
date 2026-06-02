"""Tests for the context-assembler reference."""

from __future__ import annotations

from context_assembler import (
    Candidate,
    ContextAssembler,
    Segment,
    compact_observations,
    estimate_tokens,
    rerank,
)
from context_assembler.tokens import truncate_to_tokens


def test_estimate_tokens_monotonic():
    assert estimate_tokens("") == 0
    assert estimate_tokens("a") == 1
    assert estimate_tokens("a" * 40) == 10


def test_truncate_respects_cap():
    text = "word " * 200
    out, truncated = truncate_to_tokens(text, max_tokens=10)
    assert truncated
    assert estimate_tokens(out) <= 10
    assert out.endswith("…[truncated]")


def test_rerank_keeps_relevant():
    cands = [
        Candidate("CrashLoopBackOff OOMKilled memory heap limit", source="oom"),
        Candidate("certificate rotation for the gateway", source="certs"),
        Candidate("DNS resolution failures in CoreDNS", source="dns"),
    ]
    kept = rerank("pod crash loop OOMKilled memory", cands, keep=1)
    assert len(kept) == 1
    assert kept[0].source == "oom"


def test_compaction_triggers_and_preserves_decisions():
    obs = [
        "step 1 noise",
        "step 2 noise",
        "ruled out: networking",
        "step 4 noise",
        "step 5 noise",
        "current hypothesis: undersized heap",
    ]
    result = compact_observations(obs, keep_recent=2, trigger_at=4)
    assert result.dropped == 4
    # The summary keeps the load-bearing elimination line.
    assert "ruled out: networking" in result.summary
    # Recent observations survive verbatim.
    assert result.observations[-1] == "current hypothesis: undersized heap"


def test_compaction_noop_under_threshold():
    obs = ["a", "b", "c"]
    result = compact_observations(obs, trigger_at=6)
    assert result.summary is None
    assert result.observations == obs


def test_budget_evicts_lowest_priority_first():
    assembler = ContextAssembler(window=120, reserved_reply=20)  # available=100
    segs = [
        Segment("system", "x" * 200, max_tokens=50, priority=0, source="static"),   # ~50 tok
        Segment("task", "y" * 80, max_tokens=50, priority=0, source="user"),         # ~20 tok
        Segment("nice_to_have", "z" * 400, max_tokens=100, priority=90, source="extra"),  # big
    ]
    _, report = assembler.assemble(segs)
    status = {s.name: s.status for s in report.segments}
    assert status["system"] in {"included", "truncated"}
    assert status["task"] in {"included", "truncated"}
    assert status["nice_to_have"] == "evicted"  # lowest priority drops first
    assert report.used <= report.available


def test_cacheable_segments_render_first():
    assembler = ContextAssembler(window=10_000, reserved_reply=1_000)
    segs = [
        Segment("volatile", "fresh tool output", max_tokens=100, priority=5, source="jit"),
        Segment("system", "static head", max_tokens=100, priority=0, cacheable=True, source="static"),
    ]
    window, _ = assembler.assemble(segs)
    assert window.index("### system") < window.index("### volatile")


def test_priority_zero_survives_budget_pressure():
    assembler = ContextAssembler(window=70, reserved_reply=20)  # available=50
    segs = [
        Segment("task", "t" * 100, max_tokens=10, priority=0, source="user"),   # capped to ~10
        Segment("bulk", "b" * 1000, max_tokens=200, priority=99, source="bulk"),
    ]
    _, report = assembler.assemble(segs)
    status = {s.name: s.status for s in report.segments}
    assert status["task"] in {"included", "truncated"}
    assert status["bulk"] == "evicted"
