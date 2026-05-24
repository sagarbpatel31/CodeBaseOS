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
from typing import Any, Optional

from hydra_db import AsyncHydraDB, ContentFilter, MemoryItem

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
        endpoint: Optional[str] = None,
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
    def from_env(cls) -> "HydraClient":
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
        """Create the tenant if it doesn't already exist."""
        if self._tenant_ready:
            return
        try:
            await self._client.tenant.create(tenant_id=self.tenant_id)
        except Exception:
            # Tenant likely already exists — not an error.
            pass
        self._tenant_ready = True

    # ------------------------------------------------------------------
    # Node writes
    # ------------------------------------------------------------------

    async def write_node(
        self,
        node: BaseNode,
        relations: Optional[list[str]] = None,
    ) -> str:
        """
        Persist a graph node to HydraDB as a knowledge source.
        Returns the node's source_id (= node.id).

        relations: list of other source_ids to link this node to.
        """
        await self.ensure_tenant()

        source_obj = node.to_hydra_source()

        if relations:
            source_obj["relations"] = {
                "cortex_source_ids": relations,
                "properties": {"edge_type": "related"},
            }

        app_knowledge_json = json.dumps([source_obj])

        await self._client.upload.knowledge(
            tenant_id=self.tenant_id,
            upsert=True,
            app_knowledge=app_knowledge_json,
        )

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

        sources = [n.to_hydra_source() for n in nodes]
        app_knowledge_json = json.dumps(sources)

        await self._client.upload.knowledge(
            tenant_id=self.tenant_id,
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
                kind="knowledge",
                page=1,
                page_size=1,
            )
            # SourceListResponse = Any; access as dict
            if isinstance(raw, dict):
                meta = raw.get("pagination") or raw.get("meta") or {}
                return int(meta.get("total", 0))
            # Fallback: return cached count
            return self._cache.node_counts.get("_total", 0)
        except Exception:
            return self._cache.node_counts.get("_total", 0)

    async def count_nodes_by_type(self, node_type: str) -> int:
        """Count knowledge sources of a specific type."""
        await self.ensure_tenant()
        try:
            filt = ContentFilter(source_fields={"type": node_type})
            raw = await self._client.fetch.list_data(
                tenant_id=self.tenant_id,
                kind="knowledge",
                page=1,
                page_size=1,
                filters=filt,
            )
            if isinstance(raw, dict):
                meta = raw.get("pagination") or raw.get("meta") or {}
                return int(meta.get("total", 0))
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
            filt = ContentFilter(source_fields={"type": "CostEvent"})
            page = 1
            total_cost = 0.0
            while True:
                raw = await self._client.fetch.list_data(
                    tenant_id=self.tenant_id,
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
                    total_cost += float(dm.get("cost_usd", 0.0))
                meta = raw.get("pagination") or raw.get("meta") or {}
                if not meta.get("has_next", False):
                    break
                page += 1
            self._cache.cost_usd = total_cost
            return total_cost
        except Exception:
            return self._cache.cost_usd

    async def get_episodes_ordered(self) -> list[dict[str, Any]]:
        """
        Fetch all Episode nodes ordered by sequence_no.
        Used for Merkle chain verification.
        """
        await self.ensure_tenant()
        episodes: list[dict[str, Any]] = []
        try:
            filt = ContentFilter(source_fields={"type": "Episode"})
            page = 1
            while True:
                raw = await self._client.fetch.list_data(
                    tenant_id=self.tenant_id,
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

        episodes.sort(key=lambda e: e["sequence_no"])
        return episodes

    async def update_merkle_head(self, head_hash: str, chain_length: int, ok: bool) -> None:
        """Update the cached Merkle state. Called by merkle.verify_chain()."""
        self._cache.merkle_head = head_hash
        self._cache.chain_length = chain_length
        self._cache.merkle_ok = ok
