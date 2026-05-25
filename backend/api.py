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

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from dotenv import load_dotenv

load_dotenv()

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

# Webhook firehose: most-recent ingestion events (newest first), capped.
from collections import deque

_firehose: deque = deque(maxlen=50)

# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------

class _WSManager:
    def __init__(self) -> None:
        self._clients: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients = [c for c in self._clients if c is not ws]

    async def broadcast(self, payload: dict) -> None:
        import json
        dead = []
        for ws in self._clients:
            try:
                await ws.send_text(json.dumps(payload))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

_ws_manager = _WSManager()


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


@app.get("/graph")
async def graph(as_of: str = ""):
    """Return all graph nodes + links for the dashboard force graph.

    Optional `as_of` (ISO-8601) returns a bi-temporal snapshot: only nodes
    whose valid_time <= as_of and that were not yet superseded at as_of.
    Always returns `timeRange: {min, max}` so the UI can build a slider.
    """
    if _db is None:
        return {"nodes": [], "links": [], "timeRange": {"min": "", "max": ""}}
    return await _fetch_graph_snapshot(_db, as_of=as_of or None)


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
# WebSocket — live graph feed
# ---------------------------------------------------------------------------

NODE_TYPE_SIZE = {
    "Repository": 20, "Commit": 8, "PR": 10, "Issue": 8,
    "File": 5, "Symbol": 4, "Decision": 12, "Person": 14,
    "Identity": 6, "Episode": 3, "ReviewComment": 5, "Discussion": 7,
}

