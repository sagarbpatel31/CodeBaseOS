"""
Bi-temporal helpers for CodebaseOS.

Every node has two timestamps:
  tx_time   — when WE ingested/wrote it (transaction time)
  valid_time — when this fact was true in the world (business time)

AGENTS.md invariant: "Every node has both tx_time and valid_time."

HydraDB does not natively enforce bi-temporal semantics — we implement
this layer in Python. Workaround documented in docs/hydradb-notes.md.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypeVar
from uuid import UUID

from graph.schema import BaseNode

N = TypeVar("N", bound=BaseNode)


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def make_node(
    node_class: type[N],
    episode_id: UUID,
    source: str,
    valid_time: datetime | None = None,
    valid_time_end: datetime | None = None,
    **kwargs,
) -> N:
    """
    Construct any BaseNode subclass with bi-temporal fields pre-filled.

    Args:
        node_class: The concrete node type (Commit, File, PR, etc.)
        episode_id: UUID of the Episode that is creating this node.
        source: ingestion source string ("github", "git_local", "manual", etc.)
        valid_time: when this fact is true in the real world. Defaults to tx_time.
        valid_time_end: when this fact stopped being true. None = still valid.
        **kwargs: node-type-specific fields.
    """
    tx = utc_now()
    vt = valid_time if valid_time is not None else tx
    return node_class(
        tx_time=tx,
        valid_time=vt,
        valid_time_end=valid_time_end,
        source=source,
        episode_id=episode_id,
        **kwargs,
    )


def as_of(nodes: list[N], point_in_time: datetime) -> list[N]:
    """
    Filter a list of nodes to those valid at `point_in_time`.

    Returns nodes where valid_time <= point_in_time <= (valid_time_end or ∞).
    This implements the "as of time T" bi-temporal query that HydraDB
    does not natively support. See docs/hydradb-notes.md.
    """
    result = []
    for node in nodes:
        if node.valid_time > point_in_time:
            continue
        if node.valid_time_end is not None and node.valid_time_end <= point_in_time:
            continue
        result.append(node)
    return result
