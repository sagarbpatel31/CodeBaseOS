"""
GitHub ingestion source — Phase 1 minimal implementation.

Phase 1 scope: ingest a single commit, creating:
  - Repository node (if not exists)
  - Commit node
  - File nodes for changed files
  - Identity nodes for the author (pre-resolution)

Phase 2 will add: PR pagination, issue ingestion, review comments.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

import httpx

from graph.bitemporal import make_node, utc_now
from graph.client import HydraClient
from graph.merkle import extend_chain
from graph.schema import Commit, Episode, File, Identity, Repository


class GitHubIngester:
    """
    Ingests GitHub repository data into HydraDB.

    Uses GitHub REST API v3 with a PAT for authentication.
    """

    API_BASE = "https://api.github.com"

    def __init__(self, db: HydraClient, github_token: str) -> None:
        self.db = db
        self._http = httpx.AsyncClient(
            base_url=self.API_BASE,
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    @classmethod
    def from_env(cls, db: HydraClient) -> "GitHubIngester":
        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            raise RuntimeError("GITHUB_TOKEN not set")
        return cls(db=db, github_token=token)

    async def close(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Low-level GitHub API calls
    # ------------------------------------------------------------------

    async def _get(self, path: str, params: Optional[dict] = None) -> Any:
        resp = await self._http.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        return await self._get(f"/repos/{owner}/{repo}")

    async def get_commit(self, owner: str, repo: str, sha: str) -> dict[str, Any]:
        return await self._get(f"/repos/{owner}/{repo}/commits/{sha}")

    # ------------------------------------------------------------------
    # Episode management
    # ------------------------------------------------------------------

    async def _new_episode(
        self,
        action_type: str,
        repo_id: UUID,
        sequence_no: int,
        prev_hash: str = "",
    ) -> Episode:
        ep = make_node(
            Episode,
            episode_id=uuid4(),
            source="github",
            sequence_no=sequence_no,
            action_type=action_type,
            inputs_hash="",
            outputs_hash="",
            valid_time=utc_now(),
        )
        # Chain it
        ep = extend_chain(ep, prev_hash=prev_hash)
        return ep

    # ------------------------------------------------------------------
    # Repository ingestion
    # ------------------------------------------------------------------

    async def ensure_repository(
        self,
        owner: str,
        repo: str,
        episode_id: UUID,
    ) -> tuple[Repository, str]:
        """
        Create (or return existing) Repository node.
        Returns (Repository, source_id).
        """
        data = await self.get_repo(owner, repo)
        repo_node = make_node(
            Repository,
            episode_id=episode_id,
            source="github",
            name=f"{owner}/{repo}",
            github_id=data.get("id"),
            default_branch=data.get("default_branch", "main"),
        )
        sid = await self.db.write_node(repo_node)
        return repo_node, sid

    # ------------------------------------------------------------------
    # Single commit ingestion (Phase 1 goal)
    # ------------------------------------------------------------------

    async def ingest_one_commit(
        self,
        owner: str,
        repo: str,
        sha: str,
        repo_id: UUID,
        episode: Episode,
    ) -> dict[str, Any]:
        """
        Ingest one commit from GitHub, creating:
          - Commit node
          - File nodes for each changed file
          - Identity node for the author

        Returns a summary dict with node IDs.
        """
        data = await self.get_commit(owner, repo, sha)

        git_author = data.get("commit", {}).get("author", {})
        author_name = git_author.get("name", "")
        author_email = git_author.get("email", "")
        committed_at_str = git_author.get("date", "")
        committed_at = (
            datetime.fromisoformat(committed_at_str.replace("Z", "+00:00"))
            if committed_at_str
            else utc_now()
        )

        # --- Identity node (pre-resolution) ---
        identity = make_node(
            Identity,
            episode_id=episode.id,
            source="github",
            platform="git",
            username=author_name,
            email=author_email,
            valid_time=committed_at,
        )
        identity_id = await self.db.write_node(identity)

        # --- Commit node ---
        parents = [p["sha"] for p in data.get("parents", [])]
        stats = data.get("stats", {})
        commit_node = make_node(
            Commit,
            episode_id=episode.id,
            source="github",
            sha=sha,
            message=data.get("commit", {}).get("message", ""),
            author_name=author_name,
            author_email=author_email,
            parents=parents,
            files_changed=len(data.get("files", [])),
            additions=stats.get("additions", 0),
            deletions=stats.get("deletions", 0),
            repository_id=repo_id,
            valid_time=committed_at,
        )
        commit_id = await self.db.write_node(commit_node, relations=[identity_id])

        # --- File nodes ---
        file_ids = []
        for gh_file in data.get("files", []):
            file_path = gh_file.get("filename", "")
            ext = file_path.rsplit(".", 1)[-1] if "." in file_path else ""
            lang_map = {"py": "python", "ts": "typescript", "js": "javascript", "rs": "rust", "go": "go"}
            lang = lang_map.get(ext, ext)
            file_hash = hashlib.sha256(file_path.encode()).hexdigest()[:16]

            file_node = make_node(
                File,
                episode_id=episode.id,
                source="github",
                repository_id=repo_id,
                path=file_path,
                current_hash=file_hash,
                language=lang,
                valid_time=committed_at,
            )
            fid = await self.db.write_node(file_node, relations=[commit_id])
            file_ids.append(fid)

        return {
            "commit_id": commit_id,
            "identity_id": identity_id,
            "file_ids": file_ids,
            "sha": sha,
            "author": author_name,
            "message": commit_node.message[:100],
            "files_changed": len(file_ids),
        }
