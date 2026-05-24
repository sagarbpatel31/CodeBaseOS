"""
FastAPI backend for CodebaseOS.

Phase 1 implements /status exactly per docs/status-bar-contract.md §"Backend contract".
All other endpoints are stubbed to return 501 with a roadmap message.

Performance: /status responds in <200ms via 2-second local cache.
"""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from graph.client import HydraClient
from graph.merkle import verify_chain

# ---------------------------------------------------------------------------
# App-level state
# ---------------------------------------------------------------------------

_db: Optional[HydraClient] = None

# /status cache: refresh every 2s (shorter than 5s poll interval)
_status_cache: dict[str, Any] = {}
_status_expires: float = 0.0
_STATUS_TTL = 2.0
_COST_CAP_USD = 5.00


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db
    try:
        _db = HydraClient.from_env()
        await _db.ensure_tenant()
    except Exception as exc:
        print(f"[WARN] HydraDB not available: {exc}. Running in offline mode.")
        _db = None
    yield
    # Cleanup on shutdown (nothing to do for now)


app = FastAPI(
    title="CodebaseOS Backend",
    description="Bi-temporal code provenance — HydraDB + Merkle chain",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class StatusResponse(BaseModel):
    costSpent: float
    costCap: float
    nodeCount: int
    repoCount: int
    merkleOk: bool
    merkleHead: str


# ---------------------------------------------------------------------------
# /status — THE critical endpoint (Tier 1, must ship Phase 1)
# ---------------------------------------------------------------------------

@app.get("/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    """
    Returns live system metrics for the VS Code status bar.
    Must respond in <200ms; uses a 2-second local cache.

    Shape exactly per docs/status-bar-contract.md §"Backend contract".
    """
    global _status_cache, _status_expires

    now = time.monotonic()
    if now < _status_expires and _status_cache:
        return StatusResponse(**_status_cache)

    if _db is None:
        # Backend started without HydraDB credentials — return safe zeros.
        resp = StatusResponse(
            costSpent=0.0,
            costCap=_COST_CAP_USD,
            nodeCount=0,
            repoCount=0,
            merkleOk=True,
            merkleHead="",
        )
        _status_cache = resp.model_dump()
        _status_expires = now + _STATUS_TTL
        return resp

    cost, node_count, repo_count, merkle = await _gather_status(_db)

    resp = StatusResponse(
        costSpent=round(cost, 4),
        costCap=_COST_CAP_USD,
        nodeCount=node_count,
        repoCount=repo_count,
        merkleOk=merkle.ok,
        merkleHead=merkle.head_hash or "",
    )
    _status_cache = resp.model_dump()
    _status_expires = now + _STATUS_TTL
    return resp


async def _gather_status(db: HydraClient):
    """Fetch all metrics concurrently."""
    import asyncio

    cost_task = asyncio.create_task(db.get_total_cost())
    count_task = asyncio.create_task(db.count_all_nodes())
    repo_task = asyncio.create_task(db.count_nodes_by_type("Repository"))
    merkle_task = asyncio.create_task(verify_chain(db))

    cost, node_count, repo_count, merkle = await asyncio.gather(
        cost_task, count_task, repo_task, merkle_task
    )
    return cost, node_count, repo_count, merkle


# ---------------------------------------------------------------------------
# Stubbed endpoints (Phase 2+)
# ---------------------------------------------------------------------------

def _not_yet(phase: int = 2) -> HTTPException:
    return HTTPException(
        status_code=501,
        detail=f"Implemented in Phase {phase}. See KICKOFF.md.",
    )


@app.get("/repos")
async def list_repos():
    raise _not_yet(2)


@app.post("/repos")
async def ingest_repo():
    raise _not_yet(2)


@app.get("/why")
async def why(file: str, line: int):
    raise _not_yet(4)


@app.get("/five-whys")
async def five_whys(file: str, line: int):
    raise _not_yet(4)


@app.get("/summary")
async def summary(file: str, line: int, symbol: str = ""):
    raise _not_yet(2)


@app.post("/search-nl")
async def search_nl(q: str):
    raise _not_yet(4)


@app.post("/counterfactual")
async def counterfactual(decision: str):
    raise _not_yet(4)


@app.post("/handoff")
async def handoff(module: str):
    raise _not_yet(6)


@app.get("/verify")
async def verify():
    if _db is None:
        return {"ok": True, "chain_length": 0, "head_hash": ""}
    result = await verify_chain(_db)
    return {
        "ok": result.ok,
        "chain_length": result.chain_length,
        "head_hash": result.head_hash,
        "broken_at": result.broken_at,
    }


@app.get("/baseline-rag")
async def baseline_rag(file: str, line: int):
    raise _not_yet(6)
