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
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

from graph import chain as chainstate
from graph.client import HydraClient
from graph.merkle import MerkleResult, evaluate_chain, verify_chain
from synthesizer.synthesizer import (
    COST_CAP_USD,
    BudgetExceeded,
    SynthesisResult,
    Synthesizer,
)

# ---------------------------------------------------------------------------
# App-level state
# ---------------------------------------------------------------------------

_db: HydraClient | None = None

# The single OpenAI chokepoint (AGENTS.md invariant #8). Created in lifespan.
_synth: Synthesizer | None = None

# Offline demo fixture (CBOS_OFFLINE_DEMO=1): serve a deterministic bundled graph
# with no HydraDB/OpenAI credentials so the dashboard + chaos buttons render
# anywhere. Only ever consulted when there is no live DB, so it cannot affect a
# real, credentialed demo.
_OFFLINE_DEMO = os.environ.get("CBOS_OFFLINE_DEMO", "").lower() in ("1", "true", "yes")
_offline: Any | None = None
if _OFFLINE_DEMO:
    from backend.offline import OfflineStore

    _offline = OfflineStore()

# /status cache: refresh every 2s (shorter than 5s poll interval)
_status_cache: dict[str, Any] = {}
_status_expires: float = 0.0
_STATUS_TTL = 2.0
_COST_CAP_USD = COST_CAP_USD

# Webhook firehose: most-recent ingestion events (newest first), capped.
from collections import deque

_firehose: deque = deque(maxlen=50)

# Chaos layer state (CODEBASEOS_SPEC §10). Fault injection for the live demo:
#   tamper  — a corrupted-hash view of one Episode; the real linkage check
#             then reports the chain as broken (merkleOk=false) until restore.
#   nuclear — an author marked "left the company"; their authored nodes become
#             orphaned and the system suggests reviewers from repo activity.
_chaos: dict[str, Any] = {"tamper": None, "nuclear": None}


def _bust_status_cache() -> None:
    """Force the next /status to recompute (so chaos toggles show instantly)."""
    global _status_expires
    _status_expires = 0.0

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
    global _db, _synth
    if _OFFLINE_DEMO:
        # Force the deterministic offline fixture even if .env has live creds,
        # so `CBOS_OFFLINE_DEMO=1 uvicorn ...` is a one-command clean demo.
        print("[INFO] CBOS_OFFLINE_DEMO=1 — serving bundled offline fixture.")
        _db = None
    else:
        try:
            _db = HydraClient.from_env()
            await _db.ensure_tenant()
        except Exception as exc:
            print(f"[WARN] HydraDB not available: {exc}. Running in offline mode.")
            _db = None
    # The synthesizer is the only OpenAI caller; it logs CostEvents to the graph.
    _synth = Synthesizer(_db)
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
        if _offline is not None:
            m = _offline.status_metrics(_chaos.get("tamper"))
            resp = StatusResponse(
                costSpent=m["costSpent"],
                costCap=_COST_CAP_USD,
                nodeCount=m["nodeCount"],
                repoCount=m["repoCount"],
                merkleOk=m["merkleOk"],
                merkleHead=m["merkleHead"],
            )
        else:
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
        if _offline is not None:
            return _offline.graph_snapshot(as_of or None)
        return {"nodes": [], "links": [], "timeRange": {"min": "", "max": ""}}
    return await _fetch_graph_snapshot(_db, as_of=as_of or None)


async def _gather_status(db: HydraClient):
    """Fetch all metrics concurrently."""
    import asyncio

    cost_task = asyncio.create_task(db.get_total_cost())
    count_task = asyncio.create_task(db.count_all_nodes())
    repo_task = asyncio.create_task(db.count_nodes_by_type("Repository"))
    merkle_task = asyncio.create_task(_merkle_state())

    cost, node_count, repo_count, merkle = await asyncio.gather(
        cost_task, count_task, repo_task, merkle_task
    )
    return cost, node_count, repo_count, merkle


