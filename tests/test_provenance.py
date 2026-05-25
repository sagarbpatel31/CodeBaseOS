"""
provenance spinoff tests — the public primitives work with no credentials and
without the hydra_db SDK installed.
"""

from __future__ import annotations

from uuid import uuid4

import provenance


def _build_chain(actions):
    eps, prev = [], ""
    for i, action in enumerate(actions):
        ep = provenance.extend_chain(
            provenance.make_node(
                provenance.Episode, episode_id=uuid4(), source="github",
                sequence_no=i, action_type=action,
            ),
            prev_hash=prev,
        )
        eps.append(ep)
        prev = ep.merkle_hash
    return [
        {"sequence_no": e.sequence_no, "merkle_hash": e.merkle_hash, "prev_hash": e.prev_hash}
        for e in eps
    ]


def test_merkle_chain_is_tamper_evident():
    rows = _build_chain(["ingest_repo", "ingest_commit", "ingest_pr"])
    assert provenance.evaluate_chain(rows).ok

    rows[1]["merkle_hash"] = "deadbeef" + rows[1]["merkle_hash"][8:]
    broken = provenance.evaluate_chain(rows)
    assert broken.ok is False and broken.broken_at is not None


def test_identity_resolution_exposed():
    identities = [
        {"id": "a", "dm": {"username": "Darksonn", "email": "x@y.com", "platform": "github", "platform_user_id": "1"}},
        {"id": "b", "dm": {"username": "Alice", "email": "x@y.com", "platform": "git", "platform_user_id": ""}},
    ]
    result = provenance.resolve_identities(identities)
    assert result["stats"]["auto_merged"] == 1


def test_public_api_surface():
    for name in ("make_node", "evaluate_chain", "verify_chain", "Synthesizer", "Episode"):
        assert hasattr(provenance, name)


def test_heavy_members_are_lazy():
    # Accessing the HydraDB-backed member triggers a lazy import; if the SDK is
    # absent it raises ImportError (not at package import time).
    try:
        graph_cls = provenance.ProvenanceGraph
        assert graph_cls.__name__ == "HydraClient"
    except ImportError:
        pass  # hydra_db not installed in this environment — acceptable
