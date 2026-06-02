"""Context engineering on one window, the same triage two ways.

Reproduces the worked example from the post: an SRE agent triaging a
`CrashLoopBackOff`. First the naive way — dump every tool, every retrieved
runbook chunk, and the raw logs into one window. Then the engineered way —
reranked selection, just-in-time tool results, an isolated sub-agent for the
log spew, and compaction — under an enforced budget.

Runs offline, no API key. Same facts available to both; the difference is
entirely paging strategy.
"""

from __future__ import annotations

from context_assembler import (
    Candidate,
    ContextAssembler,
    Segment,
    compact_observations,
    rerank,
)

# A small window makes the budget pressure visible without 200k of filler.
WINDOW = 6_000
RESERVED_REPLY = 1_500

TASK = "Pod checkout-7f9c is crash-looping in prod. Find the cause."

# Forty tools exist; this run is allowed seven. (select applies to tools too.)
ALL_TOOLS = [f"tool_{i}: does something in subsystem {i}" for i in range(40)]
ALLOWED_TOOLS = [
    "list_pods: list pods in a namespace",
    "get_pod_metrics: cpu/memory/restarts for one pod",
    "get_logs: recent log lines for one pod",
    "describe_pod: events and state for one pod",
    "get_limits: resource limits/requests for one pod",
    "rollout_history: recent deploy history",
    "get_runbook: fetch a runbook section by topic",
]

# Twelve runbook candidates came back from retrieval; one is actually relevant.
RUNBOOK_CANDIDATES = [
    Candidate("CrashLoopBackOff with OOMKilled: check memory limits and JVM heap; a "
              "restart will not fix an undersized heap.", source="runbook#oom"),
    Candidate("Ingress 502s: check the service mesh sidecar and upstream health.", source="runbook#502"),
    Candidate("Certificate rotation runbook for the API gateway.", source="runbook#certs"),
    Candidate("Node pressure eviction: cordon, drain, and scale the node pool.", source="runbook#node"),
    Candidate("ImagePullBackOff: verify registry credentials and image tags.", source="runbook#image"),
    Candidate("DNS resolution failures inside the cluster CoreDNS config.", source="runbook#dns"),
    Candidate("PVC stuck in Pending: check the storage class and provisioner.", source="runbook#pvc"),
    Candidate("HPA not scaling: verify metrics-server and resource requests.", source="runbook#hpa"),
    Candidate("CrashLoop from config: check env vars and mounted secrets.", source="runbook#config"),
    Candidate("Network policy blocking egress to the database.", source="runbook#netpol"),
    Candidate("Liveness probe too aggressive causes restart loops.", source="runbook#probe"),
    Candidate("Job backoff limit reached; inspect the failed pod's logs.", source="runbook#job"),
]

# ~2,000 lines of thread-dump noise with the one line that explains the crash
# at the very end — exactly where naive truncation drops it.
RAW_LOGS = (
    "\n".join(
        f"2026-06-06T12:00:{m % 60:02d}Z checkout-7f9c worker thread dump line {m} ..."
        for m in range(2_000)
    )
    + "\n2026-06-06T12:59:30Z FATAL java.lang.OutOfMemoryError: Java heap space (limit 512Mi)"
)

OBSERVATIONS = [
    "list_pods: checkout-7f9c is Running but RESTARTS=14",
    "describe_pod: last state Terminated, reason OOMKilled",
    "ruled out: networking — egress to db is healthy",
    "ruled out: image pull — image present, tag correct",
    "ruled out: config — env and secrets mount cleanly",
    "get_pod_metrics: memory at 97% of 512Mi, 3 OOM kills in 10m",
    "current hypothesis: undersized heap/limit, not a transient fault",
]


def isolated_log_summary(raw_logs: str) -> str:
    """A sub-agent reads the spew in *its own* window and returns 3 sentences."""

    fatal = [ln for ln in raw_logs.splitlines() if "OutOfMemoryError" in ln]
    return (
        "Sub-agent summary: logs show 'OutOfMemoryError: Java heap space' against a "
        f"512Mi limit. Crash is memory-driven, not transient. ({fatal[0].split(' ')[0]})"
    )