async def _merkle_state() -> MerkleResult:
    """Merkle verification for /status and /verify, honoring an active tamper.

    With no tamper this is just `verify_chain`. With a tamper active we fetch
    the real chain, inject the corrupted hash into the targeted Episode, and run
    the SAME linkage algorithm — so the break the badge shows is detected by the
    production verifier, not faked with a flag.
    """
    if _db is None:
        if _offline is not None:
            return _offline.verify(_chaos.get("tamper"))
        return MerkleResult(ok=True, head_hash="", chain_length=0)
    tamper = _chaos.get("tamper")
    if not tamper:
        return await verify_chain(_db)
    episodes = await _db.get_episodes_ordered()
    view: list[dict] = []
    for ep in episodes:
        ep = dict(ep)
        if ep.get("id") == tamper["episode_id"]:
            ep["merkle_hash"] = tamper["corrupted_hash"]
        view.append(ep)
    result = evaluate_chain(view)
    await _db.update_merkle_head(result.head_hash, result.chain_length, result.ok)
    return result


# ---------------------------------------------------------------------------
# WebSocket — live graph feed
# ---------------------------------------------------------------------------

NODE_TYPE_SIZE = {
    "Repository": 20, "Commit": 8, "PR": 10, "Issue": 8,
    "File": 5, "Symbol": 4, "Decision": 12, "Person": 14,
    "Identity": 6, "Episode": 3, "ReviewComment": 5, "Discussion": 7,
}

async def _fetch_graph_snapshot(db: HydraClient, as_of: str | None = None) -> dict:
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
        if _offline is not None:
            return _offline.repos()
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
        if _offline is not None:
            return _offline.er_queue()
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

async def _synthesize(**kwargs) -> SynthesisResult:
    """Call the single synthesizer chokepoint, translating a hard-cap hit into
    an HTTP 402 so the cost discipline is visible at the API boundary."""
    if _synth is None:
        raise HTTPException(status_code=503, detail="Synthesizer not initialized")
    try:
        return await _synth.complete(**kwargs)
    except BudgetExceeded as exc:
        raise HTTPException(status_code=402, detail=str(exc))


def _artifact_url(repo: str, node_type: str, text: str) -> str:
    """Best-effort GitHub URL for a provenance artifact, so answers are
    clickable instead of unverifiable prose."""
    import re

    if not repo or "/" not in repo:
        return ""
    base = f"https://github.com/{repo}"
    t = (node_type or "").lower()
    s = text or ""
    if "pr" in t or "pull" in t:
        m = re.search(r"#?(\d+)", s)
        return f"{base}/pull/{m.group(1)}" if m else base
    if "issue" in t:
        m = re.search(r"#?(\d+)", s)
        return f"{base}/issues/{m.group(1)}" if m else base
    if "commit" in t:
        m = re.search(r"\b([0-9a-f]{7,40})\b", s)
        return f"{base}/commit/{m.group(1)}" if m else base
    return ""


async def _recall_context(query: str, max_results: int = 8) -> tuple[str, int, list[dict]]:
    """Semantic recall from HydraDB → (context_string, node_count, sources).

    `sources` is structured [{type, title}] for the recalled knowledge nodes,
    used to attach clickable citations to answers.
    """
    recall_result = await _db._client.recall.full_recall(
        tenant_id=_db.tenant_id,
        sub_tenant_id="default",
        query=query,
        max_results=max_results,
        graph_context=True,
    )
    items: list[str] = []
    structured: list[dict] = []
    sources = getattr(recall_result, "sources", None) or []
    chunks = getattr(recall_result, "chunks", None) or []
    for src in sources[:max_results]:
        title = getattr(src, "title", "") or ""
        am = getattr(src, "additional_metadata", {}) or {}
        ntype = am.get("node_type", "")
        items.append(f"[{title} | type={ntype}]")
        structured.append({"type": ntype, "title": title})
    for chunk in chunks[:max_results]:
        content = getattr(chunk, "chunk_content", "") or ""
        if content:
            items.append(content[:400])
    context = "\n\n".join(items) or "No relevant context found in the knowledge graph."
    return context, len(sources) + len(chunks), structured


@app.post("/resolve")
async def resolve_persons():
    """Persist Person nodes for auto-merged identity clusters (>1 identity),
    bridging identities across repos. Idempotent: dedupes by primary_email.
    Person→Identity edges then render in the graph as cross-repo bridges."""
    if _db is None:
        raise HTTPException(status_code=503, detail="HydraDB not connected")
    from graph.bitemporal import make_node
    from graph.resolve import resolve_identities
    from graph.schema import Person

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


