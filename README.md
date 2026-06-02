# context-assembler

> A minimal, **runnable** reference for context engineering. The context window is RAM — small, fast, expensive, volatile. This is the memory manager: typed segments, an enforced token budget, reranked selection, and compaction, in code you can read in a sitting.

[![CI](https://github.com/ajinb/context-assembler/actions/workflows/ci.yml/badge.svg)](https://github.com/ajinb/context-assembler/actions/workflows/ci.yml) [![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

**The window is a budget, not a bucket.** Two agents on the same model and the same system prompt behave like different products if one packs its window well and the other dumps everything it can find into it. This repo is the smallest honest demonstration of the discipline — not a framework to adopt, but a reference to read, copy, and outgrow.

It runs **offline with no dependencies and no API key**: a deterministic token estimator and lexical reranker stand in for the model's tokenizer and a real cross-encoder, so the demo is reproducible and the seams are obvious.

It's the companion to [*Context engineering: the window is a budget, not a bucket*](https://cloudandsre.com/blog/context-engineering-the-window-is-a-budget).

## The four operations (+ the budget)

| Operation | Where | What it does |
|---|---|---|
| **Select** | [`rerank.py`](src/context_assembler/rerank.py) | Rerank retrieved candidates, keep the few that earn their tokens. Top-5 reranked beats top-50 raw. |
| **Compress** | [`compaction.py`](src/context_assembler/compaction.py) | Roll old observations into a summary past a trigger — lossy on purpose, keeping what's load-bearing. |
| **Isolate** | [`examples/triage_demo.py`](examples/triage_demo.py) | A sub-agent reads the log spew in its own window and returns three sentences, not the spew. |
| **Write** | (your store) | Externalize state the model doesn't need this turn. The assembler depends on segments, not a transcript. |
| **Budget** | [`assembler.py`](src/context_assembler/assembler.py) | Build the window from typed segments, enforce per-segment caps and a total budget, order for cache hits. |

The thing that ties them together is the [`ContextAssembler`](src/context_assembler/assembler.py): you can't manage what you don't measure, so it makes the budget visible and enforced.

## Run it

```bash
git clone https://github.com/ajinb/context-assembler.git
cd context-assembler
pip install -e ".[dev]"
python examples/triage_demo.py
```

You'll see the same `CrashLoopBackOff` triage assembled two ways. **Naive:** forty tools, twelve raw runbook chunks, and 2,000 log lines dumped into one window — it runs at 93% and truncates the logs, dropping the `OutOfMemoryError` line at the tail that explains the crash. **Engineered:** seven curated tools, one reranked runbook section, an isolated log summary, and compacted observations — it fits at 5%, with the OOM evidence and current hypothesis both resident.

The demo prints the allocation table for each and verifies whether the load-bearing evidence survived:

```
  SEGMENT            SOURCE                  TOKENS     CAP  STATUS
  ------------------ ---------------------- -------  ------  --------
  system             static                       7     400  included
  tools              curated-7-tools             75     600  included
  task               user                        15     200  included
  tool_results       jit:isolated-subagent       38     400  included
  observations       working-memory:compacted      76     800  included
  runbook            reranked:runbook#oom         28     600  included

  window=6000  reserved_reply=1500  available=4500  used=239  utilization=5%

  → load-bearing evidence ('OutOfMemoryError'): ✓ resident in the assembled window.
```

## Use a real tokenizer / reranker

Nothing in the package cares how a token is counted or a candidate is scored:

- Replace [`estimate_tokens`](src/context_assembler/tokens.py) with a tiktoken or Anthropic token count.
- Replace [`score`](src/context_assembler/rerank.py) with a cross-encoder or a hosted rerank API.
- Replace the extractive summary in [`compaction.py`](src/context_assembler/compaction.py) with an LLM summarization call.

The shapes — `Segment`, `ContextAssembler.assemble`, `rerank(query, candidates, keep)` — stay identical. That's the point.

## Design stance

- **The window is a measured artifact.** Every segment has a token cap, a priority, and a provenance. A segment without a budget is one that expands under load until it starves the model's own room to think.
- **Order for the cache.** Static head (system prompt, tool catalog) sorts to the front so the cacheable prefix is as long as possible.
- **Provenance on every page.** The `source` field is what you want the day you debug a context-poisoning bug.
- **Outgrow it.** Real selection is a cross-encoder; real compression is an LLM; real isolation is sub-agents with their own loops. This repo is the reference you read before you build those.

## License

Apache-2.0. Built for [cloudandsre.com](https://cloudandsre.com).