async def _fetch_graph_snapshot(db: HydraClient, as_of: Optional[str] = None) -> dict:
    """Pull all knowledge sources from HydraDB and shape them for the force graph.

    Builds links from node relationships:
      - repository_id  → Repository  (Commit, File, PR, Issue)
      - defining_file_id → File       (Symbol)
      - prev_hash chain → Episode      (Merkle chain visualization)
      - episode_id     → Episode       (provenance fallback so no node is orphaned)

    If `as_of` (ISO-8601) is given, only nodes valid at that instant are kept.
    The response always includes `timeRange` over the full (unfiltered) dataset.
    """
    try:
        nodes: list[dict] = []
        links: list[dict] = []
        node_ids: set[str] = set()
        # merkle_hash → episode node id, for converting prev_hash into a link target
        merkle_to_id: dict[str, str] = {}
        # buffered raw relationship fields per node, resolved after all ids known
        rels: list[tuple[str, str, dict, dict]] = []  # (node_id, node_type, dm, content)

        # ISO-8601 strings sort lexicographically in chronological order.
        t_min: str = ""
        t_max: str = ""

        def _valid_at(dm: dict, instant: str) -> bool:
            vt = dm.get("valid_time", "") or dm.get("tx_time", "")
            if vt and vt > instant:
                return False
            vte = dm.get("valid_time_end", "")
            if vte and vte <= instant:
                return False
            return True

        page = 1
        while True:
            raw = await db._client.fetch.list_data(
                tenant_id=db.tenant_id,
                sub_tenant_id="default",
                kind="knowledge",
                page=page,
                page_size=100,
                include_fields=["document_metadata", "content"],
            )
            if not isinstance(raw, dict):
                break
            sources = raw.get("data") or raw.get("sources") or []
            for src in sources:
                dm = src.get("document_metadata") or {}
                content = src.get("content") or {}
                if isinstance(content, str):
                    content = {}
                node_type = dm.get("node_type", "Unknown")
                nid = src.get("id", "")
                if not nid:
                    continue
                # Track full time range before any as_of filtering.
                vt = dm.get("valid_time", "") or dm.get("tx_time", "")
                if vt:
                    if not t_min or vt < t_min:
                        t_min = vt
                    if not t_max or vt > t_max:
                        t_max = vt
                # Bi-temporal filter.
                if as_of and not _valid_at(dm, as_of):
                    continue
                node_ids.add(nid)
                nodes.append({
                    "id": nid,
                    "nodeType": node_type,
                    "label": src.get("title", nid[:8]),
                    "val": NODE_TYPE_SIZE.get(node_type, 5),
                })
                if node_type == "Episode":
                    mh = dm.get("merkle_hash", "")
                    if mh:
                        merkle_to_id[mh] = nid
                rels.append((nid, node_type, dm, content))
            pagination = raw.get("pagination") or raw.get("meta") or {}
            if not pagination.get("has_next", False):
                break
            page += 1

        seen_links: set[tuple[str, str]] = set()

        def add_link(src_id: str, tgt_id: str, label: str) -> None:
            if not tgt_id or tgt_id == src_id:
                return
            if tgt_id not in node_ids:
                return
            key = (src_id, tgt_id)
            if key in seen_links:
                return
            seen_links.add(key)
            links.append({"source": src_id, "target": tgt_id, "label": label})

        # Group nodes by creating episode so we can connect satellites
        # (Identity, File, ReviewComment) to that episode's primary node
        # (a Commit, PR, or Issue). One episode = one ingest action.
        _PRIMARY = ("Commit", "PR", "Issue")
        groups: dict[str, list[tuple[str, str]]] = {}
        for nid, node_type, dm, _content in rels:
            ep_id = dm.get("episode_id") or ""
            if ep_id and node_type != "Episode":
                groups.setdefault(ep_id, []).append((nid, node_type))
        primary_of: dict[str, str] = {}
        for ep_id, members in groups.items():
            for nid, ntype in members:
                if ntype in _PRIMARY:
                    primary_of[ep_id] = nid
                    break

        # NOTE: HydraDB overwrites the `content` field with its own document
        # structure, so all relationship fields must be read from document_metadata.
        for nid, node_type, dm, _content in rels:
            linked = False
            # 1. structural: node → its repository hub
            repo_id = dm.get("repository_id") or ""
            if repo_id:
                add_link(nid, repo_id, "in_repo")
                linked = True
            # 2. Symbol → defining File
            if node_type == "Symbol":
                file_id = dm.get("defining_file_id") or ""
                if file_id:
                    add_link(nid, file_id, "defined_in")
                    linked = True
            # 3. ReviewComment → its PR (explicit foreign key)
            if node_type == "ReviewComment":
                pr_id = dm.get("pr_id") or ""
                if pr_id:
                    add_link(nid, pr_id, "review_on")
                    linked = True
            # 3b. Person → its resolved Identities (cross-repo bridge)
            if node_type == "Person":
                csv = dm.get("identity_ids_csv", "")
                for iid in (csv.split(",") if csv else []):
                    iid = iid.strip()
                    if iid:
                        add_link(nid, iid, "is")
                        linked = True
            # 4. Merkle chain between Episodes
            if node_type == "Episode":
                prev = dm.get("prev_hash", "")
                prev_id = merkle_to_id.get(prev, "")
                if prev_id:
                    add_link(nid, prev_id, "prev")
                    linked = True
            # 5. satellite → primary node within the same episode
            if node_type in ("Identity", "File", "ReviewComment"):
                ep_id = dm.get("episode_id") or ""
                primary = primary_of.get(ep_id, "")
                if primary and primary != nid:
                    label = {
                        "Identity": "authored_by",
                        "File": "touches",
                        "ReviewComment": "review_on",
                    }.get(node_type, "related")
                    add_link(nid, primary, label)
                    linked = True
            # 6. provenance fallback — keep any orphan tied to its Episode
            if not linked and node_type != "Episode":
                ep_id = dm.get("episode_id") or ""
                add_link(nid, ep_id, "from_episode")

        return {"nodes": nodes, "links": links, "timeRange": {"min": t_min, "max": t_max}}
    except Exception as exc:
        print(f"[WARN] _fetch_graph_snapshot failed: {exc}")
        return {"nodes": [], "links": [], "timeRange": {"min": "", "max": ""}}


