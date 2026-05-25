"""
Offline demo fixture tests (no credentials, no hydra_db).

The fixture only uses the pure graph helpers, so these run anywhere pydantic
is installed and guard the no-credential demo path.
"""

from __future__ import annotations

from backend.offline import OfflineStore


def test_chain_verifies_clean():
    s = OfflineStore()
    v = s.verify(None)
    assert v.ok and v.chain_length == len(s.episodes)


def test_tamper_breaks_chain_and_restore_fixes_it():
    s = OfflineStore()
    tamper = s.tamper_target()
    broken = s.verify(tamper)
    assert broken.ok is False and broken.broken_at is not None
    # Restoring = no tamper applied.
    assert s.verify(None).ok is True


def test_status_reflects_tamper():
    s = OfflineStore()
    assert s.status_metrics(None)["merkleOk"] is True
    assert s.status_metrics(s.tamper_target())["merkleOk"] is False


def test_graph_as_of_filters_later_nodes():
    s = OfflineStore()
    full = s.graph_snapshot()
    early = s.graph_snapshot(as_of="2023-06-01T00:00:00+00:00")
    assert 0 < len(early["nodes"]) < len(full["nodes"])
    assert full["timeRange"]["min"] and full["timeRange"]["max"]


def test_entity_resolution_has_merges_and_pending():
    stats = OfflineStore().er_queue()["stats"]
    assert stats["auto_merged"] >= 2  # alice + carl merge by email
    assert stats["pending"] >= 1  # mattia name~login awaits review


def test_nuclear_picks_top_author_and_suggests_reviewers():
    n = OfflineStore().nuclear()
    assert n["orphaned_count"] >= 1
    assert n["suggested_reviewers"]
    assert n["person"].lower() not in {r["name"].lower() for r in n["suggested_reviewers"]}


def test_repos_and_events_present():
    s = OfflineStore()
    assert len(s.repos()["repos"]) == 2
    assert len(s.events()["events"]) >= 1


def test_canned_llm_answers_are_free():
    s = OfflineStore()
    assert s.why("f.rs", 1)["cost_usd"] == 0.0
    assert len(s.five_whys("f.rs", 1)["chain"]) == 5
    assert s.baseline_rag("f.rs", 1)["mode"] == "baseline-no-graph"
    assert s.handoff("runtime")["key_files"]