@app.post("/extract-decisions")
async def extract_decisions(repo: str = "", limit: int = 5):
    """Mine architectural decisions from recent PRs (LLM via the synthesizer
    chokepoint) and persist Decision nodes linked to their PR. Makes the
    'why → Decision #X' provenance story real instead of manual-only."""
    if _db is None:
        raise HTTPException(status_code=503, detail="HydraDB not connected")
    import json as _json
    import os as _os

    from graph.bitemporal import make_node
    from graph.schema import Decision
    from ingester.github import GitHubIngester

    target = repo or _os.environ.get("DEMO_REPO", "tokio-rs/tokio")
    if "/" not in target:
        raise HTTPException(status_code=400, detail="repo must be owner/name")
    owner, name = target.split("/", 1)
    limit = max(1, min(limit, 10))

    # Map existing PR nodes by number so decisions can link to them.
    pr_nodes = await _db.list_nodes_by_type("PR")
    by_num = {str(p["dm"].get("pr_number", "")): p["id"] for p in pr_nodes if p["dm"].get("pr_number")}

    ingester = GitHubIngester.from_env(_db)
    chain = _ChainBuilder()
    await chain.init()
    created: list[dict] = []
    try:
        prs = await ingester.get_pulls(owner, name, limit)
        for pr in prs[:limit]:
            num = str(pr.get("number", ""))
            title = pr.get("title", "")
            body = (pr.get("body") or "")[:1500]
            res = await _synthesize(
                call_source="extract-decision",
                cache_key=f"{target}|pr{num}",
                max_tokens=300,
                response_format={"type": "json_object"},
                system=(
                    "Extract the single key architectural/design DECISION embodied by this PR. "
                    'Respond as JSON {"summary": "...", "rationale": "...", '
                    '"confidence": "low|medium|high"}. summary = one concise line; rationale = '
                    "the why. For trivial PRs (typo/docs/ci bump) use confidence \"low\"."
                ),
                user=f"PR #{num}: {title}\n\n{body}",
            )
            try:
                d = _json.loads(res.text or "{}")
            except Exception:
                d = {}
            summary = str(d.get("summary", "")).strip()
            if not summary:
                continue
            ep = await chain.next("decide")
            dec = make_node(
                Decision,
                episode_id=ep.id,
                source="extracted",
                summary=summary,
                rationale=str(d.get("rationale", "")),
                confidence=str(d.get("confidence", "medium")),
                actor="synthesizer",
                made_by_name=pr.get("user", {}).get("login", ""),
                decision_id=f"PR{num}",
            )
            rels = [by_num[num]] if num in by_num else None
            await _db.write_node(dec, relations=rels)
            created.append({
                "decision_id": f"PR{num}",
                "summary": summary,
                "confidence": dec.confidence,
                "linked_pr": num in by_num,
            })
    finally:
        await ingester.close()

    try:
        await _ws_manager.broadcast(await _fetch_graph_snapshot(_db))
    except Exception:
        pass
    return {"created": len(created), "decisions": created}


@app.get("/provenance")
async def provenance(file: str, line: int = 1, repo: str = ""):
    """The origin story: an ordered, cited provenance chain for code at
    file:line — commits → PRs → issues → decisions → people — assembled from
    graph recall, and accompanied by HydraDB's own verified graph edges."""
    if _db is None:
        raise HTTPException(status_code=503, detail="HydraDB not connected")
    import json as _json

    # 1. Locate the File node (for real, cited graph edges).
    verified_edges: list[dict] = []
    files = await _db.list_nodes_by_type("File")
    fid = ""
    for f in files:
        path = f["dm"].get("path", "") or f.get("title", "").replace("File:", "")
        if path == file or path.endswith(file) or f.get("title", "").endswith(file):
            fid = f["id"]
            break
    if fid:
        neigh = await _db.graph_neighbors(fid, limit=20)
        # Keep the most-confident, human-readable extracted relationships.
        neigh.sort(key=lambda n: n.get("confidence", 0.0), reverse=True)
        for n in neigh[:6]:
            if n.get("context"):
                verified_edges.append({
                    "predicate": n["predicate"],
                    "context": n["context"][:200],
                    "confidence": round(float(n.get("confidence", 0.0)), 2),
                })

    # 2. Recall the surrounding provenance context and assemble an ordered chain.
    scope = f"In {repo}, " if repo else ""
    query = f"{scope}the full history of {file}: commits, PRs, issues, decisions, and people behind it."
    context, ctx_count, _sources = await _recall_context(query, max_results=12)
    res = await _synthesize(
        call_source="provenance",
        cache_key=f"{repo}|{file}|{line}",
        max_tokens=500,
        response_format={"type": "json_object"},
        system=(
            "You are CodebaseOS. From the knowledge-graph context, reconstruct the ORIGIN STORY "
            "of the referenced code as an ordered provenance chain (earliest cause → latest). "
            "Each hop cites a real artifact. Respond as JSON: "
            '{"chain": [{"type": "Commit|PR|Issue|Decision|Person", "title": "...", '
            '"detail": "one sentence", "when": "date or \'\'"}]}. Up to 6 hops. '
            "Do not invent commit hashes or PR numbers not present in the context."
        ),
        user=f"Target: {file}:{line}\n\nKnowledge graph context:\n{context}",
    )
    try:
        parsed = _json.loads(res.text or "{}")
        chain_hops = parsed.get("chain", []) if isinstance(parsed, dict) else []
    except Exception:
        chain_hops = []
    chain_hops = [
        {
            "order": i + 1,
            "type": str(h.get("type", "")),
            "title": str(h.get("title", "")),
            "detail": str(h.get("detail", "")),
            "when": str(h.get("when", "")),
            # Clickable: link each hop to its GitHub artifact when derivable.
            "url": _artifact_url(repo, str(h.get("type", "")), str(h.get("title", ""))),
        }
        for i, h in enumerate(chain_hops[:6])
        if isinstance(h, dict)
    ]
    return {
        "file": file,
        "line": line,
        "chain": chain_hops,
        "verified_edges": verified_edges,
        "context_nodes": ctx_count,
        "cost_usd": round(res.cost_usd, 6),
        "cached": res.cached,
    }


