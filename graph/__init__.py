from typing import Any

from graph.schema import (
    PR,
    Commit,
    CostEvent,
    Decision,
    Discussion,
    Episode,
    File,
    Identity,
    Issue,
    Person,
    Repository,
    ReviewComment,
    Symbol,
)


def __getattr__(name: str) -> Any:  # PEP 562
    # HydraClient pulls the hydra_db SDK; import it lazily so the pure schema
    # subset (and the provenance spinoff) can be used without that dependency.
    if name == "HydraClient":
        from graph.client import HydraClient

        return HydraClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "HydraClient",
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
]
