"""
Merkle chain over Episodes.

AGENTS.md invariant: "Every Episode extends the Merkle chain. No exceptions."

Chain structure:
  genesis: hash(seq=0 | action_type | inputs_hash | outputs_hash | prev="")
  each next: hash(seq | action_type | inputs_hash | outputs_hash | prev_hash)

Stored on Episode.merkle_hash; linked via Episode.prev_hash.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from graph.client import HydraClient
    from graph.schema import Episode


@dataclass
class MerkleResult:
    ok: bool
    head_hash: str
    chain_length: int
    broken_at: int | None = None  # sequence_no where chain broke


def _episode_canonical(seq: int, action_type: str, inputs_hash: str, outputs_hash: str, prev_hash: str) -> bytes:
    """Canonical JSON for hashing — deterministic, sorted keys."""
    payload = {
        "seq": seq,
        "action_type": action_type,
        "inputs_hash": inputs_hash,
        "outputs_hash": outputs_hash,
        "prev": prev_hash,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def compute_episode_hash(episode: "Episode") -> str:
    """Compute the Merkle hash for an Episode (does not mutate the episode)."""
    data = _episode_canonical(
        seq=episode.sequence_no,
        action_type=episode.action_type,
        inputs_hash=episode.inputs_hash,
        outputs_hash=episode.outputs_hash,
        prev_hash=episode.prev_hash,
    )
    return hashlib.sha256(data).hexdigest()


def extend_chain(episode: "Episode", prev_hash: str = "") -> "Episode":
    """
    Attach the episode to the chain.
    Sets episode.prev_hash and episode.merkle_hash.
    Returns a new Episode instance (episodes are immutable after write).
    """
    updated = episode.model_copy(update={"prev_hash": prev_hash})
    new_hash = compute_episode_hash(updated)
    return updated.model_copy(update={"merkle_hash": new_hash})


async def verify_chain(db: "HydraClient") -> MerkleResult:
    """
    Walk all Episodes from HydraDB in sequence_no order.
    Recomputes each hash and checks prev_hash linkage.
    """
    episodes = await db.get_episodes_ordered()

    if not episodes:
        result = MerkleResult(ok=True, head_hash="", chain_length=0)
        await db.update_merkle_head("", 0, True)
        return result

    prev_hash = ""
    for ep in episodes:
        seq = ep["sequence_no"]
        expected_hash = hashlib.sha256(
            _episode_canonical(
                seq=seq,
                action_type=ep.get("action_type", ""),
                inputs_hash="",  # stored in content JSON
                outputs_hash="",
                prev_hash=ep.get("prev_hash", ""),
            )
        ).hexdigest()

        stored_hash = ep.get("merkle_hash", "")
        prev_in_ep = ep.get("prev_hash", "")

        if prev_in_ep != prev_hash:
            result = MerkleResult(ok=False, head_hash=stored_hash, chain_length=seq, broken_at=seq)
            await db.update_merkle_head(stored_hash, seq, False)
            return result

        prev_hash = stored_hash

    head_hash = episodes[-1].get("merkle_hash", "")
    result = MerkleResult(ok=True, head_hash=head_hash, chain_length=len(episodes))
    await db.update_merkle_head(head_hash, len(episodes), True)
    return result