@app.get("/bus-factor")
async def bus_factor(repo: str = "", top: int = 10):
    """Bus-factor / knowledge-risk: rank contributors by commit volume and
    report how few people hold >50% of the history. No LLM — pure graph counts."""
    if _db is None:
        raise HTTPException(status_code=503, detail="HydraDB not connected")
    from collections import Counter

    counts: Counter = Counter()
    for cm in await _db.list_nodes_by_type("Commit"):
        author = cm["dm"].get("author_name", "")
        if author:
            counts[author] += 1
    total = sum(counts.values())
    ranked = [{"name": n, "commits": k} for n, k in counts.most_common(max(1, min(top, 50)))]

    # Bus factor = smallest number of people covering >50% of commits.
    cum = 0
    bus = 0
    for _n, k in counts.most_common():
        cum += k
        bus += 1
        if total and cum * 2 >= total:
            break
    risk = "high" if bus <= 2 else ("medium" if bus <= 4 else "low")
    return {
        "repo": repo,
        "contributors": ranked,
        "total_commits": total,
        "unique_authors": len(counts),
        "bus_factor": bus,
        "risk": risk,
    }


@app.get("/decisions")
async def decisions(repo: str = ""):
    """List the architectural Decisions mined from the repo (headline feature).
    Each links back to the PR it was extracted from."""
    if _db is None:
        return {"decisions": []}
    import re

    out: list[dict] = []
    seen: set[str] = set()
    for d in await _db.list_nodes_by_type("Decision"):
        dm = d["dm"]
        did = dm.get("decision_id", "")
        summary = dm.get("summary", "") or d.get("title", "").replace("Decision:", "")
        if did in seen:
            continue
        seen.add(did)
        m = re.search(r"(\d+)", did)
        url = f"https://github.com/{repo}/pull/{m.group(1)}" if (repo and m) else ""
        out.append({
            "decision_id": did,
            "summary": summary,
            "confidence": dm.get("confidence", ""),
            "url": url,
        })
    return {"count": len(out), "decisions": out}


