"""
Fork-proofness of the authoritative local chain pointer (graph/chain.py).

The whole point of the file-locked pointer is that NO two episodes ever share a
prev_hash, even under concurrent writers — so the Merkle chain can't fork
regardless of HydraDB indexing lag. These tests exercise reserve() directly
(no DB needed) and assert a strictly-linear, fork-free chain.
"""

from __future__ import annotations

import threading

from graph import chain


def _assert_linear(eps: list) -> None:
    """Episodes (in claim order) must form one linear hash chain."""
    prev = ""
    for i, ep in enumerate(eps):
        assert ep.sequence_no == i, f"seq gap at {i}: {ep.sequence_no}"
        assert ep.prev_hash == prev, f"broken link at seq {i}"
        prev = ep.merkle_hash
    # No duplicate prev_hash == no fork point.
    assert len({e.prev_hash for e in eps}) == len(eps)
    # No duplicate merkle_hash.
    assert len({e.merkle_hash for e in eps}) == len(eps)


def test_sequential_chain_is_linear(tmp_path, monkeypatch):
    monkeypatch.setenv("CBOS_CHAIN_STATE", str(tmp_path / "chain.json"))
    chain.reset()
    eps = [chain.reserve("ingest_commit") for _ in range(25)]
    _assert_linear(eps)


def test_concurrent_reserve_never_forks(tmp_path, monkeypatch):
    monkeypatch.setenv("CBOS_CHAIN_STATE", str(tmp_path / "chain.json"))
    chain.reset()

    out: list = []
    barrier = threading.Barrier(20)

    def worker():
        barrier.wait()  # maximize contention
        out.append(chain.reserve("ingest_commit"))

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Every claim got a unique, contiguous sequence_no 0..19.
    seqs = sorted(e.sequence_no for e in out)
    assert seqs == list(range(20))

    # Reordering by seq must yield one linear chain (no shared prev_hash).
    _assert_linear(sorted(out, key=lambda e: e.sequence_no))


def test_reset_then_bootstrap_state(tmp_path, monkeypatch):
    monkeypatch.setenv("CBOS_CHAIN_STATE", str(tmp_path / "chain.json"))
    chain.reset(seq=7, head_hash="abc123")
    ep = chain.reserve("decide", source="manual")
    assert ep.sequence_no == 7
    assert ep.prev_hash == "abc123"
    assert ep.source == "manual"
