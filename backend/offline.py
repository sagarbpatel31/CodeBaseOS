"""
Offline demo fixture for CodebaseOS.

Activated by `CBOS_OFFLINE_DEMO=1` when no HydraDB connection is available, this
serves a small, deterministic, in-memory graph so the dashboard and the chaos
layer render on any laptop with zero credentials — a demo safety net.

Design notes:
  - Depends only on stdlib + the PURE graph helpers (graph.merkle, graph.resolve).
    It never touches HydraDB, OpenAI, or pydantic, so it always imports.
  - The Episode chain is built with the REAL canonical hashing, so /verify runs
    the production `evaluate_chain` over it and chaos/tamper is honestly detected.
"""

from __future__ import annotations

import hashlib
from typing import Any, Optional

from graph.merkle import MerkleResult, _episode_canonical, evaluate_chain
from graph.resolve import resolve_identities

# Node visual sizes mirror backend.api.NODE_TYPE_SIZE.
_SIZE = {
    "Repository": 20, "Commit": 8, "PR": 10, "Issue": 8,
    "File": 5, "Symbol": 4, "Decision": 12, "Person": 14,
    "Identity": 6, "Episode": 3, "ReviewComment": 5, "Discussion": 7,
}


def _chain(actions: list[str]) -> list[dict]:
    """Build a valid Merkle episode chain (correct prev/merkle hashes)."""
    eps: list[dict] = []
    prev = ""
    for i, action in enumerate(actions):
        h = hashlib.sha256(
            _episode_canonical(seq=i, action_type=action, inputs_hash="", outputs_hash="", prev_hash=prev)
        ).hexdigest()
        eps.append({
            "id": f"ep-{i}",
            "sequence_no": i,
            "action_type": action,
            "prev_hash": prev,
            "merkle_hash": h,
            "valid_time": _EPISODE_TIMES[i] if i < len(_EPISODE_TIMES) else "2024-01-01T00:00:00+00:00",
        })
        prev = h
    return eps


_EPISODE_TIMES = [
    "2023-03-01T09:00:00+00:00",
    "2023-03-14T11:20:00+00:00",
    "2023-05-09T16:45:00+00:00",
    "2023-07-22T13:10:00+00:00",
    "2023-09-30T08:05:00+00:00",
    "2023-11-11T19:30:00+00:00",
    "2024-01-18T10:15:00+00:00",
    "2024-02-02T12:00:00+00:00",
]


