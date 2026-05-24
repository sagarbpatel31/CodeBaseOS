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