@app.get("/why")
async def why(file: str, line: int, repo: str = ""):
    """
    Explain why code at file:line exists — what commits, decisions, and PRs led to it.
    Uses HydraDB semantic recall + OpenAI to synthesize the answer.
    """
    if _db is None:
        if _offline is not None:
            return _offline.why(file, line)
        raise HTTPException(status_code=503, detail="HydraDB not connected")

    query = f"Why does the code in {file} at line {line} exist? What commits or decisions introduced it?"
    if repo:
        query = f"In repository {repo}, {query}"

    try:
        context, ctx_count, sources = await _recall_context(query)
        result = await _synthesize(
            call_source="why",
            cache_key=f"{repo}|{file}|{line}",
            max_tokens=400,
            system=(
                "You are CodebaseOS, a code provenance assistant. "
                "Given context from a codebase knowledge graph (commits, files, decisions), "
                "explain concisely WHY the referenced code exists. "
                "Focus on the intent, the problem it solves, and what changed. "
                "Be specific and cite commit messages or decisions when available. "
                "3-5 sentences max."
            ),
            user=f"Question: {query}\n\nContext from knowledge graph:\n{context}",
        )
        # Clickable citations: link recalled PR/Issue/Commit artifacts to GitHub.
        citations = []
        seen = set()
        for s in sources:
            t = s.get("type", "")
            title = s.get("title", "")
            if t not in ("PR", "Issue", "Commit"):
                continue
            url = _artifact_url(repo, t, title)
            if url and url not in seen:
                seen.add(url)
                citations.append({"type": t, "title": title, "url": url})
        return {
            "file": file,
            "line": line,
            "explanation": result.text or "No explanation generated.",
            "citations": citations[:6],
            "context_nodes": ctx_count,
            "cost_usd": round(result.cost_usd, 6),
            "cached": result.cached,
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
        if _offline is not None:
            return _offline.five_whys(file, line)
        raise HTTPException(status_code=503, detail="HydraDB not connected")
    import json as _json

    query = f"Why does the code in {file} at line {line} exist? Trace the root cause."
    if repo:
        query = f"In repository {repo}, {query}"

    try:
        context, ctx_count, _sources = await _recall_context(query, max_results=10)
        result = await _synthesize(
            call_source="five-whys",
            cache_key=f"{repo}|{file}|{line}",
            max_tokens=500,
            response_format={"type": "json_object"},
            system=(
                "You are CodebaseOS performing a '5 Whys' root-cause analysis on "
                "a piece of code, grounded in a codebase knowledge graph. Produce a "
                "causal chain of up to 5 levels, each level asking WHY the previous "
                "answer holds, drilling from the immediate code change toward the "
                "underlying intent or decision. Be specific; cite commits/PRs/decisions "
                "from the context when possible; do not invent hashes. "
                'Respond as JSON: {"chain": [{"question": "...", "answer": "..."}]}'
            ),
            user=f"Target: {query}\n\nKnowledge graph context:\n{context}",
        )
        try:
            parsed = _json.loads(result.text or "{}")
            chain = parsed.get("chain", []) if isinstance(parsed, dict) else []
        except Exception:
            chain = []
        chain = [
            {"level": i + 1, "question": str(step.get("question", "")), "answer": str(step.get("answer", ""))}
            for i, step in enumerate(chain[:5])
            if isinstance(step, dict)
        ]
        return {
            "file": file,
            "line": line,
            "chain": chain,
            "context_nodes": ctx_count,
            "cost_usd": round(result.cost_usd, 6),
            "cached": result.cached,
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
        if _offline is not None:
            return _offline.summary(file, line, symbol)
        raise HTTPException(status_code=503, detail="HydraDB not connected")

    target = f"the symbol '{symbol}' in {file}" if symbol else f"{file} at line {line}"
    scope = f"In repository {repo}, " if repo else ""
    query = f"{scope}what does {target} do? Its purpose and behavior."
    try:
        context, ctx_count, _sources = await _recall_context(query, max_results=6)
        result = await _synthesize(
            call_source="summary",
            cache_key=f"{repo}|{file}|{line}|{symbol}",
            max_tokens=250,
            system=(
                "You are CodebaseOS. Summarize WHAT the referenced code does — its "
                "purpose and behavior — concisely (2-3 sentences). Use the knowledge "
                "graph context if helpful. Do not invent commit hashes."
            ),
            user=f"Target: {query}\n\nContext:\n{context}",
        )
        return {
            "file": file,
            "line": line,
            "symbol": symbol,
            "summary": result.text or "No summary generated.",
            "context_nodes": ctx_count,
            "cost_usd": round(result.cost_usd, 6),
            "cached": result.cached,
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
        if _offline is not None:
            return _offline.counterfactual(decision)
        raise HTTPException(status_code=503, detail="HydraDB not connected")

    query = f"What commits, PRs, files, and decisions relate to: {decision}?"
    try:
        context, ctx_count, _sources = await _recall_context(query, max_results=10)
        result = await _synthesize(
            call_source="counterfactual",
            cache_key=decision,
            max_tokens=500,
            system=(
                "You are CodebaseOS reasoning about a counterfactual: what would "
                "likely happen if the described decision or change were reversed or "
                "never made. Use the codebase knowledge-graph context to ground your "
                "reasoning in real commits/PRs/files. Cover: (1) what code/behavior "
                "would differ, (2) which downstream files or PRs would be affected, "
                "(3) risks or regressions. Be concrete; do not invent hashes. "
                "4-6 sentences."
            ),
            user=f"Decision/change to reverse: {decision}\n\nKnowledge graph context:\n{context}",
        )
        return {
            "decision": decision,
            "analysis": result.text or "No analysis generated.",
            "context_nodes": ctx_count,
            "cost_usd": round(result.cost_usd, 6),
            "cached": result.cached,
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
        if _offline is not None:
            return _offline.handoff(module)
        raise HTTPException(status_code=503, detail="HydraDB not connected")
    import json as _json

    scope = f"in repository {repo}, " if repo else ""
    query = (
        f"{scope}everything about the module '{module}': its files, the commits and PRs that "
        f"shaped it, the people who worked on it, and any decisions behind it."
    )
    try:
        context, ctx_count, _sources = await _recall_context(query, max_results=14)
        result = await _synthesize(
            call_source="handoff",
            cache_key=f"{repo}|{module}",
            max_tokens=500,
            response_format={"type": "json_object"},
            system=(
                "You are CodebaseOS generating a developer ONBOARDING TOUR for a module, "
                "grounded in a codebase knowledge graph. Produce a concise, practical tour "
                "for someone new to this module. Cite real files/commits/PRs/people from the "
                "context; do not invent hashes. Respond as JSON: "
                '{"overview": "...", "start_here": "...", '
                '"key_files": ["..."], "key_people": ["..."], "key_decisions": ["..."]}'
            ),
            user=f"Module: {module}\n\nKnowledge graph context:\n{context}",
        )
        try:
            tour = _json.loads(result.text or "{}")
            if not isinstance(tour, dict):
                tour = {}
        except Exception:
            tour = {}
        return {
            "module": module,
            "overview": str(tour.get("overview", "")),
            "start_here": str(tour.get("start_here", "")),
            "key_files": [str(x) for x in (tour.get("key_files") or [])][:8],
            "key_people": [str(x) for x in (tour.get("key_people") or [])][:8],
            "key_decisions": [str(x) for x in (tour.get("key_decisions") or [])][:8],
            "context_nodes": ctx_count,
            "cost_usd": round(result.cost_usd, 6),
            "cached": result.cached,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/explain-file")
async def explain_file(file: str, repo: str = ""):
    """Plain-English overview of an entire FILE: what it does, who owns it, key
    points, and the decisions that shaped it. The fastest 'understand this code'
    surface for a developer new to a file."""
    if _db is None:
        # Offline demo: a deterministic canned explainer (no creds needed).
        return {
            "file": file,
            "summary": f"{file} is part of the demo fixture. Ingest a real repo for a live explanation.",
            "owner": "",
            "key_points": [],
            "key_decisions": [],
            "context_nodes": 0,
            "cost_usd": 0.0,
            "cached": True,
        }
    import json as _json

    scope = f"in {repo}, " if repo else ""
    query = (
        f"{scope}what does the file {file} do, who works on it most, and what "
        f"commits, PRs, or decisions shaped it?"
    )
    try:
        context, ctx_count, _sources = await _recall_context(query, max_results=12)
        result = await _synthesize(
            call_source="explain-file",
            cache_key=f"{repo}|{file}",
            max_tokens=450,
            response_format={"type": "json_object"},
            system=(
                "You are CodebaseOS. Explain an entire FILE for a developer seeing it for the "
                "first time, grounded in the knowledge-graph context. Respond as JSON: "
                '{"summary": "what the file does, 2-3 sentences", '
                '"owner": "the person who most works on it, or \'\'", '
                '"key_points": ["..."], "key_decisions": ["..."]}. '
                "Cite real people/PRs/commits from the context; do not invent."
            ),
            user=f"File: {file}\n\nKnowledge graph context:\n{context}",
        )
        try:
            d = _json.loads(result.text or "{}")
            if not isinstance(d, dict):
                d = {}
        except Exception:
            d = {}
        return {
            "file": file,
            "summary": str(d.get("summary", "")),
            "owner": str(d.get("owner", "")),
            "key_points": [str(x) for x in (d.get("key_points") or [])][:6],
            "key_decisions": [str(x) for x in (d.get("key_decisions") or [])][:6],
            "context_nodes": ctx_count,
            "cost_usd": round(result.cost_usd, 6),
            "cached": result.cached,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/diff")
async def diff(repo: str = "", since: str = "", until: str = "", file: str = ""):
    """What changed in a time window (bi-temporal): commits, PRs, and issues
    whose valid_time falls in [since, until]. Optional `file` narrows by title.
    No LLM — pure graph counts, so it's free and instant."""
    if _db is None:
        return {"since": since, "until": until, "changes": [], "count": 0}
    # ISO-8601 sorts lexicographically; open-ended bounds when blank.
    lo = since or "0000"
    hi = until or "9999"
    needle = (file.rsplit("/", 1)[-1] or "").lower()
    changes: list[dict] = []
    for ntype in ("Commit", "PR", "Issue"):
        for n in await _db.list_nodes_by_type(ntype):
            dm = n["dm"]
            vt = dm.get("valid_time", "") or dm.get("tx_time", "")
            if not vt or vt < lo or vt > hi:
                continue
            title = n.get("title", "")
            if needle and needle not in title.lower():
                continue
            changes.append({"type": ntype, "title": title, "when": vt})
    changes.sort(key=lambda c: c["when"])
    return {
        "repo": repo,
        "since": since,
        "until": until,
        "file": file,
        "count": len(changes),
        "changes": changes[:50],
    }


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
class _ChainBuilder:
    """Appends Episodes via the authoritative local chain pointer
    (graph/chain.py): each slot is claimed under a file lock with the merkle
    hash computed locally, so HydraDB indexing lag can never fork the chain —
    and the CLI shares the same pointer file."""

    async def init(self) -> None:
        await chainstate.ensure_bootstrapped(_db)

    async def next(self, action_type: str):
        return await chainstate.next_episode(_db, action_type)


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
    if _db is None and _offline is not None and not _firehose:
        return {"events": _offline.events()["events"][:limit]}
    return {"events": list(_firehose)[:limit]}


@app.post("/chain/resync")
async def chain_resync(rebuild: bool = False):
    """Re-bootstrap the local chain pointer from HydraDB.

    The CLI and backend share the pointer file, so a resync is normally
    unnecessary. Pass rebuild=true to discard the pointer and reseed it from a
    settled HydraDB read (e.g. after manually editing the store)."""
    if rebuild:
        chainstate.reset()
    if _db is not None:
        await chainstate.ensure_bootstrapped(_db)
    return {"ok": True}


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
    if _db is None and _offline is None:
        return {"ok": True, "chain_length": 0, "head_hash": ""}
    result = await _merkle_state()
    return {
        "ok": result.ok,
        "chain_length": result.chain_length,
        "head_hash": result.head_hash,
        "broken_at": result.broken_at,
        "tampered": bool(_chaos.get("tamper")),
    }


# ---------------------------------------------------------------------------
# Chaos layer (CODEBASEOS_SPEC §10) — live fault injection for the demo
# ---------------------------------------------------------------------------

@app.get("/chaos/state")
async def chaos_state():
    """Current chaos state for the dashboard (active tamper + nuclear author)."""
    return {"tamper": _chaos.get("tamper"), "nuclear": _chaos.get("nuclear")}


@app.post("/chaos/tamper")
async def chaos_tamper():
    """Inject a single corrupted hash into the Merkle chain.

    Picks a real Episode that has a successor and corrupts its stored
    merkle_hash in the verification view. The next Episode's prev_hash no longer
    matches, so /verify and /status report the chain broken (badge turns red)
    until /chaos/restore. One altered hash → tamper detected: that is the pitch.
    """
    if _db is None:
        if _offline is not None:
            _chaos["tamper"] = _offline.tamper_target()
            _bust_status_cache()
            result = await _merkle_state()
            return {
                "tampered": _chaos["tamper"],
                "merkleOk": result.ok,
                "broken_at": result.broken_at,
                "chain_length": result.chain_length,
            }
        raise HTTPException(status_code=503, detail="HydraDB not connected")
    episodes = await _db.get_episodes_ordered()
    if len(episodes) < 2:
        raise HTTPException(
            status_code=409,
            detail="Need at least 2 episodes to demonstrate a chain break — ingest more first.",
        )
    idx = len(episodes) // 2
    if idx >= len(episodes) - 1:
        idx = len(episodes) - 2
    target = episodes[idx]
    original = target.get("merkle_hash", "") or ""
    corrupted = ("deadbeef" + original[8:]) if len(original) > 8 else "deadbeefcafebabe"
    _chaos["tamper"] = {
        "episode_id": target.get("id", ""),
        "sequence_no": target.get("sequence_no", 0),
        "action_type": target.get("action_type", ""),
        "original_hash": original,
        "corrupted_hash": corrupted,
    }
    _bust_status_cache()
    result = await _merkle_state()
    return {
        "tampered": _chaos["tamper"],
        "merkleOk": result.ok,
        "broken_at": result.broken_at,
        "chain_length": result.chain_length,
    }


@app.post("/chaos/restore")
async def chaos_restore():
    """Clear the tamper. The chain re-verifies clean and the badge goes green."""
    _chaos["tamper"] = None
    _bust_status_cache()
    result = await _merkle_state()
    return {
        "merkleOk": result.ok,
        "chain_length": result.chain_length,
        "head_hash": result.head_hash,
    }


@app.post("/chaos/nuclear")
async def chaos_nuclear(person: str = ""):
    """"Author goes nuclear": mark a contributor as having left the company.

    Their authored nodes (commits, PRs, review comments) become orphaned, and
    the system suggests reviewers from the most active remaining contributors.
    If `person` is omitted, the most prolific author is chosen automatically.
    """
    if _db is None:
        if _offline is not None:
            _chaos["nuclear"] = _offline.nuclear(person)
            _bust_status_cache()
            return _chaos["nuclear"]
        raise HTTPException(status_code=503, detail="HydraDB not connected")

    commits = await _db.list_nodes_by_type("Commit")
    prs = await _db.list_nodes_by_type("PR")
    reviews = await _db.list_nodes_by_type("ReviewComment")
    buckets = (("Commit", commits), ("PR", prs), ("ReviewComment", reviews))

    def author_of(node: dict) -> str:
        return (node.get("dm", {}).get("author_name") or "").strip()

    counts: dict[str, int] = {}
    for _label, nodes in buckets:
        for n in nodes:
            a = author_of(n)
            if a:
                counts[a] = counts.get(a, 0) + 1
    if not counts:
        raise HTTPException(
            status_code=409,
            detail="No authored nodes found — ingest commits/PRs first.",
        )

    target = person or max(counts, key=lambda k: counts[k])
    target_l = target.lower()

    orphaned_ids: list[str] = []
    by_type: dict[str, int] = {}
    for label, nodes in buckets:
        for n in nodes:
            if author_of(n).lower() == target_l:
                nid = n.get("id", "")
                if nid:
                    orphaned_ids.append(nid)
                    by_type[label] = by_type.get(label, 0) + 1

    reviewers = sorted(
        ((a, c) for a, c in counts.items() if a.lower() != target_l),
        key=lambda x: -x[1],
    )[:3]

    _chaos["nuclear"] = {
        "person": target,
        "orphaned_count": len(orphaned_ids),
        "orphaned_ids": orphaned_ids,
        "by_type": by_type,
        "suggested_reviewers": [{"name": a, "activity": c} for a, c in reviewers],
    }
    _bust_status_cache()
    return _chaos["nuclear"]


@app.post("/chaos/revive")
async def chaos_revive():
    """Clear the nuclear-author state; orphaned nodes return to normal."""
    _chaos["nuclear"] = None
    _bust_status_cache()
    return {"revived": True}


@app.get("/baseline-rag")
async def baseline_rag(file: str, line: int, repo: str = ""):
    """"Without HydraDB" baseline: answer the same /why question using ONLY the
    LLM, with no knowledge-graph retrieval and no provenance. Demonstrates the
    value of the graph by contrast — this path cannot cite commits or decisions.
    """
    if _db is None:
        if _offline is not None:
            return _offline.baseline_rag(file, line)
        raise HTTPException(status_code=503, detail="HydraDB not connected")

    query = f"Why does the code in {file} at line {line} exist? What commits or decisions introduced it?"
    if repo:
        query = f"In repository {repo}, {query}"

    try:
        result = await _synthesize(
            call_source="baseline-rag",
            cache_key=f"{repo}|{file}|{line}",
            max_tokens=400,
            system=(
                "You are a plain code assistant with NO access to the "
                "repository history, commits, PRs, or decisions — only the "
                "file path and line number the user mentions. Answer the "
                "question as best you can from general knowledge. Do not "
                "invent specific commit hashes, PR numbers, or authors. "
                "3-5 sentences max."
            ),
            user=query,
        )
        return {
            "file": file,
            "line": line,
            "explanation": result.text or "No explanation generated.",
            "context_nodes": 0,
            "cost_usd": round(result.cost_usd, 6),
            "cached": result.cached,
            "mode": "baseline-no-graph",
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
