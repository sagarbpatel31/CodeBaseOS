"""
Pydantic models for every node type in CODEBASEOS_SPEC §5.2.

Universal properties (§5.1) on every node:
  id, tx_time, valid_time, valid_time_end, source, episode_id, merkle_hash
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class BaseNode(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tx_time: datetime
    valid_time: datetime
    valid_time_end: datetime | None = None
    source: str  # "github", "git_local", "manual", etc.
    episode_id: UUID
    merkle_hash: str = ""
    node_type: str  # filled by each subclass __init_subclass__

    model_config = {"populate_by_name": True}

    def to_hydra_source(self, tenant_id: str = "codebaseos", sub_tenant_id: str = "default") -> dict[str, Any]:
        """Serialize to HydraDB app_knowledge source object."""
        doc_meta: dict[str, Any] = {
            "tx_time": self.tx_time.isoformat(),
            "valid_time": self.valid_time.isoformat(),
            # HydraDB rejects None metadata values — use empty string sentinel
            "valid_time_end": self.valid_time_end.isoformat() if self.valid_time_end else "",
            "episode_id": str(self.episode_id),
            "merkle_hash": self.merkle_hash,
            "source": self.source,
            "node_type": self.node_type,
        }
        return {
            "id": str(self.id),
            "tenant_id": tenant_id,
            "sub_tenant_id": sub_tenant_id,
            "type": self.node_type,
            "title": f"{self.node_type}:{str(self.id)[:8]}",
            # content must be a dict, not a JSON string
            "content": self.model_dump(mode="json"),
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

    def to_hydra_source(self, tenant_id: str = "codebaseos", sub_tenant_id: str = "default") -> dict[str, Any]:
        src = super().to_hydra_source(tenant_id=tenant_id, sub_tenant_id=sub_tenant_id)
        src["title"] = f"Episode:{self.sequence_no}:{self.action_type}"
        src["document_metadata"].update({
            # HydraDB drops numeric metadata — store ints as strings.
            "sequence_no": str(self.sequence_no),
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
    github_id: int | None = None
    default_branch: str = "main"
    language_breakdown: dict[str, float] = Field(default_factory=dict)

    def to_hydra_source(self, tenant_id: str = "codebaseos", sub_tenant_id: str = "default") -> dict[str, Any]:
        src = super().to_hydra_source(tenant_id=tenant_id, sub_tenant_id=sub_tenant_id)
        src["title"] = f"Repository:{self.name}"
        src["document_metadata"]["repo_name"] = self.name
        # HydraDB overwrites `content` with its own doc structure, so any field
        # we need to read back MUST live in document_metadata.
        src["document_metadata"]["default_branch"] = self.default_branch
        if self.github_id is not None:
            src["document_metadata"]["github_id"] = str(self.github_id)
        return src


# ---------------------------------------------------------------------------
# Commit
# ---------------------------------------------------------------------------

class Commit(BaseNode):
    node_type: str = "Commit"
    sha: str
    message: str
    author_id: UUID | None = None  # Person reference (set after entity resolution)
    author_name: str = ""  # raw name before resolution
    author_email: str = ""
    parents: list[str] = Field(default_factory=list)  # parent SHAs
    files_changed: int = 0
    additions: int = 0
    deletions: int = 0
    repository_id: UUID = Field(default_factory=uuid4)

    def to_hydra_source(self, tenant_id: str = "codebaseos", sub_tenant_id: str = "default") -> dict[str, Any]:
        src = super().to_hydra_source(tenant_id=tenant_id, sub_tenant_id=sub_tenant_id)
        src["title"] = f"Commit:{self.sha[:12]}"
        src["description"] = self.message[:200]
        src["document_metadata"].update({
            "sha": self.sha,
            "author_name": self.author_name,
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

    def to_hydra_source(self, tenant_id: str = "codebaseos", sub_tenant_id: str = "default") -> dict[str, Any]:
        src = super().to_hydra_source(tenant_id=tenant_id, sub_tenant_id=sub_tenant_id)
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

    def to_hydra_source(self, tenant_id: str = "codebaseos", sub_tenant_id: str = "default") -> dict[str, Any]:
        src = super().to_hydra_source(tenant_id=tenant_id, sub_tenant_id=sub_tenant_id)
        src["title"] = f"Symbol:{self.name}"
        src["document_metadata"]["defining_file_id"] = str(self.defining_file_id)
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
    author_id: UUID | None = None
    author_name: str = ""
    merged_at: datetime | None = None
    repository_id: UUID = Field(default_factory=uuid4)

    def to_hydra_source(self, tenant_id: str = "codebaseos", sub_tenant_id: str = "default") -> dict[str, Any]:
        src = super().to_hydra_source(tenant_id=tenant_id, sub_tenant_id=sub_tenant_id)
        src["title"] = f"PR:#{self.number} {self.title[:60]}"
        src["description"] = self.description[:300]
        src["document_metadata"].update({
            "pr_number": str(self.number),
            "state": self.state,
            "author_name": self.author_name,
            "repository_id": str(self.repository_id),
        })
        return src


# ---------------------------------------------------------------------------
# ReviewComment
# ---------------------------------------------------------------------------

class ReviewComment(BaseNode):
    node_type: str = "ReviewComment"
    pr_id: UUID
    file_id: UUID | None = None
    line_start: int = 0
    line_end: int = 0
    author_id: UUID | None = None
    author_name: str = ""
    body: str = ""
    in_reply_to: UUID | None = None

    def to_hydra_source(self, tenant_id: str = "codebaseos", sub_tenant_id: str = "default") -> dict[str, Any]:
        src = super().to_hydra_source(tenant_id=tenant_id, sub_tenant_id=sub_tenant_id)
        src["title"] = f"ReviewComment:{self.author_name}:{str(self.id)[:8]}"
        src["description"] = self.body[:200]
        src["document_metadata"].update({
            "pr_id": str(self.pr_id),
            "file_id": str(self.file_id) if self.file_id else "",
            "author_name": self.author_name,
        })
        return src


# ---------------------------------------------------------------------------
# Issue
# ---------------------------------------------------------------------------

class Issue(BaseNode):
    node_type: str = "Issue"
    number: int
    title: str
    body: str = ""
    state: str = "open"
    author_id: UUID | None = None
    author_name: str = ""
    labels: list[str] = Field(default_factory=list)
    repository_id: UUID = Field(default_factory=uuid4)

    def to_hydra_source(self, tenant_id: str = "codebaseos", sub_tenant_id: str = "default") -> dict[str, Any]:
        src = super().to_hydra_source(tenant_id=tenant_id, sub_tenant_id=sub_tenant_id)
        src["title"] = f"Issue:#{self.number} {self.title[:60]}"
        src["description"] = self.body[:300]
        src["document_metadata"].update({
            "issue_number": str(self.number),
            "state": self.state,
            "repository_id": str(self.repository_id),
        })
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
    made_by_id: UUID | None = None
    made_by_name: str = ""
    actor: str = ""  # e.g., "claude-code:backend"
    decision_id: str = ""  # human-readable Decision reference

    def to_hydra_source(self, tenant_id: str = "codebaseos", sub_tenant_id: str = "default") -> dict[str, Any]:
        src = super().to_hydra_source(tenant_id=tenant_id, sub_tenant_id=sub_tenant_id)
        src["title"] = f"Decision:{self.decision_id or str(self.id)[:8]}"
        src["description"] = self.summary
        src["document_metadata"].update({
            "decision_id": self.decision_id,
            # Stored in metadata (HydraDB drops `description`) so /decisions can
            # show the summary without a re-fetch.
            "summary": self.summary,
            "confidence": self.confidence,
        })
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
    identity_ids: list[str] = Field(default_factory=list)  # resolved Identity node ids

    def to_hydra_source(self, tenant_id: str = "codebaseos", sub_tenant_id: str = "default") -> dict[str, Any]:
        src = super().to_hydra_source(tenant_id=tenant_id, sub_tenant_id=sub_tenant_id)
        src["title"] = f"Person:{self.canonical_name}"
        src["document_metadata"]["primary_email"] = self.primary_email
        src["document_metadata"]["canonical_name"] = self.canonical_name
        # HydraDB metadata keeps only str/bool — store the id list as CSV.
        src["document_metadata"]["identity_ids_csv"] = ",".join(self.identity_ids)
        return src


class Identity(BaseNode):
    node_type: str = "Identity"
    platform: str  # "github", "slack", "email", "git"
    platform_user_id: str = ""
    username: str = ""
    email: str = ""
    resolved: bool = False
    person_id: UUID | None = None  # set after entity resolution

    def to_hydra_source(self, tenant_id: str = "codebaseos", sub_tenant_id: str = "default") -> dict[str, Any]:
        src = super().to_hydra_source(tenant_id=tenant_id, sub_tenant_id=sub_tenant_id)
        src["title"] = f"Identity:{self.username or self.email or str(self.id)[:8]}"
        src["document_metadata"].update({
            "platform": self.platform,
            "username": self.username,
            "email": self.email,
            "resolved": self.resolved,
            "person_id": str(self.person_id) if self.person_id else "",
        })
        return src


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

    def to_hydra_source(self, tenant_id: str = "codebaseos", sub_tenant_id: str = "default") -> dict[str, Any]:
        src = super().to_hydra_source(tenant_id=tenant_id, sub_tenant_id=sub_tenant_id)
        # HydraDB drops int/float metadata values (keeps only str/bool), so any
        # number we need to read back MUST be stored as a string.
        src["document_metadata"]["cost_usd"] = str(self.cost_usd)
        src["document_metadata"]["model"] = self.model
        src["document_metadata"]["input_tokens"] = str(self.input_tokens)
        src["document_metadata"]["output_tokens"] = str(self.output_tokens)
        return src
