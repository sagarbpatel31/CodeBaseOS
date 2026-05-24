"""
Pydantic models for every node type in CODEBASEOS_SPEC §5.2.

Universal properties (§5.1) on every node:
  id, tx_time, valid_time, valid_time_end, source, episode_id, merkle_hash
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class BaseNode(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tx_time: datetime
    valid_time: datetime
    valid_time_end: Optional[datetime] = None
    source: str  # "github", "git_local", "manual", etc.
    episode_id: UUID
    merkle_hash: str = ""
    node_type: str  # filled by each subclass __init_subclass__

    model_config = {"populate_by_name": True}

    def to_hydra_source(self) -> dict[str, Any]:
        """Serialize to HydraDB app_knowledge source object."""
        doc_meta: dict[str, Any] = {
            "tx_time": self.tx_time.isoformat(),
            "valid_time": self.valid_time.isoformat(),
            "valid_time_end": self.valid_time_end.isoformat() if self.valid_time_end else None,
            "episode_id": str(self.episode_id),
            "merkle_hash": self.merkle_hash,
            "source": self.source,
            "node_type": self.node_type,
        }
        return {
            "id": str(self.id),
            "type": self.node_type,
            "title": f"{self.node_type}:{str(self.id)[:8]}",
            "content": self.model_dump_json(),
            "timestamp": self.tx_time.isoformat(),
            "document_metadata": doc_meta,
        }


# ---------------------------------------------------------------------------
# Episode (AGENTS.md invariant: append-only, extends Merkle chain)
# ---------------------------------------------------------------------------

class Episode(BaseNode):
    node_type: str = "Episode"
    sequence_no: int
    action_type: str  # "ingest_commit", "ingest_pr", "entity_resolve", "decide", etc.
    inputs_hash: str = ""
    outputs_hash: str = ""
    prev_hash: str = ""  # Merkle chain: hash of prior Episode

    def to_hydra_source(self) -> dict[str, Any]:
        src = super().to_hydra_source()
        src["title"] = f"Episode:{self.sequence_no}:{self.action_type}"
        src["document_metadata"].update({
            "sequence_no": self.sequence_no,
            "action_type": self.action_type,
            "prev_hash": self.prev_hash,
        })
        return src


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class Repository(BaseNode):
    node_type: str = "Repository"
    name: str  # "owner/repo"
    github_id: Optional[int] = None
    default_branch: str = "main"
    language_breakdown: dict[str, float] = Field(default_factory=dict)

    def to_hydra_source(self) -> dict[str, Any]:
        src = super().to_hydra_source()
        src["title"] = f"Repository:{self.name}"
        src["document_metadata"]["repo_name"] = self.name
        return src


# ---------------------------------------------------------------------------
# Commit
# ---------------------------------------------------------------------------

class Commit(BaseNode):
    node_type: str = "Commit"
    sha: str
    message: str
    author_id: Optional[UUID] = None  # Person reference (set after entity resolution)
    author_name: str = ""  # raw name before resolution
    author_email: str = ""
    parents: list[str] = Field(default_factory=list)  # parent SHAs
    files_changed: int = 0
    additions: int = 0
    deletions: int = 0
    repository_id: UUID = Field(default_factory=uuid4)

    def to_hydra_source(self) -> dict[str, Any]:
        src = super().to_hydra_source()
        src["title"] = f"Commit:{self.sha[:12]}"
        src["description"] = self.message[:200]
        src["document_metadata"].update({
            "sha": self.sha,
            "author_email": self.author_email,
            "repository_id": str(self.repository_id),
        })
        return src


# ---------------------------------------------------------------------------
# File
# ---------------------------------------------------------------------------

class File(BaseNode):
    node_type: str = "File"
    repository_id: UUID
    path: str
    current_hash: str = ""
    language: str = ""

    def to_hydra_source(self) -> dict[str, Any]:
        src = super().to_hydra_source()
        src["title"] = f"File:{self.path}"
        src["document_metadata"].update({
            "path": self.path,
            "language": self.language,
            "repository_id": str(self.repository_id),
        })
        return src


# ---------------------------------------------------------------------------
# Symbol
# ---------------------------------------------------------------------------

class Symbol(BaseNode):
    node_type: str = "Symbol"
    name: str
    kind: str  # "fn", "struct", "class", "global"
    defining_file_id: UUID
    signature: str = ""
    language: str = ""
    abi_version: int = 1

    def to_hydra_source(self) -> dict[str, Any]:
        src = super().to_hydra_source()
        src["title"] = f"Symbol:{self.name}"
        return src


# ---------------------------------------------------------------------------
# PR
# ---------------------------------------------------------------------------

class PR(BaseNode):
    node_type: str = "PR"
    number: int
    title: str
    description: str = ""
    state: str = "open"  # "open", "merged", "closed"
    author_id: Optional[UUID] = None
    author_name: str = ""
    merged_at: Optional[datetime] = None
    repository_id: UUID = Field(default_factory=uuid4)

    def to_hydra_source(self) -> dict[str, Any]:
        src = super().to_hydra_source()
        src["title"] = f"PR:#{self.number} {self.title[:60]}"
        src["description"] = self.description[:300]
        src["document_metadata"].update({
            "pr_number": self.number,
            "state": self.state,
            "repository_id": str(self.repository_id),
        })
        return src


# ---------------------------------------------------------------------------
# ReviewComment
# ---------------------------------------------------------------------------

class ReviewComment(BaseNode):
    node_type: str = "ReviewComment"
    pr_id: UUID
    file_id: Optional[UUID] = None
    line_start: int = 0
    line_end: int = 0
    author_id: Optional[UUID] = None
    author_name: str = ""
    body: str = ""
    in_reply_to: Optional[UUID] = None


# ---------------------------------------------------------------------------
# Issue
# ---------------------------------------------------------------------------

class Issue(BaseNode):
    node_type: str = "Issue"
    number: int
    title: str
    body: str = ""
    state: str = "open"
    author_id: Optional[UUID] = None
    author_name: str = ""
    labels: list[str] = Field(default_factory=list)
    repository_id: UUID = Field(default_factory=uuid4)

    def to_hydra_source(self) -> dict[str, Any]:
        src = super().to_hydra_source()
        src["title"] = f"Issue:#{self.number} {self.title[:60]}"
        src["description"] = self.body[:300]
        return src


# ---------------------------------------------------------------------------
# Decision (immutable; supersession via edges)
# ---------------------------------------------------------------------------

class Decision(BaseNode):
    node_type: str = "Decision"
    summary: str
    rationale: str = ""
    alternatives_rejected: list[str] = Field(default_factory=list)
    confidence: str = "medium"  # "low", "medium", "high"
    made_by_id: Optional[UUID] = None
    made_by_name: str = ""
    actor: str = ""  # e.g., "claude-code:backend"
    decision_id: str = ""  # human-readable Decision reference

    def to_hydra_source(self) -> dict[str, Any]:
        src = super().to_hydra_source()
        src["title"] = f"Decision:{self.decision_id or str(self.id)[:8]}"
        src["description"] = self.summary
        src["document_metadata"]["decision_id"] = self.decision_id
        return src


# ---------------------------------------------------------------------------
# Discussion
# ---------------------------------------------------------------------------

class Discussion(BaseNode):
    node_type: str = "Discussion"
    platform: str  # "slack", "discord", "email"
    channel: str = ""
    thread_id: str = ""
    summary: str = ""


# ---------------------------------------------------------------------------
# Person + Identity
# ---------------------------------------------------------------------------

class Person(BaseNode):
    node_type: str = "Person"
    canonical_name: str
    primary_email: str = ""
    current_employer: str = ""

    def to_hydra_source(self) -> dict[str, Any]:
        src = super().to_hydra_source()
        src["title"] = f"Person:{self.canonical_name}"
        src["document_metadata"]["primary_email"] = self.primary_email
        return src


class Identity(BaseNode):
    node_type: str = "Identity"
    platform: str  # "github", "slack", "email", "git"
    platform_user_id: str = ""
    username: str = ""
    email: str = ""
    resolved: bool = False
    person_id: Optional[UUID] = None  # set after entity resolution


# ---------------------------------------------------------------------------
# CostEvent (every LLM call logged here)
# ---------------------------------------------------------------------------

class CostEvent(BaseNode):
    node_type: str = "CostEvent"
    call_id: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    call_source: str = ""  # which synthesizer template triggered this

    def to_hydra_source(self) -> dict[str, Any]:
        src = super().to_hydra_source()
        src["document_metadata"]["cost_usd"] = self.cost_usd
        src["document_metadata"]["model"] = self.model
        return src
