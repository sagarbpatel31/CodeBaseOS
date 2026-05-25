"""
Authoritative Merkle-chain tail pointer.

Problem: HydraDB indexing lags writes, so reading the chain tail back from it
to compute the next episode's prev_hash is racy — two episodes can read the
same stale tail and fork the chain.

Fix: keep the tail (seq + head_hash) in a local, lock-protected JSON file. Each
new episode atomically claims the next slot under a file lock and computes its
merkle_hash LOCALLY (via extend_chain) before the DB write. HydraDB is then
pure storage — never consulted for ordering — so forks are impossible.

Single-host assumption (CLI + backend on one machine share the file). The file
is bootstrapped once from a settled HydraDB read if it doesn't exist yet, so an
existing chain is picked up correctly.
"""

from __future__ import annotations

import fcntl
import json
import os
from uuid import uuid4

from graph.bitemporal import make_node, utc_now
from graph.merkle import extend_chain
from graph.schema import Episode

_DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".chain_state.json")


def _state_path() -> str:
    return os.environ.get("CBOS_CHAIN_STATE") or _DEFAULT_PATH


def _has_state() -> bool:
    p = _state_path()
    return os.path.exists(p) and os.path.getsize(p) > 0


async def ensure_bootstrapped(db) -> None:
    """Seed the local tail file from a settled HydraDB read, once.

    No-op if the file already exists. Safe to call before every ingest.
    """
    if _has_state():
        return
    head, seq = await db.get_chain_tail_settled()
    # Write under lock so two cold starts don't both seed.
    with open(_state_path(), "a+") as fd:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            fd.seek(0)
            raw = fd.read().strip()
            if not raw:  # still empty — we win the bootstrap
                fd.seek(0)
                fd.truncate()
                json.dump({"seq": seq, "head_hash": head}, fd)
                fd.flush()
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)


def reset(seq: int = 0, head_hash: str = "") -> None:
    """Reset the tail pointer (used after a wipe before a fresh ingest)."""
    with open(_state_path(), "w") as fd:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            json.dump({"seq": seq, "head_hash": head_hash}, fd)
            fd.flush()
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)


def reserve(action_type: str, source: str = "github") -> Episode:
    """Atomically claim the next chain slot and return a fully-linked Episode.

    Fully synchronous + file-locked: no await between read and write of the
    pointer, so concurrent writers (CLI + backend) can never share a prev_hash.
    The caller persists the returned Episode to the DB afterward; ordering is
    already fixed locally so the DB write can lag freely.
    """
    path = _state_path()
    with open(path, "a+") as fd:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            fd.seek(0)
            raw = fd.read().strip()
            state = json.loads(raw) if raw else {"seq": 0, "head_hash": ""}
            seq = int(state.get("seq", 0))
            prev = state.get("head_hash", "")

            ep = make_node(
                Episode,
                episode_id=uuid4(),
                source=source,
                sequence_no=seq,
                action_type=action_type,
                valid_time=utc_now(),
            )
            ep = extend_chain(ep, prev_hash=prev)

            fd.seek(0)
            fd.truncate()
            json.dump({"seq": seq + 1, "head_hash": ep.merkle_hash}, fd)
            fd.flush()
            return ep
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)


async def next_episode(db, action_type: str, source: str = "github") -> Episode:
    """Bootstrap if needed, reserve a slot locally, persist to the DB."""
    await ensure_bootstrapped(db)
    ep = reserve(action_type, source=source)
    await db.write_node(ep)
    return ep