def naive_window() -> list[Segment]:
    """Everything, in one window. No selection, no isolation, no compaction."""

    return [
        Segment("system", "You are an SRE triage agent.", max_tokens=400, priority=0,
                cacheable=True, source="static"),
        Segment("tools", "\n".join(ALL_TOOLS), max_tokens=4_000, priority=10,
                source="all-40-tools"),
        Segment("task", TASK, max_tokens=200, priority=0, source="user"),
        Segment("runbook", "\n".join(c.text for c in RUNBOOK_CANDIDATES),
                max_tokens=4_000, priority=20, source="retrieval-top12-raw"),
        Segment("logs", RAW_LOGS, max_tokens=3_500, priority=30, source="get_logs-raw"),
        Segment("observations", "\n".join(OBSERVATIONS), max_tokens=2_000, priority=15,
                source="working-memory"),
    ]


def engineered_window() -> list[Segment]:
    """The four operations applied before assembly."""

    # select: rerank 12 candidates -> keep 1; advertise 7 tools, not 40.
    top_runbook = rerank(TASK + " CrashLoopBackOff OOMKilled memory", RUNBOOK_CANDIDATES, keep=1)[0]

    # isolate: the 60-line log spew is summarized in a sub-agent's window.
    log_summary = isolated_log_summary(RAW_LOGS)

    # compress: roll the early investigation into a summary, keep what's load-bearing.
    compacted = compact_observations(OBSERVATIONS, keep_recent=2, trigger_at=5)

    return [
        Segment("system", "You are an SRE triage agent.", max_tokens=400, priority=0,
                cacheable=True, source="static"),
        Segment("tools", "\n".join(ALLOWED_TOOLS), max_tokens=600, priority=10,
                cacheable=True, source="curated-7-tools"),
        Segment("task", TASK, max_tokens=200, priority=0, source="user"),
        Segment("runbook", top_runbook.text, max_tokens=600, priority=20,
                source=f"reranked:{top_runbook.source}"),
        Segment("tool_results", log_summary, max_tokens=400, priority=15,
                source="jit:isolated-subagent"),
        Segment("observations", "\n".join(compacted.observations), max_tokens=800,
                priority=15, source="working-memory:compacted"),
    ]


# The one line that actually explains the crash. The whole point is whether it
# survives assembly.
LOAD_BEARING = "OutOfMemoryError"


def run(label: str, segments: list[Segment]) -> bool:
    assembler = ContextAssembler(window=WINDOW, reserved_reply=RESERVED_REPLY)
    window, report = assembler.assemble(segments)
    evicted = [s.name for s in report.segments if s.status == "evicted"]
    truncated = [s.name for s in report.segments if s.status == "truncated"]
    print(f"\n{'=' * 70}\n{label}\n{'=' * 70}")
    print(report.as_table())
    if truncated:
        print(f"\n  ⚠ truncated (tail content lost): {', '.join(truncated)}")
    if evicted:
        print(f"  ⚠ evicted (never reached the model): {', '.join(evicted)}")

    survives = LOAD_BEARING in window
    mark = "✓ resident" if survives else "✗ MISSING"
    print(f"\n  → load-bearing evidence ('{LOAD_BEARING}'): {mark} in the assembled window.")
    return survives


def main() -> None:
    naive_ok = run("NAIVE: dump everything into one window", naive_window())
    eng_ok = run("ENGINEERED: select · isolate · compress · budget", engineered_window())
    print(
        "\nSame model, same facts. The naive window truncates 2,000 raw log lines and\n"
        "drops the OutOfMemoryError line at the tail — the one fact that explains the\n"
        "crash. The engineered window carries it in a 3-sentence isolated summary, so\n"
        "the evidence and the current hypothesis are both resident under budget.\n"
    )
    assert not naive_ok and eng_ok, "demo invariant: naive loses the evidence, engineered keeps it"


if __name__ == "__main__":
    main()