@app.websocket("/ws")
async def ws_graph(websocket: WebSocket) -> None:
    await _ws_manager.connect(websocket)
    try:
        # Send current snapshot on connect
        if _db is not None:
            snapshot = await _fetch_graph_snapshot(_db)
            import json
            await websocket.send_text(json.dumps(snapshot))
        # Keep alive — push status pings every 5s
        import asyncio as _aio
        while True:
            await _aio.sleep(5)
            if _db is not None:
                snapshot = await _fetch_graph_snapshot(_db)
                await websocket.send_text(json.dumps(snapshot))
    except WebSocketDisconnect:
        _ws_manager.disconnect(websocket)
    except Exception:
        _ws_manager.disconnect(websocket)


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
    """List ingested Repository nodes for the dashboard left rail."""
    if _db is None:
        return {"repos": []}
    try:
        from hydra_db import ContentFilter
        filt = ContentFilter(document_metadata={"node_type": "Repository"})
        repos: list[dict] = []
        page = 1
        while True:
            raw = await _db._client.fetch.list_data(
                tenant_id=_db.tenant_id,
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
                content = src.get("content") or {}
                if isinstance(content, str):
                    content = {}
                name = dm.get("repo_name") or src.get("title", "")
                repos.append({
                    "id": src.get("id", ""),
                    "name": name,
                    "defaultBranch": dm.get("default_branch", ""),
                    "txTime": dm.get("tx_time", ""),
                })
            pagination = raw.get("pagination") or raw.get("meta") or {}
            if not pagination.get("has_next", False):
                break
            page += 1
        # De-dupe by name (re-ingests create new Repository nodes). Prefer the
        # most recent node, and one that actually has a default_branch set.
        by_name: dict[str, dict] = {}
        for r in repos:
            existing = by_name.get(r["name"])
            if existing is None:
                by_name[r["name"]] = r
                continue
            # Replace if this one is newer or fills in a missing branch.
            if (r.get("defaultBranch") and not existing.get("defaultBranch")) or (
                r.get("txTime", "") > existing.get("txTime", "")
            ):
                by_name[r["name"]] = r
        return {"repos": list(by_name.values())}
    except Exception as exc:
        print(f"[WARN] list_repos failed: {exc}")
        return {"repos": []}


@app.post("/repos")
async def ingest_repo(repo: str, commits: int = 5, prs: int = 0, issues: int = 0):
    """Ingest a repository via the API (commits, optionally PRs + issues).

    Uses the same in-memory-chained ingest path as the firehose, so the Merkle
    chain stays intact. Returns per-kind counts.
    """
    if _db is None:
        raise HTTPException(status_code=503, detail="HydraDB not connected")
    if "/" not in repo:
        raise HTTPException(status_code=400, detail="repo must be owner/name")
    owner, name = repo.split("/", 1)
    out: dict[str, int] = {}
    try:
        if commits > 0:
            out["commits"] = len(await _ingest_live(owner, name, "commit", min(commits, 20)))
        if prs > 0:
            out["prs"] = len(await _ingest_live(owner, name, "pr", min(prs, 20)))
        if issues > 0:
            out["issues"] = len(await _ingest_live(owner, name, "issue", min(issues, 20)))
        return {"repo": repo, "ingested": out}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/er-queue")
async def er_queue():
    """Entity-resolution view: deterministic Identity→Person clusters + review queue."""
    if _db is None:
        return {"clusters": [], "pending": [], "stats": {"identities": 0, "people": 0, "auto_merged": 0, "pending": 0}}
    from graph.resolve import resolve_identities
    identities = await _db.list_nodes_by_type("Identity")
    result = resolve_identities(identities)
    # Trim cluster member detail for transport; keep multi-identity clusters first.
    result["clusters"].sort(key=lambda c: len(c["identity_ids"]), reverse=True)
    return result


# ---------------------------------------------------------------------------
# Shared LLM helpers (cost gate, graph recall, cost logging)
# ---------------------------------------------------------------------------

async def _check_budget() -> None:
    """Refuse LLM calls once the hard cost cap is reached (AGENTS.md invariant)."""
    if _db is None:
        return
    spent = await _db.get_total_cost()
    if spent >= _COST_CAP_USD:
        raise HTTPException(
            status_code=402,
            detail=f"Cost cap reached: ${spent:.4f} / ${_COST_CAP_USD:.2f}. LLM calls disabled.",
        )


async def _recall_context(query: str, max_results: int = 8) -> tuple[str, int]:
    """Semantic recall from HydraDB → (context_string, node_count)."""
    recall_result = await _db._client.recall.full_recall(
        tenant_id=_db.tenant_id,
        sub_tenant_id="default",
        query=query,
        max_results=max_results,
        graph_context=True,
    )
    items: list[str] = []
    sources = getattr(recall_result, "sources", None) or []
    chunks = getattr(recall_result, "chunks", None) or []
    for src in sources[:max_results]:
        title = getattr(src, "title", "") or ""
        am = getattr(src, "additional_metadata", {}) or {}
        items.append(f"[{title} | type={am.get('node_type', '')}]")
    for chunk in chunks[:max_results]:
        content = getattr(chunk, "chunk_content", "") or ""
        if content:
            items.append(content[:400])
    context = "\n\n".join(items) or "No relevant context found in the knowledge graph."
    return context, len(sources) + len(chunks)


async def _log_llm_cost(usage, call_source: str) -> float:
    """Compute gpt-4o-mini cost from usage, persist a CostEvent, return cost."""
    cost_usd = (usage.prompt_tokens * 0.00000015) + (usage.completion_tokens * 0.0000006)
    from graph.schema import CostEvent
    from graph.bitemporal import make_node
    from uuid import uuid4
    cost_node = make_node(
        CostEvent,
        episode_id=uuid4(),
        source="openai",
        model="gpt-4o-mini",
        cost_usd=cost_usd,
        input_tokens=usage.prompt_tokens,
        output_tokens=usage.completion_tokens,
        call_source=call_source,
    )
    await _db.write_node(cost_node)
    return cost_usd


@app.post("/resolve")
async def resolve_persons():
    """Persist Person nodes for auto-merged identity clusters (>1 identity),
    bridging identities across repos. Idempotent: dedupes by primary_email.
    Person→Identity edges then render in the graph as cross-repo bridges."""
    if _db is None:
        raise HTTPException(status_code=503, detail="HydraDB not connected")
    from graph.resolve import resolve_identities
    from graph.schema import Person
    from graph.bitemporal import make_node

    identities = await _db.list_nodes_by_type("Identity")
    clusters = resolve_identities(identities)["clusters"]

    existing = await _db.list_nodes_by_type("Person")
    have_emails = {p["dm"].get("primary_email", "") for p in existing}

    chain = _ChainBuilder()
    await chain.init()
    created = 0
    for c in clusters:
        if len(c["identity_ids"]) < 2:
            continue  # only persist real merges
        email = c["primary_email"]
        if email and email in have_emails:
            continue  # already persisted
        ep = await chain.next("entity_resolve")
        person = make_node(
            Person,
            episode_id=ep.id,
            source="resolver",
            canonical_name=c["person_name"],
            primary_email=email,
            identity_ids=c["identity_ids"],
        )
        await _db.write_node(person, relations=c["identity_ids"])
        if email:
            have_emails.add(email)
        created += 1

    try:
        await _ws_manager.broadcast(await _fetch_graph_snapshot(_db))
    except Exception:
        pass
    return {"persons_created": created}


@app.get("/why")
async def why(file: str, line: int, repo: str = ""):
    """
    Explain why code at file:line exists — what commits, decisions, and PRs led to it.
    Uses HydraDB semantic recall + OpenAI to synthesize the answer.
    """
    if _db is None:
        raise HTTPException(status_code=503, detail="HydraDB not connected")
    await _check_budget()
    import os
    from openai import AsyncOpenAI

    query = f"Why does the code in {file} at line {line} exist? What commits or decisions introduced it?"
    if repo:
        query = f"In repository {repo}, {query}"

    try:
        context, ctx_count = await _recall_context(query)
        oai = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        chat = await oai.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=400,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are CodebaseOS, a code provenance assistant. "
                        "Given context from a codebase knowledge graph (commits, files, decisions), "
                        "explain concisely WHY the referenced code exists. "
                        "Focus on the intent, the problem it solves, and what changed. "
                        "Be specific and cite commit messages or decisions when available. "
                        "3-5 sentences max."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Question: {query}\n\nContext from knowledge graph:\n{context}",
                },
            ],
        )
        explanation = chat.choices[0].message.content or "No explanation generated."
        cost_usd = await _log_llm_cost(chat.usage, "why")
        return {
            "file": file,
            "line": line,
            "explanation": explanation,
            "context_nodes": ctx_count,
            "cost_usd": round(cost_usd, 6),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/five-whys")
async def five_whys(file: str, line: int, repo: str = ""):
    """
    Root-cause analysis: drill 5 levels of "why" from code → intent → decision.
    One LLM call produces the whole causal chain, grounded in graph context.
    """
    if _db is None:
        raise HTTPException(status_code=503, detail="HydraDB not connected")
    await _check_budget()
    import json as _json
    import os
    from openai import AsyncOpenAI

    query = f"Why does the code in {file} at line {line} exist? Trace the root cause."
    if repo:
        query = f"In repository {repo}, {query}"

    try:
        context, ctx_count = await _recall_context(query, max_results=10)
        oai = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        chat = await oai.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=600,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are CodebaseOS performing a '5 Whys' root-cause analysis on "
                        "a piece of code, grounded in a codebase knowledge graph. Produce a "
                        "causal chain of up to 5 levels, each level asking WHY the previous "
                        "answer holds, drilling from the immediate code change toward the "
                        "underlying intent or decision. Be specific; cite commits/PRs/decisions "
                        "from the context when possible; do not invent hashes. "
                        'Respond as JSON: {"chain": [{"question": "...", "answer": "..."}]}'
                    ),
                },
                {"role": "user", "content": f"Target: {query}\n\nKnowledge graph context:\n{context}"},
            ],
        )
        raw = chat.choices[0].message.content or "{}"
        try:
            parsed = _json.loads(raw)
            chain = parsed.get("chain", []) if isinstance(parsed, dict) else []
        except Exception:
            chain = []
        chain = [
            {"level": i + 1, "question": str(step.get("question", "")), "answer": str(step.get("answer", ""))}
            for i, step in enumerate(chain[:5])
            if isinstance(step, dict)
        ]
        cost_usd = await _log_llm_cost(chat.usage, "five-whys")
        return {
            "file": file,
            "line": line,
            "chain": chain,
            "context_nodes": ctx_count,
            "cost_usd": round(cost_usd, 6),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/summary")
async def summary(file: str, line: int, symbol: str = "", repo: str = ""):
    """
    Functional summary: WHAT the code at file:line (or `symbol`) does — distinct
    from /why (provenance). Grounded in graph recall.
    """
    if _db is None:
        raise HTTPException(status_code=503, detail="HydraDB not connected")
    await _check_budget()
    import os
    from openai import AsyncOpenAI

    target = f"the symbol '{symbol}' in {file}" if symbol else f"{file} at line {line}"
    scope = f"In repository {repo}, " if repo else ""
    query = f"{scope}what does {target} do? Its purpose and behavior."
    try:
        context, ctx_count = await _recall_context(query, max_results=6)
        oai = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        chat = await oai.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=250,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are CodebaseOS. Summarize WHAT the referenced code does — its "
                        "purpose and behavior — concisely (2-3 sentences). Use the knowledge "
                        "graph context if helpful. Do not invent commit hashes."
                    ),
                },
                {"role": "user", "content": f"Target: {query}\n\nContext:\n{context}"},
            ],
        )
        summary_text = chat.choices[0].message.content or "No summary generated."
        cost_usd = await _log_llm_cost(chat.usage, "summary")
        return {
            "file": file,
            "line": line,
            "symbol": symbol,
            "summary": summary_text,
            "context_nodes": ctx_count,
            "cost_usd": round(cost_usd, 6),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/search-nl")
async def search_nl(q: str, limit: int = 12):
    """
    Natural-language search over the knowledge graph. Pure HydraDB semantic
    recall — no LLM call, so it's free and fast. Returns ranked matching nodes
    (id, type, title, snippet, score) the dashboard can list and highlight.
    """
    if _db is None:
        return {"query": q, "results": []}
    limit = max(1, min(limit, 50))
    try:
        recall_result = await _db._client.recall.full_recall(
            tenant_id=_db.tenant_id,
            sub_tenant_id="default",
            query=q,
            max_results=limit,
            graph_context=True,
        )
        results: list[dict] = []
        seen_titles: set[str] = set()
        sources = getattr(recall_result, "sources", None) or []
        for src in sources:
            am = getattr(src, "additional_metadata", {}) or {}
            title = getattr(src, "title", "") or ""
            # Re-ingests create duplicate nodes with identical titles — show once.
            if title and title in seen_titles:
                continue
            seen_titles.add(title)
            results.append({
                "id": getattr(src, "id", "") or getattr(src, "source_id", ""),
                "nodeType": am.get("node_type", ""),
                "title": title,
                "score": round(float(getattr(src, "score", 0.0) or 0.0), 4),
            })
            if len(results) >= limit:
                break
        return {"query": q, "count": len(results), "results": results}
    except Exception as exc:
        print(f"[WARN] search_nl failed: {exc}")
        return {"query": q, "results": []}


@app.get("/counterfactual")
async def counterfactual(decision: str):
    """
    "What if this decision/change were reversed?" — recall related context and
    reason about the likely consequences, grounded in the knowledge graph.
    `decision` is free text or a decision summary.
    """
    if _db is None:
        raise HTTPException(status_code=503, detail="HydraDB not connected")
    await _check_budget()
    import os
    from openai import AsyncOpenAI

    query = f"What commits, PRs, files, and decisions relate to: {decision}?"
    try:
        context, ctx_count = await _recall_context(query, max_results=10)
        oai = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        chat = await oai.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=500,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are CodebaseOS reasoning about a counterfactual: what would "
                        "likely happen if the described decision or change were reversed or "
                        "never made. Use the codebase knowledge-graph context to ground your "
                        "reasoning in real commits/PRs/files. Cover: (1) what code/behavior "
                        "would differ, (2) which downstream files or PRs would be affected, "
                        "(3) risks or regressions. Be concrete; do not invent hashes. "
                        "4-6 sentences."
                    ),
                },
                {"role": "user", "content": f"Decision/change to reverse: {decision}\n\nKnowledge graph context:\n{context}"},
            ],
        )
        analysis = chat.choices[0].message.content or "No analysis generated."
        cost_usd = await _log_llm_cost(chat.usage, "counterfactual")
        return {
            "decision": decision,
            "analysis": analysis,
            "context_nodes": ctx_count,
            "cost_usd": round(cost_usd, 6),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/handoff")
async def handoff(module: str, repo: str = ""):
    """
    Generate an onboarding tour for a module/path: overview, key files, key
    people, key decisions, and where to start. Grounded in HydraDB recall.
    """
    if _db is None:
        raise HTTPException(status_code=503, detail="HydraDB not connected")
    await _check_budget()
    import json as _json
    import os
    from openai import AsyncOpenAI

    scope = f"in repository {repo}, " if repo else ""
    query = (
        f"{scope}everything about the module '{module}': its files, the commits and PRs that "
        f"shaped it, the people who worked on it, and any decisions behind it."
    )
    try:
        context, ctx_count = await _recall_context(query, max_results=14)
        oai = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        chat = await oai.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=700,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are CodebaseOS generating a developer ONBOARDING TOUR for a module, "
                        "grounded in a codebase knowledge graph. Produce a concise, practical tour "
                        "for someone new to this module. Cite real files/commits/PRs/people from the "
                        "context; do not invent hashes. Respond as JSON: "
                        '{"overview": "...", "start_here": "...", '
                        '"key_files": ["..."], "key_people": ["..."], "key_decisions": ["..."]}'
                    ),
                },
                {"role": "user", "content": f"Module: {module}\n\nKnowledge graph context:\n{context}"},
            ],
        )
        raw = chat.choices[0].message.content or "{}"
        try:
            tour = _json.loads(raw)
            if not isinstance(tour, dict):
                tour = {}
        except Exception:
            tour = {}
        cost_usd = await _log_llm_cost(chat.usage, "handoff")
        return {
            "module": module,
            "overview": str(tour.get("overview", "")),
            "start_here": str(tour.get("start_here", "")),
            "key_files": [str(x) for x in (tour.get("key_files") or [])][:8],
            "key_people": [str(x) for x in (tour.get("key_people") or [])][:8],
            "key_decisions": [str(x) for x in (tour.get("key_decisions") or [])][:8],
            "context_nodes": ctx_count,
            "cost_usd": round(cost_usd, 6),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Webhook firehose — live ingestion feed
# ---------------------------------------------------------------------------

def _record_event(kind: str, title: str, **extra) -> dict:
    """Append an ingestion event to the firehose buffer (newest first)."""
    import time as _time
    evt = {
        "ts": _time.time(),
        "kind": kind,          # "commit" | "pr" | "issue" | "webhook"
        "title": title,
        **extra,
    }
    _firehose.appendleft(evt)
    return evt


# Authoritative in-memory Merkle chain tip for backend-side ingestion.
# HydraDB indexing lag means a tail read right after a write is stale, which
# forks the chain. So we read the tip ONCE (from a settled read) and then only
# ever advance it in memory — every backend episode write goes through here.
_chain_tip: Optional[dict] = None
_chain_lock_init = False


async def _ensure_chain_tip() -> dict:
    """Initialize the in-memory chain tip from a STABLE (settled) DB read, once."""
    global _chain_tip
    if _chain_tip is not None:
        return _chain_tip
    import asyncio as _aio
    prev_len = -1
    eps: list = []
    for _ in range(8):
        eps = await _db.get_episodes_ordered()
        if len(eps) == prev_len:
            break  # length stabilized → indexing settled
        prev_len = len(eps)
        await _aio.sleep(1.5)
    _chain_tip = {
        "prev_hash": eps[-1]["merkle_hash"] if eps else "",
        "seq": len(eps),
    }
    return _chain_tip


class _ChainBuilder:
    """Appends Episodes using the authoritative in-memory tip, so concurrent or
    back-to-back ingest calls never fork the chain on stale tail reads."""

    async def init(self) -> None:
        await _ensure_chain_tip()

    async def next(self, action_type: str):
        from graph.schema import Episode
        from graph.bitemporal import make_node, utc_now
        from graph.merkle import extend_chain
        from uuid import uuid4
        tip = await _ensure_chain_tip()
        ep = make_node(
            Episode, episode_id=uuid4(), source="github",
            sequence_no=tip["seq"], action_type=action_type, valid_time=utc_now(),
        )
        ep = extend_chain(ep, prev_hash=tip["prev_hash"])
        await _db.write_node(ep)
        # Advance the authoritative tip in memory.
        tip["prev_hash"] = ep.merkle_hash
        tip["seq"] += 1
        return ep


async def _ingest_live(owner: str, repo: str, kind: str, count: int) -> list[dict]:
    """Pull latest commits/PRs/issues from GitHub, ingest each as its own
    Episode, and push an event onto the firehose. Returns the recorded events."""
    from ingester.github import GitHubIngester
    ingester = GitHubIngester.from_env(_db)
    chain = _ChainBuilder()
    await chain.init()
    events: list[dict] = []
    try:
        # Ensure repository node exists.
        ep0 = await chain.next("ingest_repo")
        repo_node, _sid = await ingester.ensure_repository(owner, repo, ep0.id)

        if kind == "commit":
            data = await ingester._get(f"/repos/{owner}/{repo}/commits", params={"per_page": count})
            for c in list(reversed(data))[:count]:
                ep = await chain.next("ingest_commit")
                r = await ingester.ingest_one_commit(owner, repo, c["sha"], repo_node.id, ep)
                events.append(_record_event(
                    "commit", r["message"] or r["sha"][:12],
                    sha=r["sha"][:12], author=r["author"], merkle=ep.merkle_hash[:12],
                ))
        elif kind == "pr":
            prs = await ingester.get_pulls(owner, repo, count)
            for pr in prs[:count]:
                ep = await chain.next("ingest_pr")
                r = await ingester.ingest_pr(owner, repo, pr, repo_node.id, ep)
                events.append(_record_event(
                    "pr", f"#{r['number']} {r['title']}",
                    author=r["author"], state=r["state"], merkle=ep.merkle_hash[:12],
                ))
        elif kind == "issue":
            issues = await ingester.get_issues(owner, repo, count)
            taken = 0
            for iss in issues:
                if taken >= count:
                    break
                if "pull_request" in iss:
                    continue
                ep = await chain.next("ingest_issue")
                r = await ingester.ingest_issue(iss, repo_node.id, ep)
                events.append(_record_event(
                    "issue", f"#{r['number']} {r['title']}",
                    author=r["author"], state=r["state"], merkle=ep.merkle_hash[:12],
                ))
                taken += 1
    finally:
        await ingester.close()

    # Push fresh graph snapshot to any connected WS clients.
    try:
        snapshot = await _fetch_graph_snapshot(_db)
        await _ws_manager.broadcast(snapshot)
    except Exception:
        pass
    return events


@app.get("/events")
async def events(limit: int = 50):
    """Return recent firehose events (newest first) for the dashboard panel."""
    return {"events": list(_firehose)[:limit]}


@app.post("/chain/resync")
async def chain_resync():
    """Reset the in-memory Merkle tip so it re-reads from HydraDB. Call after
    external ingestion (e.g. the `cbos` CLI) so backend writes chain correctly."""
    global _chain_tip
    _chain_tip = None
    tip = await _ensure_chain_tip()
    return {"seq": tip["seq"], "prev_hash": tip["prev_hash"]}


@app.post("/webhook/simulate")
async def webhook_simulate(repo: str = "", kind: str = "commit", count: int = 3):
    """Demo trigger: pull the latest items from GitHub and ingest them live,
    populating the firehose. Stands in for real GitHub webhook delivery (which
    needs a public tunnel)."""
    if _db is None:
        raise HTTPException(status_code=503, detail="HydraDB not connected")
    target = repo or os.environ.get("DEMO_REPO", "tokio-rs/tokio")
    if "/" not in target:
        raise HTTPException(status_code=400, detail="repo must be owner/name")
    if kind not in ("commit", "pr", "issue"):
        raise HTTPException(status_code=400, detail="kind must be commit|pr|issue")
    owner, name = target.split("/", 1)
    count = max(1, min(count, 10))
    try:
        evts = await _ingest_live(owner, name, kind, count)
        return {"ingested": len(evts), "events": evts}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/webhook")
async def webhook(request: Request):
    """GitHub-compatible webhook receiver. Parses the X-GitHub-Event header and
    ingests the delivered push/PR/issue, then records firehose events.

    Point a real GitHub webhook (with a tunnel) at POST /webhook to go live.
    """
    if _db is None:
        raise HTTPException(status_code=503, detail="HydraDB not connected")
    event_type = request.headers.get("X-GitHub-Event", "")
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON payload")

    repo_full = (payload.get("repository") or {}).get("full_name", "")
    if "/" not in repo_full:
        raise HTTPException(status_code=400, detail="payload missing repository.full_name")
    owner, name = repo_full.split("/", 1)

    from ingester.github import GitHubIngester
    ingester = GitHubIngester.from_env(_db)
    chain = _ChainBuilder()
    await chain.init()
    recorded: list[dict] = []
    try:
        ep0 = await chain.next("webhook")
        repo_node, _sid = await ingester.ensure_repository(owner, name, ep0.id)

        if event_type == "push":
            for c in payload.get("commits", []):
                ep = await chain.next("ingest_commit")
                r = await ingester.ingest_one_commit(owner, name, c["id"], repo_node.id, ep)
                recorded.append(_record_event(
                    "commit", r["message"] or r["sha"][:12],
                    sha=r["sha"][:12], author=r["author"], merkle=ep.merkle_hash[:12],
                ))
        elif event_type == "pull_request":
            pr = payload.get("pull_request") or {}
            ep = await chain.next("ingest_pr")
            r = await ingester.ingest_pr(owner, name, pr, repo_node.id, ep)
            recorded.append(_record_event(
                "pr", f"#{r['number']} {r['title']}", author=r["author"], state=r["state"],
            ))
        elif event_type == "issues":
            iss = payload.get("issue") or {}
            ep = await chain.next("ingest_issue")
            r = await ingester.ingest_issue(iss, repo_node.id, ep)
            recorded.append(_record_event(
                "issue", f"#{r['number']} {r['title']}", author=r["author"], state=r["state"],
            ))
        else:
            _record_event("webhook", f"unhandled event: {event_type or 'unknown'}")
    finally:
        await ingester.close()

    try:
        await _ws_manager.broadcast(await _fetch_graph_snapshot(_db))
    except Exception:
        pass
    return {"event": event_type, "ingested": len(recorded), "events": recorded}


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
async def baseline_rag(file: str, line: int, repo: str = ""):
    """"Without HydraDB" baseline: answer the same /why question using ONLY the
    LLM, with no knowledge-graph retrieval and no provenance. Demonstrates the
    value of the graph by contrast — this path cannot cite commits or decisions.
    """
    if _db is None:
        raise HTTPException(status_code=503, detail="HydraDB not connected")
    await _check_budget()
    import os
    from openai import AsyncOpenAI

    query = f"Why does the code in {file} at line {line} exist? What commits or decisions introduced it?"
    if repo:
        query = f"In repository {repo}, {query}"

    try:
        oai = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        chat = await oai.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=400,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a plain code assistant with NO access to the "
                        "repository history, commits, PRs, or decisions — only the "
                        "file path and line number the user mentions. Answer the "
                        "question as best you can from general knowledge. Do not "
                        "invent specific commit hashes, PR numbers, or authors. "
                        "3-5 sentences max."
                    ),
                },
                {"role": "user", "content": query},
            ],
        )
        explanation = chat.choices[0].message.content or "No explanation generated."
        cost_usd = (chat.usage.prompt_tokens * 0.00000015) + (chat.usage.completion_tokens * 0.0000006)
        from graph.schema import CostEvent
        from graph.bitemporal import make_node
        from uuid import uuid4
        cost_node = make_node(
            CostEvent,
            episode_id=uuid4(),
            source="openai",
            model="gpt-4o-mini",
            cost_usd=cost_usd,
            input_tokens=chat.usage.prompt_tokens,
            output_tokens=chat.usage.completion_tokens,
            call_source="baseline-rag",
        )
        await _db.write_node(cost_node)
        return {
            "file": file,
            "line": line,
            "explanation": explanation,
            "context_nodes": 0,
            "cost_usd": round(cost_usd, 6),
            "mode": "baseline-no-graph",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
