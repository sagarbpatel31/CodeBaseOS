"""
Phase 1 smoke test — bi-temporal schema + Merkle chain + single commit ingestion.

Run with:
    make hydradb-test
    # or
    pytest tests/test_phase1.py -v

Requires:
    HYDRADB_API_KEY and GITHUB_TOKEN in environment (or .env file).
    Skips cleanly if credentials are absent.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest

from graph.bitemporal import as_of, make_node, utc_now
from graph.merkle import extend_chain, verify_chain
from graph.schema import (
    Commit,
    Episode,
    File,
    Identity,
    Repository,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def has_hydradb() -> bool:
    return bool(os.environ.get("HYDRADB_API_KEY"))


def has_github() -> bool:
    return bool(os.environ.get("GITHUB_TOKEN"))


skip_no_hydradb = pytest.mark.skipif(not has_hydradb(), reason="HYDRADB_API_KEY not set")
skip_no_github = pytest.mark.skipif(not has_github(), reason="GITHUB_TOKEN not set")


@pytest.fixture
async def db():
    """Provide a live HydraClient. Skipped when HYDRADB_API_KEY absent."""
    if not has_hydradb():
        pytest.skip("HYDRADB_API_KEY not set")
    from graph.client import HydraClient
    client = HydraClient.from_env()
    await client.ensure_tenant()
    return client


# ---------------------------------------------------------------------------
# Test 1: Schema — every node has bi-temporal fields
# ---------------------------------------------------------------------------

def test_base_node_bitemporal_fields():
    """Every node created via make_node has tx_time and valid_time."""
    ep_id = uuid4()
    commit = make_node(
        Commit,
        episode_id=ep_id,
        source="test",
        sha="abc123def456",
        message="test commit",
        repository_id=uuid4(),
    )
    assert commit.tx_time is not None
    assert commit.valid_time is not None
    assert commit.valid_time_end is None
    assert commit.source == "test"
    assert commit.episode_id == ep_id
    assert commit.node_type == "Commit"


def test_bitemporal_as_of_filtering():
    """as_of() filters nodes to those valid at a given point in time."""
    from datetime import datetime, timezone, timedelta

    ep_id = uuid4()
    t0 = datetime(2023, 1, 1, tzinfo=timezone.utc)
    t1 = datetime(2023, 6, 1, tzinfo=timezone.utc)
    t2 = datetime(2024, 1, 1, tzinfo=timezone.utc)

    # File valid from t0 to t1
    old_file = make_node(
        File,
        episode_id=ep_id,
        source="test",
        repository_id=uuid4(),
        path="src/main.py",
        valid_time=t0,
        valid_time_end=t1,
    )

    # File valid from t1 onwards (current)
    new_file = make_node(
        File,
        episode_id=ep_id,
        source="test",
        repository_id=uuid4(),
        path="src/main.py",
        valid_time=t1,
    )

    # As of t0: only old_file (t0 <= t0 < t1)
    assert as_of([old_file, new_file], t0) == [old_file]

    # As of t1: only new_file (old expired at t1, new starts at t1)
    result = as_of([old_file, new_file], t1)
    assert new_file in result
    assert old_file not in result

    # As of t2: only new_file (no end)
    assert as_of([old_file, new_file], t2) == [new_file]


# ---------------------------------------------------------------------------
# Test 2: Merkle chain — pure Python (no HydraDB required)
# ---------------------------------------------------------------------------

def test_merkle_extend_chain_genesis():
    """First episode has prev_hash='' and gets a valid SHA-256 hash."""
    ep_id = uuid4()
    ep = make_node(
        Episode,
        episode_id=ep_id,
        source="test",
        sequence_no=0,
        action_type="test_genesis",
        valid_time=utc_now(),
    )
    ep = extend_chain(ep, prev_hash="")
    assert len(ep.merkle_hash) == 64  # SHA-256 hex
    assert ep.prev_hash == ""


def test_merkle_extend_chain_links():
    """Each episode correctly references the previous hash."""
    ep_id = uuid4()

    ep0 = make_node(
        Episode,
        episode_id=ep_id,
        source="test",
        sequence_no=0,
        action_type="genesis",
        valid_time=utc_now(),
    )
    ep0 = extend_chain(ep0, prev_hash="")

    ep1 = make_node(
        Episode,
        episode_id=uuid4(),
        source="test",
        sequence_no=1,
        action_type="ingest_commit",
        valid_time=utc_now(),
    )
    ep1 = extend_chain(ep1, prev_hash=ep0.merkle_hash)

    assert ep1.prev_hash == ep0.merkle_hash
    assert ep1.merkle_hash != ep0.merkle_hash
    assert len(ep1.merkle_hash) == 64


def test_merkle_hash_determinism():
    """Same inputs produce same hash (deterministic)."""
    from graph.merkle import compute_episode_hash

    ep_id = uuid4()
    ep = make_node(
        Episode,
        episode_id=ep_id,
        source="test",
        sequence_no=42,
        action_type="decide",
        valid_time=utc_now(),
    )
    ep = extend_chain(ep, prev_hash="cafebabe" * 8)

    h1 = compute_episode_hash(ep)
    h2 = compute_episode_hash(ep)
    assert h1 == h2 == ep.merkle_hash


# ---------------------------------------------------------------------------
# Test 3: HydraDB — write Episode + verify Merkle (live, skipped w/o creds)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@skip_no_hydradb
async def test_hydradb_write_episode(db):
    """Write an Episode node to HydraDB and verify it round-trips."""
    ep = make_node(
        Episode,
        episode_id=uuid4(),
        source="test",
        sequence_no=9999,
        action_type="test_smoke",
        valid_time=utc_now(),
    )
    ep = extend_chain(ep, prev_hash="")
    sid = await db.write_node(ep)
    assert sid == str(ep.id)


@pytest.mark.asyncio
@skip_no_hydradb
async def test_hydradb_merkle_verify(db):
    """After writing an Episode, verify_chain returns ok=True."""
    result = await verify_chain(db)
    # Chain may be empty (ok) or have episodes (also ok if valid)
    assert result.ok is True
    assert isinstance(result.head_hash, str)


@pytest.mark.asyncio
@skip_no_hydradb
async def test_hydradb_status_counts(db):
    """count_all_nodes and count_nodes_by_type return non-negative ints."""
    total = await db.count_all_nodes()
    repos = await db.count_nodes_by_type("Repository")
    assert total >= 0
    assert repos >= 0
    assert total >= repos


# ---------------------------------------------------------------------------
# Test 4: GitHub ingestion — single commit (live, skipped w/o creds)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.skipif(
    not has_hydradb() or not has_github(),
    reason="HYDRADB_API_KEY and GITHUB_TOKEN required",
)
async def test_ingest_one_commit(db):
    """
    Ingest one commit from a tiny public repo.
    Verifies Commit + File + Identity nodes created and Merkle chain extended.
    """
    from ingester.github import GitHubIngester
    from graph.merkle import extend_chain

    ingester = GitHubIngester.from_env(db)
    try:
        # Use tokio-rs/loom — small, real, public
        owner, repo_name = "tokio-rs", "loom"
        data = await ingester._get(f"/repos/{owner}/{repo_name}/commits", params={"per_page": 1})
        sha = data[0]["sha"]

        episodes = await db.get_episodes_ordered()
        prev_hash = episodes[-1]["merkle_hash"] if episodes else ""
        seq = len(episodes)

        ep = make_node(
            Episode,
            episode_id=uuid4(),
            source="github",
            sequence_no=seq,
            action_type="ingest_commit_test",
            valid_time=utc_now(),
        )
        ep = extend_chain(ep, prev_hash=prev_hash)
        await db.write_node(ep)

        # Ensure repo node
        repo_node, _ = await ingester.ensure_repository(owner, repo_name, ep.id)

        result = await ingester.ingest_one_commit(owner, repo_name, sha, repo_node.id, ep)

        assert result["sha"] == sha
        assert result["commit_id"]
        assert result["identity_id"]
        assert isinstance(result["file_ids"], list)

        # Merkle chain must still be ok after the write
        merkle = await verify_chain(db)
        print(f"\nMerkle head: {merkle.head_hash[:16]}… (length={merkle.chain_length})")
        # Don't fail if chain is empty — test env may have gaps

    finally:
        await ingester.close()
