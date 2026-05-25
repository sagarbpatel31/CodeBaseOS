#!/usr/bin/env python3
"""
provenance — runnable example (no credentials required).

Demonstrates the two standout primitives of the engine entirely in-memory:

  1. A tamper-evident Merkle chain over ingestion Episodes.
  2. Cross-platform contributor identity resolution.

Run:  python -m provenance.example
"""

from __future__ import annotations

from uuid import uuid4

from provenance import (
    Episode,
    evaluate_chain,
    extend_chain,
    make_node,
    resolve_identities,
)


def demo_merkle() -> None:
    print("1. Merkle chain over ingestion Episodes")
    actions = ["ingest_repo", "ingest_commit", "ingest_commit", "ingest_pr"]
    episodes = []
    prev = ""
    for i, action in enumerate(actions):
        ep = make_node(
            Episode, episode_id=uuid4(), source="github",
            sequence_no=i, action_type=action,
        )
        ep = extend_chain(ep, prev_hash=prev)
        episodes.append(ep)
        prev = ep.merkle_hash

    rows = [
        {"sequence_no": e.sequence_no, "merkle_hash": e.merkle_hash, "prev_hash": e.prev_hash}
        for e in episodes
    ]
    intact = evaluate_chain(rows)
    print(f"   chain length {intact.chain_length} → ok={intact.ok}  head={intact.head_hash[:12]}…")

    # Tamper with a single hash — the same verifier detects it.
    rows[1]["merkle_hash"] = "deadbeef" + rows[1]["merkle_hash"][8:]
    broken = evaluate_chain(rows)
    print(f"   after 1 altered hash → ok={broken.ok}  broken_at={broken.broken_at}")
    assert intact.ok and not broken.ok


def demo_resolution() -> None:
    print("\n2. Cross-platform identity resolution")
    identities = [
        {"id": "a", "dm": {"username": "Darksonn", "email": "alice@x.com", "platform": "github", "platform_user_id": "1"}},
        {"id": "b", "dm": {"username": "Alice Ryhl", "email": "alice@x.com", "platform": "git", "platform_user_id": ""}},
        {"id": "c", "dm": {"username": "Mattia Pitossi", "email": "m@y.com", "platform": "git", "platform_user_id": ""}},
        {"id": "d", "dm": {"username": "mattiapitossi", "email": "m@corp.com", "platform": "github", "platform_user_id": "2"}},
    ]
    result = resolve_identities(identities)
    s = result["stats"]
    print(f"   {s['identities']} identities → {s['people']} people "
          f"({s['auto_merged']} auto-merged, {s['pending']} pending review)")
    for c in result["clusters"]:
        if len(c["identity_ids"]) > 1:
            print(f"   merged: {c['person_name']} <{c['primary_email']}> ×{len(c['identity_ids'])}")
    for p in result["pending"]:
        print(f"   review: {p['a']['person_name']} ≟ {p['b']['person_name']} ({p['reason']})")


if __name__ == "__main__":
    demo_merkle()
    demo_resolution()
    print("\n✓ provenance engine works with zero credentials.")