class OfflineStore:
    """Holds the fixture and shapes responses to match the live endpoints."""

    def __init__(self) -> None:
        self.episodes = _chain([
            "ingest_repo", "ingest_commit", "ingest_commit", "ingest_pr",
            "ingest_issue", "ingest_repo", "ingest_commit", "entity_resolve",
        ])

        # (id, type, label, repo_id, valid_time, author_name)
        self._nodes_raw: list[tuple[str, str, str, str, str, str]] = [
            ("repo-tokio", "Repository", "Repository:tokio-rs/tokio", "", "2023-03-01T09:00:00+00:00", ""),
            ("repo-bytes", "Repository", "Repository:tokio-rs/bytes", "", "2023-11-11T19:30:00+00:00", ""),
            ("c1", "Commit", "Commit:a1b2c3d4e5f6", "repo-tokio", "2023-03-14T11:20:00+00:00", "Alice Ryhl"),
            ("c2", "Commit", "Commit:b2c3d4e5f6a1", "repo-tokio", "2023-05-09T16:45:00+00:00", "Carl Lerche"),
            ("c3", "Commit", "Commit:c3d4e5f6a1b2", "repo-tokio", "2023-09-30T08:05:00+00:00", "Alice Ryhl"),
            ("c4", "Commit", "Commit:d4e5f6a1b2c3", "repo-bytes", "2024-01-18T10:15:00+00:00", "Alice Ryhl"),
            ("f1", "File", "File:src/runtime/task/mod.rs", "repo-tokio", "2023-03-14T11:20:00+00:00", ""),
            ("f2", "File", "File:src/net/tcp/stream.rs", "repo-tokio", "2023-05-09T16:45:00+00:00", ""),
            ("f3", "File", "File:src/sync/mutex.rs", "repo-tokio", "2023-09-30T08:05:00+00:00", ""),
            ("f4", "File", "File:src/bytes_mut.rs", "repo-bytes", "2024-01-18T10:15:00+00:00", ""),
            ("pr1", "PR", "PR:#5821 Replace session affinity with JWT", "repo-tokio", "2023-07-22T13:10:00+00:00", "Alice Ryhl"),
            ("pr2", "PR", "PR:#6033 Refactor task scheduler", "repo-tokio", "2023-09-30T08:05:00+00:00", "Carl Lerche"),
            ("pr3", "PR", "PR:#412 Zero-copy buffer split", "repo-bytes", "2024-01-18T10:15:00+00:00", "Alice Ryhl"),
            ("iss1", "Issue", "Issue:#5644 Session affinity breaks on failover", "repo-tokio", "2023-07-01T10:00:00+00:00", "Eliza Weisman"),
            ("iss2", "Issue", "Issue:#398 BytesMut reallocs under load", "repo-bytes", "2023-12-20T14:00:00+00:00", "Carl Lerche"),
            ("p-alice", "Person", "Person:Alice Ryhl", "", "2024-02-02T12:00:00+00:00", ""),
            ("p-carl", "Person", "Person:Carl Lerche", "", "2024-02-02T12:00:00+00:00", ""),
            ("id-alice-gh", "Identity", "Identity:Darksonn", "", "2023-03-14T11:20:00+00:00", ""),
            ("id-alice-git", "Identity", "Identity:Alice Ryhl", "", "2023-03-14T11:20:00+00:00", ""),
            ("id-carl-gh", "Identity", "Identity:carllerche", "", "2023-05-09T16:45:00+00:00", ""),
            ("id-carl-git", "Identity", "Identity:Carl Lerche", "", "2023-05-09T16:45:00+00:00", ""),
            ("id-mattia-git", "Identity", "Identity:Mattia Pitossi", "", "2023-09-30T08:05:00+00:00", ""),
            ("id-mattia-gh", "Identity", "Identity:mattiapitossi", "", "2023-09-30T08:05:00+00:00", ""),
        ]

        # Identity dicts for entity resolution (matches graph.resolve input shape).
        self._identities = [
            {"id": "id-alice-gh", "dm": {"username": "Darksonn", "email": "alice@example.com", "platform": "github", "platform_user_id": "1001"}},
            {"id": "id-alice-git", "dm": {"username": "Alice Ryhl", "email": "alice@example.com", "platform": "git", "platform_user_id": ""}},
            {"id": "id-carl-gh", "dm": {"username": "carllerche", "email": "carl@example.com", "platform": "github", "platform_user_id": "1002"}},
            {"id": "id-carl-git", "dm": {"username": "Carl Lerche", "email": "carl@example.com", "platform": "git", "platform_user_id": ""}},
            {"id": "id-mattia-git", "dm": {"username": "Mattia Pitossi", "email": "mattia@example.com", "platform": "git", "platform_user_id": ""}},
            {"id": "id-mattia-gh", "dm": {"username": "mattiapitossi", "email": "m.pitossi@corp.com", "platform": "github", "platform_user_id": "1003"}},
        ]

        self._events = [
            {"ts": 1706800000.0, "kind": "commit", "title": "fix: zero-copy buffer split", "author": "Alice Ryhl", "merkle": self.episodes[6]["merkle_hash"][:12]},
            {"ts": 1706700000.0, "kind": "pr", "title": "#412 Zero-copy buffer split", "author": "Alice Ryhl", "state": "merged"},
            {"ts": 1706600000.0, "kind": "issue", "title": "#398 BytesMut reallocs under load", "author": "Carl Lerche", "state": "open"},
        ]

    # ------------------------------------------------------------------ graph
    def graph_snapshot(self, as_of: Optional[str] = None) -> dict:
        node_ids = {n[0] for n in self._nodes_raw}
        times = [n[4] for n in self._nodes_raw if n[4]] + [e["valid_time"] for e in self.episodes]
        t_min, t_max = (min(times), max(times)) if times else ("", "")

        def valid(vt: str) -> bool:
            return not (as_of and vt and vt > as_of)

        nodes: list[dict] = []
        present: set[str] = set()
        for nid, ntype, label, _repo, vt, _author in self._nodes_raw:
            if not valid(vt):
                continue
            present.add(nid)
            nodes.append({"id": nid, "nodeType": ntype, "label": label, "val": _SIZE.get(ntype, 5)})
        for ep in self.episodes:
            if not valid(ep["valid_time"]):
                continue
            present.add(ep["id"])
            nodes.append({
                "id": ep["id"], "nodeType": "Episode",
                "label": f"Episode:{ep['sequence_no']}:{ep['action_type']}", "val": _SIZE["Episode"],
            })

        links: list[dict] = []

        def add(src: str, tgt: str, label: str) -> None:
            if src in present and tgt in present:
                links.append({"source": src, "target": tgt, "label": label})

        for nid, ntype, _label, repo, _vt, _author in self._nodes_raw:
            if repo:
                add(nid, repo, "in_repo")
        add("p-alice", "id-alice-gh", "is")
        add("p-alice", "id-alice-git", "is")
        add("p-carl", "id-carl-gh", "is")
        add("p-carl", "id-carl-git", "is")
        for i in range(1, len(self.episodes)):
            add(self.episodes[i]["id"], self.episodes[i - 1]["id"], "prev")

        return {"nodes": nodes, "links": links, "timeRange": {"min": t_min, "max": t_max}}

    # ----------------------------------------------------------------- status
    def verify(self, tamper: Optional[dict]) -> MerkleResult:
        view = []
        for ep in self.episodes:
            ep = dict(ep)
            if tamper and ep["id"] == tamper.get("episode_id"):
                ep["merkle_hash"] = tamper["corrupted_hash"]
            view.append(ep)
        return evaluate_chain(view)

    def status_metrics(self, tamper: Optional[dict]) -> dict:
        merkle = self.verify(tamper)
        node_count = len(self._nodes_raw) + len(self.episodes)
        return {
            "costSpent": 0.0,
            "nodeCount": node_count,
            "repoCount": sum(1 for n in self._nodes_raw if n[1] == "Repository"),
            "merkleOk": merkle.ok,
            "merkleHead": merkle.head_hash or "",
        }

    # ------------------------------------------------------------------ rails
    def repos(self) -> dict:
        out = []
        for nid, ntype, label, _repo, vt, _author in self._nodes_raw:
            if ntype == "Repository":
                out.append({"id": nid, "name": label.split(":", 1)[1], "defaultBranch": "master", "txTime": vt})
        return {"repos": out}

    def er_queue(self) -> dict:
        result = resolve_identities(self._identities)
        result["clusters"].sort(key=lambda c: len(c["identity_ids"]), reverse=True)
        return result

    def events(self) -> dict:
        return {"events": self._events}

    # ------------------------------------------------------------------ chaos
    def tamper_target(self) -> dict:
        idx = len(self.episodes) // 2
        if idx >= len(self.episodes) - 1:
            idx = len(self.episodes) - 2
        target = self.episodes[idx]
        original = target["merkle_hash"]
        corrupted = "deadbeef" + original[8:]
        return {
            "episode_id": target["id"],
            "sequence_no": target["sequence_no"],
            "action_type": target["action_type"],
            "original_hash": original,
            "corrupted_hash": corrupted,
        }

    def nuclear(self, person: str = "") -> dict:
        authored: list[tuple[str, str]] = [
            (nid, author) for nid, ntype, _l, _r, _vt, author in self._nodes_raw
            if author and ntype in ("Commit", "PR")
        ]
        counts: dict[str, int] = {}
        for _nid, author in authored:
            counts[author] = counts.get(author, 0) + 1
        target = person or max(counts, key=lambda k: counts[k])
        target_l = target.lower()

        orphaned_ids: list[str] = []
        by_type: dict[str, int] = {}
        for nid, ntype, _l, _r, _vt, author in self._nodes_raw:
            if ntype in ("Commit", "PR") and author.lower() == target_l:
                orphaned_ids.append(nid)
                by_type[ntype] = by_type.get(ntype, 0) + 1
        reviewers = sorted(
            ((a, c) for a, c in counts.items() if a.lower() != target_l), key=lambda x: -x[1]
        )[:3]
        return {
            "person": target,
            "orphaned_count": len(orphaned_ids),
            "orphaned_ids": orphaned_ids,
            "by_type": by_type,
            "suggested_reviewers": [{"name": a, "activity": c} for a, c in reviewers],
        }

    # -------------------------------------------------------------- synthesis
    def why(self, file: str, line: int) -> dict:
        return {
            "file": file, "line": line,
            "explanation": (
                f"[offline demo] {file} traces to PR #5821 ('Replace session affinity "
                "with JWT'), which closed Issue #5644 after a region-failover incident. "
                "Authored by Alice Ryhl; superseded the earlier OAuth-session approach."
            ),
            "context_nodes": 7, "cost_usd": 0.0, "cached": False,
        }

    def summary(self, file: str, line: int, symbol: str = "") -> dict:
        target = symbol or file
        return {
            "file": file, "line": line, "symbol": symbol,
            "summary": f"[offline demo] {target} implements the core path described in its module's PRs.",
            "context_nodes": 5, "cost_usd": 0.0, "cached": False,
        }
