# provenance

> A bi-temporal, tamper-evident **code-provenance engine**. Answer *"why does this code exist?"* across commits, PRs, issues, and decisions — grounded in a graph, not guessed.

OSS spinoff of [CodebaseOS](../README.md). Extracted from `graph/`,
`synthesizer/`, and `ingester/` so the engine can be used on its own.

## What it gives you

- **Bi-temporal nodes** — every fact carries `tx_time` (when you learned it) and `valid_time` (when it was true), so you can query the graph *as of* any instant.
- **Merkle-verified history** — every ingestion `Episode` extends a SHA-256 chain. Change one byte and `evaluate_chain` reports exactly where it broke. History is tamper-evident.
- **Cross-platform entity resolution** — cluster GitHub / git / email identities into one `Person` (deterministic auto-merge + a review queue for ambiguous matches).
- **A single, cost-capped LLM chokepoint** — `Synthesizer` is the only thing that calls the model: hard budget cap (fails closed), per-call cap, input truncation, output cap, response caching, and a `CostEvent` logged per paid call.

## Install

```bash
pip install pydantic                # pure primitives
pip install httpx hydradb openai    # + GitHub ingest, HydraDB graph, synthesis
```

## Quickstart (no credentials)

```bash
python -m provenance.example
```

```python
from uuid import uuid4
from provenance import Episode, make_node, extend_chain, evaluate_chain

eps, prev = [], ""
for i, action in enumerate(["ingest_repo", "ingest_commit", "ingest_pr"]):
    ep = extend_chain(
        make_node(Episode, episode_id=uuid4(), source="github",
                  sequence_no=i, action_type=action),
        prev_hash=prev,
    )
    eps.append(ep); prev = ep.merkle_hash

rows = [{"sequence_no": e.sequence_no, "merkle_hash": e.merkle_hash,
         "prev_hash": e.prev_hash} for e in eps]
assert evaluate_chain(rows).ok          # intact
rows[1]["merkle_hash"] = "deadbeef" + rows[1]["merkle_hash"][8:]
assert not evaluate_chain(rows).ok      # one altered hash → detected
```

## With a graph + synthesis (credentialed)

```python
from provenance import ProvenanceGraph, Synthesizer, GitHubIngester

db = ProvenanceGraph.from_env()         # HYDRADB_API_KEY
await db.ensure_tenant()
ingester = GitHubIngester.from_env(db)  # GITHUB_TOKEN
synth = Synthesizer(db)                 # OPENAI_API_KEY; the ONLY OpenAI caller
```

## Public API

`make_node` · `as_of` · `utc_now` · `evaluate_chain` · `verify_chain` ·
`extend_chain` · `compute_episode_hash` · `MerkleResult` · `resolve_identities` ·
node models (`Episode`, `Commit`, `PR`, `Issue`, `Decision`, `Person`,
`Identity`, …) · `Synthesizer` / `SynthesisResult` / `BudgetExceeded` ·
`ProvenanceGraph` (HydraDB) · `GitHubIngester`.

## License

MIT — see [LICENSE](./LICENSE).
