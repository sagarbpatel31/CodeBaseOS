# HydraDB Notes

Findings, surprises, and workarounds discovered during implementation.

---

## SDK discovery (Phase 1 Lane B spike)

**Package name:** `hydradb` (PyPI) → installs as `hydra_db` (import name)

```python
from hydra_db import AsyncHydraDB, HydraDB, MemoryItem, ContentFilter, ForcefulRelationsPayload
```

**What HydraDB IS:** A memory/knowledge-recall platform with a graph layer underneath. Not a traditional graph database. It provides:
- `client.tenant.*` — multi-tenant workspace management
- `client.upload.knowledge()` — store documents/sources as searchable knowledge
- `client.upload.add_memory()` — store memories with metadata
- `client.recall.full_recall()` — semantic recall queries
- `client.fetch.list_data()` — list/browse stored sources
- `client.fetch.graph_relations_by_source_id()` — graph edge traversal

**What HydraDB is NOT:** It does not have native bi-temporal query support, Merkle chain enforcement, or Cypher/SPARQL query language.

---

## Architectural adaptations

### Bi-temporal storage
HydraDB does not enforce bi-temporal semantics. We implement this in Python:
- `tx_time` and `valid_time` stored in `document_metadata` of each knowledge source
- `as_of(nodes, point_in_time)` filtering done in-process (see `graph/bitemporal.py`)
- For Phase 2+: batch-query nodes and filter client-side. Consider an index on `valid_time` if HydraDB adds metadata indexing.

### Node storage format
Each graph node (Commit, File, PR, etc.) is stored as a knowledge source via `upload.knowledge(app_knowledge=...)`:
```json
{
    "id": "<uuid>",
    "type": "Commit",
    "title": "Commit:abc123",
    "content": "<full JSON of node>",
    "timestamp": "<tx_time ISO>",
    "document_metadata": {
        "tx_time": "...",
        "valid_time": "...",
        "valid_time_end": null,
        "episode_id": "...",
        "merkle_hash": "...",
        "source": "github",
        "node_type": "Commit"
    }
}
```

The `type` field is filterable via `ContentFilter(source_fields={"type": "Commit"})`.

### ⚠️ HydraDB overwrites `type` AND `content` — use `document_metadata` for everything

Two fields we send are NOT preserved as-is:

1. **`type`** is always coerced to `"document"` on read. Filtering on it does nothing.
   → Store the real type in `document_metadata.node_type` and filter with
   `ContentFilter(document_metadata={"node_type": "Commit"})`.

2. **`content`** is replaced by HydraDB's own document structure
   `{"text", "html_base64", "csv_base64", "markdown", "files", "layout"}`.
   Our `model_dump()` payload is discarded — reading `content` back returns empty strings.
   → **Any field we need to query/read back MUST live in `document_metadata`.**
   This is why `default_branch`, `repository_id`, `defining_file_id`, etc. are all
   written into `document_metadata` by each node's `to_hydra_source()`.

Rule of thumb: `document_metadata` is the only durable, queryable store. Treat
`content` as write-only / display-only.

### ⚠️ `document_metadata` keeps only strings and bools — drops ints and floats

Probe result (write `{f_val:0.1234, i_val:42, s_val:"hello", b_val:true}`,
read back): only `s_val` and `b_val` survive. `f_val` and `i_val` are gone.

This silently broke:
- `cost_usd` (float) → cost meter stuck at $0
- `sequence_no` (int) → all read back as 0 (root cause of the earlier Merkle
  ordering bug; fixed by the topological walk over `prev_hash`)
- `pr_number`, `issue_number`, `github_id` (int)

**Fix:** store every numeric metadata value as a string
(`str(self.cost_usd)`), and parse on read (`float(dm.get("cost_usd") or 0)`).
Booleans are fine as-is (`resolved: bool`).

### ⚠️ `upsert=True` is insert-only — it does NOT update existing sources

`upload.knowledge(upsert=True, ...)` with an `id` that already exists is a
**no-op**: it neither updates `document_metadata` nor duplicates the source.
Verified by probe (upsert a source with `sequence_no='999'` + new marker key →
read back unchanged, count unchanged).

Consequences:
- You cannot mutate a stored node in place. Nodes are effectively immutable
  once written (fine for our append-only model).
- **In-place repair is impossible.** To "fix" stored data you must
  `client.data.delete(ids=[...])` then re-create. But delete is **async** — a
  re-insert under the same id right after a delete races: the id may still
  appear to exist, so the upsert is skipped, then the delete lands and the
  source is gone. Net: data loss. Safe recovery is **wipe + re-ingest** with
  fresh ids (no delete/insert-same-id race).

### ⚠️ Reading the chain tail right after a write returns a STALE tail

HydraDB indexing lag: a node written milliseconds ago may not appear in the
next `fetch.list_data` call. For the Merkle chain this is catastrophic — two
episodes that each read the tail before the other indexed get the **same
`prev_hash`**, forking the chain. `verify` then walks one branch and reports
the other as BROKEN.

This bites whenever the tail is re-read mid-batch or between back-to-back API
calls (e.g. the webhook firehose firing several events quickly).

**Fix (backend, `_chain_tip`):** read the tail **once** from a *settled* read
(poll `get_episodes_ordered` until its length stops changing → indexing caught
up), cache `{prev_hash, seq}` in memory, then only ever **advance it in
memory**. Every backend episode write goes through this single authoritative
tip; nothing re-queries the tail mid-flight. `POST /chain/resync` resets it
after external ingestion (e.g. the `cbos` CLI writes episodes the backend
didn't make). The CLI itself already chains in-memory within a single run.

### Deleting sources
`client.data.delete(tenant_id, ids, sub_tenant_id)` removes sources by id.
Deletion is asynchronous — the count drains over several seconds. Used for the
`wipe` recovery path and one-off cleanup (e.g. stray test nodes).

### Merkle chain
Implemented in pure Python (see `graph/merkle.py`). Episodes are stored as HydraDB knowledge sources with `merkle_hash` and `prev_hash` in `document_metadata`. Chain verification walks all Episode nodes and recomputes hashes.

### Node counting
`SourceListResponse = typing.Any` — the knowledge list response is untyped in the SDK. We access it as a dict and extract `pagination.total`. Falls back to in-memory cache if the response format is unexpected.

### Edges / relations
`ForcefulRelationsPayload` can link sources via `cortex_source_ids`. Used for:
- Commit → Identity (authored_by)
- File → Commit (produced_by)
- Phase 2+: PR → Commit, Decision → PR, etc.

`client.fetch.graph_relations_by_source_id()` traverses these edges.

---

## Performance notes

- `/status` target: <200ms. Achieved via 2-second local cache.
- `list_data(page_size=1)` for counts: fast (one API call, minimal data).
- `verify_chain()` on large repos may be slow (one API call per page of episodes). Cache Merkle result between verifications.

---

## Open questions

1. Does `ContentFilter(source_fields={"type": "..."})` work for `kind="knowledge"` listing? (needs live test with credentials)
2. Does the `app_knowledge` JSON format accept all fields documented in `include_fields` on fetch? (needs validation)
3. Rate limits for batch writes (`write_nodes_bulk`)? Unclear from docs.
4. `SourceListResponse = typing.Any` — what is the actual shape? (needs live API call to inspect)
