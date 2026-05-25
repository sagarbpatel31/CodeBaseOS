"""
provenance — a bi-temporal code-provenance engine.

OSS spinoff of CodebaseOS. Ingest a repository's history into a bi-temporal,
Merkle-verified knowledge graph, resolve contributor identities across
platforms, and synthesize "why does this code exist?" answers through a single
cost-capped LLM chokepoint.

This package is a thin facade over the CodebaseOS core modules (graph/,
synthesizer/, ingester/) so the engine can be lifted into a standalone repo.

Pure primitives (Merkle chain, entity resolution, bi-temporal helpers, node
schema, synthesizer) import with no credentials. The HydraDB-backed graph and
the GitHub ingester are imported lazily on first access, so you only need those
heavier dependencies when you actually use them.

Example:
    from provenance import make_node, extend_chain, evaluate_chain, Episode

    eps, prev = [], ""
    for i, action in enumerate(["ingest_repo", "ingest_commit", "ingest_pr"]):
        ep = extend_chain(make_node(Episode, episode_id=..., source="github",
                                    sequence_no=i, action_type=action), prev_hash=prev)
        eps.append(ep); prev = ep.merkle_hash

    result = evaluate_chain([{"sequence_no": e.sequence_no,
                              "merkle_hash": e.merkle_hash,
                              "prev_hash": e.prev_hash} for e in eps])
    assert result.ok  # tamper-evident: change any hash and this turns False
"""

from __future__ import annotations

import importlib
from typing import Any

# Pure primitives — safe to import without HydraDB/OpenAI credentials.
from graph.bitemporal import as_of, make_node, utc_now
from graph.merkle import (
    MerkleResult,
    compute_episode_hash,
    evaluate_chain,
    extend_chain,
    verify_chain,
)
from graph.resolve import resolve_identities
from graph.schema import (
    Commit,
    CostEvent,
    Decision,
    Discussion,
    Episode,
    File,
    Identity,
    Issue,
    Person,
    PR,
    Repository,
    ReviewComment,
    Symbol,
)
from synthesizer.synthesizer import BudgetExceeded, SynthesisResult, Synthesizer

__version__ = "0.1.0"

# Heavy / credentialed members, imported on first attribute access.
_LAZY: dict[str, tuple[str, str]] = {
    "ProvenanceGraph": ("graph.client", "HydraClient"),
    "GitHubIngester": ("ingester.github", "GitHubIngester"),
}


def __getattr__(name: str) -> Any:  # PEP 562
    if name in _LAZY:
        module_name, attr = _LAZY[name]
        return getattr(importlib.import_module(module_name), attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # bi-temporal
    "make_node",
    "as_of",
    "utc_now",
    # merkle
    "MerkleResult",
    "evaluate_chain",
    "verify_chain",
    "extend_chain",
    "compute_episode_hash",
    # entity resolution
    "resolve_identities",
    # schema
    "Episode",
    "Repository",
    "Commit",
    "File",
    "Symbol",
    "PR",
    "ReviewComment",
    "Issue",
    "Decision",
    "Discussion",
    "Person",
    "Identity",
    "CostEvent",
    # synthesizer
    "Synthesizer",
    "SynthesisResult",
    "BudgetExceeded",
    # lazy (HydraDB / GitHub)
    "ProvenanceGraph",
    "GitHubIngester",
]
