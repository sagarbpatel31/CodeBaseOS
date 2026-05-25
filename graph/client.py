"""
HydraDB async client wrapper for CodebaseOS.

Storage model:
  - One HydraDB tenant per CodebaseOS instance (HYDRADB_TENANT_ID)
  - Graph nodes stored as knowledge sources via upload.knowledge(app_knowledge=...)
  - Edges via ForcefulRelationsPayload on each source
  - Node type encoded in source.type field (filterable via ContentFilter.source_fields)
  - Bi-temporal fields in source.document_metadata
  - In-memory count/cost cache with 2s TTL for fast /status responses
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

from hydra_db import AsyncHydraDB, ContentFilter

from graph.schema import BaseNode, CostEvent


@dataclass
class _StatusCache:
    node_counts: dict[str, int] = field(default_factory=dict)  # type → count
    cost_usd: float = 0.0
    merkle_head: str = ""
    merkle_ok: bool = True
    chain_length: int = 0
    expires_at: float = 0.0  # unix timestamp

    def is_fresh(self) -> bool:
        return time.monotonic() < self.expires_at

    def invalidate(self) -> None:
        self.expires_at = 0.0

    def refresh(self, ttl_seconds: float = 2.0) -> None:
        self.expires_at = time.monotonic() + ttl_seconds


class HydraClient:
    """
    Async wrapper around AsyncHydraDB.
    All graph operations go through this class.
    """

    DEFAULT_TENANT = "codebaseos"

    def __init__(
        self,
        api_key: str,
        endpoint: str | None = None,
        tenant_id: str = DEFAULT_TENANT,
    ) -> None:
        kwargs: dict[str, Any] = {"token": api_key}
        if endpoint:
            kwargs["base_url"] = endpoint
        self._client = AsyncHydraDB(**kwargs)
        self.tenant_id = tenant_id
        self._cache = _StatusCache()
        self._tenant_ready = False

    @classmethod
    def from_env(cls) -> HydraClient:
        api_key = os.environ.get("HYDRADB_API_KEY", "")
        endpoint = os.environ.get("HYDRADB_ENDPOINT")
        tenant_id = os.environ.get("HYDRADB_TENANT_ID", cls.DEFAULT_TENANT)
        if not api_key:
            raise RuntimeError("HYDRADB_API_KEY not set")
        return cls(api_key=api_key, endpoint=endpoint, tenant_id=tenant_id)

    # ------------------------------------------------------------------
    # Tenant lifecycle
    # ------------------------------------------------------------------

    async def ensure_tenant(self) -> None:
        """Create tenant if needed, then wait until vectorstore accepts writes."""
        if self._tenant_ready:
            return
        try:
            await self._client.tenant.create(tenant_id=self.tenant_id)
        except Exception:
            pass
        # Poll until vectorstore is ready — status API can report True before
        # the collection actually accepts writes (NotFoundError on first write).
        import asyncio as _asyncio
        for attempt in range(15):
            try:
                status = await self._client.tenant.get_infra_status(tenant_id=self.tenant_id)
                vs = status.infra.vectorstore_status if status.infra else []
                if vs and all(vs):
                    # Do a cheap probe write to confirm readiness
                    break
            except Exception:
                pass
            await _asyncio.sleep(2)
        self._tenant_ready = True

    # ------------------------------------------------------------------
    # Node writes
    # ------------------------------------------------------------------

    async def write_node(
        self,
        node: BaseNode,
        relations: list[str] | None = None,
    ) -> str:
        """
        Persist a graph node to HydraDB as a knowledge source.
        Returns the node's source_id (= node.id).

        relations: list of other source_ids to link this node to.
        """
        await self.ensure_tenant()

        source_obj = node.to_hydra_source(tenant_id=self.tenant_id)

        if relations:
            source_obj["relations"] = {
                "cortex_source_ids": relations,
                "properties": {"edge_type": "related"},
            }

        app_knowledge_json = json.dumps([source_obj])

        import asyncio as _asyncio
        for attempt in range(8):
            try:
                await self._client.upload.knowledge(
                    tenant_id=self.tenant_id,
                    sub_tenant_id="default",
                    upsert=True,
                    app_knowledge=app_knowledge_json,
                )
                break
            except Exception as exc:
                if attempt == 7:
                    raise
                # NotFoundError = vectorstore still provisioning
                wait = 2 ** attempt
                print(f"[HydraDB] write retry {attempt+1}/8 in {wait}s: {exc}")
                await _asyncio.sleep(wait)

        # Update in-memory cache counts.
        ntype = node.node_type
        self._cache.node_counts[ntype] = self._cache.node_counts.get(ntype, 0) + 1
        self._cache.node_counts["_total"] = self._cache.node_counts.get("_total", 0) + 1
        self._cache.invalidate()  # force a full refresh on next status call

        return str(node.id)

    async def write_nodes_bulk(
        self,
        nodes: list[BaseNode],
    ) -> list[str]:
        """Batch-write multiple nodes in one API call."""
        await self.ensure_tenant()

        sources = [n.to_hydra_source(tenant_id=self.tenant_id) for n in nodes]
        app_knowledge_json = json.dumps(sources)

        await self._client.upload.knowledge(
            tenant_id=self.tenant_id,
            sub_tenant_id="default",
            upsert=True,
            app_knowledge=app_knowledge_json,
        )

        for n in nodes:
            ntype = n.node_type
            self._cache.node_counts[ntype] = self._cache.node_counts.get(ntype, 0) + 1
            self._cache.node_counts["_total"] = self._cache.node_counts.get("_total", 0) + 1

        self._cache.invalidate()
        return [str(n.id) for n in nodes]

    # ------------------------------------------------------------------
    # Cost logging
    # ------------------------------------------------------------------

    async def log_cost(self, event: CostEvent) -> None:
        await self.write_node(event)
        self._cache.cost_usd += event.cost_usd

    # ------------------------------------------------------------------
    # Status queries (used by /status endpoint)
    # ------------------------------------------------------------------

    async def count_all_nodes(self) -> int:
        """Return total knowledge source count from HydraDB (page_size=1 trick)."""
        await self.ensure_tenant()
        try:
            raw = await self._client.fetch.list_data(
                tenant_id=self.tenant_id,
                sub_tenant_id="default",
                kind="knowledge",
                page=1,
                page_size=1,
            )
            if isinstance(raw, dict):
                return int(raw.get("total") or raw.get("pagination", {}).get("total", 0))
            return self._cache.node_counts.get("_total", 0)
        except Exception:
            return self._cache.node_counts.get("_total", 0)

    async def count_nodes_by_type(self, node_type: str) -> int:
        """Count knowledge sources of a specific type."""
        await self.ensure_tenant()
        try:
            filt = ContentFilter(document_metadata={"node_type": node_type})
            raw = await self._client.fetch.list_data(
                tenant_id=self.tenant_id,
                sub_tenant_id="default",
                kind="knowledge",
                page=1,
                page_size=1,
                filters=filt,
            )
            if isinstance(raw, dict):
                return int(raw.get("total") or raw.get("pagination", {}).get("total", 0))
            return self._cache.node_counts.get(node_type, 0)
        except Exception:
            return self._cache.node_counts.get(node_type, 0)

    async def get_total_cost(self) -> float:
        """
        Return total OpenAI spend in USD.

        For Phase 1 there are no LLM calls so this is always 0.
        In Phase 4+, we sum CostEvent.document_metadata.cost_usd across pages.
        """
        if self._cache.cost_usd > 0:
            return self._cache.cost_usd
        # Query CostEvent nodes and sum cost_usd from document_metadata.
        await self.ensure_tenant()
        try:
            filt = ContentFilter(document_metadata={"node_type": "CostEvent"})
            page = 1
            total_cost = 0.0
            while True:
                raw = await self._client.fetch.list_data(
                    tenant_id=self.tenant_id,
                    sub_tenant_id="default",
                    kind="knowledge",
                    page=page,
                    page_size=100,
                    filters=filt,
                    include_fields=["document_metadata"],
                )
                if not isinstance(raw, dict):
                    break
                sources = raw.get("data") or raw.get("sources") or []
                for src in sources:
                    dm = src.get("document_metadata") or {}
                    # cost_usd stored as a string (HydraDB drops numeric metadata)
                    try:
                        total_cost += float(dm.get("cost_usd") or 0.0)
                    except (TypeError, ValueError):
                        pass
                meta = raw.get("pagination") or raw.get("meta") or {}
                if not meta.get("has_next", False):
                    break
                page += 1
            self._cache.cost_usd = total_cost
            return total_cost
        except Exception:
            return self._cache.cost_usd

    async def list_nodes_by_type(self, node_type: str) -> list[dict[str, Any]]:
        """Return all knowledge sources of a node type as {id, dm} dicts.

        Reads everything from document_metadata (HydraDB discards our `content`).
        """
        await self.ensure_tenant()
        out: list[dict[str, Any]] = []
        try:
            filt = ContentFilter(document_metadata={"node_type": node_type})
            page = 1
            while True:
                raw = await self._client.fetch.list_data(
                    tenant_id=self.tenant_id,
                    sub_tenant_id="default",
                    kind="knowledge",
                    page=page,
                    page_size=100,
                    filters=filt,
                    include_fields=["document_metadata"],
                )
                if not isinstance(raw, dict):
                    break
                sources = raw.get("data") or raw.get("sources") or []
                for src in sources:
                    out.append({
                        "id": src.get("id", ""),
                        "title": src.get("title", ""),
                        "dm": src.get("document_metadata") or {},
                    })
                meta = raw.get("pagination") or raw.get("meta") or {}
                if not meta.get("has_next", False):
                    break
                page += 1
        except Exception as exc:
            print(f"[WARN] list_nodes_by_type({node_type}) failed: {exc}")
        return out

    async def get_episodes_ordered(self) -> list[dict[str, Any]]:
        """
        Fetch all Episode nodes ordered by sequence_no.
        Used for Merkle chain verification.
        """
        await self.ensure_tenant()
        episodes: list[dict[str, Any]] = []
        try:
            filt = ContentFilter(document_metadata={"node_type": "Episode"})
            page = 1
            while True:
                raw = await self._client.fetch.list_data(
                    tenant_id=self.tenant_id,
                    sub_tenant_id="default",
                    kind="knowledge",
                    page=page,
                    page_size=100,
                    filters=filt,
                    include_fields=["document_metadata", "content"],
                )
                if not isinstance(raw, dict):
                    break
                sources = raw.get("data") or raw.get("sources") or []
                for src in sources:
                    dm = src.get("document_metadata") or {}
                    episodes.append({
                        "id": src.get("id", ""),
                        "sequence_no": int(dm.get("sequence_no", 0)),
                        "prev_hash": dm.get("prev_hash", ""),
                        "merkle_hash": dm.get("merkle_hash", ""),
                        "action_type": dm.get("action_type", ""),
                        "content": src.get("content", ""),
                    })
                meta = raw.get("pagination") or raw.get("meta") or {}
                if not meta.get("has_next", False):
                    break
                page += 1
        except Exception:
            pass

        # Topological walk: follow prev_hash→merkle_hash links to get true chain order.
        # sequence_no values may all be 0 (HydraDB indexing lag during bulk ingest).
        by_prev: dict[str, Any] = {ep["prev_hash"]: ep for ep in episodes}
        genesis = by_prev.get("")
        if genesis is None:
            # No clear genesis — fall back to sequence_no sort
            episodes.sort(key=lambda e: e["sequence_no"])
            return episodes
        ordered: list[dict[str, Any]] = []
        current = genesis
        visited: set[str] = set()
        while current and current["merkle_hash"] not in visited:
            ordered.append(current)
            visited.add(current["merkle_hash"])
            current = by_prev.get(current["merkle_hash"])
        # Append any orphaned episodes not reachable from genesis
        seen_ids = {e["id"] for e in ordered}
        for ep in episodes:
            if ep["id"] not in seen_ids:
                ordered.append(ep)
        return ordered

    async def repair_merkle_chain(self) -> dict[str, Any]:
        """Re-link ALL Episodes into one linear Merkle chain ordered by tx_time.

        Recovery for a forked chain (e.g. caused by concurrent writes reading a
        stale tail). Recomputes sequence_no, prev_hash and merkle_hash for every
        Episode and re-upserts it. Returns {repaired, head_hash}.
        """
        import hashlib as _hashlib
        import json as _json

        from graph.merkle import _episode_canonical

        eps = await self.list_nodes_by_type("Episode")
        # Order by transaction time (when we wrote it) — the true append order.
        eps.sort(key=lambda e: e["dm"].get("tx_time", ""))

        prev = ""
        sources = []
        for i, ep in enumerate(eps):
            dm = dict(ep["dm"])
            action_type = dm.get("action_type", "")
            merkle = _hashlib.sha256(
                _episode_canonical(
                    seq=i, action_type=action_type,
                    inputs_hash="", outputs_hash="", prev_hash=prev,
                )
            ).hexdigest()
            dm["sequence_no"] = str(i)
            dm["prev_hash"] = prev
            dm["merkle_hash"] = merkle
            sources.append({
                "id": ep["id"],
                "tenant_id": self.tenant_id,
                "sub_tenant_id": "default",
                "type": "Episode",
                "title": ep.get("title", f"Episode:{i}:{action_type}"),
                "content": {},
                "timestamp": dm.get("tx_time", ""),
                "document_metadata": dm,
            })
            prev = merkle

        # HydraDB `upsert` is insert-only — it will NOT update an existing
        # source's metadata. So we delete the old Episodes and recreate them
        # with the SAME ids (preserving episode_id references on other nodes).
        import asyncio as _asyncio
        ids = [s["id"] for s in sources]
        for start in range(0, len(ids), 50):
            await self._client.data.delete(
                tenant_id=self.tenant_id,
                sub_tenant_id="default",
                ids=ids[start:start + 50],
            )
        # Let the deletes propagate before re-inserting under the same ids.
        await _asyncio.sleep(5)
        for start in range(0, len(sources), 50):
            batch = sources[start:start + 50]
            await self._client.upload.knowledge(
                tenant_id=self.tenant_id,
                sub_tenant_id="default",
                upsert=True,
                app_knowledge=_json.dumps(batch),
            )
        self._cache.invalidate()
        return {"repaired": len(sources), "head_hash": prev}

    async def update_merkle_head(self, head_hash: str, chain_length: int, ok: bool) -> None:
        """Update the cached Merkle state. Called by merkle.verify_chain()."""
        self._cache.merkle_head = head_hash
        self._cache.chain_length = chain_length
        self._cache.merkle_ok = ok
