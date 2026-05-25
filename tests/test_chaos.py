"""
Chaos layer + offline endpoint tests, driven through the real FastAPI app in
offline demo mode (no HydraDB/OpenAI credentials).

Skipped automatically if the hydra_db SDK is not installed (backend.api imports
the graph client at module load); runs in CI where deps are present.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("hydra_db")

# Offline mode must be set before importing the app (read at import time).
# Use "" (not pop): load_dotenv(override=False) would refill a popped key from
# a local .env, reconnecting the live backend and breaking offline assertions.
os.environ["CBOS_OFFLINE_DEMO"] = "1"
os.environ["HYDRADB_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from backend.api import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
        # Reset chaos state between tests.
        c.post("/chaos/restore")
        c.post("/chaos/revive")
        yield c


def test_status_and_graph_populated_offline(client):
    s = client.get("/status").json()
    assert s["nodeCount"] > 0 and s["repoCount"] == 2 and s["merkleOk"] is True
    g = client.get("/graph").json()
    assert g["nodes"] and g["links"]


def test_graph_as_of_filters(client):
    full = client.get("/graph").json()
    early = client.get("/graph", params={"as_of": "2023-06-01T00:00:00+00:00"}).json()
    assert len(early["nodes"]) < len(full["nodes"])


def test_tamper_turns_merkle_red_then_restore(client):
    t = client.post("/chaos/tamper").json()
    assert t["merkleOk"] is False
    assert client.get("/status").json()["merkleOk"] is False
    v = client.get("/verify").json()
    assert v["ok"] is False and v["tampered"] is True

    r = client.post("/chaos/restore").json()
    assert r["merkleOk"] is True
    assert client.get("/status").json()["merkleOk"] is True


def test_nuclear_orphans_and_reviewers(client):
    n = client.post("/chaos/nuclear").json()
    assert n["orphaned_count"] >= 1 and n["suggested_reviewers"]
    assert client.get("/chaos/state").json()["nuclear"] is not None
    client.post("/chaos/revive")
    assert client.get("/chaos/state").json()["nuclear"] is None


def test_llm_endpoints_canned_and_free(client):
    why = client.get("/why", params={"file": "src/sync/mutex.rs", "line": 1}).json()
    assert why["cost_usd"] == 0.0 and why["explanation"]
    fw = client.get("/five-whys", params={"file": "a.rs", "line": 1}).json()
    assert len(fw["chain"]) == 5
    br = client.get("/baseline-rag", params={"file": "a.rs", "line": 1}).json()
    assert br["mode"] == "baseline-no-graph"


def test_er_queue_offline(client):
    stats = client.get("/er-queue").json()["stats"]
    assert stats["auto_merged"] >= 2 and stats["pending"] >= 1
